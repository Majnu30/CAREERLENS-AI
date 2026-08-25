import io
import os
import csv
import json
import re
import random
import uuid
import hashlib
import html
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
ADMIN_PIN = os.getenv("ADMIN_PIN", "1234")

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# LOGGING & STYLES
# ============================================================

def log_event(event_type: str, username: str, rating: str = "N/A", details: str = ""):
    file_exists = os.path.isfile(ANALYTICS_FILE)
    try:
        with open(ANALYTICS_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Event", "Username", "Rating", "Details"])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                event_type,
                username,
                rating,
                details
            ])
    except Exception:
        pass

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

:root {
    --bg-page: #f8fafc;
    --navy-sidebar: #0a1128;
    --card-bg: #ffffff;
    --border-subtle: #e2e8f0;
    --text-navy: #0f172a;
    --text-muted: #64748b;
    --blue-primary: #2563eb;
    --purple-accent: #7c3aed;
    --emerald-accent: #059669;
}

.stApp {
    background-color: var(--bg-page) !important;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
    color: var(--text-navy) !important;
}

.block-container {
    max-width: 1420px;
    padding: 24px 38px 40px !important;
}

[data-testid="stSidebar"] {
    background-color: var(--navy-sidebar) !important;
}

[data-testid="stSidebar"] * {
    color: #f8fafc !important;
}

.sidebar-brand-box {
    background: #ffffff;
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 12px;
}

.sidebar-brand-box * {
    color: #0a1128 !important;
}

.stButton > button {
    border-radius: 10px !important;
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    border: none !important;
    padding: 0.6rem 1.4rem !important;
}

.stButton > button * {
    color: #ffffff !important;
}

.header-banner {
    background: linear-gradient(135deg, #091224 0%, #0d1b38 60%, #1e1b4b 100%);
    border-radius: 20px;
    padding: 24px 30px;
    margin-bottom: 20px;
    color: #ffffff;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-title {
    font-size: 1.7rem;
    font-weight: 900;
    color: #ffffff !important;
    margin: 0;
}

.content-box {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 24px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    margin-bottom: 18px;
}

.tag-badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 700;
    margin: 3px;
}
.tag-blue { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }
.tag-purple { background: #faf5ff; color: #7e22ce; border: 1px solid #f3e8ff; }
.tag-green { background: #f0fdf4; color: #15803d; border: 1px solid #dcfce7; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# API HELPERS
# ============================================================

def api_analyze_resume(file) -> Dict:
    files = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}
    res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, timeout=60)
    res.raise_for_status()
    return res.json()

def api_match_job(resume_text: str, job_description: str) -> Dict:
    payload = {"resume_text": resume_text, "job_description": job_description}
    res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
    res.raise_for_status()
    return res.json()

def api_screen_candidates(files: List, job_description: str) -> List[Dict]:
    file_payload = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in files]
    data_payload = {"job_description": job_description}
    res = requests.post(
        f"{API_BASE_URL}/api/recruiter/screen",
        files=file_payload,
        data=data_payload,
        timeout=120,
    )
    res.raise_for_status()
    return res.json()

def api_send_email(to_email: str, subject: str, content: str) -> tuple[bool, str]:
    payload = {"to_email": to_email, "subject": subject, "content": content}
    try:
        res = requests.post(f"{API_BASE_URL}/api/send-email", json=payload, timeout=30)
        if res.status_code == 200:
            return True, "Delivered"
        else:
            try:
                err_detail = res.json().get("detail", res.text)
            except Exception:
                err_detail = res.text
            return False, str(err_detail)
    except Exception as exc:
        return False, str(exc)

# ============================================================
# STATE
# ============================================================

if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "username" not in st.session_state: st.session_state.username = "Guest Explorer"
if "active_workspace" not in st.session_state: st.session_state.active_workspace = "Job Seeker Workspace"

# Recruiter Flow States
if "recruiter_step" not in st.session_state: st.session_state.recruiter_step = 1
if "recruiter_candidates" not in st.session_state: st.session_state.recruiter_candidates = []
if "shortlisted_candidates" not in st.session_state: st.session_state.shortlisted_candidates = []
if "recruiter_job_desc" not in st.session_state: st.session_state.recruiter_job_desc = ""
if "recruiter_role" not in st.session_state: st.session_state.recruiter_role = "Software Developer"

# ============================================================
# AUTHENTICATION
# ============================================================

