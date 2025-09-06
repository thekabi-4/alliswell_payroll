# superclinic.py
"""
Backend logic for All Is Well Super Clinic attendance data.
Handles parsing, storage, policy application, and reporting.
"""

import pandas as pd
from datetime import datetime, timedelta
import sqlite3
import calendar
import os
import logging  # Import logging module

# --- Configure Logging ---
# Create a logger object
logger = logging.getLogger('superclinic_logger')
logger.setLevel(logging.DEBUG)  # Set to DEBUG for maximum verbosity

# Prevent adding multiple handlers if the module is reloaded
if not logger.handlers:
    # Create console handler and set level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Add formatter to ch
    ch.setFormatter(formatter)

    # Add ch to logger
    logger.addHandler(ch)

# --- Configuration for Super Clinic DB ---
DB_NAME = "superclinic.db"
EMPLOYEES_TABLE = "employees_sc"
ATTENDANCE_TABLE = "monthly_attendance_sc"

# --- Database Initialization ---
def init_superclinic_db():
    """Initializes the SQLite database and creates tables for Super Clinic data."""
    logger.info(f"Initializing Super Clinic database ({DB_NAME})...")
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute(f'''
            CREATE TABLE IF NOT EXISTS {EMPLOYEES_TABLE} (
                employee_code TEXT PRIMARY KEY,
                name TEXT,
                department TEXT DEFAULT 'Super Clinic',
                category TEXT DEFAULT 'Non-Medical',
                date_of_joining DATE,
                initial_paid_cl INTEGER DEFAULT 1,
                initial_paid_wo INTEGER DEFAULT 3,
                cl_calendar_year_quota INTEGER, -- For consultants
                cl_used_this_year INTEGER DEFAULT 0 -- Track usage for consultants
            )
        ''')

        c.execute(f'''
            CREATE TABLE IF NOT EXISTS {ATTENDANCE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_code TEXT,
                month_year TEXT, -- e.g., 'June 2025' (standardized)
                day INTEGER, -- Day of the month (1-31)
                status_raw TEXT, -- Directly from Excel (e.g., 'P', 'A') - Often NULL for SC
                status_calculated TEXT, -- Our calculated status (P, AB, WO, CL, Absent)
                in_time TEXT, -- Parsed and standardized (e.g., '08:54 AM')
                out_time TEXT, -- Parsed and standardized (e.g., '06:11 PM')
                total_hours REAL, -- Calculated hours (if needed)
                leave_type_used TEXT, -- WO, CL, or NULL for tracking
                FOREIGN KEY (employee_code) REFERENCES {EMPLOYEES_TABLE} (employee_code),
                UNIQUE(employee_code, month_year, day) ON CONFLICT REPLACE
            )
        ''')

        conn.commit()
        conn.close()
        logger.info(f"Super Clinic database ({DB_NAME}) initialized.")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during DB init: {e}") # Use exception for full traceback

# --- Helper Functions ---
def to_clean_str(x) -> str:
    """Convert to clean string, handling various data types."""
    if pd.isna(x) or x is None:
        return ""
    s = str(x).strip()
    if s.lower() == "nan":
        return ""
    return s

def parse_time_sc(time_str):
    """Enhanced time parsing with multiple format support"""
    if pd.isna(time_str) or str(time_str).strip() in ["--:--", "", "00:00", "0:00"]:
        return None
    
    time_str_clean = str(time_str).strip()
    
    # Handle various time formats
    formats_to_try = ["%H:%M", "%I:%M %p", "%H:%M:%S", "%I:%M%p"]
    
    for fmt in formats_to_try:
        try:
            parsed_time = datetime.strptime(time_str_clean, fmt)
            return parsed_time.strftime("%H:%M")
        except ValueError:
            continue
    
    logger.debug(f"Could not parse time string: '{time_str_clean}'")
    return None

def standardize_month_year(month_year_str_raw):
    """Standardizes a month-year string like 'June-2025' to 'Jun 2025'."""
    if not month_year_str_raw:
        return None
    try:
        parts = str(month_year_str_raw).strip().split("-")
        if len(parts) >= 2:
            month_name_raw = parts[0].strip()
            year_str = parts[1].strip()
            year = int(year_str)
            # Standardize format to match All Is Well Hospital (e.g., "Aug 2025")
            # Use first 3 letters of the month name from the file and capitalize
            month_name_standard = month_name_raw[:3].capitalize()
            standardized_result = f"{month_name_standard} {year}"
            logger.debug(f"      Standardized '{month_year_str_raw}' -> '{standardized_result}'")
            return standardized_result
    except (ValueError, IndexError) as e:
        logger.warning(f"Warning: Could not parse month/year string '{month_year_str_raw}': {e}")
        pass
    return None

