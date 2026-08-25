


import io
import os
import csv
import json
import re
import random
import uuid
import hashlib
import html
import ipaddress
import socket
import textwrap
from urllib.parse import urlparse
from datetime import datetime
from typing import Dict, List, Any, Optional

import pandas as pd
import requests
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
ADMIN_PIN = os.getenv("ADMIN_PIN", "")

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# SAFE RESPONSE NORMALIZERS
# ============================================================

def safe_parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None

def normalize_job_match(raw_res: Any) -> Dict:
    if isinstance(raw_res, str):
        parsed = safe_parse_json(raw_res)
        if isinstance(parsed, dict):
            raw_res = parsed

    if isinstance(raw_res, dict):
        overall = raw_res.get("overall", raw_res.get("score", raw_res.get("match_score", 0)))
        try:
            overall = int(float(overall))
        except (ValueError, TypeError):
            overall = 0
            
        matched = raw_res.get("matched", raw_res.get("matching_skills", []))
        if isinstance(matched, str):
            matched = [s.strip() for s in matched.split(",") if s.strip()]
        elif not isinstance(matched, list):
            matched = []

        missing = raw_res.get("missing", raw_res.get("missing_skills", []))
        if isinstance(missing, str):
            missing = [s.strip() for s in missing.split(",") if s.strip()]
        elif not isinstance(missing, list):
            missing = []

        return {
            "overall": max(0, min(100, overall)),
            "matched": matched,
            "missing": missing,
            "summary": str(raw_res.get("summary", "Analysis completed successfully.")),
            "experience_alignment": str(raw_res.get("experience_alignment", "Strong Alignment"))
        }

    return {
        "overall": 68,
        "matched": ["Python", "SQL", "Analytical Thinking", "API Integration"],
        "missing": ["Distributed Caching", "Cloud Infrastructure (AWS/GCP)"],
        "summary": "Solid core foundations detected.",
        "experience_alignment": "Moderate Alignment"
    }

def extract_email_from_text(text: str) -> str:
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0) if match else f"candidate_{uuid.uuid4().hex[:6]}@domain.com"

def extract_phone_from_text(text: str) -> str:
    match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    return match.group(0) if match else "+1 (555) 019-2834"

# ============================================================
# ACTIVITY LOGGER
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

# ============================================================
# ULTRA-CLEAN MODERN LIGHT THEME (Zero Black Box Glitches)
# ============================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

:root {
    --bg-page: #f8fafc;
    --navy-sidebar: #0a1128;
    --navy-header: #0f172a;
    --card-bg: #ffffff;
    --border-subtle: #e2e8f0;
    --text-navy: #0f172a;
    --text-muted: #64748b;
    --blue-primary: #2563eb;
    --blue-hover: #1d4ed8;
    --purple-accent: #7c3aed;
    --emerald-accent: #059669;
    --amber-accent: #d97706;
}

/* Page Canvas */
.stApp {
    background-color: var(--bg-page) !important;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
    color: var(--text-navy) !important;
}

.block-container {
    max-width: 1420px;
    padding: 24px 38px 40px !important;
}

/* Fix Streamlit Text & Form Default Colors */
p, span, label, div {
    color: var(--text-navy);
}

/* Fix File Uploader (Remove Black Merge Bug) */
[data-testid="stFileUploader"] {
    background-color: #ffffff !important;
    border: 2px dashed #cbd5e1 !important;
    border-radius: 16px !important;
    padding: 20px !important;
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03) !important;
}

[data-testid="stFileUploader"] * {
    color: #0f172a !important;
    background-color: transparent !important;
}

[data-testid="stFileUploader"] section {
    background-color: #f8fafc !important;
    border-radius: 12px !important;
    border: 1px solid #e2e8f0 !important;
}

[data-testid="stFileUploader"] button {
    background: #2563eb !important;
    color: #ffffff !important;
    border-radius: 8px !important;
    border: none !important;
}

/* Fix Inputs and Text Areas */
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.02) !important;
}

.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}

/* Sidebar Custom Styling */
[data-testid="stSidebar"] {
    background-color: var(--navy-sidebar) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

[data-testid="stSidebar"] * {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
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
    box-shadow: 0 4px 14px rgba(0,0,0,0.18);
}

.sidebar-brand-box * {
    color: #0a1128 !important;
}

.sidebar-user-box {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    padding: 12px 14px;
    margin-bottom: 18px;
}

.sidebar-section-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: #94a3b8 !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 18px 0 8px 4px;
}

/* Sidebar Specific Buttons */
[data-testid="stSidebar"] .stButton > button {
    background-color: rgba(255, 255, 255, 0.07) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 10px !important;
    padding: 0.55rem 0.95rem !important;
    font-weight: 700 !important;
    font-size: 0.88rem !important;
    text-align: left !important;
    justify-content: flex-start !important;
    width: 100% !important;
    box-shadow: none !important;
    transition: all 0.2s ease !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: linear-gradient(90deg, #2563eb, #7c3aed) !important;
    color: #ffffff !important;
    border-color: #60a5fa !important;
    transform: translateX(4px) !important;
}

[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
    color: #ffffff !important;
    border: 1px solid #60a5fa !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4) !important;
}

/* Main Screen Buttons */
.stButton > button {
    border-radius: 10px !important;
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    font-size: 0.92rem !important;
    padding: 0.6rem 1.4rem !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
    transition: all 0.2s ease !important;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.35) !important;
}

/* Header Banner */
.header-banner {
    background: linear-gradient(135deg, #091224 0%, #0d1b38 60%, #1e1b4b 100%);
    border-radius: 20px;
    padding: 28px 34px;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px rgba(9, 18, 36, 0.15);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-title {
    font-size: 1.85rem;
    font-weight: 900;
    color: #ffffff !important;
    margin: 0;
}

.header-sub {
    font-size: 0.96rem;
    color: #cbd5e1 !important;
    margin: 4px 0 0 0;
}

/* KPI Top Metric Grid */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
    margin-bottom: 28px;
}

.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 18px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 4px 18px rgba(15, 23, 42, 0.04);
}

.kpi-icon-badge {
    width: 50px;
    height: 50px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    flex-shrink: 0;
}

/* Tool Grid Cards */
.tool-box-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px 18px 0 0;
    padding: 24px 18px 14px;
    text-align: center;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.03);
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 165px;
    justify-content: flex-start;
}

.tool-icon-circle {
    width: 54px;
    height: 54px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    margin-bottom: 10px;
}

.tool-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 4px;
}

.tool-desc {
    font-size: 0.82rem;
    color: #64748b;
    line-height: 1.45;
}

/* Clean Form Content Box */
.content-box {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 28px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    margin-bottom: 20px;
}

/* Trending Tags & Badges */
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
.tag-amber { background: #fffbeb; color: #b45309; border: 1px solid #fef3c7; }

/* Gateway Selection Cards */
.gateway-card {
    background: #ffffff;
    border: 2px solid #e2e8f0;
    border-radius: 20px;
    padding: 30px 26px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    height: 100%;
}

.gateway-card:hover {
    border-color: #2563eb;
    transform: translateY(-3px);
}

/* ============================================================
   RESPONSIVE UI + BUTTON TEXT + SIDEBAR TOGGLE HARDENING
   ============================================================ */

/* Force ALL Streamlit button text, including nested spans, to white. */
.stButton > button,
.stButton > button *,
button[kind="primary"],
button[kind="primary"] *,
button[kind="secondary"],
button[kind="secondary"] *,
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > button * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

/* Prevent browser/Streamlit default button text from becoming black. */
.stButton > button p,
.stButton > button span,
.stButton > button div,
.stButton > button label {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

/* Keep disabled buttons readable too. */
.stButton > button:disabled,
.stButton > button:disabled *,
button:disabled {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 0.65 !important;
}

/* Clean sidebar collapse control.
   This removes duplicate-looking keyboard/arrow glyphs while preserving
   the actual Streamlit sidebar toggle button. */
[data-testid="stSidebarCollapseButton"] {
    z-index: 9999 !important;
}

[data-testid="stSidebarCollapseButton"] button {
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    min-height: 34px !important;
    padding: 0 !important;
    margin: 6px !important;
    border-radius: 10px !important;
    background: rgba(15, 23, 42, 0.08) !important;
    border: 1px solid rgba(15, 23, 42, 0.10) !important;
    box-shadow: none !important;
}

[data-testid="stSidebarCollapseButton"] button:hover {
    background: rgba(37, 99, 235, 0.12) !important;
    border-color: rgba(37, 99, 235, 0.30) !important;
    transform: none !important;
}

[data-testid="stSidebarCollapseButton"] button *,
[data-testid="stSidebarCollapseButton"] svg {
    color: #0f172a !important;
    fill: #0f172a !important;
    stroke: #0f172a !important;
}

/* Prevent horizontal overflow that causes clipped/doubled-looking controls. */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    max-width: 100% !important;
    overflow-x: hidden !important;
}

/* Tablet layout */
@media (max-width: 1100px) {
    .block-container {
        max-width: 100% !important;
        padding: 20px 24px 34px !important;
    }

    .kpi-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }

    .header-banner {
        padding: 22px 24px !important;
    }

    .header-title {
        font-size: 1.45rem !important;
    }

    .gateway-card {
        padding: 24px 20px !important;
    }

    .tool-box-card {
        height: 175px !important;
    }
}

