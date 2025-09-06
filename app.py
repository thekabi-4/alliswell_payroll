# app.py
"""
Streamlit frontend for All Is Well Hospital and Super Clinic Attendance Calculators.
Enhanced with modern UI/UX, user identification, data previews, and clipboard functionality.
"""
import streamlit as st
import pandas as pd
import sqlite3
import tempfile
import os
import base64
from datetime import datetime

# --- Import backend modules ---
try:
    import hospital
    HOSPITAL_AVAILABLE = True
except ImportError as e:
    st.error(f"Error importing 'hospital.py': {e}")
    HOSPITAL_AVAILABLE = False

try:
    import superclinic # This is the new parser you saved
    SUPERCLINIC_AVAILABLE = True
except ImportError as e:
    st.error(f"Error importing 'superclinic.py': {e}")
    SUPERCLINIC_AVAILABLE = False

# --- Session State Initialization ---
if 'user_name' not in st.session_state:
    st.session_state.user_name = "Guest"
if 'uploaded_file_info' not in st.session_state:
    st.session_state.uploaded_file_info = None
if 'processed_data_info' not in st.session_state:
    st.session_state.processed_data_info = None
if 'last_summary_df' not in st.session_state:
    st.session_state.last_summary_df = None
if 'last_detail_df' not in st.session_state:
    st.session_state.last_detail_df = None