def categorize_employee(name, department="Super Clinic"):
    """
    Determine employee category based on name patterns or other heuristics
    This is a simplified version - in practice, you might have more sophisticated logic
    """
    name_lower = name.lower()
    
    # Consultant/Doctor patterns
    consultant_keywords = ['dr.', 'dr ', 'doctor', 'consultant']
    if any(keyword in name_lower for keyword in consultant_keywords):
        return "Consultant"
    
    # RMO patterns
    rmo_keywords = ['rmo', 'resident']
    if any(keyword in name_lower for keyword in rmo_keywords):
        return "RMO"
    
    # Paramedical patterns
    paramedical_keywords = ['nurse', 'technician', 'therapist', 'radiologist']
    if any(keyword in name_lower for keyword in paramedical_keywords):
        return "Paramedical"
    
    # Default to Non-Medical/Office Staff
    return "Non-Medical"

def get_consultant_cl_quota(date_of_joining):
    """
    Determine CL quota based on date of joining (for consultants)
    Rule 3: 12 CL for those who joined after 01st January 2023, 13 CL for those before
    """
    if date_of_joining:
        try:
            joining_date = datetime.strptime(date_of_joining, "%Y-%m-%d")
            cutoff_date = datetime(2023, 1, 1)
            return 12 if joining_date >= cutoff_date else 13
        except ValueError:
            logger.warning(f"Invalid date format for joining date: {date_of_joining}")
            return 12  # Default assumption
    return 12  # Default assumption

# --- Core Parsing Function ---

def find_report_month(df_full):
    """Robustly searches for the 'Report Month' and standardizes it."""
    month_year_str_standardized = None
    logger.debug("Debug: Searching for 'Report Month' in file header...")
    # Check first 15 rows
    for i in range(min(15, len(df_full))):
        row = df_full.iloc[i]
        row_values = [to_clean_str(val) for val in row]

        # Look for "Report Month" pattern in the row
        for j, cell_value in enumerate(row_values):
            if "report month" in cell_value.lower():
                logger.debug(f"  Found 'Report Month' indicator at Row {i}, Col {j}: '{cell_value}'")
                # Strategy 1: Value in the same cell after colon (e.g., "Report Month: June-2025")
                if ":" in cell_value:
                    parts = cell_value.split(":", 1)
                    if len(parts) > 1 and parts[1].strip():
                        potential_month = parts[1].strip()
                        standardized = standardize_month_year(potential_month)
                        if standardized:
                            month_year_str_standardized = standardized
                            logger.debug(f"    Extracted and standardized from same cell (colon): '{potential_month}' -> '{standardized}'")
                            return month_year_str_standardized # Found it, return immediately

                # Strategy 2: Value in the same cell after "Month" word (e.g., "Report Month June-2025")
                words = cell_value.split()
                for k, word in enumerate(words):
                    if word.lower().startswith("month") and k + 1 < len(words):
                        potential_month = words[k + 1]
                        standardized = standardize_month_year(potential_month)
                        if standardized:
                            month_year_str_standardized = standardized
                            logger.debug(f"    Extracted and standardized from same cell (after 'Month'): '{potential_month}' -> '{standardized}'")
                            return month_year_str_standardized # Found it

                # Strategy 3: Value in subsequent cells in the same row
                for k in range(j + 1, min(j + 5, len(row_values))): # Check next 4 cells
                    potential_month = row_values[k]
                    # Basic check for month-year pattern
                    if "-" in potential_month and not "report" in potential_month.lower():
                        standardized = standardize_month_year(potential_month)
                        if standardized:
                            month_year_str_standardized = standardized
                            logger.debug(f"    Extracted and standardized from same row, later cell ({k}): '{potential_month}' -> '{standardized}'")
                            return month_year_str_standardized # Found it

                # Strategy 4: Value in the cell directly below (next row, same column)
                if i + 1 < len(df_full):
                    next_row = df_full.iloc[i + 1]
                    if j < len(next_row):
                       potential_month_below = to_clean_str(next_row.iloc[j])
                       if "-" in potential_month_below:
                           standardized = standardize_month_year(potential_month_below)
                           if standardized:
                               month_year_str_standardized = standardized
                               logger.debug(f"    Extracted and standardized from cell below (Row {i+1}, Col {j}): '{potential_month_below}' -> '{standardized}'")
                               return month_year_str_standardized # Found it

                # Strategy 5: Value in the first cell of the next row
                if i + 1 < len(df_full):
                    next_row = df_full.iloc[i + 1]
                    if len(next_row) > 0:
                        potential_month_first = to_clean_str(next_row.iloc[0])
                        # Avoid picking up "Dept. Name" etc.
                        if "-" in potential_month_first and not any(keyword in potential_month_first.lower() for keyword in ["dept", "compname", "report"]):
                            standardized = standardize_month_year(potential_month_first)
                            if standardized:
                                month_year_str_standardized = standardized
                                logger.debug(f"    Extracted and standardized from first cell of next row (Row {i+1}): '{potential_month_first}' -> '{standardized}'")
                                return month_year_str_standardized # Found it

    # Final fallback: Broad search in header rows for any "-YYYY" pattern
    logger.debug("  Final fallback: Searching header for '-YYYY' pattern...")
    for i in range(min(10, len(df_full))):
        row = df_full.iloc[i]
        row_values = [to_clean_str(val) for val in row]
        for cell_value in row_values:
            # Simple check for dash followed by 4 digits
            if "-" in cell_value:
                parts = cell_value.split("-")
                if len(parts) == 2 and len(parts[1]) == 4 and parts[1].isdigit():
                    standardized = standardize_month_year(cell_value)
                    if standardized:
                        logger.debug(f"    Found and standardized via fallback search: '{cell_value}' -> '{standardized}'")
                        return standardized # Found it

    return None # Not found