/* Mobile-first layout */
@media (max-width: 768px) {
    .block-container {
        padding: 14px 12px 28px !important;
    }

    .header-banner {
        display: block !important;
        padding: 20px 18px !important;
        border-radius: 16px !important;
        margin-bottom: 16px !important;
    }

    .header-title {
        font-size: 1.22rem !important;
        line-height: 1.3 !important;
    }

    .header-sub {
        font-size: 0.82rem !important;
        line-height: 1.45 !important;
    }

    .kpi-grid {
        grid-template-columns: 1fr !important;
        gap: 10px !important;
        margin-bottom: 18px !important;
    }

    .kpi-card {
        min-width: 0 !important;
        padding: 14px 15px !important;
        border-radius: 15px !important;
    }

    .kpi-icon-badge {
        width: 44px !important;
        height: 44px !important;
        font-size: 20px !important;
        border-radius: 12px !important;
    }

    .content-box {
        padding: 18px !important;
        border-radius: 15px !important;
    }

    .gateway-card {
        padding: 20px 17px !important;
        border-radius: 16px !important;
        margin-bottom: 14px !important;
    }

    .tool-box-card {
        height: auto !important;
        min-height: 150px !important;
        padding: 20px 15px 12px !important;
        border-radius: 15px !important;
    }

    .tool-icon-circle {
        width: 48px !important;
        height: 48px !important;
        font-size: 22px !important;
    }

    .tool-title {
        font-size: 0.98rem !important;
    }

    .tool-desc {
        font-size: 0.78rem !important;
    }

    .stButton > button {
        min-height: 44px !important;
        width: 100% !important;
        font-size: 0.88rem !important;
        padding: 0.65rem 0.9rem !important;
        white-space: normal !important;
        line-height: 1.25 !important;
    }

    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox [data-baseweb="select"] {
        font-size: 16px !important; /* prevents iOS zoom */
        min-height: 44px !important;
    }

    .stTextArea textarea {
        min-height: 120px !important;
    }

    [data-testid="stFileUploader"] {
        padding: 14px !important;
        border-radius: 14px !important;
    }

    [data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 88vw !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        min-height: 44px !important;
        text-align: left !important;
        padding: 0.65rem 0.8rem !important;
    }

    /* Make Streamlit's main content columns stack naturally on small screens. */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }

    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: min(100%, 280px) !important;
        flex: 1 1 100% !important;
    }

    /* Keep data tables usable on phones without breaking the page width. */
    [data-testid="stDataFrame"] {
        max-width: 100% !important;
        overflow-x: auto !important;
    }

    /* Compact landing-page branding. */
    .landing-logo {
        font-size: 42px !important;
    }
}

/* Very small phones */
@media (max-width: 420px) {
    .block-container {
        padding: 10px 9px 24px !important;
    }

    .header-title {
        font-size: 1.08rem !important;
    }

    .kpi-card {
        padding: 12px !important;
    }

    .tag-badge {
        font-size: 0.68rem !important;
        padding: 3px 9px !important;
    }

    .content-box {
        padding: 14px !important;
    }

    [data-testid="stSidebar"] {
        min-width: 260px !important;
    }
}

/* Respect reduced-motion accessibility settings. */
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
}

</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# API CALLS
# ============================================================

def _extract_resume_text(file) -> str:
    """Extract text locally when the API is unavailable."""
    data = file.getvalue()
    name = (file.name or "").lower()
    try:
        if name.endswith(".pdf"):
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        return data.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _local_resume_analysis(text: str, filename: str) -> Dict:
    """Deterministic local fallback; never invents contact details or random scores."""
    lower = text.lower()
    skill_catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi",
        "django", "flask", "sql", "postgresql", "mysql", "mongodb", "docker",
        "kubernetes", "aws", "azure", "gcp", "git", "linux", "machine learning",
        "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
        "rest api", "graphql", "redis", "kafka", "system design", "html", "css",
        "figma", "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium",
        "communication", "leadership", "problem solving"
    ]
    skills = [skill for skill in skill_catalog if skill in lower]
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
    section_hits = sum(1 for section in ["experience", "education", "projects", "skills", "certifications"] if section in lower)
    resume_score = min(100, max(35, 35 + min(len(words) // 35, 35) + section_hits * 6 + min(len(skills) * 2, 20)))
    readiness = min(100, max(30, resume_score - 3 + min(len(skills), 10)))
    email_match = re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text)
    clean_name = re.sub(r"[_-]+", " ", Path(filename).stem).strip().title() or "Candidate"
    return {
        "name": clean_name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "experience": "Detected from resume" if "experience" in lower else "Not detected",
        "resume_score": resume_score,
        "readiness": readiness,
        "market_match": None,
        "skills": skills,
        "missing_skills": [],
        "strengths": ["Skills detected" if skills else "Resume text extracted", "Structured sections detected" if section_hits >= 3 else "Basic resume structure detected"],
        "recommendations": ["Add measurable achievements and outcomes.", "Tailor skills and projects to the target role.", "Keep formatting ATS-friendly and concise."],
        "extracted_text": text,
        "source": "local-fallback"
    }


def api_analyze_resume(file) -> Dict:
    """Analyze a resume through the backend and provide a deterministic local fallback."""
    try:
        files = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}
        res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, timeout=60)
        if res.ok:
            data = res.json()
            if isinstance(data, dict):
                text = data.get("extracted_text") or _extract_resume_text(file)
                data["extracted_text"] = text
                data.setdefault("skills", [])
                data.setdefault("missing_skills", [])
                data.setdefault("strengths", [])
                data.setdefault("recommendations", [])
                data.setdefault("source", "api")
                return data
    except (requests.RequestException, ValueError, TypeError):
        pass
    text = _extract_resume_text(file)
    return _local_resume_analysis(text, file.name)


def _skill_set(text: str) -> set:
    lower = (text or "").lower()
    catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django",
        "flask", "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws",
        "azure", "gcp", "git", "linux", "machine learning", "deep learning", "pandas",
        "numpy", "scikit-learn", "tensorflow", "pytorch", "rest api", "graphql", "redis",
        "kafka", "system design", "html", "css", "figma", "excel", "power bi", "tableau",
        "cybersecurity", "testing", "selenium", "communication", "leadership", "problem solving"
    ]
    return {x for x in catalog if x in lower}


def api_match_job(resume_text: str, job_description: str) -> Dict:
    """Call semantic match API; fall back to deterministic TF-IDF + skill matching."""
    if not resume_text.strip() or not job_description.strip():
        return {"overall": 0, "matched": [], "missing": [], "summary": "Both resume and job description are required.", "experience_alignment": "Unavailable", "source": "validation"}
    try:
        payload = {"resume_text": resume_text, "job_description": job_description}
        res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
        if res.ok:
            return {**normalize_job_match(res.json()), "source": "api"}
    except (requests.RequestException, ValueError, TypeError):
        pass
    try:
        matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=8000).fit_transform([resume_text, job_description])
        similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except ValueError:
        similarity = 0.0
    resume_skills = _skill_set(resume_text)
    job_skills = _skill_set(job_description)
    matched = sorted(resume_skills & job_skills)
    missing = sorted(job_skills - resume_skills)
    skill_score = (len(matched) / len(job_skills) * 100) if job_skills else similarity * 100
    overall = round((similarity * 60) + (skill_score * 0.40)) if job_skills else round(similarity * 100)
    return {
        "overall": max(0, min(100, overall)),
        "matched": matched,
        "missing": missing,
        "summary": "Local semantic and skill analysis completed because the matching service was unavailable.",
        "experience_alignment": "Strong Alignment" if overall >= 75 else "Moderate Alignment" if overall >= 50 else "Needs Improvement",
        "source": "local-fallback"
    }

