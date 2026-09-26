from pathlib import Path
from datetime import date, datetime, timedelta
from html import escape
import sqlite3
import re

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Job Application Tracker",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

APPLICATIONS_DIR = BASE_DIR / "applications"
APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = APPLICATIONS_DIR / "applications.db"


# ============================================================
# CONSTANTS
# ============================================================

STATUSES = [
    "Saved",
    "Applied",
    "Screening",
    "Interview",
    "Offer",
    "Rejected",
    "Withdrawn",
]

WORK_MODES = [
    "Remote",
    "Hybrid",
    "On-site",
    "Flexible",
    "Not Specified",
]

JOB_TYPES = [
    "Full-time",
    "Part-time",
    "Internship",
    "Contract",
    "Temporary",
    "Not Specified",
]

SOURCES = [
    "LinkedIn",
    "Naukri",
    "Indeed",
    "Company Website",
    "Referral",
    "Consultant",
    "College/University",
    "Other",
]


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            location TEXT DEFAULT '',
            work_mode TEXT DEFAULT 'Not Specified',
            job_type TEXT DEFAULT 'Full-time',
            date_applied TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Applied',
            source TEXT DEFAULT 'Other',
            job_url TEXT DEFAULT '',
            salary TEXT DEFAULT '',
            recruiter_name TEXT DEFAULT '',
            recruiter_email TEXT DEFAULT '',
            follow_up_date TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        )
        """
    )

    cursor.execute("PRAGMA table_info(applications)")
    existing_columns = {row["name"] for row in cursor.fetchall()}

    required_columns = {
        "location": "TEXT DEFAULT ''",
        "work_mode": "TEXT DEFAULT 'Not Specified'",
        "job_type": "TEXT DEFAULT 'Full-time'",
        "source": "TEXT DEFAULT 'Other'",
        "job_url": "TEXT DEFAULT ''",
        "salary": "TEXT DEFAULT ''",
        "recruiter_name": "TEXT DEFAULT ''",
        "recruiter_email": "TEXT DEFAULT ''",
        "follow_up_date": "TEXT DEFAULT ''",
        "notes": "TEXT DEFAULT ''",
        "created_at": "TEXT DEFAULT ''",
    }

    for column, definition in required_columns.items():
        if column not in existing_columns:
            cursor.execute(
                f"ALTER TABLE applications ADD COLUMN {column} {definition}"
            )

    conn.commit()
    conn.close()


initialize_database()


# ============================================================
# DATABASE CRUD
# ============================================================

def add_application(data):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO applications (
            company, role, location, work_mode, job_type,
            date_applied, status, source, job_url, salary,
            recruiter_name, recruiter_email,
            follow_up_date, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["company"],
            data["role"],
            data["location"],
            data["work_mode"],
            data["job_type"],
            data["date_applied"],
            data["status"],
            data["source"],
            data["job_url"],
            data["salary"],
            data["recruiter_name"],
            data["recruiter_email"],
            data["follow_up_date"],
            data["notes"],
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def update_application(application_id, data):
    conn = get_connection()
    conn.execute(
        """
        UPDATE applications
        SET
            company = ?, role = ?, location = ?, work_mode = ?,
            job_type = ?, date_applied = ?, status = ?, source = ?,
            job_url = ?, salary = ?, 
            recruiter_name = ?, recruiter_email = ?,
            follow_up_date = ?, notes = ?
        WHERE id = ?
        """,
        (
            data["company"],
            data["role"],
            data["location"],
            data["work_mode"],
            data["job_type"],
            data["date_applied"],
            data["status"],
            data["source"],
            data["job_url"],
            data["salary"],
            data["recruiter_name"],
            data["recruiter_email"],
            data["follow_up_date"],
            data["notes"],
            application_id,
        ),
    )
    conn.commit()
    conn.close()


def delete_application(application_id):
    conn = get_connection()
    conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
    conn.commit()
    conn.close()


def get_applications():
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT *
        FROM applications
        ORDER BY date_applied DESC, id DESC
        """,
        conn,
    )
    conn.close()
    return df


