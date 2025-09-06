# hospital.py

import pandas as pd
from datetime import datetime
import sqlite3
import calendar
import re
import os # For file path handling

# --- Configuration ---
DB_NAME = "attendance.db"
EMPLOYEES_TABLE = "employees"
ATTENDANCE_TABLE = "monthly_attendance"

# --- Database Functions ---

def init_db():
    """Initializes the SQLite database and creates tables."""
    print("Initializing database...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute(f'''
        CREATE TABLE IF NOT EXISTS {EMPLOYEES_TABLE} (
            employee_code TEXT PRIMARY KEY,
            name TEXT,
            department TEXT,
            category TEXT,
            date_of_joining DATE,
            initial_paid_cl INTEGER,
            initial_paid_wo INTEGER
        )
    ''')

    c.execute(f'''
        CREATE TABLE IF NOT EXISTS {ATTENDANCE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT,
            month_year TEXT,
            day INTEGER,
            status_raw TEXT,
            status_calculated TEXT,
            in_time TEXT,
            out_time TEXT,
            total_hours REAL,
            FOREIGN KEY (employee_code) REFERENCES {EMPLOYEES_TABLE} (employee_code),
            UNIQUE(employee_code, month_year, day) ON CONFLICT REPLACE -- Prevent duplicates
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized.")

def get_days_in_month(month_year_str):
    """Calculates the number of days in a given month/year string."""
    try:
        parts = month_year_str.strip().split()
        if len(parts) < 2:
             print(f"Warning: Could not parse month_year '{month_year_str}'. Assuming 31 days.")
             return 31

        month_name = parts[-2]
        year_str = parts[-1]
        year = int(year_str)

        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
            'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
            'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        month_num = month_map.get(month_name, 1)

        days = calendar.monthrange(year, month_num)[1]
        return days
    except (ValueError, IndexError) as e:
        print(f"Error calculating days for '{month_year_str}': {e}. Assuming 31 days.")
        return 31

# --- Helper Functions for Parsing ---

def parse_employee_details(details_text):
    """Parses employee details."""
    emp_code = "Unknown"
    name = "Unknown"
    department = "Unknown"
    month_year = "Unknown"

    if isinstance(details_text, str):
        parts = details_text.split("|")
        for part in parts:
            if ":" in part:
                key, value = part.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "Employe Code": # Typo in Excel
                    emp_code = value
                elif key == "Name":
                    name = value
                elif key == "Department":
                    department = value
                elif key == "Month": # Space in "Month :"
                    month_year = value
    return emp_code, name, department, month_year

def parse_time(time_str):
    """Parses time string."""
    if pd.isna(time_str) or time_str == "" or time_str == "0" or time_str == "00:00" or time_str == ":" or time_str == "--":
        return None
    time_str = str(time_str).strip()
    if re.match(r'\d{1,2}:\d{2}\s*(AM|PM)', time_str, re.IGNORECASE):
        try:
            parsed_time = datetime.strptime(time_str, "%I:%M %p")
            return parsed_time.strftime("%I:%M %p")
        except ValueError:
            pass
    print(f"Warning: Unrecognized time format '{time_str}'.")
    return None

def find_data_rows(block_df):
    """Finds indices of data rows within an employee block slice."""
    indices = {'date': None, 'attendance': None, 'in': None, 'out': None, 'total_hour': None}
    for i, row in block_df.iterrows():
        first_cell = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
        if first_cell.startswith("Date"):
            indices['date'] = i
        elif first_cell.startswith("Attendance"):
            indices['attendance'] = i
        elif first_cell.startswith("IN"):
            indices['in'] = i
        elif first_cell.startswith("OUT"):
            indices['out'] = i
        elif first_cell.startswith("Total Hour"):
            indices['total_hour'] = i
    return indices

# --- Core Parsing Function ---

def parse_excel_and_store(file_path):
    """Parses the Excel file and stores data in the database."""
    print(f"Starting to parse Excel file: {file_path}")
    # Resolve path to handle potential issues
    file_path = os.path.abspath(file_path)
    try:
        df_full = pd.read_excel(file_path, header=None, engine='xlrd')
        print("Excel file read successfully.")

        if df_full.empty:
            print("Warning: The Excel file appears to be empty.")
            return

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # --- Clear existing data for the month before parsing ---
        # This prevents duplicates from previous runs or partial parses
        # We need to determine the month first. Let's get it from the first valid employee block.
        month_year_to_clear = None
        for i, row in df_full.iterrows():
            for cell in row:
                if isinstance(cell, str) and "Employe Code:" in cell:
                    details_text = " ".join(df_full.iloc[i].dropna().astype(str))
                    _, _, _, month_year = parse_employee_details(details_text)
                    if month_year != "Unknown":
                        month_year_to_clear = month_year
                        break
            if month_year_to_clear:
                break

        if month_year_to_clear:
            print(f"Deleting existing data for month '{month_year_to_clear}' to avoid duplicates...")
            c.execute(f"DELETE FROM {ATTENDANCE_TABLE} WHERE month_year = ?", (month_year_to_clear,))
            conn.commit()
        else:
            print("Warning: Could not determine month from file to clear existing data.")

        header_indices = []
        for i, row in df_full.iterrows():
            for cell in row:
                if isinstance(cell, str) and "Employe Code:" in cell:
                    header_indices.append(i)
                    break

        if not header_indices:
            print("Warning: No employee headers found.")
            return

        processed_blocks = 0

        for i, header_idx in enumerate(header_indices):
            print(f"\nAnalyzing potential block starting at row {header_idx}...")

            details_text = " ".join(df_full.iloc[header_idx].dropna().astype(str))
            emp_code, name, department, month_year = parse_employee_details(details_text)

            if emp_code == "Unknown":
                print(f"  Skipping row {header_idx}, could not determine employee code.")
                continue

            print(f"  Identified Employee: {name} ({emp_code}), Department: {department}, Month: {month_year}")

            # Look for the 'Date' row immediately after this header
            date_row_idx = None
            for j in range(header_idx + 1, min(header_idx + 5, len(df_full))):
                first_cell = str(df_full.iloc[j, 0]).strip() if not pd.isna(df_full.iloc[j, 0]) else ""
                if first_cell.startswith("Date"):
                    date_row_idx = j
                    break

            if date_row_idx is None:
                print(f"  Warning: No 'Date' row found for {emp_code}. Skipping.")
                continue

            print(f"  Found 'Date' row for {emp_code} at row {date_row_idx}.")

            # Determine the end of this data block
            block_end_idx = len(df_full)
            for j in range(i + 1, len(header_indices)):
                next_header_idx = header_indices[j]
                potential_date_row_idx = next_header_idx + 1
                if potential_date_row_idx < len(df_full):
                    first_cell_next = str(df_full.iloc[potential_date_row_idx, 0]).strip() if not pd.isna(df_full.iloc[potential_date_row_idx, 0]) else ""
                    if first_cell_next.startswith("Date"):
                        block_end_idx = next_header_idx
                        print(f"  Determined block end for {emp_code} at row {block_end_idx}.")
                        break

            # Slice the block DataFrame
            block_df = df_full.iloc[header_idx:block_end_idx].reset_index(drop=True)
            print(f"  Processing data block (rows {header_idx} to {block_end_idx - 1}).")

            # Find row indices within the slice
            row_indices = find_data_rows(block_df)
            date_idx_in_slice = row_indices['date']
            in_idx_in_slice = row_indices['in']
            out_idx_in_slice = row_indices['out']

            if date_idx_in_slice is None:
                print(f"  Error: 'Date' row not found in sliced block for {emp_code}.")
                continue
            if in_idx_in_slice is None and out_idx_in_slice is None:
                print(f"  Warning: Neither 'IN' nor 'OUT' row found for {emp_code}. Skipping.")
                continue

            # Extract day columns
            date_row_in_slice = block_df.iloc[date_idx_in_slice]
            day_columns = {}
            for col_idx in range(1, len(date_row_in_slice)):
                try:
                    day_val = pd.to_numeric(date_row_in_slice.iloc[col_idx], errors='coerce')
                    if not pd.isna(day_val) and 1 <= day_val <= 31:
                        day_columns[int(day_val)] = col_idx
                except (ValueError, TypeError):
                    pass

            if not day_columns:
                print(f"  Warning: Could not identify day columns for {emp_code}.")
                continue

            days_in_month = get_days_in_month(month_year)

            # --- Insert/Update Employee Details into employees table ---
            # Only insert if not already exists, otherwise update name/department if needed
            c.execute(f"SELECT COUNT(*) FROM {EMPLOYEES_TABLE} WHERE employee_code = ?", (emp_code,))
            count = c.fetchone()[0]
            if count == 0:
                # Insert new employee
                c.execute(f"""
                    INSERT INTO {EMPLOYEES_TABLE} (employee_code, name, department, category, date_of_joining, initial_paid_cl, initial_paid_wo)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (emp_code, name, department, "Non-Medical", None, 1, 3)) # Default values
                print(f"  Inserted employee {emp_code} into employees table.")
            else:
                 # Update name/department if they might have changed (optional, but good practice)
                 c.execute(f"""
                    UPDATE {EMPLOYEES_TABLE}
                    SET name = ?, department = ?
                    WHERE employee_code = ?
                 """, (name, department, emp_code))
                 print(f"  Updated employee {emp_code} info in employees table.")

            # Extract Data for Each Day
            attendance_data = []
            processed_days = set()

            for day in range(1, days_in_month + 1):
                col_idx = day_columns.get(day)
                if col_idx is None:
                    print(f"    Day {day}: Data not found. Inserting NULLs.")
                    attendance_data.append((emp_code, month_year, day, None, None, None, None, None))
                    processed_days.add(day)
                    continue

                status_raw = None
                in_time_raw = None
                out_time_raw = None

                if row_indices['attendance'] is not None and len(block_df) > row_indices['attendance']:
                    status_raw = block_df.iloc[row_indices['attendance'], col_idx]
                if in_idx_in_slice is not None and len(block_df) > in_idx_in_slice:
                    in_time_raw = block_df.iloc[in_idx_in_slice, col_idx]
                if out_idx_in_slice is not None and len(block_df) > out_idx_in_slice:
                    out_time_raw = block_df.iloc[out_idx_in_slice, col_idx]

                in_time = parse_time(in_time_raw)
                out_time = parse_time(out_time_raw)
                status_calculated = None # Will be set by policy logic

                attendance_data.append((
                    emp_code, month_year, day, status_raw, status_calculated,
                    in_time, out_time, None # total_hours
                ))
                processed_days.add(day)

            if len(processed_days) != days_in_month:
                 print(f"  Warning: Processed {len(processed_days)} days, expected {days_in_month}.")

            # Insert Data (UNIQUE constraint handles potential remaining duplicates in this block)
            try:
                c.executemany(f'''
                    INSERT OR REPLACE INTO {ATTENDANCE_TABLE}
                    (employee_code, month_year, day, status_raw, status_calculated, in_time, out_time, total_hours)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', attendance_data)
                conn.commit()
                print(f"  Data for {emp_code} inserted/updated successfully.")
                processed_blocks += 1
            except Exception as e:
                 print(f"  Error inserting data for {emp_code}: {e}")

        conn.close()
        print(f"\nParsing completed. Processed {processed_blocks} employee data blocks.")

    except Exception as e:
        print(f"An error occurred during parsing: {e}")
        import traceback
        traceback.print_exc()

# --- Leave Policy Application Logic ---

def apply_leave_policy_for_month(employee_code, month_year):
    """
    Applies the leave policy logic.
    Rules:
    1. Presence ('P') = IN or OUT time exists.
    2. For a sequence of > 3 consecutive 'AB' days:
        - The first 3 days are allocated to WO (using the WO quota).
        - Days 4 and beyond are marked as 'Absent'.
        - The CL quota is NOT used for any day in this sequence.
    3. Remaining 'AB' days (not in long sequences) are allocated to WO (max 3) then CL (max 1).
       (If WO is used in a long sequence, CL can still be used for other short absences).
    """
    print(f"Applying leave policy for {employee_code} in {month_year}...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        # --- Step 1: Calculate initial status_calculated ('P' or 'AB') ---
        query_initial = f"""
            SELECT id, day, in_time, out_time
            FROM {ATTENDANCE_TABLE}
            WHERE employee_code = ? AND month_year = ?
        """ # ORDER BY is handled in Python for sequence logic
        c.execute(query_initial, (employee_code, month_year))
        records = c.fetchall()

        if not records:
            print(f"  No records found for {employee_code} in {month_year}.")
            return

        updates = []
        for record in records:
            record_id, day, in_time, out_time = record
            if (in_time is not None and in_time != "") or (out_time is not None and out_time != ""):
                status_calc = 'P'
            else:
                status_calc = 'AB'
            updates.append((status_calc, record_id))

        c.executemany(f"UPDATE {ATTENDANCE_TABLE} SET status_calculated = ? WHERE id = ?", updates)
        conn.commit()
        print(f"  Initial status_calculated set for {len(records)} days.")

        # --- Step 2: Identify Consecutive Absence Sequences ---
        # Fetch records with initial status, ordered by day
        query_with_status = f"""
            SELECT id, day, status_calculated
            FROM {ATTENDANCE_TABLE}
            WHERE employee_code = ? AND month_year = ?
            ORDER BY day
        """
        c.execute(query_with_status, (employee_code, month_year))
        records_with_status = c.fetchall()

        # Find sequences of consecutive 'AB' days
        sequences = []  # List of lists, each inner list is a sequence of (record_id, day)
        current_sequence = []

        for i, (record_id, day, status) in enumerate(records_with_status):
            if status == 'AB':
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

        print(f"  Found {len(sequences)} consecutive 'AB' sequences.")

        # Process each sequence
        long_absence_updates = []
        for sequence in sequences:
            if len(sequence) > 3:
                # Mark days 4, 5, 6, ... as 'Absent'
                for i in range(3, len(sequence)):
                    long_absence_updates.append(('Absent', sequence[i][0]))
                print(f"    Marked days {sequence[3][1]}-{sequence[-1][1]} as 'Absent' (long sequence).")
            # Note: The first 3 days remain 'AB' for potential WO allocation in Step 3.

        if long_absence_updates:
            c.executemany(f"UPDATE {ATTENDANCE_TABLE} SET status_calculated = ? WHERE id = ?", long_absence_updates)
            conn.commit()
            print(f"  Marked {len(long_absence_updates)} days as 'Absent' (days after 3 in long sequences).")

        # --- Step 3: Allocate Leave Quotas (3 WO + 1 CL) for Remaining 'AB' Days ---
        # Fetch records again after marking long absences
        c.execute(query_with_status, (employee_code, month_year)) # Re-use the query with ORDER BY
        records_after_long_absence = c.fetchall()

        # Get a list of remaining 'AB' days (not yet marked 'Absent')
        remaining_ab_days = []
        for record in records_after_long_absence:
             record_id, day, status = record
             # status is already fetched correctly
             if status == 'AB':
                 remaining_ab_days.append((record_id, day))

        print(f"  Found {len(remaining_ab_days)} 'AB' days eligible for WO/CL allocation.")

        wo_allocated = 0
        cl_allocated = 0
        quota_updates = []

        for record_id, day in remaining_ab_days:
            # Allocate to WO first, then CL, regardless of sequence origin (as per rule 3)
            # This allows CL to be used for short absences even if WO was used in a long one.
            if wo_allocated < 3:
                quota_updates.append(('WO', record_id))
                wo_allocated += 1
            elif cl_allocated < 1: # Only allocate CL if WO quota is full
                quota_updates.append(('CL', record_id))
                cl_allocated += 1
            else:
                # Exceeds total quota (3 WO + 1 CL = 4), mark as Absent
                # This handles cases where there are more than 4 isolated AB days
                # or AB days after long sequences have used up WO quota.
                quota_updates.append(('Absent', record_id))
                print(f"    Warning: Day {day} exceeds leave quota (WO: {wo_allocated}, CL: {cl_allocated}). Marking as 'Absent'.")

        if quota_updates:
            c.executemany(f"UPDATE {ATTENDANCE_TABLE} SET status_calculated = ? WHERE id = ?", quota_updates)
            conn.commit()
            print(f"  Allocated quotas: {wo_allocated} WO, {cl_allocated} CL. Updated {len(quota_updates)} days.")

        print(f"Leave policy applied successfully for {employee_code} in {month_year}.")

    except Exception as e:
        print(f"Error applying leave policy for {employee_code} in {month_year}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def process_attendance_for_month(employee_code, month_year):
    """Wrapper for applying policy."""
    apply_leave_policy_for_month(employee_code, month_year)

# --- Functions for Streamlit Frontend ---

def get_summary_report():
    """Generates a summary report."""
    conn = sqlite3.connect(DB_NAME)
    # Corrected column names in query to match output interpretation
    # Join with employees table to get name
    # Calculate used and unused CL/WO
    query = f"""
    SELECT
        ma.employee_code,
        e.name, -- Get name from employees table
        ma.month_year,
        COUNT(CASE WHEN ma.status_calculated = 'P' THEN 1 END) as Present,
        COUNT(CASE WHEN ma.status_calculated = 'Absent' THEN 1 END) as Absent,
        COUNT(CASE WHEN ma.status_calculated = 'WO' THEN 1 END) as Used_WO,
        COUNT(CASE WHEN ma.status_calculated = 'CL' THEN 1 END) as Used_CL,
        (3 - COUNT(CASE WHEN ma.status_calculated = 'WO' THEN 1 END)) as Unused_WO, -- Assuming 3 WO quota
        (1 - COUNT(CASE WHEN ma.status_calculated = 'CL' THEN 1 END)) as Unused_CL, -- Assuming 1 CL quota
        COUNT(CASE WHEN ma.status_calculated = 'AB' THEN 1 END) as Still_AB -- Should be 0 after policy
    FROM {ATTENDANCE_TABLE} ma
    LEFT JOIN {EMPLOYEES_TABLE} e ON ma.employee_code = e.employee_code -- Join to get name
    GROUP BY ma.employee_code, e.name, ma.month_year -- Group by name as well
    ORDER BY ma.employee_code, ma.month_year
    """
    try:
        df_summary = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error fetching summary report: {e}")
        df_summary = pd.DataFrame()
    finally:
        conn.close()
    return df_summary

def get_detailed_report(employee_code, month_year):
    """Fetches detailed daily attendance."""
    conn = sqlite3.connect(DB_NAME)
    query = f"""
    SELECT day, status_raw, status_calculated, in_time, out_time, total_hours
    FROM {ATTENDANCE_TABLE}
    WHERE employee_code = ? AND month_year = ?
    ORDER BY day
    """
    try:
        df_detail = pd.read_sql_query(query, conn, params=(employee_code, month_year))
    except Exception as e:
        print(f"Error fetching detailed report: {e}")
        df_detail = pd.DataFrame()
    finally:
        conn.close()
    return df_detail

# --- Main Execution Guard ---
if __name__ == "__main__":
    init_db()
    # parse_excel_and_store("path/to/your/All is well Aug.xls")