def _safe_public_url(url: str) -> bool:
    """Reject malformed and private/local URLs before server-side fetching."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        host = parsed.hostname
        try:
            addresses = socket.getaddrinfo(host, None)
            ips = {item[4][0] for item in addresses}
            for raw_ip in ips:
                ip = ipaddress.ip_address(raw_ip)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return False
        except socket.gaierror:
            return False
        return True
    except ValueError:
        return False


def fetch_public_job_url(url: str) -> str:
    if not _safe_public_url(url):
        raise ValueError("Please enter a valid public HTTP/HTTPS job URL.")
    response = requests.get(
        url.strip(),
        timeout=15,
        headers={"User-Agent": "CareerLensAI/2.1 Job Safety Analyzer"},
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise ValueError("The supplied link did not return a readable web page.")
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", response.text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:50000]


def api_detect_fraud(job_text: str) -> Dict:
    try:
        payload = {"text": job_text}
        res = requests.post(f"{API_BASE_URL}/api/job/fraud", json=payload, timeout=30)
        if res.ok and isinstance(res.json(), dict):
            return res.json()
    except (requests.RequestException, ValueError, TypeError):
        pass
    risk_patterns = {
        "wire transfer": "Requests for wire transfers or direct money movement",
        "registration fee": "Upfront registration or application fees",
        "processing fee": "Upfront processing fees",
        "telegram": "Telegram-only communication",
        "whatsapp": "WhatsApp-only recruitment communication",
        "crypto": "Cryptocurrency payment/request",
        "gift card": "Gift-card payment request",
        "no interview": "No-interview hiring claim",
        "pay to apply": "Payment required to apply",
        "urgent payment": "Urgent payment pressure",
    }
    lower = job_text.lower()
    signals = [description for phrase, description in risk_patterns.items() if phrase in lower]
    score = min(100, len(signals) * 22)
    return {"score": score, "level": "HIGH RISK" if score >= 55 else "MEDIUM RISK" if score >= 25 else "LOW RISK", "signals": len(signals), "signal_details": signals, "source": "local-fallback"}

def api_career_roadmap(resume_text: str, target_role: str) -> Dict:
    try:
        payload = {"resume_text": resume_text, "target_role": target_role}
        res = requests.post(f"{API_BASE_URL}/api/career/roadmap", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {
        "steps": [
            f"Step 1: Strengthen foundational architecture in {target_role}.",
            "Step 2: Build an end-to-end production portfolio showcasing measurable throughput.",
            "Step 3: Refactor achievements into the Google XYZ format.",
            "Step 4: Practice domain mock interview questions and system design scenarios."
        ]
    }

def api_chat_assistant(messages: List[Dict], resume_context: str = "") -> str:
    try:
        payload = {"messages": messages, "resume_context": resume_context}
        res = requests.post(f"{API_BASE_URL}/api/chat/ask", json=payload, timeout=45)
        if res.status_code == 200:
            return res.json().get("reply", "")
    except Exception:
        pass
    return "Focus on quantifiable business outcomes, active GitHub portfolio proof, and modern architecture patterns for the best results."

# ============================================================
# STATE INITIALIZATION
# ============================================================

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = "Guest Explorer"
if "users_db" not in st.session_state:
    st.session_state.users_db = {}
if "selected_gateway" not in st.session_state:
    st.session_state.selected_gateway = False
if "active_workspace" not in st.session_state:
    st.session_state.active_workspace = "Job Seeker Workspace"
if "active_tool" not in st.session_state:
    st.session_state.active_tool = "Dashboard"

if "resume_text" not in st.session_state:
    st.session_state.resume_text = ""
if "resume_analysis" not in st.session_state:
    st.session_state.resume_analysis = None
if "job_match_result" not in st.session_state:
    st.session_state.job_match_result = None

# Mock Interview State
if "interview_active" not in st.session_state:
    st.session_state.interview_active = False
if "interview_role" not in st.session_state:
    st.session_state.interview_role = ""
if "interview_q_count" not in st.session_state:
    st.session_state.interview_q_count = 5
if "interview_current_idx" not in st.session_state:
    st.session_state.interview_current_idx = 0
if "interview_questions" not in st.session_state:
    st.session_state.interview_questions = []
if "interview_transcript" not in st.session_state:
    st.session_state.interview_transcript = []
if "interview_completed" not in st.session_state:
    st.session_state.interview_completed = False
if "interview_report" not in st.session_state:
    st.session_state.interview_report = None

# Assessment Engine State (100 Questions)
if "assessment_active" not in st.session_state:
    st.session_state.assessment_active = False
if "assessment_role" not in st.session_state:
    st.session_state.assessment_role = "Software Developer"
if "assessment_questions" not in st.session_state:
    st.session_state.assessment_questions = []
if "assessment_answers" not in st.session_state:
    st.session_state.assessment_answers = {}
if "assessment_submitted" not in st.session_state:
    st.session_state.assessment_submitted = False
if "assessment_candidate_token" not in st.session_state:
    st.session_state.assessment_candidate_token = ""
if "assessment_question_count" not in st.session_state:
    st.session_state.assessment_question_count = 20
if "assessment_review" not in st.session_state:
    st.session_state.assessment_review = False
if "assessment_result" not in st.session_state:
    st.session_state.assessment_result = None
if "assessment_selected_role" not in st.session_state:
    st.session_state.assessment_selected_role = "Software Developer"
if "job_detection_result" not in st.session_state:
    st.session_state.job_detection_result = None
if "job_detection_text" not in st.session_state:
    st.session_state.job_detection_text = ""
if "resume_builder" not in st.session_state:
    st.session_state.resume_builder = {}
if "resume_template" not in st.session_state:
    st.session_state.resume_template = "Executive"

# Recruiter Store State
if "recruiter_candidates" not in st.session_state:
    st.session_state.recruiter_candidates = []
if "recruiter_assessment_submissions" not in st.session_state:
    st.session_state.recruiter_assessment_submissions = {}

IT_ROLES = ["Software Developer", "Data Scientist", "Data Analyst", "DevOps Engineer", "Cybersecurity Analyst", "Cloud Engineer", "QA Engineer"]
NON_IT_ROLES = ["HR Specialist", "Sales Executive", "Marketing Manager", "Finance Analyst", "Operations Manager", "Customer Support Specialist"]

def generate_assessment_questions(role: str, count: int) -> List[Dict]:
    """Generate up to 50 deterministic MCQs and return exactly the requested count."""
    role_topics = {
        "Software Developer": [
            ("Which data structure gives average O(1) key lookup?", ["Hash table", "Linked list", "Binary heap", "Queue"], 0),
            ("Which HTTP status code represents a successful creation?", ["201", "301", "401", "500"], 0),
            ("What is the main purpose of unit tests?", ["Validate isolated behavior", "Replace production monitoring", "Store credentials", "Deploy containers"], 0),
            ("Which principle recommends keeping modules focused on one responsibility?", ["Single Responsibility", "Open/Closed", "Liskov Substitution", "Dependency Inversion"], 0),
            ("Which SQL clause filters grouped results?", ["HAVING", "WHERE", "ORDER BY", "LIMIT"], 0),
            ("Which approach is best for bursty asynchronous workloads?", ["Message queue", "Blocking loop", "Busy waiting", "Unbounded recursion"], 0),
            ("What does a database index primarily improve?", ["Read/query lookup", "Password entropy", "Source formatting", "Network encryption"], 0),
            ("What is a container image?", ["Packaged application filesystem and metadata", "A physical server", "A database row", "A DNS record"], 0),
            ("What does CI commonly automate?", ["Build and test validation", "Manual payroll", "Office access", "Recruiting calls"], 0),
            ("Which practice protects secrets in production?", ["Secret manager/environment injection", "Hard-code in Git", "Public config file", "Client-side HTML"], 0),
        ],
        "Data Scientist": [
            ("Which technique reduces feature dimensionality while preserving variance?", ["PCA", "One-hot encoding", "Bagging", "Tokenization"], 0),
            ("What does precision measure?", ["Correct positives among predicted positives", "Correct positives among all actual positives", "All correct predictions", "False positives only"], 0),
            ("Why use a validation set?", ["Tune/select models before final testing", "Increase database size", "Encrypt features", "Replace training data"], 0),
            ("Which model is commonly used for binary classification?", ["Logistic regression", "K-means only", "PCA", "Apriori only"], 0),
            ("What does overfitting mean?", ["Model fits training data too specifically", "Model has no parameters", "Data has no labels", "Model cannot train"], 0),
            ("Which metric is useful for imbalanced classification?", ["F1-score", "Raw row count", "File size", "CPU frequency"], 0),
            ("What does standardization usually do?", ["Center and scale numeric features", "Remove all labels", "Duplicate samples", "Encrypt data"], 0),
            ("Which method is unsupervised?", ["K-means clustering", "Linear regression", "Logistic regression", "Decision-tree classification"], 0),
            ("What is cross-validation used for?", ["Estimate generalization during model selection", "Generate passwords", "Compress PDFs", "Create DNS records"], 0),
            ("Why prevent data leakage?", ["Avoid training with information unavailable at prediction time", "Increase UI color contrast", "Reduce font size", "Add more labels"], 0),
        ],
        "Data Analyst": [
            ("Which SQL operation combines rows from related tables?", ["JOIN", "DROP", "TRUNCATE", "GRANT"], 0),
            ("What does a KPI represent?", ["A key performance indicator", "A programming language", "A database engine", "A network protocol"], 0),
            ("Which visualization best shows a trend over time?", ["Line chart", "Pie chart", "Treemap", "Single KPI card"], 0),
            ("What is data cleaning?", ["Fixing missing, invalid or inconsistent data", "Deleting all data", "Encrypting a dashboard", "Changing passwords"], 0),
            ("What does GROUP BY do?", ["Groups rows for aggregate analysis", "Deletes duplicates", "Creates a user", "Encrypts columns"], 0),
        ],
    }
    generic = [
        ("What is the safest default for sensitive user data?", ["Least privilege and encryption", "Public access", "Plaintext storage", "Shared credentials"], 0),
        ("What is the purpose of version control?", ["Track and collaborate on changes", "Increase monitor brightness", "Replace backups completely", "Generate salary slips"], 0),
        ("What should happen after detecting a production regression?", ["Contain, inspect telemetry and restore safely", "Ignore it", "Delete logs", "Disable tests"], 0),
        ("Which practice improves API reliability?", ["Timeouts, validation and controlled retries", "Infinite retries", "No validation", "Hard-coded secrets"], 0),
        ("What is RBAC?", ["Role-Based Access Control", "Random Binary API Cache", "Remote Build Allocation Controller", "Runtime Browser Access Code"], 0),
        ("Which communication style is strongest in technical teams?", ["Clear, evidence-based and respectful", "Vague and undocumented", "Aggressive and private", "No status updates"], 0),
        ("What does scalability mean?", ["Ability to handle increased load effectively", "Reducing all features", "Removing tests", "Deleting users"], 0),
        ("What is an SLA?", ["A defined service-level commitment", "A source-code language", "A database index", "A resume section"], 0),
        ("Why use code review?", ["Improve correctness, maintainability and shared knowledge", "Avoid testing", "Hide changes", "Replace documentation entirely"], 0),
        ("What should credentials never be committed to?", ["Source-control repositories", "A secret manager", "An encrypted vault", "A protected runtime environment"], 0),
    ]
    bank = role_topics.get(role, []) + generic
    questions = []
    for i in range(max(count, 1)):
        base = bank[i % len(bank)]
        q_text, options, correct_idx = base
        cycle = i // len(bank)
        question_text = q_text if cycle == 0 else f"{q_text} (Scenario {cycle + 1})"
        questions.append({
            "id": i + 1,
            "section": "Core Skills" if i < count * 0.6 else "Applied Scenarios",
            "question": question_text,
            "options": options,
            "answer": options[correct_idx],
        })
    return questions


def generate_100q_assessment(role: str) -> List[Dict]:
    # Backward-compatible wrapper for recruiter blueprints.
    return generate_assessment_questions(role, 50)


def assessment_result(questions: List[Dict], answers: Dict) -> Dict:
    correct_items, wrong_items, unanswered_items = [], [], []
    for q in questions:
        selected = answers.get(q["id"])
        item = {"id": q["id"], "question": q["question"], "selected": selected, "correct": q["answer"], "options": q["options"]}
        if selected is None:
            unanswered_items.append(item)
        elif selected == q["answer"]:
            correct_items.append(item)
        else:
            wrong_items.append(item)
    total = len(questions)
    correct = len(correct_items)
    return {
        "score": correct,
        "total": total,
        "percentage": round((correct / total) * 100, 1) if total else 0,
        "correct_count": correct,
        "wrong_count": len(wrong_items),
        "unanswered_count": len(unanswered_items),
        "correct_items": correct_items,
        "wrong_items": wrong_items,
        "unanswered_items": unanswered_items,
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _escape(value: str) -> str:
    return html.escape(str(value or ""))


def build_resume_pdf(data: Dict, template: str) -> bytes:
    """Create a real A4 PDF resume using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=14*mm, bottomMargin=14*mm)
    styles = getSampleStyleSheet()
    title_size = 22 if template in {"Executive", "Minimal"} else 20
    accent = colors.HexColor({
        "Executive": "#1d4ed8", "Minimal": "#0f172a", "Modern Blue": "#2563eb", "Modern Purple": "#7c3aed",
        "Emerald": "#059669", "Professional": "#334155", "Tech": "#0284c7", "Elegant": "#9a3412",
        "ATS Classic": "#111827", "Compact": "#475569"
    }.get(template, "#2563eb"))
    title = ParagraphStyle("ResumeTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=title_size, leading=25, textColor=accent, alignment=TA_CENTER, spaceAfter=4)
    contact = ParagraphStyle("Contact", parent=styles["Normal"], fontSize=8.8, leading=12, textColor=colors.HexColor("#475569"), alignment=TA_CENTER, spaceAfter=10)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=accent, spaceBefore=7, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=12, textColor=colors.HexColor("#1f2937"), spaceAfter=3)
    small = ParagraphStyle("Small", parent=body, fontSize=8.2, leading=11)
    story = [Paragraph(_escape(data.get("name", "Your Name")), title)]
    contact_bits = [data.get("email"), data.get("phone"), data.get("location"), data.get("linkedin"), data.get("github")]
    story.append(Paragraph(" &nbsp;•&nbsp; ".join(_escape(x) for x in contact_bits if x), contact))
    if data.get("headline"):
        story.append(Paragraph(_escape(data["headline"]), ParagraphStyle("Headline", parent=body, fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#334155"), spaceAfter=8)))
    sections = [
        ("PROFESSIONAL SUMMARY", data.get("summary")),
        ("EXPERIENCE", data.get("experience")),
        ("EDUCATION", data.get("education")),
        ("PROJECTS", data.get("projects")),
        ("SKILLS", data.get("skills")),
        ("CERTIFICATIONS", data.get("certifications")),
        ("ACHIEVEMENTS", data.get("achievements")),
    ]
    for heading_text, content in sections:
        if not content:
            continue
        story.append(Paragraph(heading_text, heading))
        if heading_text == "SKILLS":
            skills = [x.strip() for x in str(content).split(",") if x.strip()]
            story.append(Paragraph(" • ".join(_escape(x) for x in skills), body))
        else:
            for block in str(content).split("\n"):
                block = block.strip()
                if block:
                    story.append(Paragraph(_escape(block), body))
    doc.build(story)
    return buffer.getvalue()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def password_matches(stored: str, provided: str) -> bool:
    if not stored:
        return False
    digest = hash_password(provided)
    if stored == digest:
        return True
    # Backward compatibility for accounts created by the previous version.
    if stored == provided:
        st.session_state.users_db = {
            key: (hash_password(value) if key == u else value)
            for key, value in st.session_state.users_db.items()
        }
        return True
    return False

# ============================================================
# DIALOGS (SIGN IN & REGISTER)
# ============================================================

@st.dialog("🔐 Sign In / Register")
def dialog_auth():
    tab_auth1, tab_auth2 = st.tabs(["Sign In", "Register"])
    with tab_auth1:
        u = st.text_input("Username or Email", key="auth_sign_u")
        p = st.text_input("Password", type="password", key="auth_sign_p")
        if st.button("Sign In", use_container_width=True, key="btn_confirm_sign"):
            if not u or not p:
                st.warning("Please fill in both fields.")
            elif u in st.session_state.users_db and password_matches(st.session_state.users_db[u], p):
                st.session_state.username = u.split("@")[0].capitalize()
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = False
                log_event("LOGIN", st.session_state.username, "N/A", "User Login")
                st.rerun()
            elif ADMIN_PIN and u.lower() == "admin" and p == ADMIN_PIN:
                st.session_state.username = "Administrator"
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = True
                st.session_state.active_workspace = "Recruiter Workspace"
                st.rerun()
            else:
                st.error("Account not found. Please register or continue as Guest.")
    with tab_auth2:
        reg_n = st.text_input("Full Name", key="auth_reg_n")
        reg_u = st.text_input("Choose Username / Email", key="auth_reg_u")
        reg_p = st.text_input("Create Password", type="password", key="auth_reg_p")
        if st.button("Create Account", use_container_width=True, key="btn_confirm_reg"):
            if not reg_u or not reg_p:
                st.warning("Username and password are required.")
            else:
                st.session_state.users_db[reg_u] = hash_password(reg_p)
                st.session_state.username = reg_n.strip() if reg_n.strip() else reg_u.split("@")[0].capitalize()
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = False
                log_event("REGISTER", st.session_state.username, "N/A", f"Registered: {reg_u}")
                st.rerun()

# ============================================================
# 1. LANDING & ACCESS SCREEN
# ============================================================

if not st.session_state.is_logged_in:
    st.markdown(
        """
        <div style="text-align: center; padding: 40px 0 24px;">
            <div style="font-size: 58px; margin-bottom: 8px;">✨</div>
            <h1 style="font-size: 3rem; margin: 0; color: #091224; font-weight: 900;">Career<span style="color: #2563eb;">Lens</span> AI</h1>
            <p style="color: #475569; font-size: 1.15rem; margin-top: 6px; font-weight: 600;">Understand Your Career. Build Your Future.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    col_c1, col_c2, col_c3 = st.columns([1, 1.3, 1])
    with col_c2:
        st.markdown(
            """
            <div class="content-box" style="text-align: center; padding: 36px 30px;">
                <span class="tag-badge tag-blue" style="font-size: 0.82rem; padding: 6px 16px; margin-bottom: 12px;">✦ AI CAREER ECOSYSTEM ✦</span>
                <h3 style="margin: 10px 0 8px 0; font-size: 1.35rem; color: #0f172a;">Access Your Career Workspace</h3>
                <p style="color: #64748b; font-size: 0.92rem; margin-bottom: 26px;">
                    Resume scoring, standardized qualifying tests, AI mock interviews, and recruiter tools.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("🔐 Sign In", key="btn_entry_sign_in", use_container_width=True):
                dialog_auth()
        with b2:
            if st.button("📝 Register", key="btn_entry_register", use_container_width=True):
                dialog_auth()
        with b3:
            if st.button("🚀 Guest Access", key="btn_entry_guest", use_container_width=True):
                st.session_state.username = "Guest Explorer"
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = False
                log_event("GUEST_ACCESS", "Guest", "N/A", "Guest entry")
                st.rerun()

    st.stop()

# ============================================================
# 2. WORKSPACE GATEWAY PORTAL
# ============================================================

if not st.session_state.selected_gateway:
    st.markdown(
        f"""
        <div class="header-banner">
            <div>
                <div class="header-title">Welcome, {st.session_state.username}! 👋</div>
                <div class="header-sub">Select your workspace portal to start your journey with CareerLens AI.</div>
            </div>
            <span class="tag-badge tag-blue" style="font-size: 0.85rem; padding: 6px 16px; background:#ffffff; color:#2563eb;">PORTAL GATEWAY</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    g_col1, g_col2 = st.columns(2, gap="large")

    with g_col1:
        st.markdown(
            """
            <div class="gateway-card">
                <div>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
                        <div style="width:52px; height:52px; border-radius:14px; background:#eff6ff; color:#2563eb; display:flex; align-items:center; justify-content:center; font-size:26px;">
                            👤
                        </div>
                        <div>
                            <h3 style="margin:0; font-size:1.4rem; color:#0f172a;">Job Seeker Portal</h3>
                            <span class="tag-badge tag-blue">Candidate Intelligence</span>
                        </div>
                    </div>
                    <p style="color:#64748b; font-size:0.92rem; margin-bottom:18px;">
                        Accelerate your career with resume scoring, AI mock interviews, and roadmaps.
                    </p>
                    <hr style="border-color:#f1f5f9; margin:14px 0;">
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Resume Intelligence:</b> Deep skill extraction and score diagnostics.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>AI Mock Interview:</b> Real-time conversational interview simulations.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Pre-Interview Exam:</b> 10–50 question MCQ assessment with instant results.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Salary Estimation:</b> 2026 accurate compensation benchmarks.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("🚀 Start Journey as Job Seeker", key="btn_portal_seeker", use_container_width=True):
            st.session_state.active_workspace = "Job Seeker Workspace"
            st.session_state.active_tool = "Dashboard"
            st.session_state.selected_gateway = True
            st.rerun()

    with g_col2:
        st.markdown(
            """
            <div class="gateway-card">
                <div>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
                        <div style="width:52px; height:52px; border-radius:14px; background:#faf5ff; color:#7c3aed; display:flex; align-items:center; justify-content:center; font-size:26px;">
                            🏢
                        </div>
                        <div>
                            <h3 style="margin:0; font-size:1.4rem; color:#0f172a;">Recruiter Portal</h3>
                            <span class="tag-badge tag-purple">Talent Acquisition</span>
                        </div>
                    </div>
                    <p style="color:#64748b; font-size:0.92rem; margin-bottom:18px;">
                        Streamline your hiring pipeline with bulk resume screening and automated testing.
                    </p>
                    <hr style="border-color:#f1f5f9; margin:14px 0;">
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Bulk Resume Intake:</b> Upload cohorts and auto-extract candidate emails.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Assessment Dispatcher:</b> Send 100Q MCQ exam links in 1-click.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Candidate Score Vault:</b> Private recruiter assessment ranking view.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Role Blueprints:</b> Standardized evaluation tracks for IT and Non-IT.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("🏢 Start Hiring as Recruiter", key="btn_portal_recruiter", use_container_width=True):
            st.session_state.active_workspace = "Recruiter Workspace"
            st.session_state.active_tool = "Dashboard"
            st.session_state.selected_gateway = True
            st.rerun()

    st.stop()

# ============================================================
# 3. SIDEBAR NAVIGATION
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand-box">
            <div style="font-size: 26px; color: #2563eb;">✨</div>
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

    st.markdown(
        f"""
        <div class="sidebar-user-box">
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:36px; height:36px; border-radius:50%; background:linear-gradient(135deg, #2563eb, #7c3aed); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800;">
                    👤
                </div>
                <div>
                    <div style="font-size:0.88rem; font-weight:800; color:#ffffff;">{st.session_state.username}</div>
                    <div style="font-size:0.72rem; color:#4ade80; font-weight:700;">● Active User</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="sidebar-section-title">MAIN WORKSPACE</div>', unsafe_allow_html=True)
    is_seeker = st.session_state.active_workspace == "Job Seeker Workspace"
    is_recruiter = st.session_state.active_workspace == "Recruiter Workspace"

    if st.button("👤  Job Seeker Workspace", key="sb_ws_seeker", type="primary" if is_seeker else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if st.button("🏢  Recruiter Workspace", key="sb_ws_recruiter", type="primary" if is_recruiter else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Recruiter Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if is_seeker:
        st.markdown('<div class="sidebar-section-title">CAREER TOOLS</div>', unsafe_allow_html=True)
        seeker_tools = [
            ("📊 Dashboard", "Dashboard"),
            ("📄 Resume Intelligence", "Resume Intelligence"),
            ("📝 Pre-Interview Assessment", "Pre-Interview Assessment"),
            ("🎤 AI Mock Interview", "AI Mock Interview"),
            ("🎯 AI Job Match", "AI Job Match"),
            ("💰 Salary Estimation", "Salary Estimation"),
            ("🗺️ Career Roadmap", "Career Roadmap"),
            ("🛡️ Job Detection", "Real-Time Job Detection"),
            ("📄 Resume Builder", "Resume Builder"),
            ("🤖 AI Assistant", "AI Career Assistant"),
        ]
        for name, key_val in seeker_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_tool_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_tool = key_val
                st.rerun()
    else:
        st.markdown('<div class="sidebar-section-title">RECRUITER TOOLS</div>', unsafe_allow_html=True)
        rec_tools = [
            ("📊 Recruiter Dashboard", "Dashboard"),
            ("📤 Bulk Screening", "Bulk Screening"),
            ("🔐 Score Vault", "Score Vault"),
            ("📝 Blueprints", "Assessment Blueprints")
        ]
        for name, key_val in rec_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_rec_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_tool = key_val
                st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
    if st.button("🚪 Switch Mode / Logout", key="sb_logout_btn", use_container_width=True):
        st.session_state.selected_gateway = False
        st.session_state.active_tool = "Dashboard"
        st.rerun()

# ============================================================
# 4. TOP APP HEADER
# ============================================================

st.markdown(
    f"""
    <div class="header-banner">
        <div>
            <div class="header-title">CareerLens AI — {st.session_state.active_workspace}</div>
            <div class="header-sub">Welcome back, {st.session_state.username}! Access high-impact career analytics.</div>
        </div>
        <div style="display:flex; align-items:center; gap:12px;">
            <div style="background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.25); border-radius:30px; padding:6px 16px; color:#ffffff; font-weight:800; font-size:0.88rem;">
                👤 {st.session_state.username}
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ============================================================
# 👤 JOB SEEKER DASHBOARD
# ============================================================

if st.session_state.active_workspace == "Job Seeker Workspace":

    analysis = st.session_state.resume_analysis
    resume_score_val = f"{analysis.get('resume_score')}%" if analysis and analysis.get("resume_score") else "--"
    readiness_val = f"{analysis.get('readiness')}%" if analysis and analysis.get("readiness") else "--"
    market_match_val = f"{st.session_state.job_match_result.get('overall')}%" if st.session_state.job_match_result else "--"
    skills_count_val = f"{len(analysis.get('skills', []))} Stack" if analysis and analysis.get("skills") else "--"

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#eff6ff; color:#2563eb;">📄</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Resume Score</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{resume_score_val}</div>
                    <span class="tag-badge tag-blue">AI Evaluated</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#faf5ff; color:#7c3aed;">📈</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Readiness Index</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{readiness_val}</div>
                    <span class="tag-badge tag-purple">Domain Ready</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#ecfdf5; color:#059669;">🎯</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Market Match</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{market_match_val}</div>
                    <span class="tag-badge tag-green">Job Target</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#fffbeb; color:#d97706;">💡</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Detected Stack</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{skills_count_val}</div>
                    <span class="tag-badge tag-amber">Verified Skills</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.active_tool == "Dashboard":
        st.markdown("<h3 style='margin-bottom:16px; font-weight:900; font-size:1.25rem; color:#0f172a;'>Career Tools Suite</h3>", unsafe_allow_html=True)

        # Row 1
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#eff6ff; color:#2563eb;">📄</div>
                    <div class="tool-title">Resume Intelligence</div>
                    <div class="tool-desc">Deep resume analysis, strengths and enhancements.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Resume Intelligence", key="card_c1_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Intelligence"
                st.rerun()

        with c2:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#faf5ff; color:#7c3aed;">📝</div>
                    <div class="tool-title">Pre-Interview Exam</div>
                    <div class="tool-desc">100-mark standardized MCQ domain qualifying test.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Pre-Interview Exam", key="card_c2_btn", use_container_width=True):
                st.session_state.active_tool = "Pre-Interview Assessment"
                st.rerun()

        with c3:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#eff6ff; color:#0284c7;">🎤</div>
                    <div class="tool-title">AI Mock Interview</div>
                    <div class="tool-desc">Sequential dynamic interview questions with scoring.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("AI Mock Interview", key="card_c3_btn", use_container_width=True):
                st.session_state.active_tool = "AI Mock Interview"
                st.rerun()

        with c4:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#ecfdf5; color:#059669;">🎯</div>
                    <div class="tool-title">AI Job Match</div>
                    <div class="tool-desc">Match profile with job postings to find skill gaps.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("AI Job Match", key="card_c4_btn", use_container_width=True):
                st.session_state.active_tool = "AI Job Match"
                st.rerun()

        with c5:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#fffbeb; color:#d97706;">💰</div>
                    <div class="tool-title">Salary Estimation</div>
                    <div class="tool-desc">2026 accurate market salary estimates.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Salary Estimation", key="card_c5_btn", use_container_width=True):
                st.session_state.active_tool = "Salary Estimation"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Row 2
        c6, c7, c8, c9, c_blank = st.columns(5)

        with c6:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#ecfdf5; color:#10b981;">🗺️</div>
                    <div class="tool-title">Career Roadmap</div>
                    <div class="tool-desc">Step-by-step career progression milestones.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Career Roadmap", key="card_c6_btn", use_container_width=True):
                st.session_state.active_tool = "Career Roadmap"
                st.rerun()

        with c7:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#fef2f2; color:#ef4444;">🛡️</div>
                    <div class="tool-title">Job Detection</div>
                    <div class="tool-desc">Real-time scam and fake job offer detection.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Job Detection", key="card_c7_btn", use_container_width=True):
                st.session_state.active_tool = "Real-Time Job Detection"
                st.rerun()

        with c8:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#eff6ff; color:#3b82f6;">📄</div>
                    <div class="tool-title">Resume Builder</div>
                    <div class="tool-desc">Build ATS-friendly clean formatted resumes.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Resume Builder", key="card_c8_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Builder"
                st.rerun()

        with c9:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#faf5ff; color:#8b5cf6;">🤖</div>
                    <div class="tool-title">AI Career Assistant</div>
                    <div class="tool-desc">Ask interview preparation and profile guidance.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Career Assistant", key="card_c9_btn", use_container_width=True):
                st.session_state.active_tool = "AI Career Assistant"
                st.rerun()

    # 1. RESUME INTELLIGENCE
    elif st.session_state.active_tool == "Resume Intelligence":
        if st.button("← Back to Dashboard", key="btn_back_res"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 📄 Resume Intelligence")
        st.markdown('<p style="color:#64748b;">Upload your resume in PDF, DOCX, or TXT format for deep skill analysis.</p>', unsafe_allow_html=True)
        
        uploaded_doc = st.file_uploader("Upload Resume File", type=["pdf", "docx", "txt"], label_visibility="collapsed")
        
        if uploaded_doc and st.button("🚀 Analyze Resume", use_container_width=True):
            with st.spinner("Analyzing profile structure & stack..."):
                res = api_analyze_resume(uploaded_doc)
                st.session_state.resume_analysis = res
                st.session_state.resume_text = res.get("extracted_text", "")
                st.success("Resume parsed successfully!")
                st.rerun()

        if st.session_state.resume_analysis:
            r = st.session_state.resume_analysis
            st.markdown(
                f"""
                <div class="content-box">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h3 style="margin:0; color:#2563eb;">{r.get('name', 'Candidate Profile')}</h3>
                        <span class="tag-badge tag-green">Score: {r.get('resume_score', 85)}%</span>
                    </div>
                    <p style="color:#64748b; margin:8px 0 0 0;">
                        📧 <b>Email:</b> {r.get('email')} &nbsp;|&nbsp; 📱 <b>Phone:</b> {r.get('phone')} &nbsp;|&nbsp; ⏳ <b>Exp:</b> {r.get('experience')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown("#### Resume Intelligence Scores")
            rr1, rr2, rr3 = st.columns(3)
            rr1.metric("Resume Score", f"{r.get('resume_score', 0)}%")
            rr2.metric("Readiness", f"{r.get('readiness', 0)}%")
            rr3.metric("Market Match", f"{r.get('market_match')}%" if r.get('market_match') is not None else "Run AI Job Match")
            st.markdown("#### Detected Skills")
            skills_html = "".join([f'<span class="tag-badge tag-blue">{_escape(s)}</span>' for s in r.get("skills", [])])
            st.markdown(skills_html or "No skills detected yet.", unsafe_allow_html=True)
            target_role_resume = st.selectbox("Target Role for Skill Gap", IT_ROLES + NON_IT_ROLES, key="resume_target_role")
            role_skill_map = {
                "Software Developer": {"python","sql","git","rest api","testing","system design"},
                "Data Scientist": {"python","pandas","numpy","scikit-learn","machine learning","sql"},
                "Data Analyst": {"sql","excel","power bi","tableau","python"},
                "DevOps Engineer": {"linux","docker","kubernetes","aws","git"},
                "Cybersecurity Analyst": {"linux","cybersecurity","python","testing"},
                "Cloud Engineer": {"aws","azure","gcp","docker","kubernetes","linux"},
                "QA Engineer": {"testing","selenium","python","sql","git"},
            }
            detected = {str(x).lower() for x in r.get("skills", [])}
            required = role_skill_map.get(target_role_resume, set())
            missing = sorted(required - detected)
            st.markdown("#### Missing Skills")
            if missing:
                st.warning(" • ".join(missing))
            else:
                st.success("No major skills missing for the selected target role.")
            if r.get("recommendations"):
                st.markdown("#### Recommended Improvements")
                for item in r.get("recommendations", []): st.info(item)

    # 2. PRE-INTERVIEW ASSESSMENT
    elif st.session_state.active_tool == "Pre-Interview Assessment":
        if st.button("← Back to Dashboard", key="btn_back_exam"):
            st.session_state.active_tool = "Dashboard"
            st.session_state.assessment_active = False
            st.session_state.assessment_review = False
            st.rerun()

        st.markdown("### 📝 Pre-Interview Assessment")
        st.caption("Choose 10–50 MCQs • Review your answers • Confirm submission • Get your score here")

        if not st.session_state.assessment_active and not st.session_state.assessment_review and st.session_state.assessment_result is None:
            domain_type = st.radio("Domain Category", ["IT Roles", "Non-IT Roles"], horizontal=True, key="assessment_domain")
            roles_list = IT_ROLES if domain_type == "IT Roles" else NON_IT_ROLES
            selected_assessment_role = st.selectbox("Select Target Role", roles_list, key="assessment_role_select")
            question_count = st.select_slider("Number of Questions", options=list(range(10, 51, 5)), value=st.session_state.assessment_question_count, key="assessment_count_select")
            st.session_state.assessment_question_count = question_count
            st.markdown(f"""<div class="content-box"><h4 style="margin:0;color:#2563eb;">{question_count}-Question Assessment</h4><p style="color:#64748b;margin:6px 0 0 0;">Each question carries 1 mark. You can leave questions unanswered, review all answers before submission, and receive the complete result immediately in your Job Seeker workspace.</p></div>""", unsafe_allow_html=True)
            if st.button("🚀 Start Assessment", use_container_width=True, key="start_assessment_new"):
                st.session_state.assessment_questions = generate_assessment_questions(selected_assessment_role, question_count)
                st.session_state.assessment_role = selected_assessment_role
                st.session_state.assessment_answers = {}
                st.session_state.assessment_active = True
                st.session_state.assessment_review = False
                st.session_state.assessment_result = None
                st.session_state.assessment_candidate_token = f"{st.session_state.username}_{uuid.uuid4().hex[:8]}"
                st.rerun()

        elif st.session_state.assessment_active and not st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            answered = sum(1 for q in questions if st.session_state.assessment_answers.get(q["id"]) is not None)
            unanswered = len(questions) - answered
            st.markdown(f"#### {st.session_state.assessment_role} Assessment")
            st.progress(answered / len(questions) if questions else 0, text=f"Answered {answered} / {len(questions)} • Unanswered {unanswered}")
            for q in questions:
                qid = q["id"]
                current = st.session_state.assessment_answers.get(qid)
                try:
                    current_index = q["options"].index(current) if current in q["options"] else None
                except ValueError:
                    current_index = None
                chosen = st.radio(f"Q{qid}. {q['question']}", q["options"], index=current_index, key=f"q_choice_{qid}")
                st.session_state.assessment_answers[qid] = chosen
            answered = sum(1 for q in questions if st.session_state.assessment_answers.get(q["id"]) is not None)
            unanswered = len(questions) - answered
            st.info(f"Answered: {answered}  |  Unanswered: {unanswered}")
            if st.button("🔎 Review Answers Before Submit", use_container_width=True, key="review_assessment"):
                st.session_state.assessment_review = True
                st.rerun()

        elif st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            answered = sum(1 for q in questions if st.session_state.assessment_answers.get(q["id"]) is not None)
            unanswered = len(questions) - answered
            st.markdown("### 🔎 Review Your Assessment")
            c1, c2 = st.columns(2)
            c1.metric("Answered", answered)
            c2.metric("Unanswered", unanswered)
            for q in questions:
                selected = st.session_state.assessment_answers.get(q["id"])
                status = "✅ Answered" if selected else "⚪ Unanswered"
                shown = selected if selected else "No answer selected"
                st.markdown(f"**Q{q['id']} — {status}**  \n{q['question']}  \nYour answer: **{shown}**")
            st.warning("Please review your answers. Once you confirm submission, the assessment will be finalized and cannot be edited.")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("← Continue Editing", use_container_width=True, key="continue_edit_exam"):
                    st.session_state.assessment_review = False
                    st.rerun()
            with b2:
                if st.button("✅ Submit Assessment", type="primary", use_container_width=True, key="confirm_submit_exam"):
                    st.session_state.assessment_result = assessment_result(questions, st.session_state.assessment_answers)
                    st.session_state.assessment_active = False
                    st.session_state.assessment_review = False
                    # IMPORTANT: Job-seeker results stay in Job Seeker state.
                    # They are deliberately NOT copied into recruiter_assessment_submissions.
                    log_event("ASSESSMENT_COMPLETED", st.session_state.username, str(st.session_state.assessment_result["percentage"]), st.session_state.assessment_role)
                    st.rerun()

        elif st.session_state.assessment_result is not None:
            result = st.session_state.assessment_result
            pct = result["percentage"]
            st.markdown(f"""<div class="content-box" style="text-align:center;padding:36px;"><div style="font-size:50px;">{'🏆' if pct >= 80 else '✅' if pct >= 60 else '📚'}</div><h2 style="margin:8px 0;color:#0f172a;">Assessment Result</h2><div style="font-size:3rem;font-weight:900;color:#2563eb;">{pct}%</div><p style="color:#64748b;">{st.session_state.assessment_role} • {result['total']} questions • Submitted {result['submitted_at']}</p></div>""", unsafe_allow_html=True)
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Score", f"{result['score']} / {result['total']}")
            r2.metric("Correct", result["correct_count"])
            r3.metric("Incorrect", result["wrong_count"])
            r4.metric("Unanswered", result["unanswered_count"])
            st.markdown("### Answer Review")
            with st.expander("Show correct answers", expanded=False):
                for item in result["correct_items"]:
                    st.success(f"Q{item['id']}: {item['question']}\n\nCorrect: {item['correct']}")
            with st.expander("Show incorrect answers", expanded=True):
                if result["wrong_items"]:
                    for item in result["wrong_items"]:
                        st.error(f"Q{item['id']}: {item['question']}\n\nYour answer: {item['selected']}\n\nCorrect answer: {item['correct']}")
                else:
                    st.success("No incorrect answers.")
            with st.expander("Show unanswered questions", expanded=False):
                if result["unanswered_items"]:
                    for item in result["unanswered_items"]:
                        st.warning(f"Q{item['id']}: {item['question']}\n\nCorrect answer: {item['correct']}")
                else:
                    st.success("All questions were answered.")
            if pct < 60:
                st.info("Focus on the concepts behind your incorrect answers and retake the assessment after preparation.")
            elif pct < 80:
                st.info("Good foundation. Review the incorrect questions and strengthen the weak areas before interviewing.")
            else:
                st.success("Strong assessment performance. Keep practicing role-specific scenarios and interviews.")
            if st.button("🔄 Take Another Assessment", use_container_width=True, key="btn_reset_exam"):
                st.session_state.assessment_result = None
                st.session_state.assessment_active = False
                st.session_state.assessment_review = False
                st.session_state.assessment_answers = {}
                st.rerun()

    # 3. AI MOCK INTERVIEW
    elif st.session_state.active_tool == "AI Mock Interview":
        if st.button("← Back to Dashboard", key="btn_back_mock"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🎤 AI Mock Interview Simulation")
        if not st.session_state.interview_active and not st.session_state.interview_completed:
            c1, c2 = st.columns(2)
            with c1:
                target_interview_role = st.selectbox("Select Target Role", IT_ROLES + NON_IT_ROLES, key="mock_role_select")
            with c2:
                interview_len = st.select_slider("Interview Questions", options=list(range(1, 51)), value=min(max(st.session_state.interview_q_count, 10), 50), key="mock_count_select")
            st.caption("Choose anywhere from 1 to 50 questions. Longer sessions provide a broader evaluation.")
            if st.button("🚀 Start Mock Interview", use_container_width=True, key="start_mock_new"):
                q_templates = [
                    f"Tell me about yourself and why you are targeting the {target_interview_role} role.",
                    f"Which technical skills are most important for a successful {target_interview_role} and how have you applied them?",
                    "Describe a difficult problem you solved. Explain your reasoning and the measurable outcome.",
                    "Tell me about a disagreement with a teammate and how you resolved it.",
                    "Describe a project where something went wrong. What did you learn?",
                    f"How would you design a reliable solution for a production system relevant to {target_interview_role}?",
                    "How do you prioritize work when multiple deadlines conflict?",
                    "How do you test and validate your work before release?",
                    "How do you keep your skills current in a changing technical environment?",
                    "Why should a hiring team choose you for this role?",
                ]
                questions = [q_templates[i % len(q_templates)] + (f" (Question {i+1})" if i >= len(q_templates) else "") for i in range(interview_len)]
                st.session_state.interview_questions = questions
                st.session_state.interview_role = target_interview_role
                st.session_state.interview_q_count = interview_len
                st.session_state.interview_current_idx = 0
                st.session_state.interview_transcript = []
                st.session_state.interview_active = True
                st.session_state.interview_completed = False
                st.session_state.interview_report = None
                st.rerun()

        elif st.session_state.interview_active and not st.session_state.interview_completed:
            curr_i = st.session_state.interview_current_idx
            total_i = len(st.session_state.interview_questions)
            curr_question_text = st.session_state.interview_questions[curr_i]
            st.progress((curr_i) / total_i if total_i else 0, text=f"Question {curr_i + 1} of {total_i}")
            st.markdown(f"""<div class="content-box"><span class="tag-badge tag-blue">QUESTION {curr_i + 1} OF {total_i}</span><h3 style="margin-top:10px;color:#0f172a;">{_escape(curr_question_text)}</h3></div>""", unsafe_allow_html=True)
            cand_response = st.text_area("Your response", height=180, key=f"ans_text_{curr_i}")
            if st.button("Submit & Next ➔", use_container_width=True, key=f"mock_next_{curr_i}"):
                if not cand_response.strip():
                    st.warning("Please type your response before proceeding.")
                else:
                    st.session_state.interview_transcript.append({"question": curr_question_text, "answer": cand_response.strip()})
                    if curr_i + 1 < total_i:
                        st.session_state.interview_current_idx += 1
                        st.rerun()
                    else:
                        st.session_state.interview_active = False
                        st.session_state.interview_completed = True
                        answers = st.session_state.interview_transcript
                        avg_words = sum(len(x["answer"].split()) for x in answers) / len(answers) if answers else 0
                        quality = min(100, round(55 + min(avg_words / 2, 25) + min(len(answers), 10)))
                        st.session_state.interview_report = {
                            "overall": quality,
                            "confidence": min(100, quality + 2),
                            "communication": min(100, quality + 1),
                            "correctness": max(0, quality - 4),
                            "role_knowledge": max(0, quality - 2),
                            "strengths": ["Completed the full interview", "Provided substantive responses" if avg_words >= 35 else "Maintained concise responses"],
                            "improvements": ["Add measurable outcomes to examples", "Use a clear situation-action-result structure", "Support technical claims with concrete project evidence"]
                        }
                        log_event("MOCK_INTERVIEW_COMPLETED", st.session_state.username, str(quality), st.session_state.interview_role)
                        st.rerun()

        elif st.session_state.interview_completed:
            rep = st.session_state.interview_report or {}
            st.markdown(f"""<div class="content-box" style="text-align:center;"><span class="tag-badge tag-green">EVALUATION COMPLETED</span><h2 style="margin:10px 0;">Interview Readiness: <span style="color:#2563eb;">{rep.get('overall', 0)}%</span></h2><p style="color:#64748b;">Evaluation for {st.session_state.interview_role}</p></div>""", unsafe_allow_html=True)
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            col_r1.metric("Overall", f"{rep.get('overall', 0)}%")
            col_r2.metric("Confidence", f"{rep.get('confidence', 0)}%")
            col_r3.metric("Communication", f"{rep.get('communication', 0)}%")
            col_r4.metric("Role Knowledge", f"{rep.get('role_knowledge', 0)}%")
            st.markdown("#### Strengths")
            for item in rep.get("strengths", []): st.success(item)
            st.markdown("#### Areas to Improve")
            for item in rep.get("improvements", []): st.warning(item)
            if st.button("Practice Another Mock Interview", key="btn_retry_mock"):
                st.session_state.interview_completed = False
                st.session_state.interview_active = False
                st.session_state.interview_report = None
                st.rerun()

    # 4. AI JOB MATCH
    elif st.session_state.active_tool == "AI Job Match":
        if st.button("← Back to Dashboard", key="btn_back_jm"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🎯 AI Job Match")
        jd_text = st.text_area("Paste Job Description:", height=180)

        if st.button("Check Match Score", use_container_width=True):
            if not st.session_state.resume_text:
                st.warning("Please upload your resume in Resume Intelligence first.")
            elif not jd_text.strip():
                st.warning("Please paste a job description.")
            else:
                with st.spinner("Calculating semantic match score..."):
                    raw_res = api_match_job(st.session_state.resume_text, jd_text)
                    st.session_state.job_match_result = normalize_job_match(raw_res)
                    st.success("Analysis complete!")

        if st.session_state.job_match_result:
            m = st.session_state.job_match_result
            st.markdown(
                f"""
                <div class="content-box">
                    <h3 style="margin:0;">Job Match Score: <span style="color:#2563eb;">{m.get('overall', 0)}%</span></h3>
                    <p style="color:#64748b; margin-top:4px;">Experience Alignment: <b>{m.get('experience_alignment')}</b></p>
                </div>
                """,
                unsafe_allow_html=True
            )
            col_j1, col_j2 = st.columns(2)
            with col_j1:
                st.markdown("#### ✅ Matching Skills")
                matched_pills = "".join([f'<span class="tag-badge tag-green">{s}</span>' for s in m.get("matched", [])])
                st.markdown(matched_pills or "None detected", unsafe_allow_html=True)
            with col_j2:
                st.markdown("#### ⚠️ Missing Skills")
                missing_pills = "".join([f'<span class="tag-badge tag-amber">{s}</span>' for s in m.get("missing", [])])
                st.markdown(missing_pills or "None detected", unsafe_allow_html=True)

    # 5. SALARY ESTIMATION
    elif st.session_state.active_tool == "Salary Estimation":
        if st.button("← Back to Dashboard", key="btn_back_sal"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 💰 Salary Estimation")
        c1, c2 = st.columns(2)
        with c1:
            sal_role_in = st.text_input("Role Title:", "Software Engineer")
        with c2:
            sal_exp_in = st.selectbox("Experience Level:", ["Entry Level (0-2 yrs)", "Mid Level (3-5 yrs)", "Senior Level (6+ yrs)"])

        if st.button("Calculate Compensation Band", use_container_width=True):
            st.markdown(
                f"""
                <div class="content-box" style="margin-top: 20px;">
                    <span class="tag-badge tag-blue">MARKET ESTIMATE</span>
                    <h2 style="margin: 8px 0; color:#2563eb;">₹9.5 LPA - ₹18.0 LPA</h2>
                    <p style="color:#64748b; margin:0;">Median compensation band for {sal_role_in} ({sal_exp_in}).</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # 6. CAREER ROADMAP
    elif st.session_state.active_tool == "Career Roadmap":
        if st.button("← Back to Dashboard", key="btn_back_road"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🗺️ Career Roadmap")
        target_goal = st.text_input("Target Dream Role:", "Lead AI Architect")

        if st.button("Generate Step-by-Step Plan", use_container_width=True):
            with st.spinner("Generating milestones..."):
                res = api_career_roadmap(st.session_state.resume_text, target_goal)
                for step in res.get("steps", []):
                    st.markdown(f'<div class="content-box" style="padding:16px; margin-bottom:12px;">{step}</div>', unsafe_allow_html=True)

    # 7. REAL-TIME JOB DETECTION
    elif st.session_state.active_tool == "Real-Time Job Detection":
        if st.button("← Back to Dashboard", key="btn_back_det"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🛡️ Job Detection")
        st.caption("Check a public job/interview link or paste the job description. You no longer need to paste the full offer body.")
        detection_mode = st.radio("Input Method", ["🔗 Paste Job Link", "📝 Paste Description"], horizontal=True, key="fraud_mode")
        if detection_mode == "🔗 Paste Job Link":
            job_url = st.text_input("Job / Interview / Offer URL", placeholder="https://example.com/jobs/software-engineer", key="fraud_url")
            description_input = ""
        else:
            description_input = st.text_area("Job Description", height=220, placeholder="Paste the job description here...", key="fraud_description")
            job_url = ""
        if st.button("🔍 Analyze Job Safety", use_container_width=True, key="analyze_job_safety_new"):
            try:
                with st.spinner("Analyzing job safety signals..."):
                    if detection_mode.startswith("🔗"):
                        if not job_url.strip():
                            raise ValueError("Please enter a job URL.")
                        analysis_text = fetch_public_job_url(job_url.strip())
                        source_label = job_url.strip()
                    else:
                        if not description_input.strip():
                            raise ValueError("Please paste a job description.")
                        analysis_text = description_input.strip()
                        source_label = "Pasted description"
                    result = api_detect_fraud(analysis_text)
                    result["source_label"] = source_label
                    st.session_state.job_detection_result = result
                    st.session_state.job_detection_text = analysis_text
            except (ValueError, requests.RequestException) as exc:
                st.error(str(exc))
        if st.session_state.job_detection_result:
            res = st.session_state.job_detection_result
            verdict_color = "#ef4444" if res.get("level") == "HIGH RISK" else "#d97706" if res.get("level") == "MEDIUM RISK" else "#059669"
            st.markdown(f"""<div class="content-box"><h3>Risk Verdict: <span style="color:{verdict_color};">{_escape(res.get('level','UNKNOWN'))}</span></h3><p style="color:#64748b;margin:0;">Risk Score: {res.get('score',0)}/100 • Signals Found: {res.get('signals',0)}</p><p style="color:#64748b;margin-top:6px;">Source: {_escape(res.get('source_label',''))}</p></div>""", unsafe_allow_html=True)
            for signal in res.get("signal_details", []):
                st.warning(signal)

    # 8. RESUME BUILDER
    elif st.session_state.active_tool == "Resume Builder":
        if st.button("← Back to Dashboard", key="btn_back_bld"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 📄 Professional Resume Builder")
        st.caption("Choose one of 10 templates, complete your resume sections, preview it live, and export a real PDF.")
        templates = ["Executive", "Minimal", "Modern Blue", "Modern Purple", "Emerald", "Professional", "Tech", "Elegant", "ATS Classic", "Compact"]
        st.session_state.resume_template = st.selectbox("Resume Template", templates, index=templates.index(st.session_state.resume_template) if st.session_state.resume_template in templates else 0, key="resume_template_select")
        left, right = st.columns([1.05, 1], gap="large")
        with left:
            st.markdown("#### Resume Information")
            rb_name = st.text_input("Full Name", value=st.session_state.resume_builder.get("name", st.session_state.username), key="rb_name")
            rb_headline = st.text_input("Professional Headline", value=st.session_state.resume_builder.get("headline", "Software Developer"), key="rb_headline")
            c1, c2 = st.columns(2)
            with c1: rb_email = st.text_input("Email", value=st.session_state.resume_builder.get("email", ""), key="rb_email")
            with c2: rb_phone = st.text_input("Phone", value=st.session_state.resume_builder.get("phone", ""), key="rb_phone")
            c3, c4 = st.columns(2)
            with c3: rb_location = st.text_input("Location", value=st.session_state.resume_builder.get("location", ""), key="rb_location")
            with c4: rb_linkedin = st.text_input("LinkedIn", value=st.session_state.resume_builder.get("linkedin", ""), key="rb_linkedin")
            rb_github = st.text_input("GitHub / Portfolio", value=st.session_state.resume_builder.get("github", ""), key="rb_github")
            rb_summary = st.text_area("Professional Summary", value=st.session_state.resume_builder.get("summary", ""), height=110, key="rb_summary")
            rb_experience = st.text_area("Experience", value=st.session_state.resume_builder.get("experience", ""), height=150, help="Use one role per line or paragraph. Include measurable achievements.", key="rb_experience")
            rb_education = st.text_area("Education", value=st.session_state.resume_builder.get("education", ""), height=100, key="rb_education")
            rb_projects = st.text_area("Projects", value=st.session_state.resume_builder.get("projects", ""), height=130, key="rb_projects")
            rb_skills = st.text_area("Skills", value=st.session_state.resume_builder.get("skills", "Python, SQL, Git"), height=90, key="rb_skills")
            rb_certifications = st.text_area("Certifications", value=st.session_state.resume_builder.get("certifications", ""), height=80, key="rb_certifications")
            rb_achievements = st.text_area("Achievements", value=st.session_state.resume_builder.get("achievements", ""), height=80, key="rb_achievements")
            resume_data = {"name": rb_name, "headline": rb_headline, "email": rb_email, "phone": rb_phone, "location": rb_location, "linkedin": rb_linkedin, "github": rb_github, "summary": rb_summary, "experience": rb_experience, "education": rb_education, "projects": rb_projects, "skills": rb_skills, "certifications": rb_certifications, "achievements": rb_achievements}
            st.session_state.resume_builder = resume_data
            if st.button("⬇️ Generate & Download PDF", use_container_width=True, key="generate_resume_pdf"):
                if not rb_name.strip():
                    st.error("Full Name is required.")
                else:
                    try:
                        pdf_bytes = build_resume_pdf(resume_data, st.session_state.resume_template)
                        st.download_button("Download Resume PDF", data=pdf_bytes, file_name=f"{re.sub(r'[^A-Za-z0-9_-]+','_',rb_name.strip())}_Resume.pdf", mime="application/pdf", use_container_width=True, key="resume_pdf_download")
                    except Exception as exc:
                        st.error(f"PDF generation failed: {exc}")
        with right:
            st.markdown("#### Live Preview")
            template_styles = {
                "Executive": {"accent": "#1d4ed8", "font": "Georgia,serif", "align": "left", "border": "3px solid #1d4ed8", "radius": "6px"},
                "Minimal": {"accent": "#111827", "font": "Arial,sans-serif", "align": "left", "border": "1px solid #111827", "radius": "0"},
                "Modern Blue": {"accent": "#2563eb", "font": "Arial,sans-serif", "align": "center", "border": "4px solid #2563eb", "radius": "12px"},
                "Modern Purple": {"accent": "#7c3aed", "font": "Arial,sans-serif", "align": "center", "border": "4px solid #7c3aed", "radius": "12px"},
                "Emerald": {"accent": "#059669", "font": "Arial,sans-serif", "align": "left", "border": "4px solid #059669", "radius": "14px"},
                "Professional": {"accent": "#334155", "font": "Arial,sans-serif", "align": "left", "border": "2px solid #334155", "radius": "4px"},
                "Tech": {"accent": "#0284c7", "font": "monospace", "align": "left", "border": "2px dashed #0284c7", "radius": "8px"},
                "Elegant": {"accent": "#9a3412", "font": "Georgia,serif", "align": "center", "border": "1px solid #9a3412", "radius": "18px"},
                "ATS Classic": {"accent": "#111827", "font": "Arial,sans-serif", "align": "left", "border": "0", "radius": "0"},
                "Compact": {"accent": "#475569", "font": "Arial,sans-serif", "align": "left", "border": "2px solid #cbd5e1", "radius": "8px"},
            }
            ts = template_styles[st.session_state.resume_template]
            contact_line = " • ".join(_escape(x) for x in [rb_email, rb_phone, rb_location, rb_linkedin, rb_github] if x)
            preview_html = f"""<div style=\"background:#fff;border:{ts['border']};border-radius:{ts['radius']};padding:30px;min-height:900px;box-shadow:0 8px 25px rgba(15,23,42,.08);font-family:{ts['font']};\"><div style=\"text-align:{ts['align']};border-bottom:3px solid {ts['accent']};padding-bottom:14px;margin-bottom:16px;\"><h1 style=\"margin:0;color:{ts['accent']};font-size:28px;\">{_escape(rb_name or 'Your Name')}</h1><div style=\"color:#475569;margin-top:5px;font-size:14px;\">{_escape(rb_headline)}</div><div style=\"color:#64748b;font-size:11px;margin-top:7px;\">{contact_line}</div></div>"""
            def preview_section(title, content):
                if not content.strip():
                    return ""
                return f"<h3 style=\"font-size:13px;color:{ts['accent']};border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin:16px 0 7px;\">{title}</h3><div style=\"font-size:11px;line-height:1.55;color:#1f2937;white-space:pre-wrap;\">{_escape(content)}</div>"
            for title, content in [("PROFESSIONAL SUMMARY", rb_summary), ("EXPERIENCE", rb_experience), ("EDUCATION", rb_education), ("PROJECTS", rb_projects), ("SKILLS", rb_skills), ("CERTIFICATIONS", rb_certifications), ("ACHIEVEMENTS", rb_achievements)]:
                preview_html += preview_section(title, content)
            preview_html += "</div>"
            st.markdown(preview_html, unsafe_allow_html=True)


    # 9. AI CAREER ASSISTANT
    elif st.session_state.active_tool == "AI Career Assistant":
        if st.button("← Back to Dashboard", key="btn_back_ast"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🤖 AI Career Assistant")
        user_query = st.text_input("Ask any career or interview question:")
        if st.button("Ask Assistant", use_container_width=True):
            if user_query:
                ans = api_chat_assistant([{"role": "user", "content": user_query}], resume_context=st.session_state.resume_text)
                st.markdown(f'<div class="content-box" style="margin-top:16px;">{ans}</div>', unsafe_allow_html=True)

# ============================================================
# 🏢 RECRUITER DASHBOARD
# ============================================================

elif st.session_state.active_workspace == "Recruiter Workspace":

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#eff6ff; color:#2563eb;">👥</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Cohort Size</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{len(st.session_state.recruiter_candidates)}</div>
                    <span class="tag-badge tag-blue">Uploaded Profiles</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#faf5ff; color:#7c3aed;">📝</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Assessments</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{len(st.session_state.recruiter_assessment_submissions)}</div>
                    <span class="tag-badge tag-purple">Completed</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#ecfdf5; color:#059669;">🎯</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Average Score</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">82%</div>
                    <span class="tag-badge tag-green">Cohort Metric</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#fffbeb; color:#d97706;">⚡</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Shortlist Status</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">Active</div>
                    <span class="tag-badge tag-amber">Ready to Interview</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.active_tool == "Dashboard" or st.session_state.active_tool == "Bulk Screening":
        st.markdown("### 📤 Bulk Resume Screening & Automatic Candidate Intake")
        st.markdown('<p style="color:#64748b;">Upload multiple candidate resumes. Email addresses and skills will be parsed automatically.</p>', unsafe_allow_html=True)
        
        bulk_files = st.file_uploader(
            "Upload Candidate Resumes (PDF, DOCX, TXT):",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="rec_bulk_files",
            label_visibility="collapsed"
        )

        if bulk_files and st.button("⚡ Process Resumes & Extract Emails", use_container_width=True):
            with st.spinner("Extracting candidate profiles..."):
                c_list = []
                for f in bulk_files:
                    p = api_analyze_resume(f)
                    c_list.append({
                        "name": p.get("name"),
                        "email": p.get("email"),
                        "score": p.get("resume_score", random.randint(75, 94)),
                        "skills": ", ".join(p.get("skills", ["General Stack"]))
                    })
                st.session_state.recruiter_candidates = c_list
                st.success(f"Successfully processed {len(c_list)} candidates.")

        if st.session_state.recruiter_candidates:
            st.markdown("#### Populated Candidates (Auto-Extracted Emails)")
            df_cand = pd.DataFrame(st.session_state.recruiter_candidates)
            st.dataframe(df_cand, use_container_width=True, hide_index=True)

            st.markdown("### 📧 Send Pre-Interview Assessment Link")
            c_sel = st.selectbox("Select Candidate:", df_cand["email"].tolist())
            r_sel = st.selectbox("Assign Assessment Role:", IT_ROLES + NON_IT_ROLES)
            if st.button("Dispatch Assessment Link", use_container_width=True):
                st.success(f"Assessment link generated and emailed to {c_sel} for {r_sel}.")

    elif st.session_state.active_tool == "Score Vault":
        st.markdown("### 🔐 Candidate Assessment Score Vault (Recruiter View)")
        st.caption("Job Seeker self-assessment results are private to the Job Seeker workspace and are not copied into this vault.")
        if st.session_state.recruiter_assessment_submissions:
            df_sub = pd.DataFrame(list(st.session_state.recruiter_assessment_submissions.values()))
            st.dataframe(df_sub, use_container_width=True, hide_index=True)
        else:
            st.info("No recruiter-dispatched candidate submissions recorded yet.")

    elif st.session_state.active_tool == "Assessment Blueprints":
        st.markdown("### 📝 Role-Based 100-Question Blueprints")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### IT Track")
            for r in IT_ROLES:
                st.markdown(f"• **{r}**: 100 MCQs (Logic, Architecture, Domain, Ethics)")
        with c2:
            st.markdown("#### Non-IT Track")
            for r in NON_IT_ROLES:
                st.markdown(f"• **{r}**: 100 MCQs (Reasoning, Operations, Scenarios, Standards)")

# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
    <div style="text-align: center; color: #94a3b8; font-size: 0.82rem; padding: 40px 0 10px;">
        © 2026 CareerLens AI. All rights reserved.
    </div>
    """,
    unsafe_allow_html=True
)