# ============================================================
# HELPERS
# ============================================================

def safe_date(value, default=None):
    if default is None:
        default = date.today()
    if not value:
        return default
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return default


def format_date(value):
    if not value:
        return ""
    parsed = safe_date(value, None)
    if parsed:
        return parsed.strftime("%d %b %Y")
    return str(value)


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def md(text, **kwargs):
    lines = [line.strip() for line in str(text).splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    st.markdown(cleaned, **kwargs)


def status_badge(status):
    status_class = status.lower().replace(" ", "-")
    return f"""
    <span class="status-badge status-{escape(status_class)}">
        {escape(status)}
    </span>
    """


# ============================================================
# LINKEDIN / JOB TEXT EXTRACTION
# ============================================================

def extract_from_linkedin_url(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = soup.get_text("\n", strip=True)
        return {"title": title, "text": text}
    except Exception as error:
        return {"error": str(error)}


def extract_from_pasted_text(text):
    result = {
        "company": "",
        "role": "",
        "location": "",
        "job_url": "",
        "salary": "",
        "notes": text.strip(),
    }

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        result["role"] = lines[0][:150]

    role_patterns = [
        r"(?:role|position|job title)\s*[:\-]\s*(.+)",
        r"(?:designation)\s*[:\-]\s*(.+)",
    ]
    for line in lines:
        for pattern in role_patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                result["role"] = match.group(1).strip()
                break

    company_patterns = [r"(?:company|organization|employer)\s*[:\-]\s*(.+)"]
    for line in lines:
        for pattern in company_patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                result["company"] = match.group(1).strip()
                break

    location_patterns = [r"(?:location|place)\s*[:\-]\s*(.+)"]
    for line in lines:
        for pattern in location_patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                result["location"] = match.group(1).strip()
                break

    return result


# ============================================================
# GLOBAL CSS - PREMIUM UI UPGRADES
# ============================================================

md(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1450px;
    }

    .stApp {
        background-color: #f8fafc;
    }

    /* ---------- SIDEBAR ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #020617 0%, #0f172a 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.05);
        min-width: 280px !important;
    }

    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 2rem;
    }

    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #94a3b8 !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 8px;
        padding: 0 10px;
    }

    /* HIDE THE DEFAULT WHITE RADIO CIRCLES */
    section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        border-radius: 8px !important;
        padding: 10px 14px !important;
        margin: 0 !important;
        transition: all 0.2s ease;
        background: transparent !important;
        border: 1px solid transparent;
        display: flex;
        align-items: center;
        width: 100%;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background: rgba(255,255,255,0.05) !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label p {
        color: #cbd5e1 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        letter-spacing: 0.3px;
        margin: 0 !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background: rgba(99,102,241,0.15) !important;
        border: 1px solid rgba(99,102,241,0.3);
        box-shadow: inset 0 0 12px rgba(99,102,241,0.1);
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    /* ---------- BRAND ---------- */
    .brand-box {
        padding: 0px 14px 30px 14px;
    }

    .brand-title {
        color: white;
        font-size: 26px;
        font-weight: 800;
        margin-bottom: 2px;
        letter-spacing: -0.5px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .brand-subtitle {
        color: #64748b;
        font-size: 13px;
        font-weight: 500;
    }

    /* ---------- HERO ---------- */
    .hero-title {
        font-size: 38px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 6px;
        letter-spacing: -1px;
    }

    .hero-subtitle {
        color: #64748b;
        font-size: 16px;
        margin-bottom: 32px;
        font-weight: 400;
    }

    /* ---------- KPI CARDS ---------- */
    .kpi-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 20px;
        padding: 24px;
        min-height: 135px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        transition: all 0.3s ease;
    }

    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
    }

    .kpi-label {
        color: #64748b;
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }

    .kpi-value {
        color: #0f172a;
        font-size: 36px;
        font-weight: 800;
        letter-spacing: -1px;
    }

    .kpi-accent {
        position: absolute;
        left: 0;
        bottom: 0;
        height: 4px;
        width: 100%;
        opacity: 0.8;
    }

    .kpi-accent.blue { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
    .kpi-accent.violet { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }
    .kpi-accent.amber { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
    .kpi-accent.emerald { background: linear-gradient(90deg, #10b981, #34d399); }
    .kpi-accent.rose { background: linear-gradient(90deg, #f43f5e, #fb7185); }

    /* ---------- SECTION HEADERS ---------- */
    .section-title {
        font-size: 22px;
        font-weight: 700;
        color: #0f172a;
        margin-top: 32px;
        margin-bottom: 4px;
        letter-spacing: -0.5px;
    }

    .section-subtitle {
        color: #64748b;
        font-size: 14px;
        margin-bottom: 20px;
    }

    /* ---------- EMPTY STATE ---------- */
    .empty-state {
        background: #f8fafc;
        border: 2px dashed #cbd5e1;
        border-radius: 16px;
        padding: 40px;
        text-align: center;
        color: #64748b;
        margin-top: 10px;
        transition: all 0.2s ease;
    }
    
    .empty-state:hover {
        border-color: #94a3b8;
        background: white;
    }

    .empty-state-icon {
        font-size: 36px;
        margin-bottom: 12px;
        opacity: 0.8;
    }

    /* ---------- APPLICATION CARDS ---------- */
    .application-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        transition: all 0.2s ease;
    }

    .application-card:hover {
        border-color: #cbd5e1;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        transform: translateY(-2px);
    }

    .application-company {
        color: #0f172a;
        font-size: 18px;
        font-weight: 700;
        letter-spacing: -0.3px;
    }

    .application-role {
        color: #475569;
        font-size: 14px;
        margin-top: 4px;
        font-weight: 500;
    }

    .application-meta {
        color: #64748b;
        font-size: 12px;
        margin-top: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* ---------- BADGES ---------- */
    .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .status-saved { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
    .status-applied { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
    .status-screening { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }
    .status-interview { background: #fffbeb; color: #d97706; border: 1px solid #fde68a; }
    .status-offer { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
    .status-rejected { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
    .status-withdrawn { background: #fafafa; color: #737373; border: 1px solid #e5e5e5; }

    /* ---------- KANBAN PIPELINE ---------- */
    .pipeline-column {
        background: #f1f5f9;
        border-radius: 12px;
        padding: 16px;
        min-height: 400px;
        border: 1px solid #e2e8f0;
    }

    .pipeline-header {
        color: #334155;
        font-weight: 700;
        font-size: 14px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .pipeline-count {
        background: #e2e8f0;
        color: #475569;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 11px;
    }

    .pipeline-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px;
        margin-bottom: 10px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        border-left: 4px solid #cbd5e1;
    }
    
    .pipeline-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    
    .pipeline-card.Applied { border-left-color: #3b82f6; }
    .pipeline-card.Screening { border-left-color: #8b5cf6; }
    .pipeline-card.Interview { border-left-color: #f59e0b; }
    .pipeline-card.Offer { border-left-color: #10b981; }

    .pipeline-company {
        font-weight: 700;
        color: #0f172a;
        font-size: 14px;
    }

    .pipeline-role {
        color: #64748b;
        font-size: 12px;
        margin-top: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* ---------- FOOTER ---------- */
    .app-footer {
        text-align: center;
        color: #94a3b8;
        font-size: 12px;
        margin-top: 60px;
        padding-top: 24px;
        border-top: 1px solid #e2e8f0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    md(
        """
        <div class="brand-box">
            <div class="brand-title">💼 JobTracker</div>
            <div class="brand-subtitle">Personal Job Search OS</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigation",
        [
            "Overview",
            "Applications",
            "Pipeline",
            "Follow-ups",
            "Analytics",
        ],
        label_visibility="collapsed",
    )


# ============================================================
# COMMON DATA
# ============================================================

df = get_applications()

if "editing_id" not in st.session_state:
    st.session_state.editing_id = None


# ============================================================
# APPLICATION FORM
# ============================================================

def application_form(existing=None, form_key="application_form"):
    is_edit = existing is not None and "id" in (existing or {})

    if existing is None:
        existing = {}

    default_follow_up = safe_date(
        existing.get("follow_up_date"),
        date.today() + timedelta(days=7),
    )
    default_date = safe_date(existing.get("date_applied"), date.today())

    md(
        """
        <div class="section-title">Add Application</div>
        <div class="section-subtitle">
            Keep every job opportunity organized in one place.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form(form_key, border=True):
        col1, col2 = st.columns(2)

        with col1:
            company = st.text_input("Company *", value=existing.get("company", ""))
            role = st.text_input("Role *", value=existing.get("role", ""))
            location = st.text_input("Location", value=existing.get("location", ""))
            job_url = st.text_input("Job URL", value=existing.get("job_url", ""))
            salary = st.text_input("Salary / CTC", value=existing.get("salary", ""))
            recruiter_name = st.text_input(
                "Recruiter Name", value=existing.get("recruiter_name", "")
            )
            recruiter_email = st.text_input(
                "Recruiter Email", value=existing.get("recruiter_email", "")
            )

        with col2:
            date_applied = st.date_input("Date Applied", value=default_date)

            current_status = existing.get("status", "Applied")
            status_index = (
                STATUSES.index(current_status)
                if current_status in STATUSES
                else 1
            )
            status = st.selectbox("Status", STATUSES, index=status_index)

            current_work_mode = existing.get("work_mode", "Not Specified")
            work_mode_index = (
                WORK_MODES.index(current_work_mode)
                if current_work_mode in WORK_MODES
                else len(WORK_MODES) - 1
            )
            work_mode = st.selectbox("Work Mode", WORK_MODES, index=work_mode_index)

            current_job_type = existing.get("job_type", "Full-time")
            job_type_index = (
                JOB_TYPES.index(current_job_type)
                if current_job_type in JOB_TYPES
                else 0
            )
            job_type = st.selectbox("Job Type", JOB_TYPES, index=job_type_index)

            current_source = existing.get("source", "Other")
            source_index = (
                SOURCES.index(current_source)
                if current_source in SOURCES
                else len(SOURCES) - 1
            )
            source = st.selectbox("Source", SOURCES, index=source_index)

            follow_up_date = st.date_input("Follow-up Date", value=default_follow_up)

        notes = st.text_area(
            "Notes",
            value=existing.get("notes", ""),
            height=120,
            placeholder="Interview notes, job requirements, contact information, etc.",
        )

        button_label = "Update Application" if is_edit else "Add Application"
        submitted = st.form_submit_button(
            button_label, type="primary", use_container_width=True
        )

        if submitted:
            company = normalize_text(company)
            role = normalize_text(role)

            if not company:
                st.error("Company name is required.")
                return
            if not role:
                st.error("Job role is required.")
                return

            data = {
                "company": company,
                "role": role,
                "location": normalize_text(location),
                "work_mode": work_mode,
                "job_type": job_type,
                "date_applied": date_applied.isoformat(),
                "status": status,
                "source": source,
                "job_url": normalize_text(job_url),
                "salary": normalize_text(salary),
                "recruiter_name": normalize_text(recruiter_name),
                "recruiter_email": normalize_text(recruiter_email),
                "follow_up_date": follow_up_date.isoformat(),
                "notes": normalize_text(notes),
            }

            if is_edit:
                update_application(existing["id"], data)
                st.session_state.editing_id = None
                st.success("Application updated successfully.")
            else:
                add_application(data)
                st.success("Application added successfully.")

            st.rerun()


# ============================================================
# OVERVIEW
# ============================================================

def show_overview():
    total = len(df)

    active_statuses = ["Applied", "Screening", "Interview"]
    active = int(df["status"].isin(active_statuses).sum()) if not df.empty else 0
    interviews = int((df["status"] == "Interview").sum()) if not df.empty else 0
    offers = int((df["status"] == "Offer").sum()) if not df.empty else 0
    responses = (
        int(df["status"].isin(["Screening", "Interview", "Offer", "Rejected"]).sum())
        if not df.empty else 0
    )
    response_rate = round((responses / total) * 100) if total else 0

    # 1. HERO
    md(
        """
        <div class="hero-title">Job Application Tracker 👋</div>
        <div class="hero-subtitle">
            Your personal command center for tracking applications, interviews, and offers.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. KPI CARDS
    cards = [
        ("Total Apps", total, "blue"),
        ("Active Pipeline", active, "violet"),
        ("Interviews", interviews, "amber"),
        ("Offers", offers, "emerald"),
        ("Response Rate", f"{response_rate}%", "rose"),
    ]

    columns = st.columns(5)

    for column, (label, value, accent) in zip(columns, cards):
        with column:
            md(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">{escape(label)}</div>
                    <div class="kpi-value">{escape(str(value))}</div>
                    <div class="kpi-accent {escape(accent)}"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("") # Spacer

    # 3. STATUS + RECENT
    col1, spacer, col2 = st.columns([1, 0.1, 1.2])

    with col1:
        md(
            """
            <div class="section-title">🎯 Status Breakdown</div>
            <div class="section-subtitle">Distribution by stage</div>
            """,
            unsafe_allow_html=True,
        )
        if df.empty:
            md(
                """
                <div class="empty-state">No data yet.</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            status_df = df["status"].value_counts().reset_index()
            status_df.columns = ["status", "count"]
            fig = px.pie(status_df, names="status", values="count", hole=0.6)
            fig.update_traces(hoverinfo='label+percent', textinfo='none')
            fig.update_layout(
                height=350, 
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        md(
            """
            <div class="section-title">Recent Applications</div>
            <div class="section-subtitle">Your latest job applications</div>
            """,
            unsafe_allow_html=True,
        )
        if df.empty:
            md(
                """
                <div class="empty-state">
                    <div class="empty-state-icon">📋</div>
                    <div>
                        No applications yet.<br/>
                        Head to <b>Applications</b> to add your first one.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            recent = df.head(4)
            for _, row in recent.iterrows():
                md(
                    f"""
                    <div class="application-card">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <div class="application-company">{escape(str(row["company"]))}</div>
                                <div class="application-role">{escape(str(row["role"]))}</div>
                            </div>
                            <div>{status_badge(str(row["status"]))}</div>
                        </div>
                        <div class="application-meta">
                            📅 {escape(format_date(row["date_applied"]))}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # 4. APPLICATION ACTIVITY (bottom)
    md(
        """
        <div class="section-title">📈 Application Activity</div>
        <div class="section-subtitle">Daily applications with a smoothed momentum trend line</div>
        """,
        unsafe_allow_html=True,
    )

    if df.empty:
        md(
            """
            <div class="empty-state">Add applications to see activity.</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        activity = (
            df.groupby("date_applied")
            .size()
            .reset_index(name="applications")
        )
        activity["date_applied"] = pd.to_datetime(activity["date_applied"])
        activity = activity.sort_values("date_applied")

        if len(activity) > 0:
            full_range = pd.date_range(
                start=activity["date_applied"].min(),
                end=activity["date_applied"].max(),
                freq="D",
            )
            activity = (
                activity.set_index("date_applied")
                .reindex(full_range, fill_value=0)
                .rename_axis("date_applied")
                .reset_index()
            )
            
            # Use Exponential Moving Average (EMA) instead of a rolling mean for sparse data.
            # This ensures smooth transitions and prevents the jagged edge drop-offs back to 0.
            activity["trend"] = activity["applications"].ewm(span=14, adjust=False).mean()

        fig = px.area(
            activity,
            x="date_applied",
            y="applications",
            labels={"date_applied": "Date", "applications": "Applications"},
        )
        
        # Keep the area chart linear for accurate daily hit tracking
        fig.update_traces(
            line_color="#4f46e5",
            fillcolor="rgba(79, 70, 229, 0.1)",
            line_width=2,
            name="Applications"
        )
        
        # Add the EMA trend line with a spline shape for a visually smooth curve
        fig.add_scatter(
            x=activity["date_applied"],
            y=activity["trend"],
            mode="lines",
            name="14-Day Momentum",
            line=dict(color="#f43f5e", width=2.5, shape="spline", smoothing=1.3),
            hoverinfo="y+name"
        )
        
        fig.update_layout(
            height=320,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title=None,
            yaxis_title=None,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#e2e8f0", rangemode="tozero", zerolinecolor="#cbd5e1"),
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# APPLICATIONS
# ============================================================

def show_applications():
    md(
        """
        <div class="hero-title">Applications</div>
        <div class="hero-subtitle">
            Add, search, update, and manage your job applications.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Import
    with st.expander("⚡ Import from LinkedIn / Job Description"):
        import_tab1, import_tab2 = st.tabs(["LinkedIn URL", "Paste Job Description"])

        with import_tab1:
            linkedin_url = st.text_input(
                "LinkedIn Job URL",
                placeholder="https://www.linkedin.com/jobs/view/...",
            )
            if st.button("Extract Job Details", key="linkedin_extract"):
                if not linkedin_url.strip():
                    st.warning("Please enter a LinkedIn job URL.")
                else:
                    with st.spinner("Trying to extract job details..."):
                        result = extract_from_linkedin_url(linkedin_url.strip())
                    if "error" in result:
                        st.error(
                            "Could not extract the job details. "
                            "LinkedIn may block automated requests."
                        )
                    else:
                        st.session_state["linkedin_prefill"] = {
                            "role": result.get("title", ""),
                            "job_url": linkedin_url.strip(),
                            "notes": result.get("text", "")[:5000],
                            "source": "LinkedIn",
                        }
                        st.success("Details extracted. Review them in the form below.")

        with import_tab2:
            pasted_text = st.text_area(
                "Paste job description",
                height=220,
                placeholder="Paste the complete job description here...",
            )
            if st.button("Extract Details", key="paste_extract"):
                if not pasted_text.strip():
                    st.warning("Please paste a job description.")
                else:
                    extracted = extract_from_pasted_text(pasted_text)
                    extracted["source"] = "LinkedIn"
                    st.session_state["linkedin_prefill"] = extracted
                    st.success("Details extracted. Review them in the form below.")

    # Form
    prefill = st.session_state.pop("linkedin_prefill", None)
    application_form(existing=prefill, form_key="new_application_form")

    st.divider()

    # Filters + Table
    md(
        """
        <div class="section-title">Application Database</div>
        <div class="section-subtitle">
            Search and filter through your complete history.
        </div>
        """,
        unsafe_allow_html=True,
    )

    filter_col1, filter_col2 = st.columns([3, 1])

    with filter_col1:
        search = st.text_input(
            "Search",
            placeholder="Search company, role, or location...",
            label_visibility="collapsed",
        )
    with filter_col2:
        status_filter = st.selectbox(
            "Status", ["All"] + STATUSES, label_visibility="collapsed"
        )

    filtered = df.copy()

    if search.strip():
        search_lower = search.lower()
        mask = (
            filtered["company"].fillna("").str.lower().str.contains(search_lower, regex=False)
            | filtered["role"].fillna("").str.lower().str.contains(search_lower, regex=False)
            | filtered["location"].fillna("").str.lower().str.contains(search_lower, regex=False)
        )
        filtered = filtered[mask]

    if status_filter != "All":
        filtered = filtered[filtered["status"] == status_filter]

    st.caption(f"Showing {len(filtered)} application(s)")

    if filtered.empty:
        md(
            """
            <div class="empty-state">
                <div class="empty-state-icon">📋</div>
                No applications match your filters.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        display_df = filtered[
            ["company", "role", "location", "date_applied", "status", "source"]
        ].copy()
        display_df["date_applied"] = display_df["date_applied"].apply(format_date)
        display_df.columns = [
            "Company", "Role", "Location", "Date Applied", "Status", "Source"
        ]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.write("")
        md("### Quick Actions")
        
        col_select, col_edit, col_del = st.columns([2, 1, 1])
        with col_select:
            selected_id = st.selectbox(
                "Select application to manage",
                filtered["id"].tolist(),
                format_func=lambda x: (
                    f"#{x} — "
                    f"{df.loc[df['id'] == x, 'company'].iloc[0]} — "
                    f"{df.loc[df['id'] == x, 'role'].iloc[0]}"
                ),
                label_visibility="collapsed"
            )

        with col_edit:
            if st.button("✏️ Edit App", use_container_width=True):
                st.session_state.editing_id = selected_id

        with col_del:
            if st.button("🗑️ Delete App", use_container_width=True):
                delete_application(selected_id)
                if st.session_state.editing_id == selected_id:
                    st.session_state.editing_id = None
                st.success("Application deleted.")
                st.rerun()

        if st.session_state.editing_id is not None:
            edit_match = df[df["id"] == st.session_state.editing_id]
            if edit_match.empty:
                st.session_state.editing_id = None
            else:
                edit_row = edit_match.iloc[0].to_dict()
                st.write("")
                application_form(
                    existing=edit_row,
                    form_key=f"edit_form_{st.session_state.editing_id}",
                )
                if st.button("Cancel Edit", type="secondary"):
                    st.session_state.editing_id = None
                    st.rerun()

    # Export
    st.divider()
    if not df.empty:
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Export Data as CSV",
            data=csv_data,
            file_name="job_applications.csv",
            mime="text/csv",
        )


# ============================================================
# PIPELINE
# ============================================================

def show_pipeline():
    md(
        """
        <div class="hero-title">Kanban Pipeline</div>
        <div class="hero-subtitle">
            Visualize where every application currently stands.
        </div>
        """,
        unsafe_allow_html=True,
    )

    pipeline_statuses = [
        "Saved", "Applied", "Screening", "Interview", "Offer", "Rejected"
    ]
    columns = st.columns(len(pipeline_statuses))

    for column, status in zip(columns, pipeline_statuses):
        with column:
            status_df = (
                df[df["status"] == status] if not df.empty else pd.DataFrame()
            )
            count = len(status_df)
            
            md(
                f"""
                <div class="pipeline-column">
                    <div class="pipeline-header">
                        <span>{escape(status)}</span>
                        <span class="pipeline-count">{count}</span>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            
            if status_df.empty:
                md(
                    """
                    <div style="text-align: center; padding: 20px 0; color: #94a3b8; font-size: 13px;">
                        Empty
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            else:
                for _, row in status_df.iterrows():
                    md(
                        f"""
                        <div class="pipeline-card {escape(status)}">
                            <div class="pipeline-company">{escape(str(row["company"]))}</div>
                            <div class="pipeline-role">{escape(str(row["role"]))}</div>
                            <div style="margin-top: 8px; font-size: 11px; color: #94a3b8;">
                                {escape(str(row["location"])) or 'No location'}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            md("</div>", unsafe_allow_html=True)


# ============================================================
# FOLLOW-UPS
# ============================================================

def show_followups():
    md(
        """
        <div class="hero-title">Action Center</div>
        <div class="hero-subtitle">
            Keep track of recruiters, pending replies, and follow-up dates.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df.empty:
        md(
            """
            <div class="empty-state">
                <div class="empty-state-icon">📅</div>
                No follow-ups yet.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    today = date.today()
    working_df = df.copy()
    working_df["followup_date"] = pd.to_datetime(
        working_df["follow_up_date"], errors="coerce"
    ).dt.date

    overdue = working_df[
        working_df["followup_date"].notna()
        & (working_df["followup_date"] < today)
        & ~working_df["status"].isin(["Offer", "Rejected", "Withdrawn"])
    ]
    today_df = working_df[working_df["followup_date"] == today]
    upcoming = working_df[
        working_df["followup_date"].notna()
        & (working_df["followup_date"] > today)
        & (working_df["followup_date"] <= today + timedelta(days=7))
    ]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("🔴 Overdue", len(overdue))
    with c2:
        st.metric("🟡 Due Today", len(today_df))
    with c3:
        st.metric("🟢 Next 7 Days", len(upcoming))
    
    st.write("")

    def render_followup_section(title, data):
        md(
            f"""
            <div class="section-title" style="font-size: 18px; margin-top: 10px;">{escape(title)}</div>
            """,
            unsafe_allow_html=True,
        )
        if data.empty:
            st.info("Nothing in this queue.")
            return
        for _, row in data.iterrows():
            recruiter = (
                str(row["recruiter_name"])
                if row["recruiter_name"]
                else "Recruiter not specified"
            )
            md(
                f"""
                <div class="application-card" style="border-left: 4px solid #94a3b8;">
                    <div class="application-company">{escape(str(row["company"]))}</div>
                    <div class="application-role">{escape(str(row["role"]))}</div>
                    <div class="application-meta">
                        📅 <b>{escape(format_date(row["follow_up_date"]))}</b>
                        &nbsp; · &nbsp; 👤 {escape(recruiter)}
                        &nbsp; · &nbsp; {status_badge(str(row["status"]))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    col1, col2 = st.columns(2)
    with col1:
        render_followup_section("Needs Attention (Overdue)", overdue)
        render_followup_section("Due Today", today_df)
    with col2:
        render_followup_section("Upcoming (Next 7 Days)", upcoming)


# ============================================================
# ANALYTICS
# ============================================================

def show_analytics():
    md(
        """
        <div class="hero-title">Insights</div>
        <div class="hero-subtitle">
            Understand your job search activity and pipeline effectiveness.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df.empty:
        md(
            """
            <div class="empty-state">
                <div class="empty-state-icon">📊</div>
                Add applications to generate analytics.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    status_counts = df["status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Applications"]

    source_counts = df["source"].value_counts().reset_index()
    source_counts.columns = ["Source", "Applications"]

    mode_counts = df["work_mode"].value_counts().reset_index()
    mode_counts.columns = ["Work Mode", "Applications"]

    # Reusable chart layout settings
    chart_layout = dict(
        height=320, 
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(gridcolor="#e2e8f0"),
        xaxis=dict(showgrid=False)
    )

    c1, c2 = st.columns(2)

    with c1:
        with st.container(border=True):
            st.subheader("Applications by Status")
            fig = px.bar(status_counts, x="Status", y="Applications", color="Status", 
                         color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(**chart_layout, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        with st.container(border=True):
            st.subheader("Sourcing Channels")
            fig = px.bar(source_counts, x="Source", y="Applications", color_discrete_sequence=["#6366f1"])
            fig.update_layout(**chart_layout)
            st.plotly_chart(fig, use_container_width=True)
            
    st.write("")

    c3, c4, c5 = st.columns([1, 2, 1])

    with c4:
        with st.container(border=True):
            st.subheader("Work Mode Preferences")
            fig = px.pie(mode_counts, names="Work Mode", values="Applications", hole=0.6,
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), 
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE ROUTING
# ============================================================

if page == "Overview":
    show_overview()
elif page == "Applications":
    show_applications()
elif page == "Pipeline":
    show_pipeline()
elif page == "Follow-ups":
    show_followups()
elif page == "Analytics":
    show_analytics()


# ============================================================
# FOOTER
# ============================================================

md(
    """
    <div class="app-footer">
        JobTracker OS · Built on Streamlit · Your data stays local
    </div>
    """,
    unsafe_allow_html=True,
)