# --- Custom CSS for Enhanced UI ---
st.markdown("""
<style>
    /* Main theme colors */
    :root {
        --primary-color: #4CAF50;
        --primary-hover: #45a049;
        --secondary-color: #2196F3;
        --background-color: #f8f9fa;
        --text-color: #333333;
        --success-color: #4CAF50;
        --warning-color: #FF9800;
        --error-color: #F44336;
        --info-color: #2196F3;
        --preview-bg: #e8f5e9;
        --preview-border: #4CAF50;
    }
    
    /* Header styling */
    header { background-color: var(--primary-color) !important; }
    header .css-1v0mbdj { color: white !important; }
    
    /* Navigation styling */
    .css-1d391kg { background-color: #2c3e50 !important; }
    .css-1d391kg .css-12w0qpk { color: white !important; }
    
    /* Button styling */
    .stButton>button {
        background-color: var(--primary-color);
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
        transition: background-color 0.3s;
    }
    .stButton>button:hover {
        background-color: var(--primary-hover);
    }
    .stButton>button:disabled {
        background-color: #cccccc;
    }
    
    /* Card styling */
    .data-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 20px;
        background-color: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Status indicators */
    .status-success { color: var(--success-color); }
    .status-warning { color: var(--warning-color); }
    .status-error { color: var(--error-color); }
    .status-info { color: var(--info-color); }
    
    /* User info in header */
    .user-info {
        position: fixed;
        top: 10px;
        right: 20px;
        background-color: rgba(255, 255, 255, 0.9);
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        z-index: 999;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Data preview styling */
    .data-preview {
        background-color: var(--preview-bg);
        border-left: 4px solid var(--preview-border);
        padding: 10px;
        margin: 10px 0;
        border-radius: 4px;
    }
    
    /* Loading spinner customization */
    .stSpinner > div {
        border-color: var(--primary-color) !important;
    }
    
    /* Download button styling */
    a.download-btn {
        background-color: var(--secondary-color) !important;
        color: white !important;
        padding: 8px 16px !important;
        border-radius: 4px !important;
        text-decoration: none !important;
        display: inline-block !important;
        margin: 5px 0 !important;
    }
    a.download-btn:hover {
        background-color: #1976D2 !important;
    }
    
    /* Section headers */
    h1, h2, h3, h4, h5, h6 {
        color: #2c3e50;
    }
    
    /* Info boxes */
    .stAlert {
        border-radius: 5px;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #f1f8e9;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- User Identification ---
with st.sidebar:
    st.header("👤 User Profile")
    user_name = st.text_input("Enter your name:", value=st.session_state.user_name)
    if st.button("Update Name"):
        st.session_state.user_name = user_name
        st.success(f"Name updated to: {user_name}")
    
    st.markdown("---")
    st.markdown("### 📋 Application Info")
    st.info("This application processes attendance data for All Is Well Hospital and Super Clinic according to organizational policies.")

# --- Display User Name in Header ---
st.markdown(f"<div class='user-info'>👤 {st.session_state.user_name}</div>", unsafe_allow_html=True)

# --- App Title ---
st.title("🏥 All Is Well Hospital & Super Clinic - Attendance Calculator")
st.markdown("---")

# --- Source Selection ---
st.header("📋 Select Data Source")
source_type = st.radio("Choose the organization type:", ("All Is Well Hospital", "All Is Well Super Clinic"))

# --- File Upload ---
st.header("📤 1. Upload Attendance File")
uploaded_file = st.file_uploader("Choose the Excel file", type=["xls", "xlsx"], key="file_uploader")

temp_file_path = None
if uploaded_file is not None:
    try:
        # Save uploaded file to a temporary location for pandas to read
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xls") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_file_path = tmp_file.name
        
        # Read file for preview
        try:
            df_preview = pd.read_excel(temp_file_path, header=None)
            rows, cols = df_preview.shape
            st.session_state.uploaded_file_info = {
                "name": uploaded_file.name,
                "rows": rows,
                "cols": cols,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.success(f"File uploaded successfully: {uploaded_file.name}")
        except Exception as e:
            st.error(f"Error reading file for preview: {e}")
            st.session_state.uploaded_file_info = None
            
    except Exception as e:
        st.error(f"Error saving uploaded file: {e}")
        temp_file_path = None
        st.session_state.uploaded_file_info = None

# --- Display File Preview Info ---
if st.session_state.uploaded_file_info:
    with st.expander("📊 File Preview Info", expanded=True):
        st.markdown(f"""
        <div class="data-preview">
            <b>File:</b> {st.session_state.uploaded_file_info['name']}<br>
            <b>Dimensions:</b> {st.session_state.uploaded_file_info['rows']} rows × {st.session_state.uploaded_file_info['cols']} columns<br>
            <b>Uploaded:</b> {st.session_state.uploaded_file_info['timestamp']}
        </div>
        """, unsafe_allow_html=True)

# --- Parsing Section ---
st.header("⚙️ 2. Parse and Store Data")
parse_col1, parse_col2 = st.columns([3, 1])
with parse_col1:
    parse_button = st.button("Parse Excel File", type="primary", disabled=not (temp_file_path and os.path.exists(temp_file_path)))
with parse_col2:
    if st.session_state.processed_data_info:
        st.markdown(f"<small class='status-success'>Last processed: {st.session_state.processed_data_info.get('timestamp', 'N/A')}</small>", unsafe_allow_html=True)

if parse_button:
    if temp_file_path and os.path.exists(temp_file_path):
        with st.spinner("Parsing Excel file..."):
            try:
                if source_type == "All Is Well Hospital":
                    if HOSPITAL_AVAILABLE:
                        hospital.init_db() # Ensure hospital DB tables exist
                        hospital.parse_excel_and_store(temp_file_path)
                        st.session_state.processed_data_info = {
                            "source": "Hospital",
                            "action": "Parsed",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.success("Hospital file parsed and data stored in 'attendance.db'!")
                    else:
                        st.error("Hospital processing module is not available.")
                else: # All Is Well Super Clinic
                    if SUPERCLINIC_AVAILABLE:
                        # The superclinic.py should handle its own DB init
                        superclinic.parse_superclinic_and_store(temp_file_path)
                        st.session_state.processed_data_info = {
                            "source": "Super Clinic",
                            "action": "Parsed",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.success("Super Clinic file parsed and data stored in 'superclinic.db'!")
                    else:
                        st.error("Super Clinic processing module is not available.")
            except Exception as e:
                st.error(f"An error occurred during parsing: {e}")
                # Optionally print traceback for debugging in development
                import traceback
                with st.expander("Show Error Details"):
                    st.text_area("Traceback", traceback.format_exc(), height=200)
    else:
        st.warning("Please upload a file first.")

# --- Leave Policy Application Section ---
st.header("📋 3. Apply Leave Policies")
st.info("This step calculates the final attendance status (P, WO, CL, Absent) based on IN/OUT times and organizational rules.")

# --- Determine DB connection details based on source ---
DB_NAME = None
ATTENDANCE_TABLE = None
EMPLOYEES_TABLE = None
apply_policy_func = None
apply_all_policy_func = None
get_summary_report_func = None
get_detailed_report_func = None

if source_type == "All Is Well Hospital":
    if HOSPITAL_AVAILABLE:
        DB_NAME = hospital.DB_NAME
        ATTENDANCE_TABLE = hospital.ATTENDANCE_TABLE
        EMPLOYEES_TABLE = hospital.EMPLOYEES_TABLE
        apply_policy_func = hospital.apply_leave_policy_for_month
        get_summary_report_func = hospital.get_summary_report
        get_detailed_report_func = hospital.get_detailed_report
elif source_type == "All Is Well Super Clinic":
    if SUPERCLINIC_AVAILABLE:
        DB_NAME = superclinic.DB_NAME
        ATTENDANCE_TABLE = superclinic.ATTENDANCE_TABLE
        EMPLOYEES_TABLE = superclinic.EMPLOYEES_TABLE
        apply_policy_func = superclinic.apply_appropriate_leave_policy
        apply_all_policy_func = superclinic.apply_leave_policy_for_all_employees_sc
        get_summary_report_func = superclinic.get_summary_report_sc
        get_detailed_report_func = superclinic.get_detailed_report_sc

# Check if necessary components are available for this section
if DB_NAME and ATTENDANCE_TABLE and apply_policy_func and get_summary_report_func and get_detailed_report_func:
    try:
        # Fetch list of months for policy application
        conn = sqlite3.connect(DB_NAME)
        months_df = pd.read_sql_query(
            f"SELECT DISTINCT month_year FROM {ATTENDANCE_TABLE} ORDER BY month_year",
            conn
        )
        conn.close()

        if not months_df.empty:
            months = months_df['month_year'].tolist()
            selected_month = st.selectbox("Select Month to Process", months)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Apply Policy for Selected Month", use_container_width=True):
                    if selected_month:
                        with st.spinner(f"Applying leave policy for all employees in {selected_month}..."):
                            try:
                                if source_type == "All Is Well Super Clinic" and apply_all_policy_func:
                                    apply_all_policy_func(selected_month)
                                else:
                                    # Fallback for Hospital or if function not available
                                    conn = sqlite3.connect(DB_NAME)
                                    c = conn.cursor()
                                    c.execute(f"""
                                        SELECT DISTINCT employee_code 
                                        FROM {ATTENDANCE_TABLE} 
                                        WHERE month_year = ?
                                    """, (selected_month,))
                                    employees = c.fetchall()
                                    conn.close()
                                    
                                    progress_bar = st.progress(0)
                                    status_text = st.empty()
                                    total = len(employees)
                                    errors = []
                                    
                                    for i, (emp_code,) in enumerate(employees):
                                        status_text.text(f"Processing {i+1}/{total}: {emp_code}")
                                        try:
                                            apply_policy_func(emp_code, selected_month)
                                        except Exception as e:
                                            errors.append(f"Error processing {emp_code}: {e}")
                                        progress_bar.progress((i + 1) / total)
                                    
                                    progress_bar.empty()
                                    status_text.empty()
                                    
                                    if errors:
                                        st.warning(f"Policies applied with {len(errors)} errors.")
                                        with st.expander("See Errors"):
                                            for err in errors[:5]:
                                                st.error(err)
                                
                                st.session_state.processed_data_info = {
                                    "source": source_type,
                                    "action": f"Applied policy for {selected_month}",
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                st.success(f"Leave policy successfully applied for all employees in {selected_month}!")
                            except Exception as e:
                                st.error(f"An error occurred while applying policy for {selected_month}: {e}")
                                import traceback
                                with st.expander("Show Error Details"):
                                    st.text_area("Traceback", traceback.format_exc(), height=200)
                    else:
                        st.warning("Please select a month.")

            with col2:
                if st.button("Apply Policy for ALL Months", type="primary", use_container_width=True):
                    with st.spinner("Applying leave policies for ALL months..."):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        total = len(months)
                        errors = []
                        
                        for i, month in enumerate(months):
                            status_text.text(f"Processing month {i+1}/{total}: {month}")
                            try:
                                if source_type == "All Is Well Super Clinic" and apply_all_policy_func:
                                    apply_all_policy_func(month)
                                else:
                                    # Fallback for Hospital or if function not available
                                    conn = sqlite3.connect(DB_NAME)
                                    c = conn.cursor()
                                    c.execute(f"""
                                        SELECT DISTINCT employee_code 
                                        FROM {ATTENDANCE_TABLE} 
                                        WHERE month_year = ?
                                    """, (month,))
                                    employees = c.fetchall()
                                    conn.close()
                                    
                                    for emp_code, in employees:
                                        apply_policy_func(emp_code, month)
                            except Exception as e:
                                errors.append(f"Error processing month {month}: {e}")
                            progress_bar.progress((i + 1) / total)
                        
                        progress_bar.empty()
                        status_text.empty()
                        if errors:
                            st.warning(f"Policies applied with {len(errors)} errors.")
                            with st.expander("See Errors"):
                                for err in errors[:5]:
                                    st.error(err)
                        else:
                            st.session_state.processed_data_info = {
                                "source": source_type,
                                "action": "Applied policies for ALL months",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            st.success("Leave policies applied successfully for ALL months!")

        else:
            st.info("No attendance data found in the database. Please parse an attendance file first.")

    except Exception as e:
        st.error(f"Error fetching months list: {e}")
        import traceback
        with st.expander("Show Error Details"):
            st.text_area("Traceback", traceback.format_exc(), height=200)

else:
    st.info("Please ensure the selected data source module is available and correctly configured.")

# --- Results Display Section ---
st.header("📈 4. View Results")

# --- Summary Report ---
summary_expander = st.expander("📋 Attendance Summary", expanded=False)
with summary_expander:
    if st.checkbox("Show Summary Report"):
        st.subheader("Attendance Summary")
        if get_summary_report_func:
            try:
                with st.spinner("Loading summary report..."):
                    df_summary = get_summary_report_func()
                    st.session_state.last_summary_df = df_summary
                    
                    if not df_summary.empty:
                        # Display data info
                        rows, cols = df_summary.shape
                        st.markdown(f"""
                        <div class="data-preview">
                            <b>Summary Report:</b> {rows} rows × {cols} columns
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Display data
                        st.dataframe(df_summary, use_container_width=True)
                        
                        # Download and copy options
                        col1, col2 = st.columns(2)
                        with col1:
                            csv_summary = df_summary.to_csv(index=False)
                            st.download_button(
                                label="📥 Download Summary CSV",
                                data=csv_summary,
                                file_name='attendance_summary.csv',
                                mime='text/csv',
                                key="download_summary"
                            )
                        with col2:
                            if st.button("📋 Copy Summary to Clipboard"):
                                st.session_state.clipboard_data = csv_summary
                                st.success("Summary data copied to clipboard!")
                                
                    else:
                        st.info("No summary data available. Please parse an attendance file and apply policies first.")
            except Exception as e:
                st.error(f"Error loading summary report: {e}")
                import traceback
                with st.expander("Show Error Details"):
                    st.text_area("Traceback", traceback.format_exc(), height=200)
        else:
            st.info("Summary report function is not available for the selected source.")

# --- Detailed Report ---
detail_expander = st.expander("🔍 Detailed Report for Employee", expanded=False)
with detail_expander:
    st.subheader("Detailed Report for Employee")
    if DB_NAME and ATTENDANCE_TABLE:
        try:
            # Get list of employees for selection
            conn = sqlite3.connect(DB_NAME)
            emp_list_df = pd.read_sql_query(f"SELECT DISTINCT employee_code FROM {ATTENDANCE_TABLE}", conn)
            conn.close()
            employee_codes = emp_list_df['employee_code'].tolist() if not emp_list_df.empty else []
        except Exception as e:
            st.error(f"Error fetching employees: {e}")
            employee_codes = []

        selected_emp_code = st.selectbox("Select Employee Code", employee_codes, key="detail_emp")

        # Get list of months for the selected employee
        try:
            if selected_emp_code:
                conn = sqlite3.connect(DB_NAME)
                month_list_df = pd.read_sql_query(
                    f"SELECT DISTINCT month_year FROM {ATTENDANCE_TABLE} WHERE employee_code = ? ORDER BY month_year",
                    conn, params=(selected_emp_code,)
                )
                conn.close()
                months = month_list_df['month_year'].tolist() if not month_list_df.empty else []
            else:
                months = []
        except Exception as e:
            st.error(f"Error fetching months: {e}")
            months = []

        selected_month = st.selectbox("Select Month", months, key="detail_month")

        if st.button("Load Detailed Report") and selected_emp_code and selected_month:
            if get_detailed_report_func:
                with st.spinner("Loading detailed report..."):
                    try:
                        df_detail = get_detailed_report_func(selected_emp_code, selected_month)
                        st.session_state.last_detail_df = df_detail
                        
                        if not df_detail.empty:
                            # Display data info
                            rows, cols = df_detail.shape
                            st.markdown(f"""
                            <div class="data-preview">
                                <b>Detailed Report for {selected_emp_code} in {selected_month}:</b> {rows} rows × {cols} columns
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Display data
                            st.dataframe(df_detail, use_container_width=True)
                            
                            # Download and copy options
                            col1, col2 = st.columns(2)
                            with col1:
                                csv_detail = df_detail.to_csv(index=False)
                                st.download_button(
                                    label="📥 Download Detailed CSV",
                                    data=csv_detail,
                                    file_name=f'attendance_detail_{selected_emp_code}_{selected_month.replace(" ", "_")}.csv',
                                    mime='text/csv',
                                    key="download_detail"
                                )
                            with col2:
                                if st.button("📋 Copy Details to Clipboard"):
                                    st.session_state.clipboard_data = csv_detail
                                    st.success("Detailed data copied to clipboard!")
                                    
                        else:
                            st.info("No detailed data found for the selected employee and month.")
                    except Exception as e:
                        st.error(f"Error loading detailed report: {e}")
                        import traceback
                        with st.expander("Show Error Details"):
                            st.text_area("Traceback", traceback.format_exc(), height=200)
            else:
                st.info("Detailed report function is not available for the selected source.")
    else:
        st.info("Database connection details are not available for the selected source.")

# --- Clipboard Functionality ---
if 'clipboard_data' in st.session_state:
    st.markdown("---")
    st.markdown("### 📋 Clipboard")
    with st.expander("View Copied Data"):
        st.text_area("Copied Data", st.session_state.clipboard_data, height=200, key="clipboard_view")
        if st.button("Clear Clipboard"):
            del st.session_state.clipboard_data
            st.success("Clipboard cleared!")

# --- Footer ---
st.markdown("---")
st.caption(f"__authenticated user: {st.session_state.user_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

# --- Cleanup Temporary File ---
# It's good practice to clean up the temp file, although Streamlit might handle this
# on rerun. We can try to remove it at the end of the script run.
if temp_file_path and os.path.exists(temp_file_path):
    try:
        os.unlink(temp_file_path)
    except:
        pass # Ignore errors in cleanup
    
# Streamlit runs the script from top to bottom; no need for a main() function call.