def parse_superclinic_and_store(file_path: str):
    """Parses the Super Clinic Excel file and stores data in the superclinic.db database."""
    logger.info(f"Starting to parse Super Clinic Excel file: {file_path}")

    # Ensure the Super Clinic database is initialized
    init_superclinic_db()

    df_full = None
    try:
        # --- Attempt to read the file, letting pandas auto-detect the engine ---
        logger.debug("  Attempting to read file with pandas auto-detect engine...")
        df_full = pd.read_excel(file_path, header=None)
        logger.info("  Excel file read successfully with auto-detect.")

    except Exception as e:
        logger.error(f"  Auto-detect failed: {e}")
        # --- If auto-detect fails, fall back to explicit engine selection ---
        _, file_extension = os.path.splitext(file_path)
        file_extension = file_extension.lower()
        engine = None

        if file_extension == '.xls':
            engine = 'xlrd'
            logger.debug(f"  Trying engine '{engine}' for .xls file...")
        elif file_extension == '.xlsx':
            engine = 'openpyxl'
            logger.debug(f"  Trying engine '{engine}' for .xlsx file...")
        else:
            engine = 'openpyxl' # Default fallback
            logger.debug(f"  Unknown extension '{file_extension}'. Trying engine '{engine}'...")

        try:
            df_full = pd.read_excel(file_path, header=None, engine=engine)
            logger.info(f"  Excel file read successfully with engine '{engine}'.")
        except Exception as e2:
            logger.error(f"  Failed with engine '{engine}': {e2}")
            logger.critical("  Critical Error: Unable to read the Excel file with any available engine.")
            return # Stop processing

    if df_full is None or df_full.empty:
        logger.warning("Warning: The Excel file appears to be empty or unreadable.")
        return

    try:
        # --- Extract Month/Year ---
        month_year_str = find_report_month(df_full) # Use the new robust finder
        if not month_year_str:
             logger.error("Error: Could not determine 'Report Month' from the file.")
             logger.error("       Please check the file format. Expected something like 'Report Month: June-2025'.")
             return # Cannot proceed without month

        logger.info(f"  Successfully determined and standardized Month/Year: '{month_year_str}'")

        # --- Clear existing data for this month ---
        logger.info(f"  Deleting existing data for month '{month_year_str}' from '{ATTENDANCE_TABLE}'...")
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(f"DELETE FROM {ATTENDANCE_TABLE} WHERE month_year = ?", (month_year_str,))
        deleted_rows = c.rowcount
        conn.commit()
        conn.close()
        logger.debug(f"    Deleted {deleted_rows} existing rows for {month_year_str}.")

        # --- Process the file in blocks to find employees ---
        processed_blocks = 0
        emp_start_row = 0
        total_rows = len(df_full)

        while emp_start_row < total_rows:
            # Look for the start of an employee block ("Empcode")
            row = df_full.iloc[emp_start_row]
            row_str = to_clean_str(row.iloc[0]) if len(row) > 0 else ""

            if "Empcode" in row_str:
                logger.info(f"\n--- Processing employee block starting at row {emp_start_row} ---")

                # --- Extract Employee Details from the header row ---
                emp_code = "Unknown"
                name = "Unknown"
                row_values = [to_clean_str(cell) for cell in row]

                # Find indices of "Empcode" and "Name"
                empcode_idx = -1
                name_idx = -1
                for i, val in enumerate(row_values):
                    if val.startswith("Empcode"):
                        empcode_idx = i
                    elif val == "Name":
                        name_idx = i

                # Extract values that come *after* "Empcode" and "Name"
                if empcode_idx != -1:
                    for i in range(empcode_idx + 1, len(row_values)):
                        if row_values[i] and row_values[i] != "Name":
                            emp_code = row_values[i]
                            break

                if name_idx != -1:
                    for i in range(name_idx + 1, len(row_values)):
                        if row_values[i]:
                            name = row_values[i]
                            break

                if emp_code == "Unknown":
                    logger.warning(f"  Skipping block at row {emp_start_row}, could not determine employee code.")
                    emp_start_row += 1
                    continue

                logger.info(f"  Found Employee: {emp_code} - '{name}'")

                # --- Determine Employee Category ---
                category = categorize_employee(name)
                logger.info(f"  Employee category determined: {category}")

                # --- Set appropriate leave quotas based on category ---
                initial_wo_quota = 3  # Default for most categories
                initial_cl_quota = 1  # Default for most categories
                cl_calendar_year_quota = None  # Only for consultants

                if category == "Consultant":
                    # For consultants, we need to determine CL quota based on joining date
                    # For now, we'll set a default and update it when we have the joining date
                    initial_wo_quota = 0  # Consultants don't get weekly offs in the same way
                    initial_cl_quota = 0  # Will be set based on joining date
                    cl_calendar_year_quota = 12  # Default, will be updated based on joining date

                # --- Insert/Update Employee Details ---
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute(f"SELECT COUNT(*) FROM {EMPLOYEES_TABLE} WHERE employee_code = ?", (emp_code,))
                count = c.fetchone()[0]
                if count == 0:
                    c.execute(f"""
                        INSERT INTO {EMPLOYEES_TABLE} 
                        (employee_code, name, department, category, date_of_joining, 
                         initial_paid_cl, initial_paid_wo, cl_calendar_year_quota, cl_used_this_year)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (emp_code, name, "Super Clinic", category, None, 
                          initial_cl_quota, initial_wo_quota, cl_calendar_year_quota, 0))
                    logger.info(f"  Inserted new employee {emp_code} into '{EMPLOYEES_TABLE}' table with category {category}.")
                else:
                     c.execute(f"""
                        UPDATE {EMPLOYEES_TABLE}
                        SET name = ?, category = ?
                        WHERE employee_code = ?
                     """, (name, category, emp_code))
                     logger.info(f"  Updated employee {emp_code} name and category in '{EMPLOYEES_TABLE}' table.")
                conn.commit()
                conn.close()

                # --- Locate Daily Data Rows (IN, OUT) ---
                # Assume IN is 2 rows below Empcode row, OUT is 3 rows below
                in_row_idx = emp_start_row + 2
                out_row_idx = emp_start_row + 3

                if in_row_idx >= total_rows or out_row_idx >= total_rows:
                    logger.warning(f"  Warning: IN/OUT rows not found for {emp_code} (beyond file bounds). Skipping daily data.")
                    # Move to next potential block
                    emp_start_row += 1
                    # Simple heuristic: look for next "Empcode" or advance a bit
                    found_next_block = False
                    for next_check in range(emp_start_row, min(emp_start_row + 10, total_rows)):
                         if "Empcode" in to_clean_str(df_full.iloc[next_check, 0]):
                             emp_start_row = next_check
                             found_next_block = True
                             break
                    if not found_next_block:
                         emp_start_row += 5 # Default advance
                    continue

                # --- Extract Daily Data ---
                logger.debug(f"  Extracting daily data from rows {in_row_idx} (IN) and {out_row_idx} (OUT)...")
                attendance_data = []
                # Assuming day columns start from index 1 (column B)
                for day_col_idx in range(1, 32): # Check columns 1 to 31
                    if day_col_idx >= len(df_full.columns):
                        # logger.debug(f"    Day {day_col_idx}: Column index out of bounds. Skipping.")
                        continue # Stop if columns run out

                    in_time_raw = df_full.iloc[in_row_idx, day_col_idx] if in_row_idx < total_rows else None
                    out_time_raw = df_full.iloc[out_row_idx, day_col_idx] if out_row_idx < total_rows else None

                    in_time = parse_time_sc(in_time_raw)
                    out_time = parse_time_sc(out_time_raw)

                    # Note: status_raw is often not applicable/directly usable for SC, so we leave it NULL
                    # The logic will determine status_calculated based on in/out times.
                    attendance_data.append((
                        emp_code, month_year_str, day_col_idx, None, None, # status_raw, status_calculated NULL initially
                        in_time, out_time, None, None # total_hours placeholder, leave_type_used
                    ))

                # --- Store Daily Attendance Data ---
                if attendance_data:
                    try:
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.executemany(f'''
                            INSERT OR REPLACE INTO {ATTENDANCE_TABLE}
                            (employee_code, month_year, day, status_raw, status_calculated, 
                             in_time, out_time, total_hours, leave_type_used)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', attendance_data)
                        inserted_rows = c.rowcount
                        conn.commit()
                        conn.close()
                        logger.info(f"  Daily data for {emp_code} inserted/updated in '{ATTENDANCE_TABLE}' table. ({inserted_rows} rows affected)")
                        processed_blocks += 1
                    except Exception as e:
                         logger.error(f"  Error inserting daily data for {emp_code}: {e}")
                         conn.close() # Ensure connection is closed on error
                else:
                     logger.info(f"  No daily data extracted for {emp_code}.")

                # --- Move to Next Employee Block ---
                # Heuristic: Look for the next "Empcode" row.
                # Start searching a few rows after the current OUT row.
                search_start = out_row_idx + 2
                next_block_found = False
                for next_row_idx in range(search_start, min(search_start + 20, total_rows)):
                    if "Empcode" in to_clean_str(df_full.iloc[next_row_idx, 0]):
                        emp_start_row = next_row_idx
                        next_block_found = True
                        logger.debug(f"  Next employee block found at row {emp_start_row}.")
                        break

                if not next_block_found:
                    logger.debug(f"  No next 'Empcode' found quickly. Advancing pointer.")
                    # If not found, advance pointer cautiously to avoid infinite loops
                    # A common pattern is ~9-10 rows per employee block.
                    # Let's try advancing by 10 and see if we land on an Empcode.
                    tentative_advance = 10
                    tentative_row = emp_start_row + tentative_advance
                    if tentative_row < total_rows and "Empcode" in to_clean_str(df_full.iloc[tentative_row, 0]):
                        emp_start_row = tentative_row
                        logger.debug(f"    Tentatively advanced to row {emp_start_row} (found 'Empcode').")
                    else:
                        # If that doesn't work, advance by 1 and continue the loop
                        emp_start_row += 1
                        logger.debug(f"    Advancing by 1 to row {emp_start_row}.")

            else:
                # Current row is not an Empcode row, move to the next
                emp_start_row += 1

        logger.info(f"\n--- Super Clinic Parsing completed. Processed {processed_blocks} employee data blocks. ---")

    except Exception as e:
        logger.exception(f"An unexpected error occurred during Super Clinic parsing: {e}")

# --- Leave Policy Application Logic for Super Clinic ---

def apply_appropriate_leave_policy(employee_code, month_year):
    """
    Apply the correct leave policy based on employee category
    """
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute(f"SELECT category FROM {EMPLOYEES_TABLE} WHERE employee_code = ?", (employee_code,))
        result = c.fetchone()
        if result:
            category = result[0]
            logger.info(f"Applying leave policy for {category} employee {employee_code}")
            
            if category == "Consultant":
                apply_consultant_leave_policy(employee_code, month_year)
            else:
                apply_staff_leave_policy(employee_code, month_year)
        else:
            logger.warning(f"Employee {employee_code} not found. Applying default staff policy.")
            apply_staff_leave_policy(employee_code, month_year)
    finally:
        conn.close()

def apply_consultant_leave_policy(employee_code, month_year):
    """
    Apply leave policy for consultants based on their specific rules
    """
    logger.info(f"Applying consultant leave policy for employee {employee_code} in {month_year}...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        # Get consultant details
        c.execute(f"""
            SELECT date_of_joining, cl_calendar_year_quota, cl_used_this_year 
            FROM {EMPLOYEES_TABLE} WHERE employee_code = ?
        """, (employee_code,))
        result = c.fetchone()
        
        if not result:
            logger.error(f"Consultant {employee_code} not found in database")
            return
            
        date_of_joining, cl_quota, cl_used = result
        if cl_quota is None:
            cl_quota = get_consultant_cl_quota(date_of_joining)
            # Update the quota in the database
            c.execute(f"""
                UPDATE {EMPLOYEES_TABLE} 
                SET cl_calendar_year_quota = ? 
                WHERE employee_code = ?
            """, (cl_quota, employee_code))
            conn.commit()

        logger.info(f"Consultant {employee_code} has CL quota: {cl_quota}, used: {cl_used}")

        # Calculate total present days
        c.execute(f"""
            SELECT COUNT(*) FROM {ATTENDANCE_TABLE} 
            WHERE employee_code = ? AND month_year = ? 
            AND (in_time IS NOT NULL OR out_time IS NOT NULL)
        """, (employee_code, month_year))
        
        present_days = c.fetchone()[0]
        logger.debug(f"Consultant {employee_code} has {present_days} present days")

        # For consultants, all Sundays are paid weekly off (Rule 1)
        # But we need to mark regular attendance first
        # Step 1: Calculate initial status_calculated ('P' or 'AB')
        query_initial = f"""
            SELECT id, day, in_time, out_time
            FROM {ATTENDANCE_TABLE}
            WHERE employee_code = ? AND month_year = ?
        """
        c.execute(query_initial, (employee_code, month_year))
        records = c.fetchall()

        if not records:
            logger.warning(f"  No records found for {employee_code} in {month_year}.")
            return

        updates = []
        for record in records:
            record_id, day, in_time, out_time = record
            # Determine presence based on IN or OUT time
            if (in_time is not None and in_time != "") or (out_time is not None and out_time != ""):
                status_calc = 'P'
            else:
                status_calc = 'AB' # Mark as Absent initially, will be refined
            updates.append((status_calc, record_id))

        # Batch update initial statuses
        c.executemany(f"UPDATE {ATTENDANCE_TABLE} SET status_calculated = ? WHERE id = ?", updates)
        conn.commit()
        logger.info(f"  Initial status_calculated ('P'/'AB') set for {len(records)} days.")

        # For consultants, CL usage is more flexible but tracked annually
        # We'll allocate remaining AB days to CL if available
        remaining_cl = cl_quota - cl_used
        logger.info(f"Consultant has {remaining_cl} CL remaining for allocation")

        if remaining_cl > 0:
            # Get all AB days that haven't been marked as 'Absent' due to long sequences
            c.execute(f"""
                SELECT id, day FROM {ATTENDANCE_TABLE}
                WHERE employee_code = ? AND month_year = ? AND status_calculated = 'AB'
                ORDER BY day
            """, (employee_code, month_year))
            
            ab_records = c.fetchall()
            
            # Allocate CL to AB days (up to remaining quota)
            cl_updates = []
            cl_to_allocate = min(len(ab_records), remaining_cl)
            
            for i in range(cl_to_allocate):
                record_id, day = ab_records[i]
                cl_updates.append(('CL', 'CL', record_id))  # status_calculated, leave_type_used, id
            
            if cl_updates:
                c.executemany(f"""
                    UPDATE {ATTENDANCE_TABLE} 
                    SET status_calculated = ?, leave_type_used = ? 
                    WHERE id = ?
                """, cl_updates)
                conn.commit()
                logger.info(f"Allocated {len(cl_updates)} CL days for consultant {employee_code}")
                
                # Update the used CL count
                new_cl_used = cl_used + len(cl_updates)
                c.execute(f"""
                    UPDATE {EMPLOYEES_TABLE} 
                    SET cl_used_this_year = ? 
                    WHERE employee_code = ?
                """, (new_cl_used, employee_code))
                conn.commit()

            # Mark any remaining AB days as 'Absent'
            if len(ab_records) > cl_to_allocate:
                absent_updates = []
                for i in range(cl_to_allocate, len(ab_records)):
                    record_id, day = ab_records[i]
                    absent_updates.append(('Absent', record_id))
                
                c.executemany(f"""
                    UPDATE {ATTENDANCE_TABLE} 
                    SET status_calculated = ? 
                    WHERE id = ?
                """, absent_updates)
                conn.commit()
                logger.info(f"Marked {len(absent_updates)} days as 'Absent' for consultant {employee_code}")

        logger.info(f"Consultant leave policy applied successfully for {employee_code} in {month_year}.")

    except Exception as e:
        logger.exception(f"Error applying consultant leave policy for {employee_code}: {e}")
    finally:
        conn.close()

def apply_staff_leave_policy(employee_code, month_year):
    """
    Applies the leave policy logic to Super Clinic staff (Non-Medical, Paramedical, RMOs & Office Staff)
    Rules:
    1. Presence ('P') = IN or OUT time exists.
    2. After 9 days attendance only, the employee will be eligible for one paid weekly off.
    3. For a sequence of > 3 consecutive 'AB' days:
        - The first 3 days are allocated to WO (using the WO quota).
        - Days 4 and beyond are marked as 'Absent'.
        - The CL quota is NOT used for any day in this sequence.
    4. For a sequence of exactly 3 consecutive 'AB' days:
        - All 3 days are allocated to WO (using the WO quota).
        - The CL quota is NOT used for any day in this sequence.
    5. Remaining 'AB' days (not in long sequences) are allocated to WO (max 3) then CL (max 1).
    6. More than 03 paid leave cannot be clubbed together.
    7. In case if CL not taken by any employee then it will paid in same month salary.
    """
    logger.info(f"Applying staff leave policy for Super Clinic employee {employee_code} in {month_year}...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        # --- Step 1: Calculate total present days to determine eligibility ---
        c.execute(f"""
            SELECT COUNT(*) FROM {ATTENDANCE_TABLE} 
            WHERE employee_code = ? AND month_year = ? 
            AND (in_time IS NOT NULL OR out_time IS NOT NULL)
        """, (employee_code, month_year))
        
        present_days = c.fetchone()[0]
        logger.debug(f"Employee {employee_code} has {present_days} present days")
        
        # Check eligibility for paid leaves (Rule 1: 9+ days attendance required)
        is_eligible_for_paid_leaves = present_days >= 9
        logger.debug(f"Eligibility for paid leaves: {is_eligible_for_paid_leaves}")
        
        # Get employee leave quotas
        c.execute(f"""
            SELECT initial_paid_wo, initial_paid_cl 
            FROM {EMPLOYEES_TABLE} 
            WHERE employee_code = ?
        """, (employee_code,))
        wo_quota, cl_quota = c.fetchone() or (3, 1)
        
        logger.debug(f"Employee {employee_code} has quotas: WO={wo_quota}, CL={cl_quota}")

        # --- Step 2: Calculate initial status_calculated ('P' or 'AB') ---
        query_initial = f"""
            SELECT id, day, in_time, out_time
            FROM {ATTENDANCE_TABLE}
            WHERE employee_code = ? AND month_year = ?
        """
        c.execute(query_initial, (employee_code, month_year))
        records = c.fetchall()

        if not records:
            logger.warning(f"  No records found for {employee_code} in {month_year}.")
            return

        updates = []
        for record in records:
            record_id, day, in_time, out_time = record
            # Determine presence based on IN or OUT time
            if (in_time is not None and in_time != "") or (out_time is not None and out_time != ""):
                status_calc = 'P'
            else:
                status_calc = 'AB' # Mark as Absent initially, will be refined
            updates.append((status_calc, record_id))

        # Batch update initial statuses
        c.executemany(f"UPDATE {ATTENDANCE_TABLE} SET status_calculated = ? WHERE id = ?", updates)
        conn.commit()
        logger.info(f"  Initial status_calculated ('P'/'AB') set for {len(records)} days.")

        # If not eligible for paid leaves, mark all absent days as 'Absent'
        if not is_eligible_for_paid_leaves:
            logger.info(f"Employee {employee_code} not eligible for paid leaves (less than 9 present days)")
            # Mark all absent days as 'Absent' without using quotas
            c.execute(f"""
                UPDATE {ATTENDANCE_TABLE} 
                SET status_calculated = 'Absent' 
                WHERE employee_code = ? AND month_year = ? 
                AND in_time IS NULL AND out_time IS NULL
            """, (employee_code, month_year))
            conn.commit()
            logger.info(f"Marked all absent days as 'Absent' for ineligible employee {employee_code}")
            return

        # --- Step 3: Identify and Mark Long Continuous Absences (> 3 consecutive 'AB') ---
        # Fetch records again with the initial status, ordered by day
        query_with_status_ordered = f"""
            SELECT id, day, status_calculated
            FROM {ATTENDANCE_TABLE}
            WHERE employee_code = ? AND month_year = ?
            ORDER BY day
        """
        c.execute(query_with_status_ordered, (employee_code, month_year))
        records_with_status = c.fetchall()

        # Find consecutive 'AB' sequences
        sequences = [] # List of lists, each inner list is a sequence of (record_id, day)
        current_sequence = []

        for i, (record_id, day, status_calc) in enumerate(records_with_status):
            if status_calc == 'AB':
                # Check if this day is consecutive to the previous one in the current sequence
                if not current_sequence or day == current_sequence[-1][1] + 1:
                    current_sequence.append((record_id, day))
                else:
                    # Sequence broken, save the current one and start a new one
                    if len(current_sequence) > 0:
                        sequences.append(current_sequence)
                    current_sequence = [(record_id, day)]
            else:
                # Not an AB day, so sequence is broken
                if len(current_sequence) > 0:
                    sequences.append(current_sequence)
                current_sequence = []

        # Don't forget the last sequence if it ends with AB
        if len(current_sequence) > 0:
            sequences.append(current_sequence)

        logger.info(f"  Found {len(sequences)} consecutive 'AB' sequences.")

        # Process each sequence
        long_absence_updates = []
        for sequence in sequences:
            if len(sequence) > 3:
                # Mark days 4, 5, 6, ... as 'Absent'
                for i in range(3, len(sequence)):
                    long_absence_updates.append(('Absent', sequence[i][0]))
                logger.debug(f"    Marked days {sequence[3][1]}-{sequence[-1][1]} as 'Absent' (long sequence).")

        # Batch update long absences
        if long_absence_updates:
            c.executemany(f"UPDATE {ATTENDANCE_TABLE} SET status_calculated = ? WHERE id = ?", long_absence_updates)
            conn.commit()
            logger.info(f"  Marked {len(long_absence_updates)} days as 'Absent' (days after 3 in long sequences).")

        # --- Step 4: Allocate Leave Quotas (3 WO + 1 CL) for Remaining 'AB' Days ---
        # Fetch records again after marking long absences, ordered by day
        c.execute(query_with_status_ordered, (employee_code, month_year)) # Re-use the correctly ordered query
        records_after_long_absence = c.fetchall()

        # Get a list of remaining 'AB' days (not yet marked 'Absent')
        remaining_ab_days = []
        for record in records_after_long_absence:
             record_id, day, status = record
             # status is already fetched correctly
             if status == 'AB':
                 remaining_ab_days.append((record_id, day))

        logger.info(f"  Found {len(remaining_ab_days)} 'AB' days eligible for WO/CL allocation.")

        # Allocate remaining AB days to WO first, then CL
        wo_allocated = 0
        cl_allocated = 0
        quota_updates = []

        # Iterate through the remaining 'AB' days
        for record_id, day in remaining_ab_days:
            # Allocate to WO first, then CL
            if wo_allocated < wo_quota:
                quota_updates.append(('WO', 'WO', record_id))  # status_calculated, leave_type_used, id
                wo_allocated += 1
            elif cl_allocated < cl_quota: # Only allocate CL if WO quota is full
                quota_updates.append(('CL', 'CL', record_id))  # status_calculated, leave_type_used, id
                cl_allocated += 1
            else:
                # Exceeds total quota, mark as Absent
                quota_updates.append(('Absent', None, record_id))  # status_calculated, leave_type_used, id
                logger.warning(f"    Warning: Day {day} exceeds leave quota. Marking as 'Absent'.")

        # Batch update quota allocations
        if quota_updates:
            c.executemany(f"""
                UPDATE {ATTENDANCE_TABLE} 
                SET status_calculated = ?, leave_type_used = ? 
                WHERE id = ?
            """, quota_updates)
            conn.commit()
            logger.info(f"  Allocated quotas: {wo_allocated} WO, {cl_allocated} CL. Updated {len(quota_updates)} days.")
        
        logger.info(f"Staff leave policy applied successfully for {employee_code} in {month_year}.")

    except Exception as e:
        logger.exception(f"Error applying staff leave policy for Super Clinic employee {employee_code} in {month_year}: {e}")
    finally:
        conn.close()

# --- Functions for Streamlit Frontend to interact with Super Clinic DB ---

def get_summary_report_sc():
    """Generates a summary report from the superclinic.db database."""
    logger.debug("Fetching summary report...")
    conn = sqlite3.connect(DB_NAME)
    # Corrected column names in query to match output interpretation
    # Join with employees_sc table to get name
    # Calculate used and unused CL/WO
    query = f"""
    WITH final_status AS (
        SELECT
            ma.employee_code,
            e.name,
            e.category,
            ma.month_year,
            ma.day,
            ma.status_calculated,
            ma.leave_type_used
        FROM {ATTENDANCE_TABLE} ma
        LEFT JOIN {EMPLOYEES_TABLE} e
            ON ma.employee_code = e.employee_code
    )
    SELECT
        employee_code,
        name,
        category,
        month_year,
        SUM(CASE WHEN status_calculated = 'P' THEN 1 ELSE 0 END) as Present,
        SUM(CASE WHEN status_calculated = 'Absent' THEN 1 ELSE 0 END) as Absent,
        SUM(CASE WHEN status_calculated = 'WO' THEN 1 ELSE 0 END) as Used_WO,
        SUM(CASE WHEN status_calculated = 'CL' THEN 1 ELSE 0 END) as Used_CL,
        (3 - SUM(CASE WHEN status_calculated = 'WO' THEN 1 ELSE 0 END)) as Unused_WO,
        (1 - SUM(CASE WHEN status_calculated = 'CL' THEN 1 ELSE 0 END)) as Unused_CL,
        SUM(CASE WHEN status_calculated = 'AB' THEN 1 ELSE 0 END) as Still_AB
    FROM final_status
    GROUP BY employee_code, name, category, month_year
    ORDER BY employee_code, month_year
    """
    try:
        df_summary = pd.read_sql_query(query, conn)
        logger.debug(f"  Summary report fetched successfully. Shape: {df_summary.shape}")
        # Log a sample to check names
        if not df_summary.empty:
             logger.debug(f"  Sample row from summary:\n{df_summary.iloc[0].to_dict()}")
    except Exception as e:
        logger.error(f"Error fetching Super Clinic summary report: {e}")
        df_summary = pd.DataFrame()
    finally:
        conn.close()
    return df_summary

def get_detailed_report_sc(employee_code, month_year):
    """Fetches detailed daily attendance for an employee/month from superclinic.db."""
    logger.debug(f"Fetching detailed report for {employee_code}, {month_year}...")
    conn = sqlite3.connect(DB_NAME)
    query = f"""
    SELECT day, status_raw, status_calculated, in_time, out_time, total_hours, leave_type_used
    FROM {ATTENDANCE_TABLE}
    WHERE employee_code = ? AND month_year = ?
    ORDER BY day
    """
    try:
        df_detail = pd.read_sql_query(query, conn, params=(employee_code, month_year))
        logger.debug(f"  Detailed report fetched successfully for {employee_code}, {month_year}. Shape: {df_detail.shape}")
    except Exception as e:
        logger.error(f"Error fetching Super Clinic detailed report for {employee_code}, {month_year}: {e}")
        df_detail = pd.DataFrame()
    finally:
        conn.close()
    return df_detail

def apply_leave_policy_for_all_employees_sc(month_year):
    """
    Apply leave policy for all employees for a given month
    """
    logger.info(f"Applying leave policy for all employees in {month_year}...")
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        # Get all employees with attendance records for this month
        c.execute(f"""
            SELECT DISTINCT ma.employee_code, e.category
            FROM {ATTENDANCE_TABLE} ma
            JOIN {EMPLOYEES_TABLE} e ON ma.employee_code = e.employee_code
            WHERE ma.month_year = ?
        """, (month_year,))
        
        employees = c.fetchall()
        logger.info(f"Found {len(employees)} employees with attendance records for {month_year}")
        
        for employee_code, category in employees:
            logger.info(f"Processing employee {employee_code} ({category})")
            apply_appropriate_leave_policy(employee_code, month_year)
            
        logger.info(f"Leave policy applied for all employees in {month_year}")
    except Exception as e:
        logger.exception(f"Error applying leave policy for all employees: {e}")
    finally:
        conn.close()

# --- Main Execution Guard ---
if __name__ == "__main__":
    # init_superclinic_db()
    # parse_superclinic_and_store("path/to/your/All_is_well_Super_Clinic_June_2025.xlsx")
    pass