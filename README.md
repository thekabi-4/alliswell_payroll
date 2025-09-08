# 🏥 All Is Well Attendance System

A complete **Attendance & Payroll Management System** for **All Is Well Hospital** and **Super Clinic**, built with **Python, Streamlit, and SQLite**. It enables uploading, parsing, validating, and processing attendance sheets, applying hospital-specific leave policies, and generating payroll-ready reports.

---

## ✨ Features

* 📤 **Upload Attendance Files** (Excel)
* ⚙️ **Parse Data** into SQLite for structured processing
* 📋 **Apply Leave Policies**

  * ✅ 9-day attendance rule for eligibility
  * ✅ Weekly offs & Casual Leaves (CL) management
  * ✅ Consultant leave policies (pre & post-2023 joining)
* 📊 **Reports**

  * Attendance summary per employee
  * Detailed month-wise breakdown
  * Export to CSV
* 🖥 **Streamlit Frontend** with modern UI
* 🗄 **SQLite Database** backend with schema for employees & attendance tracking

---

## 🚀 Tech Stack

* **Frontend**: Streamlit
* **Backend**: Python 3.11+
* **Database**: SQLite
* **Packaging**: PyInstaller / auto-py-to-exe

---

## 📦 Installation

### 1️⃣ Clone Repository

```bash
git clone https://github.com/thekabi-4/alliswell_payroll.git
cd alliswell_payroll
```

### 2️⃣ Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate  # macOS/Linux
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## ▶️ Usage

### Run as a Streamlit App

```bash
streamlit run app.py
```

### OR

### Run as a Streamlit App

```bash
alliswellpayroll.streamlit.app
```

* Select `app.py`
* Choose **One Directory** or **One File**
* Add DB & assets under *Additional Files*
* Build ✅

---

## 📂 Project Structure

```
alliswell_payroll/
│── app.py                 # Streamlit frontend
│── hospital.py            # Hospital leave policy logic
│── superclinic.py         # Super Clinic leave policy logic
│── db/attendance.db       # SQLite database (generated)
│── requirements.txt       # Dependencies
│── README.md              # Documentation
└── assets/                # Icons, images, etc.
```

---

## 📝 Leave Policy Highlights

* **Hospital Staff**: Eligible for paid weekly off only after 9 days attendance.
* **Consultants**:

  * Joined **before 2023-01-01** → 13 CL per year.
  * Joined **after 2023-01-01** → 12 CL per year.
  * CL allocated in **two halves**: Jan–Jun & Jul–Dec.

---

## 📊 Reports

* **Summary Report**: Total present, absent, leaves, weekly offs.
* **Detailed Report**: Day-wise attendance with applied leave policies.
* **CSV Export** for payroll processing.

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you’d like to improve.

---

## 📜 License

This project is licensed under the Proprietary License.

---

## 👨‍💻 Author

**Kabilesh** – [GitHub](https://github.com/thekabi-4)