if not st.session_state.is_logged_in:
    st.markdown(
        """
        <div style="text-align: center; padding: 40px 0 24px;">
            <div style="font-size: 58px; margin-bottom: 8px;">💼</div>
            <h1 style="font-size: 3rem; margin: 0; color: #091224; font-weight: 900;">Career<span style="color: #2563eb;">Lens</span> AI</h1>
            <p style="color: #475569; font-size: 1.15rem; margin-top: 6px; font-weight: 600;">Understand Your Career. Build Your Future.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    col_c1, col_c2, col_c3 = st.columns([1, 1.4, 1])
    with col_c2:
        st.markdown(
            """
            <div class="content-box" style="text-align: center; padding: 36px 30px;">
                <span class="tag-badge tag-blue" style="font-size: 0.82rem; padding: 6px 16px; margin-bottom: 12px;">✦ AI CAREER ECOSYSTEM ✦</span>
                <h3 style="margin: 10px 0 8px 0; font-size: 1.35rem; color: #0f172a;">Access Your Career Workspace</h3>
                <p style="color: #64748b; font-size: 0.92rem; margin-bottom: 26px;">
                    Resume scoring, qualifying tests, and automated recruiter email dispatchers.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🚀 Explore as Guest", use_container_width=True):
                st.session_state.username = "Guest Explorer"
                st.session_state.is_logged_in = True
                st.rerun()
        with b2:
            if st.button("🏢 Recruiter Admin", use_container_width=True):
                st.session_state.username = "Administrator"
                st.session_state.is_logged_in = True
                st.session_state.active_workspace = "Recruiter Workspace"
                st.rerun()
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-brand-box">
            <div style="font-size: 26px; color: #2563eb;">💼</div>
            <div>
                <div style="font-size: 1.15rem; font-weight: 900; color: #091224; line-height: 1.1;">
                    Career<span style="color: #2563eb;">lens</span> <span style="color: #7c3aed;">AI</span>
                </div>
                <div style="font-size: 0.68rem; color: #64748b; font-weight: 700;">
                    Your Career, Our Intelligence
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("### Workspaces")
    if st.button("👤 Candidate Workspace", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.rerun()
    if st.button("🏢 Recruiter Workspace", use_container_width=True):
        st.session_state.active_workspace = "Recruiter Workspace"
        st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.is_logged_in = False
        st.session_state.username = "Guest Explorer"
        st.rerun()

# ============================================================
# RECRUITER WORKSPACE
# ============================================================

if st.session_state.active_workspace == "Recruiter Workspace":
    st.markdown(
        f"""
        <div class="header-banner">
            <div>
                <div class="header-title">Recruiter Command Suite</div>
                <div class="header-sub">Hiring Pipeline · Screen Resumes, Shortlist, and Dispatch Assessments</div>
            </div>
            <div style="color:#ffffff; font-weight:800;">Recruiter: {st.session_state.username}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Step Progress Indicator
    step_labels = ["1. Bulk Screening", "2. Shortlisting & Selection", "3. Assessment Dispatcher", "4. Score Vault"]
    col_steps = st.columns(4)
    for idx, name in enumerate(step_labels, 1):
        with col_steps[idx-1]:
            is_active = (st.session_state.recruiter_step == idx)
            tag_class = "tag-blue" if is_active else "tag-purple"
            st.markdown(f'<div style="text-align:center;"><span class="tag-badge {tag_class}" style="padding:6px 14px; font-size:0.82rem;">{name}</span></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- STEP 1: BULK SCREENING ---
    if st.session_state.recruiter_step == 1:
        st.subheader("Step 1: Job Description & Bulk Resume Screening")
        st.session_state.recruiter_role = st.text_input("Position Title", value=st.session_state.recruiter_role)
        st.session_state.recruiter_job_desc = st.text_area(
            "Job Description & Requirements",
            value=st.session_state.recruiter_job_desc,
            height=140,
            placeholder="Paste technical requirements and qualifications..."
        )
        bulk_files = st.file_uploader("Upload Resumes (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True)

        if st.button("⚡ Screen & Rank All Resumes", use_container_width=True):
            if not st.session_state.recruiter_job_desc.strip() or not bulk_files:
                st.warning("Please provide a job description and upload at least one resume.")
            else:
                with st.spinner("Processing resumes and calculating rankings..."):
                    try:
                        results = api_screen_candidates(bulk_files, st.session_state.recruiter_job_desc)
                        st.session_state.recruiter_candidates = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
                        st.session_state.shortlisted_candidates = list(st.session_state.recruiter_candidates)
                        st.success(f"Screening complete! Processed {len(results)} candidate(s).")
                    except Exception as e:
                        st.error(f"Error during screening: {e}")

        if st.session_state.recruiter_candidates:
            df_disp = pd.DataFrame(st.session_state.recruiter_candidates)[["name", "email", "score"]]
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Next: Shortlist Candidates ➡️", use_container_width=True):
                st.session_state.recruiter_step = 2
                st.rerun()

    # --- STEP 2: SHORTLISTING & SELECTION ---
    elif st.session_state.recruiter_step == 2:
        st.subheader("Step 2: Candidate Shortlisting")
        
        candidates = st.session_state.recruiter_candidates
        if not candidates:
            st.warning("No candidates available. Please run Step 1 bulk screening first.")
            if st.button("⬅️ Back to Step 1"):
                st.session_state.recruiter_step = 1
                st.rerun()
        else:
            select_all = st.checkbox("Select All Candidates", value=True)
            selected_list = []

            for idx, cand in enumerate(candidates):
                col_c1, col_c2 = st.columns([0.1, 0.9])
                with col_c1:
                    is_selected = st.checkbox("", value=select_all, key=f"cand_box_{idx}", label_visibility="collapsed")
                with col_c2:
                    st.markdown(f"""
                    <div class="content-box" style="padding:12px 18px; margin-bottom:8px;">
                        <b>{cand['name']}</b> | Match Score: <span style="color:#2563eb; font-weight:800;">{cand.get('score', 0)}%</span> | 📧 {cand['email']}
                    </div>
                    """, unsafe_allow_html=True)
                if is_selected:
                    selected_list.append(cand)

            st.session_state.shortlisted_candidates = selected_list
            st.caption(f"Shortlisted: {len(selected_list)} / {len(candidates)} candidates")

            col_n1, col_n2 = st.columns(2)
            with col_n1:
                if st.button("⬅️ Back to Bulk Screening", use_container_width=True):
                    st.session_state.recruiter_step = 1
                    st.rerun()
            with col_n2:
                if st.button("Next: Assessment Dispatcher ➡️", use_container_width=True):
                    if not selected_list:
                        st.warning("Please select at least one candidate.")
                    else:
                        st.session_state.recruiter_step = 3
                        st.rerun()

    # --- STEP 3: ASSESSMENT DISPATCHER ---
    elif st.session_state.recruiter_step == 3:
        st.subheader("Step 3: Assessment Dispatcher (SendGrid Integration)")
        
        shortlisted = st.session_state.shortlisted_candidates
        st.markdown(f"Dispatching test invitations to **{len(shortlisted)}** shortlisted candidate(s).")
        
        sub_input = st.text_input("Email Subject", value=f"Technical Assessment: {st.session_state.recruiter_role} Position")
        link_input = st.text_input("Assessment Portal URL", value="https://careerlens-ai.streamlit.app/")
        body_input = st.text_area(
            "Email Template (HTML)",
            value="""<p>Dear Candidate,</p>
<p>Congratulations! You have been shortlisted for the <b>Technical Assessment</b> round.</p>
<p>Please complete your assessment via the portal link below:</p>
<p><a href="{link}"><b>Start Your Qualifying Examination</b></a></p>
<p>Best regards,<br>Talent Acquisition Team</p>""",
            height=140
        )

        if st.button("📨 Send Assessment Invitations via SendGrid", use_container_width=True):
            dispatch_results = []
            with st.spinner("Dispatching assessment emails..."):
                for cand in shortlisted:
                    email_to = cand.get("email")
                    formatted_body = body_input.replace("{link}", link_input)
                    sent, msg = api_send_email(email_to, sub_input, formatted_body)
                    dispatch_results.append({
                        "Candidate": cand.get("name"),
                        "Email": email_to,
                        "Status": "Sent" if sent else "Failed",
                        "Details": msg
                    })

            st.dataframe(pd.DataFrame(dispatch_results), use_container_width=True, hide_index=True)

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Shortlisting", use_container_width=True):
                st.session_state.recruiter_step = 2
                st.rerun()
        with col_n2:
            if st.button("Next: Score Vault & Analytics ➡️", use_container_width=True):
                st.session_state.recruiter_step = 4
                st.rerun()

    # --- STEP 4: SCORE VAULT & RESULTS ---
    elif st.session_state.recruiter_step == 4:
        st.subheader("Step 4: Score Vault & Assessment Results")
        
        if st.session_state.recruiter_candidates:
            df_full = pd.DataFrame(st.session_state.recruiter_candidates)
            st.markdown("#### Candidate Cohort Results")
            st.dataframe(df_full, use_container_width=True, hide_index=True)

            st.download_button(
                "⬇️ Download Cohort Report (CSV)",
                df_full.to_csv(index=False).encode("utf-8"),
                file_name="cohort_assessment_report.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("No cohort results available.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⬅️ Back to Assessment Dispatcher", use_container_width=True):
            st.session_state.recruiter_step = 3
            st.rerun()

else:
    st.info("Switch to the Recruiter Workspace from the sidebar to manage candidate pipelines.")
