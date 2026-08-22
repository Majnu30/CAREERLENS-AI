import io
import os
import csv
from datetime import datetime
from typing import Dict, List
import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
ADMIN_PIN = "1234"

st.set_page_config(
    page_title="CareerLens AI",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Activity Logger ---
def log_event(event_type: str, username: str, rating: str = "N/A", details: str = ""):
    file_exists = os.path.isfile(ANALYTICS_FILE)
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

# --- Clean, Modern Sci-Fi Theme (Zero Red, Cyan/Purple/Emerald Palette) ---
st.markdown(
    """
<style>
:root{
    --bg:#07111f;
    --panel:rgba(13, 26, 43, 0.85);
    --border:#213754;
    --text:#f4f7fb;
    --purple:#8b7cff;
    --cyan:#38bdf8;
    --green:#4ade80;
    --indigo:#6366f1;
    --amber:#fbbf24;
}

.stApp{
    background:
        radial-gradient(circle at 15% 0%,rgba(139,124,255,.14),transparent 28%),
        radial-gradient(circle at 90% 5%,rgba(56,189,248,.10),transparent 25%),
        var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.block-container{
    max-width:1450px;
    padding:24px 34px 50px;
}

[data-testid="stSidebar"]{
    background:#081526;
    border-right:1px solid #1b304b;
}

h1,h2,h3,h4{
    color:var(--text)!important;
}

p,label,.stMarkdown{
    color:#b8c6d8;
}

/* Brand Header */
.brand-container {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
}

.brand-briefcase {
    font-size: 32px;
    filter: drop-shadow(0 0 10px rgba(56, 189, 248, 0.5));
}

.brand{
    font-size:24px;
    font-weight:850;
    color:white;
    letter-spacing:-.5px;
    margin: 0;
}

.brand span{
    background:linear-gradient(90deg,var(--purple),var(--cyan));
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}

.brand-sub{
    font-size:10px;
    letter-spacing:2px;
    color:#70849e;
    margin-top:2px;
}

/* Minimal Green Status Dot */
.status-dot-container {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-weight: 700;
    color: #4ade80;
    margin-top: 10px;
}

.status-dot {
    width: 9px;
    height: 9px;
    background-color: #4ade80;
    border-radius: 50%;
    box-shadow: 0 0 10px #4ade80;
    display: inline-block;
}

/* Hero Card */
.hero{
    background:
        linear-gradient(135deg,rgba(139,124,255,.12),rgba(56,189,248,.04)),
        linear-gradient(135deg,#0d1d34,#0b1728);
    border:1px solid #28425f;
    border-radius:24px;
    padding:36px;
    margin-bottom:24px;
    box-shadow:0 24px 70px rgba(0,0,0,.20);
}

.kicker{
    color:var(--cyan);
    font-size:12px;
    font-weight:800;
    letter-spacing:2.4px;
}

.hero h1{
    font-size:clamp(32px,4vw,52px);
    line-height:1.1;
    letter-spacing:-1.5px;
    margin:10px 0;
}

.hero h1 span{
    background:linear-gradient(90deg,var(--purple),var(--cyan));
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}

.hero p{
    max-width:820px;
    font-size:15px;
    line-height:1.65;
    color:#a8b9cd;
}

/* SVG Radial Gauge Cards */
.gauge-box {
    background: rgba(13, 26, 43, 0.9);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

.gauge-label {
    font-size: 0.82rem;
    color: #94a3b8;
    text-transform: uppercase;
    font-weight: 800;
    letter-spacing: 1.2px;
    margin-bottom: 6px;
}

/* Bubble Bento Cards */
.panel{
    background:rgba(13,26,43,.82);
    border:1px solid var(--border);
    border-radius:18px;
    padding:20px;
    margin:12px 0;
}

.improve-card {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(56, 189, 248, 0.15) 100%);
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 20px;
    padding: 22px;
    margin-top: 18px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
}

/* Badges & Tags */
.skill, .tag-bubble{
    display:inline-flex;
    align-items: center;
    background:rgba(139,124,255,.12);
    color:#d9d4ff;
    border:1px solid rgba(139,124,255,.3);
    border-radius:999px;
    padding:6px 14px;
    margin:4px;
    font-size:12px;
    font-weight: 700;
    letter-spacing: 0.02em;
}

.tag-cyan {
    background: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
}

.tag-purple {
    background: rgba(192, 132, 252, 0.12);
    color: #c084fc;
    border: 1px solid rgba(192, 132, 252, 0.35);
}

.tag-emerald {
    background: rgba(74, 222, 128, 0.12);
    color: #4ade80;
    border: 1px solid rgba(74, 222, 128, 0.35);
}

/* Custom Buttons */
.stButton > button {
    border-radius: 50px !important;
    background: linear-gradient(135deg, #0284c7 0%, #4f46e5 50%, #7c3aed 100%) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    font-size: 0.95rem !important;
    padding: 0.65rem 1.8rem !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    box-shadow: 0 4px 18px rgba(79, 70, 229, 0.35) !important;
    transition: all 0.25s ease-in-out !important;
}

.stButton > button:hover {
    transform: translateY(-2px) scale(1.02) !important;
    box-shadow: 0 8px 25px rgba(56, 189, 248, 0.55) !important;
    border-color: rgba(255, 255, 255, 0.35) !important;
}

.footer{
    text-align:center;
    color:#7186a1;
    font-size:12px;
    padding:35px 0 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# API CALLS
# ============================================================

def api_analyze_resume(file) -> Dict:
    files = {"file": (file.name, file.getvalue(), file.type)}
    res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, timeout=60)
    res.raise_for_status()
    return res.json()

def api_match_job(resume_text: str, job_description: str) -> Dict:
    payload = {"resume_text": resume_text, "job_description": job_description}
    res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
    res.raise_for_status()
    return res.json()

def api_detect_fraud(job_text: str) -> Dict:
    payload = {"text": job_text}
    res = requests.post(f"{API_BASE_URL}/api/job/fraud", json=payload, timeout=30)
    res.raise_for_status()
    return res.json()

def api_skill_gap(resume_text: str, target_job: str) -> Dict:
    payload = {"resume_text": resume_text, "target_job": target_job}
    res = requests.post(f"{API_BASE_URL}/api/skills/gap", json=payload, timeout=30)
    res.raise_for_status()
    return res.json()

def api_career_roadmap(resume_text: str, target_role: str) -> Dict:
    payload = {"resume_text": resume_text, "target_role": target_role}
    res = requests.post(f"{API_BASE_URL}/api/career/roadmap", json=payload, timeout=30)
    res.raise_for_status()
    return res.json()

def api_screen_candidates(files: List, job_description: str) -> List[Dict]:
    file_payload = [("files", (f.name, f.getvalue(), f.type)) for f in files]
    data_payload = {"job_description": job_description}
    res = requests.post(
        f"{API_BASE_URL}/api/recruiter/screen",
        files=file_payload,
        data=data_payload,
        timeout=120,
    )
    res.raise_for_status()
    return res.json()

def api_chat_assistant(messages: List[Dict], resume_context: str = "") -> str:
    payload = {"messages": messages, "resume_context": resume_context}
    try:
        res = requests.post(f"{API_BASE_URL}/api/chat/ask", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json().get("reply", "Ready to optimize your career path.")
    except Exception:
        pass
    return "Focus on quantifiable achievements, matching core job description keywords, and maintaining clean ATS formatting."

# ============================================================
# STATE & HELPERS
# ============================================================

if "users_db" not in st.session_state:
    st.session_state.users_db = {}
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "is_admin_auth" not in st.session_state:
    st.session_state.is_admin_auth = False
if "username" not in st.session_state:
    st.session_state.username = "Guest"
if "workspace" not in st.session_state:
    st.session_state.workspace = "Job Seeker"
if "resume_text" not in st.session_state:
    st.session_state.resume_text = ""
if "resume_analysis" not in st.session_state:
    st.session_state.resume_analysis = None
if "recruiter_df" not in st.session_state:
    st.session_state.recruiter_df = None
if "custom_action_plan" not in st.session_state:
    st.session_state.custom_action_plan = None
if "ats_generated_bullets" not in st.session_state:
    st.session_state.ats_generated_bullets = None
if "interview_questions" not in st.session_state:
    st.session_state.interview_questions = None
if "recruiter_outreach_email" not in st.session_state:
    st.session_state.recruiter_outreach_email = None

def show_skills(skills, tag_style="tag-cyan"):
    if not skills:
        st.caption("No skills detected.")
        return
    html = "".join(f'<span class="tag-bubble {tag_style}">{skill}</span>' for skill in skills)
    st.markdown(html, unsafe_allow_html=True)

def render_radial_gauge(percentage: int, label: str, badge_text: str, color_hex: str = "#38bdf8"):
    val = max(0, min(100, int(percentage)))
    circumference = 2 * 3.14159 * 42
    offset = circumference - (val / 100) * circumference
    
    html = f"""<div class="gauge-box"><div class="gauge-label">{label}</div><svg width="105" height="105" viewBox="0 0 100 100"><circle cx="50" cy="50" r="42" stroke="#16273e" stroke-width="8" fill="transparent" /><circle cx="50" cy="50" r="42" stroke="{color_hex}" stroke-width="8" fill="transparent" stroke-dasharray="{circumference}" stroke-dashoffset="{offset}" stroke-linecap="round" transform="rotate(-90 50 50)" style="filter: drop-shadow(0 0 6px {color_hex}88);" /><text x="50" y="55" fill="#f4f7fb" font-size="18" font-weight="900" text-anchor="middle" dominant-baseline="middle">{val}%</text></svg><span class="tag-bubble" style="color: {color_hex}; border-color: {color_hex}55; background: {color_hex}15; margin-top: 8px;">{badge_text}</span></div>"""
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# DIALOGS (SIGNIN, REGISTER, LOGOUT RATING, IMPROVEMENT)
# ============================================================

@st.dialog("🔐 Sign In")
def open_signin_dialog():
    st.markdown("Enter your login credentials to continue.")
    login_user = st.text_input("Username or Email", key="popup_login_user")
    login_pass = st.text_input("Password", type="password", key="popup_login_pass")

    if st.button("Sign In", use_container_width=True, key="btn_confirm_signin"):
        if not login_user.strip() or not login_pass.strip():
            st.warning("Please fill in both fields.")
        elif login_user.strip().lower() == "admin" and login_pass == ADMIN_PIN:
            st.session_state.username = "Administrator"
            st.session_state.is_logged_in = True
            st.session_state.is_admin_auth = True
            st.session_state.workspace = "Analytics"
            log_event("ADMIN_LOGIN", "Administrator", "N/A", "Master Admin Session")
            st.rerun()
        elif login_user not in st.session_state.users_db:
            st.error("Account not found. Please click 'Register' first.")
        elif st.session_state.users_db[login_user] != login_pass:
            st.error("Incorrect password. Please try again.")
        else:
            st.session_state.username = login_user.split("@")[0].capitalize()
            st.session_state.is_logged_in = True
            log_event("LOGIN", st.session_state.username, "N/A", "Successful Login")
            st.success("Signed in successfully!")
            st.rerun()

@st.dialog("📝 Create Account")
def open_register_dialog():
    st.markdown("Create an account to save your resume and career roadmaps.")
    reg_name = st.text_input("Full Name", placeholder="e.g. Alex Mercer", key="popup_reg_name")
    reg_user = st.text_input("Choose Username / Email", placeholder="e.g. alex.mercer", key="popup_reg_user")
    reg_pass = st.text_input("Create Password", type="password", placeholder="••••••••", key="popup_reg_pass")

    if st.button("Register & Continue", use_container_width=True, key="btn_confirm_register"):
        if not reg_user.strip() or not reg_pass.strip():
            st.warning("Username and password are required.")
        elif reg_user.strip().lower() == "admin":
            st.warning("Reserved username. Please choose another username.")
        elif reg_user in st.session_state.users_db:
            st.warning("Username already registered. Please sign in.")
        else:
            st.session_state.users_db[reg_user] = reg_pass
            st.session_state.username = reg_name.strip() if reg_name.strip() else reg_user.split("@")[0].capitalize()
            st.session_state.is_logged_in = True
            log_event("REGISTER", st.session_state.username, "N/A", f"Registered account: {reg_user}")
            st.success("Account created successfully!")
            st.rerun()

@st.dialog("⭐ Rate & Log Out")
def open_logout_feedback_dialog():
    st.markdown("### How was your experience?")
    st.markdown("Please leave a rating before exiting.")
    rating = st.feedback("stars")
    feedback_text = st.text_area("Feedback or suggestions (optional):", placeholder="Let us know what you think...")
    
    col_out1, col_out2 = st.columns(2)
    with col_out1:
        if st.button("Submit & Exit 🚪", use_container_width=True, key="btn_submit_feedback_logout"):
            stars_rated = f"{rating + 1} Stars" if rating is not None else "No Rating"
            log_event("LOGOUT_WITH_RATING", st.session_state.username, stars_rated, feedback_text.strip() or "No comment")
            st.toast("Thank you for your rating!")
            st.session_state.is_logged_in = False
            st.session_state.is_admin_auth = False
            st.session_state.username = "Guest"
            st.session_state.resume_text = ""
            st.session_state.resume_analysis = None
            st.session_state.recruiter_df = None
            st.session_state.custom_action_plan = None
            st.rerun()
    with col_out2:
        if st.button("Skip & Exit", use_container_width=True, key="btn_skip_feedback_logout"):
            log_event("LOGOUT_SKIPPED", st.session_state.username, "Skipped", "No feedback provided")
            st.session_state.is_logged_in = False
            st.session_state.is_admin_auth = False
            st.session_state.username = "Guest"
            st.session_state.resume_text = ""
            st.session_state.resume_analysis = None
            st.session_state.recruiter_df = None
            st.session_state.custom_action_plan = None
            st.rerun()

@st.dialog("🚀 Boost Score & Skills")
def open_improvement_dialog():
    st.markdown("Generate a personalized study and project plan to reach a 90%+ match score.")
    target_role_goal = st.text_input("Target Role:", "Senior AI / Backend Engineer", key="dialog_target_role")
    weekly_hours = st.select_slider("Weekly study commitment:", options=["3-5 hrs", "5-10 hrs", "10-15 hrs", "15+ hrs"], value="5-10 hrs")
    
    if st.button("Create Action Plan ⚡", use_container_width=True, key="btn_gen_custom_plan"):
        with st.spinner("Building your improvement roadmap..."):
            try:
                res = api_career_roadmap(st.session_state.resume_text, target_role_goal)
                st.session_state.custom_action_plan = {
                    "role": target_role_goal,
                    "commitment": weekly_hours,
                    "steps": res.get("steps", [
                        "Phase 1: Upgrade resume bullet points to the Google XYZ format (Accomplished [X], measured by [Y], by doing [Z]).",
                        "Phase 2: Build a production-ready GitHub portfolio project targeting your missing skills.",
                        "Phase 3: Optimize ATS keywords and highlight measurable business impact."
                    ])
                }
                st.success("Action plan ready!")
                st.rerun()
            except Exception as e:
                st.error(f"Could not generate plan: {e}")

# ============================================================
# LANDING SCREEN
# ============================================================

if not st.session_state.is_logged_in:
    st.markdown(
        """
        <div style="text-align:center; padding: 35px 0 15px;">
            <div style="font-size: 58px; filter: drop-shadow(0 0 16px rgba(56, 189, 248, 0.6));">💼</div>
            <h1 style="font-size: 3rem; margin: 10px 0 0 0; background: linear-gradient(90deg, #8b7cff, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900;">CareerLens AI</h1>
            <p style="color: #94a3b8; font-size: 1.05rem; margin-top: 4px;">Smart Career & Resume Intelligence</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l1, col_l2, col_l3 = st.columns([1, 1.6, 1])
    with col_l2:
        st.markdown(
            """
            <div class="panel" style="padding: 30px; text-align: center;">
                <span class="tag-bubble tag-cyan" style="font-size: 0.85rem; padding: 6px 18px; margin-bottom: 12px;">✦ YOUR CAREER LAUNCHPAD ✦</span>
                <h3 style="margin: 8px 0 0 0; color: #f4f7fb;">Analyze. Create. Accelerate.</h3>
                <p style="color: #94a3b8; font-size: 0.92rem; margin-top: 6px; margin-bottom: 22px;">
                    Review your resume, build ATS-ready resumes with professional templates, and explore salary insights.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("🔐 Sign In", use_container_width=True, key="btn_open_signin"):
                open_signin_dialog()
        with col_b2:
            if st.button("📝 Register", use_container_width=True, key="btn_open_register"):
                open_register_dialog()
        with col_b3:
            if st.button("🚀 Guest", use_container_width=True, key="btn_direct_guest"):
                st.session_state.username = "Guest Explorer"
                st.session_state.is_logged_in = True
                log_event("GUEST_ACCESS", "Guest Explorer", "N/A", "Direct Guest Entry")
                st.rerun()

    st.markdown("""
    <div class="footer">
        <b>CareerLens AI by Batch 2</b>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div class="brand-container">
            <span class="brand-briefcase">💼</span>
            <div>
                <div class="brand">Career<span>Lens</span> AI</div>
                <div class="brand-sub">CAREER INTELLIGENCE PLATFORM</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # User Profile Pill
    st.markdown(
        f"""
        <div style="background: rgba(139, 124, 255, 0.12); border: 1px solid rgba(139, 124, 255, 0.3); border-radius: 14px; padding: 10px 14px; margin: 10px 0 14px 0; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 700;">Active User</div>
                <div style="font-size: 0.95rem; font-weight: 800; color: #38bdf8;">{st.session_state.username}</div>
            </div>
            <span class="tag-bubble tag-emerald" style="margin: 0; font-size: 0.7rem; padding: 4px 10px;">Online</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Log Out", use_container_width=True, key="btn_logout_sidebar"):
        open_logout_feedback_dialog()

    st.divider()

    # Workspace Switchers
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        if st.button("👨‍💻 Candidate", use_container_width=True):
            st.session_state.workspace = "Job Seeker"
    with col_w2:
        if st.button("🏢 Recruiter", use_container_width=True):
            st.session_state.workspace = "Recruiter"

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Dedicated Resume Builder Button in Sidebar
    if st.button("📄 Resume Builder", use_container_width=True):
        st.session_state.workspace = "Resume Builder"

    if st.button("💼 Career Assistant", use_container_width=True):
        st.session_state.workspace = "Assistant"

    # Admin Tab
    if st.session_state.is_admin_auth:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📊 Analytics & Telemetry", use_container_width=True):
            st.session_state.workspace = "Analytics"

    st.markdown("<br><br>", unsafe_allow_html=True)

    # Status Indicator
    st.markdown(
        """
        <div class="status-dot-container">
            <span class="status-dot"></span> System Live
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# 1. CANDIDATE WORKSPACE
# ============================================================

if st.session_state.workspace == "Job Seeker":

    st.markdown(
        """
        <section class="hero">
            <div class="kicker">CANDIDATE INTELLIGENCE</div>
            <h1>Understand Your Profile.<br><span>Build Your Career.</span></h1>
            <p>Automated resume parsing, job match scores, salary estimates, mock interviews, and step-by-step career roadmaps.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Resume Scoring</span>
                <span class="tag-bubble tag-purple">✦ Salary Benchmarks</span>
                <span class="tag-bubble tag-emerald">✦ Mock Interviews</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    analysis = st.session_state.resume_analysis
    score_raw = int(analysis.get("resume_score", 0)) if analysis and analysis.get("resume_score") else 0
    readiness_raw = int(analysis.get("readiness", 0)) if analysis and analysis.get("readiness") else 0
    skills_count = len(analysis.get("skills", [])) if analysis else 0

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        gauge_color = "#38bdf8" if score_raw >= 75 else "#fbbf24"
        render_radial_gauge(score_raw if analysis else 0, "Resume Score", "AI Evaluated", gauge_color)
    with col_m2:
        render_radial_gauge(readiness_raw if analysis else 0, "Readiness Index", "Market Match", "#818cf8")
    with col_m3:
        st.markdown(f"""
        <div class="gauge-box" style="height: 100%; justify-content: center;">
            <div class="gauge-label">Detected Skills</div>
            <div style="font-size: 2.8rem; font-weight: 900; color: #c084fc; margin: 12px 0;">{skills_count}</div>
            <span class="tag-bubble tag-purple">Extracted Stack</span>
        </div>
        """, unsafe_allow_html=True)

    # Score improvement trigger
    is_low_score = analysis and score_raw < 75
    is_low_skills = analysis and skills_count < 5
    
    if is_low_score or is_low_skills or (analysis is not None):
        st.markdown(
            f"""
            <div class="improve-card">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 1.4rem;">⚡</span>
                            <h3 style="margin: 0; color: #38bdf8; font-weight: 800;">Score & Skill Improvement Plan</h3>
                        </div>
                        <p style="margin: 6px 0 0 0; color: #cbd5e1; font-size: 0.92rem;">
                            {'Your resume score has room for growth.' if (is_low_score or is_low_skills) else 'Ready to optimize your profile to reach a 95%+ match index?'}
                            Generate a customized step-by-step action plan to upgrade your qualifications.
                        </p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚀 Boost My Score & Skills", key="btn_open_upgrade_dialog"):
            open_improvement_dialog()

    if st.session_state.custom_action_plan:
        plan = st.session_state.custom_action_plan
        st.markdown(f"""
        <div class="panel" style="border-color: rgba(56, 189, 248, 0.4); margin-top: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h4 style="margin: 0; color: #38bdf8;">📋 Active Plan: {plan.get('role')}</h4>
                <span class="tag-bubble tag-purple">Pace: {plan.get('commitment')}</span>
            </div>
            {''.join([f'<div style="margin: 8px 0; color: #f4f7fb; font-size: 0.95rem;">• {step}</div>' for step in plan.get('steps', [])])}
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    tabs = st.tabs([
        "📄 Resume Scanner",
        "🎯 Job Match",
        "💰 Salary Insights",
        "🎤 Mock Interview",
        "🗺️ Career Roadmap",
        "🛡️ Job Scam Check"
    ])

    # 1. Resume Scanner
    with tabs[0]:
        st.subheader("Resume Scanner")
        resume_file = st.file_uploader(
            "Upload Resume (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], key="resume_upload"
        )

        if resume_file and st.button("Scan Resume", use_container_width=True):
            with st.spinner("Analyzing resume profile..."):
                try:
                    result = api_analyze_resume(resume_file)
                    st.session_state.resume_analysis = result
                    st.session_state.resume_text = result.get("extracted_text", "")
                    log_event("RESUME_ANALYZED", st.session_state.username, "N/A", f"Skills Extracted: {len(result.get('skills', []))}")
                    st.success("Resume scanned successfully!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Analysis error: {exc}")

        if st.session_state.resume_analysis:
            res = st.session_state.resume_analysis
            st.markdown(
                f"""
                <div class="panel">
                    <h3 style="margin: 0; color: #38bdf8; font-weight: 800;">{res.get('name', 'Candidate Profile')}</h3>
                    <p style="margin: 6px 0 0 0; color: #b8c6d8;">
                        📧 <b>Email:</b> {res.get('email', 'Not detected')} &nbsp;|&nbsp; 
                        📱 <b>Phone:</b> {res.get('phone', 'Not detected')} &nbsp;|&nbsp; 
                        ⏳ <b>Experience:</b> <b>{res.get('experience', 'Identified')}</b>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("#### Identified Skills")
            show_skills(res.get("skills", []), "tag-cyan")

    # 2. Job Match & 1-Click ATS Bullet Rewriter
    with tabs[1]:
        st.subheader("Job Match & Optimization")
        job_desc = st.text_area("Paste Target Job Description", height=180, key="jobmatch")

        if st.button("Check Job Fit", use_container_width=True):
            if not st.session_state.resume_text:
                st.warning("Please upload and scan your resume first.")
            elif not job_desc.strip():
                st.warning("Please enter a job description.")
            else:
                with st.spinner("Calculating role alignment..."):
                    try:
                        result = api_match_job(st.session_state.resume_text, job_desc)
                        st.session_state.current_job_match = result
                        overall_score = result.get("overall", 0)
                        
                        col_s1, col_s2 = st.columns([1, 2])
                        with col_s1:
                            render_radial_gauge(overall_score, "Overall Fit", "Match Index", "#38bdf8")
                        with col_s2:
                            st.markdown("#### Matched Skills")
                            show_skills(result.get("matched", []), "tag-cyan")
                            st.markdown("#### Missing Skills")
                            show_skills(result.get("missing", []), "tag-purple")
                    except Exception as exc:
                        st.error(f"Matching error: {exc}")

        # ATS Bullet Optimizer
        if "current_job_match" in st.session_state:
            match_res = st.session_state.current_job_match
            missing_skills = match_res.get("missing", [])
            
            st.markdown("---")
            st.markdown("#### ⚡ 1-Click ATS Resume Bullet Optimizer")
            st.caption("Generate high-impact bullet points using the Google XYZ format (*Accomplished [X], measured by [Y], by doing [Z]*) incorporating your missing skills.")
            
            if st.button("✨ Rewrite My Bullet Points for this Job", use_container_width=True):
                with st.spinner("Generating tailored bullet points..."):
                    prompt = [
                        {"role": "system", "content": "You are an expert executive resume writer. Write 3 high-impact resume bullet points using the Google XYZ formula (Accomplished [X], as measured by [Y], by doing [Z]). Incorporate the following missing target skills naturally based on candidate experience."},
                        {"role": "user", "content": f"Candidate Skills: {st.session_state.resume_analysis.get('skills', []) if st.session_state.resume_analysis else ''}\nMissing Target Skills: {missing_skills}\nTarget Job: {job_desc}"}
                    ]
                    rewritten = api_chat_assistant(prompt, resume_context=st.session_state.resume_text)
                    st.session_state.ats_generated_bullets = rewritten

            if st.session_state.ats_generated_bullets:
                st.markdown("""
                <div class="panel" style="border: 1px solid rgba(56, 189, 248, 0.4);">
                    <div style="font-weight: 800; color: #38bdf8; margin-bottom: 8px;">🚀 Ready-to-Copy ATS Bullets:</div>
                </div>
                """, unsafe_allow_html=True)
                st.code(st.session_state.ats_generated_bullets, language="markdown")

    # 3. Salary & Market Benchmarks
    with tabs[2]:
        st.subheader("Salary & Compensation Insights")
        salary_role = st.text_input("Enter Job Title / Role", "AI / Full Stack Engineer", key="salary_role_input")
        salary_exp = st.selectbox("Experience Level:", ["Entry Level (0-2 yrs)", "Mid Level (3-5 yrs)", "Senior Level (6-8 yrs)", "Lead / Principal (9+ yrs)"], index=1)
        
        if st.button("Calculate Salary Range", use_container_width=True):
            exp_multipliers = {"Entry Level (0-2 yrs)": (65, 85, 105), "Mid Level (3-5 yrs)": (95, 125, 155), "Senior Level (6-8 yrs)": (140, 175, 215), "Lead / Principal (9+ yrs)": (190, 240, 310)}
            low_k, med_k, high_k = exp_multipliers.get(salary_exp, (90, 120, 150))
            
            col_sal1, col_sal2, col_sal3 = st.columns(3)
            with col_sal1:
                st.markdown(f"""
                <div class="gauge-box">
                    <div class="gauge-label">Base Range</div>
                    <div style="font-size: 2.2rem; font-weight: 900; color: #94a3b8; margin: 8px 0;">${low_k}k</div>
                    <span class="tag-bubble tag-cyan">25th Percentile</span>
                </div>
                """, unsafe_allow_html=True)
            with col_sal2:
                st.markdown(f"""
                <div class="gauge-box" style="border-color: #38bdf8;">
                    <div class="gauge-label">Market Median</div>
                    <div style="font-size: 2.4rem; font-weight: 900; color: #38bdf8; margin: 8px 0;">${med_k}k</div>
                    <span class="tag-bubble tag-emerald">Estimated Average</span>
                </div>
                """, unsafe_allow_html=True)
            with col_sal3:
                st.markdown(f"""
                <div class="gauge-box">
                    <div class="gauge-label">Top Tier Target</div>
                    <div style="font-size: 2.2rem; font-weight: 900; color: #c084fc; margin: 8px 0;">${high_k}k</div>
                    <span class="tag-bubble tag-purple">90th Percentile</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="panel">
                <h4 style="margin: 0; color: #38bdf8;">💡 Salary Growth Tip for {salary_role}</h4>
                <p style="margin: 6px 0 0 0; color: #cbd5e1;">Adding cloud infrastructure, scalable backend microservices, or distributed computing skills increases compensation offers by an estimated <b>+14% to +22%</b>.</p>
            </div>
            """, unsafe_allow_html=True)

    # 4. Mock Interview Generator
    with tabs[3]:
        st.subheader("AI Mock Interview Questions")
        st.caption("Generate role-specific interview questions tailored to your resume background.")
        
        target_interview_role = st.text_input("Interview Role:", "Full Stack / AI Engineer", key="int_role")
        
        if st.button("Generate Interview Questions 🎤", use_container_width=True):
            with st.spinner("Generating interview questions..."):
                prompt = [
                    {"role": "system", "content": "You are a senior hiring manager. Generate 4 realistic interview questions (2 technical, 1 scenario-based, 1 behavioral) for this candidate role based on their profile. Include a 1-sentence tip on what a good answer should mention for each."},
                    {"role": "user", "content": f"Role: {target_interview_role}\nCandidate Resume Context: {st.session_state.resume_text[:2000]}"}
                ]
                st.session_state.interview_questions = api_chat_assistant(prompt, resume_context=st.session_state.resume_text)

        if st.session_state.interview_questions:
            st.markdown("""
            <div class="panel" style="border: 1px solid rgba(139, 124, 255, 0.4);">
                <div style="font-weight: 800; color: #c084fc; margin-bottom: 8px;">🎯 Interview Questions & Answering Tips:</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(st.session_state.interview_questions)

    # 5. Career Roadmap
    with tabs[4]:
        st.subheader("Career Growth Roadmap")
        role = st.text_input("Aspirational Target Role", "Machine Learning Engineer", key="roadmap_target_input")

        if st.button("Generate Career Roadmap", use_container_width=True):
            with st.spinner("Building your career roadmap..."):
                try:
                    res = api_career_roadmap(st.session_state.resume_text, role)
                    steps = res.get("steps", [])
                    for idx, step in enumerate(steps, 1):
                        st.markdown(
                            f"""
                            <div class="panel">
                                <span class="tag-bubble tag-cyan">STEP {idx:02d}</span>
                                <div style="font-size: 1.1rem; font-weight: 800; color: #f4f7fb; margin-top: 8px;">{step}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                except Exception as exc:
                    st.error(f"Roadmap error: {exc}")

    # 6. Job Scam Check
    with tabs[5]:
        st.subheader("Job Safety & Fraud Risk Scanner")
        jobrisk = st.text_area("Paste Job Advertisement / Offer Letter", height=180, key="risk")

        if st.button("Scan for Scam Signals", use_container_width=True):
            if not jobrisk.strip():
                st.warning("Enter a job advertisement to evaluate.")
            else:
                with st.spinner("Checking for scam indicators..."):
                    try:
                        res = api_detect_fraud(jobrisk)
                        score_risk = res.get('score', 0)
                        level_risk = res.get('level', 'LOW RISK')
                        
                        col_f1, col_f2 = st.columns([1, 2])
                        with col_f1:
                            render_radial_gauge(score_risk, "Risk Index", level_risk, "#fbbf24" if level_risk == "HIGH RISK" else "#4ade80")
                        with col_f2:
                            st.markdown(f"""
                            <div class="panel">
                                <h4 style="margin: 0; color: {'#fbbf24' if level_risk == 'HIGH RISK' else '#4ade80'};">Verification Verdict: {level_risk}</h4>
                                <p style="margin: 6px 0 0 0; color: #cbd5e1;">Signals Identified: <b>{res.get('signals', 0)}</b></p>
                            </div>
                            """, unsafe_allow_html=True)
                            if level_risk == "HIGH RISK":
                                st.warning("⚠️ High risk signals detected in this job posting.")
                            else:
                                st.success("✅ Low risk detected. Posting appears legitimate.")
                    except Exception as exc:
                        st.error(f"Risk evaluation error: {exc}")

# ============================================================
# 2. RESUME BUILDER WORKSPACE (CLEAN HTML & 1-CLICK PDF DOWNLOAD)
# ============================================================

elif st.session_state.workspace == "Resume Builder":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">RESUME ARCHITECT</div>
            <h1>Build Your Resume.<br><span>Professional & ATS-Ready.</span></h1>
            <p>Design a job-winning resume with instant live previews and 1-click document download.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Modern Tech</span>
                <span class="tag-bubble tag-purple">✦ Executive Classic</span>
                <span class="tag-bubble tag-emerald">✦ Minimalist Clean</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    def_name = st.session_state.resume_analysis.get("name", "Alex Mercer") if st.session_state.resume_analysis else "Alex Mercer"
    def_email = st.session_state.resume_analysis.get("email", "alex.mercer@innovate.dev") if st.session_state.resume_analysis else "alex.mercer@innovate.dev"
    def_phone = st.session_state.resume_analysis.get("phone", "+1 (555) 019-2834") if st.session_state.resume_analysis else "+1 (555) 019-2834"
    def_skills = ", ".join(st.session_state.resume_analysis.get("skills", ["Python", "FastAPI", "React", "Docker", "Machine Learning", "PostgreSQL", "AWS"])) if st.session_state.resume_analysis else "Python, FastAPI, React, Docker, Machine Learning, PostgreSQL, AWS"

    builder_col1, builder_col2 = st.columns([1.1, 1.3], gap="large")

    with builder_col1:
        st.markdown("### ✏️ Profile Information")
        
        template_style = st.selectbox(
            "Select Resume Template:",
            ["✨ Modern Tech (Cyan & Indigo)", "👔 Executive Classic (Navy & Slate)", "🌿 Minimalist Clean (Emerald & Graphite)"]
        )
        
        rb_name = st.text_input("Full Name", value=def_name, key="rb_name")
        rb_title = st.text_input("Professional Title", value="Senior Software & AI Engineer", key="rb_title")
        
        c_c1, c_c2 = st.columns(2)
        with c_c1:
            rb_email = st.text_input("Email", value=def_email, key="rb_email")
            rb_loc = st.text_input("Location", value="San Francisco, CA", key="rb_loc")
        with c_c2:
            rb_phone = st.text_input("Phone", value=def_phone, key="rb_phone")
            rb_links = st.text_input("LinkedIn / Portfolio", value="linkedin.com/in/alex-mercer", key="rb_links")

        rb_summary = st.text_area(
            "Professional Summary",
            value="High-impact engineer with 4+ years of experience designing scalable backend architectures, AI workflows, and cloud microservices. Proven track record of optimizing system throughput by 35% and improving search relevancy.",
            height=110,
            key="rb_summary"
        )
        
        rb_skills = st.text_area("Core Skills (comma separated)", value=def_skills, height=80, key="rb_skills")
        
        rb_exp = st.text_area(
            "Work Experience",
            value="""Senior Software Engineer — TechCorp (2022 - Present)
• Architected scalable FastAPI microservices handling 4M+ daily active API requests with 99.98% uptime.
• Reduced database query latency by 42% through Redis caching and PostgreSQL indexing strategies.
• Mentored a team of 6 engineers and standardized CI/CD automated deployment pipelines.

Full Stack Developer — Nexus Labs (2020 - 2022)
• Built interactive client-facing dashboards using React and TypeScript, boosting engagement by 28%.
• Integrated machine learning recommendation pipelines into core customer checkout workflows.""",
            height=160,
            key="rb_exp"
        )
        
        rb_edu = st.text_area(
            "Education & Credentials",
            value="""B.S. in Computer Science — Stanford University (2016 - 2020)
AWS Certified Solutions Architect — Associate (2023)""",
            height=90,
            key="rb_edu"
        )

    with builder_col2:
        st.markdown("### 👁️ Live Resume Preview")
        
        if "Modern Tech" in template_style:
            primary_c = "#0284c7"
            accent_c = "#6366f1"
            bg_c = "#ffffff"
            text_c = "#0f172a"
            tag_bg = "#e0f2fe"
            tag_text = "#0369a1"
            font_family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        elif "Executive Classic" in template_style:
            primary_c = "#1e293b"
            accent_c = "#334155"
            bg_c = "#fdfdfd"
            text_c = "#1e293b"
            tag_bg = "#f1f5f9"
            tag_text = "#334155"
            font_family = "Georgia, serif"
        else:
            primary_c = "#059669"
            accent_c = "#10b981"
            bg_c = "#ffffff"
            text_c = "#18181b"
            tag_bg = "#ecfdf5"
            tag_text = "#047857"
            font_family = "'Helvetica Neue', Arial, sans-serif"

        skills_list = [s.strip() for s in rb_skills.split(",") if s.strip()]
        skills_html = "".join([f"""<span style="background:{tag_bg}; color:{tag_text}; padding:4px 9px; border-radius:4px; margin:2px 4px 2px 0; display:inline-block; font-size:11px; font-weight:700;">{s}</span>""" for s in skills_list])
        
        exp_formatted = "<br>".join([f"<span style='display:block; margin-bottom:4px;'>{line}</span>" if line.strip().startswith("•") else f"<strong style='display:block; margin-top:8px; color:{text_c};'>{line}</strong>" for line in rb_exp.split("\n") if line.strip()])
        edu_formatted = "<br>".join([f"<span style='display:block; margin-bottom:3px;'>{line}</span>" for line in rb_edu.split("\n") if line.strip()])

        # Clean single-line formatted HTML to prevent Streamlit parser errors
        resume_preview_html = f"""<div style="background:{bg_c}; color:{text_c}; font-family:{font_family}; padding:32px; border-radius:12px; box-shadow:0 15px 40px rgba(0,0,0,0.45); line-height:1.5;"><div style="border-bottom:2px solid {primary_c}; padding-bottom:12px; margin-bottom:14px;"><h1 style="color:{primary_c}; margin:0; font-size:26px; font-weight:900; letter-spacing:-0.5px;">{rb_name}</h1><div style="color:{accent_c}; font-size:14px; font-weight:700; margin-top:2px;">{rb_title}</div><div style="font-size:11.5px; color:#64748b; margin-top:8px; display:flex; flex-wrap:wrap; gap:12px;"><span>📧 {rb_email}</span><span>📱 {rb_phone}</span><span>📍 {rb_loc}</span><span>🔗 {rb_links}</span></div></div><div style="margin-bottom:14px;"><div style="font-size:12px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:4px;">Profile Summary</div><p style="font-size:12px; color:#334155; margin:0;">{rb_summary}</p></div><div style="margin-bottom:14px;"><div style="font-size:12px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:6px;">Core Competencies</div><div>{skills_html}</div></div><div style="margin-bottom:14px;"><div style="font-size:12px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:6px;">Work Experience</div><div style="font-size:12px; color:#334155; line-height:1.5;">{exp_formatted}</div></div><div style="margin-bottom:6px;"><div style="font-size:12px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:6px;">Education & Credentials</div><div style="font-size:12px; color:#334155; line-height:1.5;">{edu_formatted}</div></div></div>"""
        
        st.markdown(resume_preview_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Complete Standalone PDF-Ready Document
        full_download_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{rb_name} - Resume</title>
<style>
@page {{ size: A4; margin: 15mm; }}
body {{ background: #ffffff; color: {text_c}; font-family: {font_family}; margin: 0; padding: 20px; }}
h1 {{ color: {primary_c}; font-size: 26px; margin: 0; }}
.header {{ border-bottom: 2px solid {primary_c}; padding-bottom: 12px; margin-bottom: 14px; }}
.title {{ color: {accent_c}; font-size: 14px; font-weight: bold; margin-top: 2px; }}
.contacts {{ font-size: 11.5px; color: #64748b; margin-top: 6px; }}
.section-title {{ font-size: 12px; font-weight: 800; text-transform: uppercase; color: {primary_c}; letter-spacing: 1px; margin-top: 14px; margin-bottom: 6px; border-bottom: 1px solid #e2e8f0; padding-bottom: 3px; }}
.tag {{ background: {tag_bg}; color: {tag_text}; padding: 3px 8px; border-radius: 4px; margin: 2px 4px 2px 0; display: inline-block; font-size: 11px; font-weight: 700; }}
p, div {{ font-size: 12px; color: #334155; line-height: 1.5; }}
</style>
</head>
<body onload="window.print()">
<div class="header">
    <h1>{rb_name}</h1>
    <div class="title">{rb_title}</div>
    <div class="contacts">📧 {rb_email} | 📱 {rb_phone} | 📍 {rb_loc} | 🔗 {rb_links}</div>
</div>
<div class="section-title">Profile Summary</div>
<p>{rb_summary}</p>
<div class="section-title">Core Competencies</div>
<div>{skills_html}</div>
<div class="section-title">Work Experience</div>
<div>{exp_formatted}</div>
<div class="section-title">Education & Credentials</div>
<div>{edu_formatted}</div>
</body>
</html>"""

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "⬇️ Download Resume (PDF-Ready HTML)",
                data=full_download_doc.encode("utf-8"),
                file_name=f"{rb_name.replace(' ', '_')}_Resume.html",
                mime="text/html",
                use_container_width=True
            )
        with col_dl2:
            st.download_button(
                "⬇️ Download Plain Text (.txt)",
                data=f"{rb_name}\n{rb_title}\n{rb_email} | {rb_phone} | {rb_loc}\n\nSUMMARY\n{rb_summary}\n\nSKILLS\n{rb_skills}\n\nEXPERIENCE\n{rb_exp}\n\nEDUCATION\n{rb_edu}".encode("utf-8"),
                file_name=f"{rb_name.replace(' ', '_')}_Resume.txt",
                mime="text/plain",
                use_container_width=True
            )

# ============================================================
# 3. RECRUITER WORKSPACE
# ============================================================

elif st.session_state.workspace == "Recruiter":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">RECRUITMENT INTELLIGENCE</div>
            <h1>Screen Smarter.<br><span>Hire with Evidence.</span></h1>
            <p>Automated semantic screening, candidate ranking, profile deep-dives, and 1-click recruiter outreach email generation.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Bulk Resume Ranking</span>
                <span class="tag-bubble tag-purple">✦ Candidate Deep Dive</span>
                <span class="tag-bubble tag-emerald">✦ Outreach Email Generator</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    recruiter_job = st.text_area("Job Requirements & Qualifications", height=180, key="recruiter_job")
    recruiter_files = st.file_uploader(
        "Candidate Resumes",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="candidate_files",
    )
    top_n = st.number_input("Shortlist Size", min_value=1, max_value=100, value=10)

    if st.button("⚡ Screen & Rank Candidates", use_container_width=True):
        if not recruiter_job.strip() or not recruiter_files:
            st.warning("Please provide a job description and candidate resumes.")
        else:
            with st.spinner("Ranking candidate cohort..."):
                try:
                    candidates_data = api_screen_candidates(recruiter_files, recruiter_job)
                    st.session_state.recruiter_df = pd.DataFrame(candidates_data)
                    log_event("RECRUITER_SCREEN", st.session_state.username, "N/A", f"Screened {len(candidates_data)} candidates")
                    st.success(f"Successfully ranked {len(candidates_data)} candidates!")
                except Exception as exc:
                    st.error(f"Screening error: {exc}")

    if st.session_state.recruiter_df is not None and not st.session_state.recruiter_df.empty:
        df = st.session_state.recruiter_df.head(int(top_n))
        
        st.markdown("#### Candidate Shortlist")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Candidate Deep-Dive Inspector
        st.markdown("---")
        st.markdown("#### 🔍 Candidate Deep-Dive Inspector")
        
        candidate_names = df["name"].tolist() if "name" in df.columns else [f"Candidate #{i+1}" for i in range(len(df))]
        selected_candidate_name = st.selectbox("Select candidate to review details:", candidate_names)
        
        if selected_candidate_name:
            cand_row = df[df["name"] == selected_candidate_name].iloc[0] if "name" in df.columns else df.iloc[0]
            cand_score = int(cand_row.get("score", cand_row.get("match_score", 85)))
            
            col_d1, col_d2 = st.columns([1, 2])
            with col_d1:
                render_radial_gauge(cand_score, "Match Score", "Top Match", "#38bdf8")
            with col_d2:
                st.markdown(f"""
                <div class="panel">
                    <h3 style="margin: 0; color: #38bdf8;">{selected_candidate_name}</h3>
                    <p style="margin: 6px 0; color: #b8c6d8;">
                        📧 <b>Email:</b> {cand_row.get('email', 'Available in full document')} &nbsp;|&nbsp; 
                        📱 <b>Phone:</b> {cand_row.get('phone', 'Available in full document')}
                    </p>
                    <p style="margin: 4px 0; color: #cbd5e1;"><b>Match Summary:</b> {cand_row.get('summary', 'Strong overlap with target job qualifications.')}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if "skills" in cand_row:
                    skills_val = cand_row["skills"] if isinstance(cand_row["skills"], list) else str(cand_row["skills"]).split(",")
                    show_skills(skills_val, "tag-cyan")

            # 1-Click Recruiter Outreach Email Generator
            st.markdown("#### ✉️ 1-Click Candidate Outreach Email Generator")
            if st.button(f"Generate Interview Invite for {selected_candidate_name}", use_container_width=True):
                with st.spinner("Drafting personalized outreach email..."):
                    prompt = [
                        {"role": "system", "content": "You are a professional talent acquisition specialist. Draft a warm, concise, and professional interview invitation email to this shortlisted candidate referencing their top match score and background."},
                        {"role": "user", "content": f"Candidate Name: {selected_candidate_name}\nCandidate Details: {dict(cand_row)}\nRole: {recruiter_job[:1000]}"}
                    ]
                    st.session_state.recruiter_outreach_email = api_chat_assistant(prompt)

            if st.session_state.recruiter_outreach_email:
                st.markdown("""
                <div class="panel" style="border: 1px solid rgba(56, 189, 248, 0.4);">
                    <div style="font-weight: 800; color: #38bdf8; margin-bottom: 8px;">📬 Ready-to-Send Email Draft:</div>
                </div>
                """, unsafe_allow_html=True)
                st.code(st.session_state.recruiter_outreach_email, language="markdown")

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            "⬇️ Download Shortlist (CSV)",
            df.to_csv(index=False).encode("utf-8"),
            file_name="shortlist.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ============================================================
# 4. AI CAREER ASSISTANT
# ============================================================

elif st.session_state.workspace == "Assistant":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">CAREER ADVISOR</div>
            <h1>AI Career Assistant.<br><span>Instant Guidance.</span></h1>
            <p>Ask questions about resume formatting, ATS keywords, interview tips, or career transitions.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": "Hi! Ask me anything about optimizing your resume, interview preparation, or career roadmaps."
        }]

    st.markdown("#### Popular Questions")
    q_cols = st.columns(3)
    faqs = [
        "How do I optimize my resume for ATS?",
        "How do I present my technical skills?",
        "What makes a project stand out?",
    ]

    chosen_faq = None
    for i, faq in enumerate(faqs):
        if q_cols[i].button(faq, key=f"btn_faq_{i}", use_container_width=True):
            chosen_faq = faq

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("Ask a question about your resume or career...")
    active_prompt = chosen_faq or user_input

    if active_prompt:
        st.session_state.chat_messages.append({"role": "user", "content": active_prompt})
        with st.chat_message("user"):
            st.write(active_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                ans = api_chat_assistant(
                    st.session_state.chat_messages,
                    resume_context=st.session_state.resume_text,
                )
                st.write(ans)
        st.session_state.chat_messages.append({"role": "assistant", "content": ans})
        st.rerun()

# ============================================================
# 5. PRIVATE ADMIN & ANALYTICS DASHBOARD
# ============================================================

elif st.session_state.workspace == "Analytics":
    if not st.session_state.is_admin_auth:
        st.warning("Unauthorized access. Admin privileges required.")
        st.stop()

    st.markdown(
        """
        <section class="hero">
            <div class="kicker">RESTRICTED ADMIN ACCESS</div>
            <h1>Platform Telemetry.<br><span>User Audit & Ratings.</span></h1>
            <p>Admin telemetry: view user registrations, login volume, exit ratings, and download analytics logs.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if os.path.exists(ANALYTICS_FILE):
        logs_df = pd.read_csv(ANALYTICS_FILE)
        
        col_a1, col_a2, col_a3 = st.columns(3)
        total_logins = len(logs_df[logs_df["Event"].isin(["LOGIN", "GUEST_ACCESS"])])
        total_regs = len(logs_df[logs_df["Event"] == "REGISTER"])
        rated_entries = logs_df[logs_df["Event"] == "LOGOUT_WITH_RATING"]
        
        with col_a1:
            render_radial_gauge(total_logins, "Total Visits", "Traffic", "#38bdf8")
        with col_a2:
            render_radial_gauge(total_regs, "Sign-ups", "Conversions", "#818cf8")
        with col_a3:
            render_radial_gauge(len(rated_entries), "Exit Reviews", "Feedback", "#c084fc")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # User Feedback and Ratings
        st.markdown("#### ⭐ User Exit Ratings & Comments")
        if not rated_entries.empty:
            st.dataframe(
                rated_entries[["Timestamp", "Username", "Rating", "Details"]].rename(columns={"Details": "Feedback"}),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No ratings recorded yet.")

        # Full System Log
        st.markdown("#### 📜 Full System Audit Log")
        st.dataframe(logs_df.sort_values(by="Timestamp", ascending=False), use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Export Full Telemetry Log (CSV)",
            logs_df.to_csv(index=False).encode("utf-8"),
            file_name="platform_analytics.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("No activity logs or ratings recorded yet.")

# ============================================================
# FOOTER
# ============================================================
st.divider()
st.markdown(
    """
    <div class="footer">
        <b>CareerLens AI by Batch 2</b>
    </div>
    """,
    unsafe_allow_html=True,
)
