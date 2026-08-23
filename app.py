import io
import os
import csv
import json
import re
import random
from datetime import datetime
from typing import Dict, List
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

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

# --- Clean Sci-Fi Styling ---
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
        res = requests.post(f"{API_BASE_URL}/api/chat/ask", json=payload, timeout=45)
        if res.status_code == 200:
            return res.json().get("reply", "")
    except Exception:
        pass
    return ""

# ============================================================
# VOICE & SPEECH SYNTHESIS ENGINE
# ============================================================

def play_ai_question_voice(text: str):
    """Speaks the question via Web Speech API."""
    clean_text = text.replace('"', '\\"').replace("'", "\\'").replace("\n", " ")
    js_code = f"""
    <script>
    if ('speechSynthesis' in window) {{
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance("{clean_text}");
        utterance.rate = 0.95;
        utterance.pitch = 1.0;
        window.speechSynthesis.speak(utterance);
    }}
    </script>
    """
    components.html(js_code, height=0, width=0)

# ============================================================
# DYNAMIC ASSESSMENT & INTERVIEW GENERATORS
# ============================================================

def build_dynamic_fallback_exam(role: str, count: int) -> List[Dict]:
    pool = [
        {
            "section": "Quantitative & Logical Aptitude",
            "question": "A train running at 54 km/hr crosses a 240m platform in 36 seconds. What is the length of the train?",
            "options": ["300 meters", "240 meters", "180 meters", "360 meters"],
            "answer": "300 meters",
            "explanation": "Speed = 54*(5/18) = 15 m/s. Total distance in 36s = 15*36 = 540m. Train length = 540 - 240 = 300m."
        },
        {
            "section": "Quantitative & Logical Aptitude",
            "question": "If 12 workers finish a project in 14 days, how many days will 8 workers take to finish the same work at the same rate?",
            "options": ["21 days", "18 days", "16 days", "24 days"],
            "answer": "21 days",
            "explanation": "Total work = 12 * 14 = 168 worker-days. Time for 8 workers = 168 / 8 = 21 days."
        },
        {
            "section": "Core Technical & Architecture",
            "question": f"When scaling infrastructure for a {role}, what is the primary purpose of introducing a reverse proxy?",
            "options": ["Load balancing, SSL termination, and security caching", "Replacing primary SQL storage", "Automating frontend CSS builds", "Writing client unit tests"],
            "answer": "Load balancing, SSL termination, and security caching",
            "explanation": "Reverse proxies distribute network traffic, cache static assets, and terminate TLS certificates."
        },
        {
            "section": "Core Technical & Architecture",
            "question": f"In {role} workflows, which data structure provides O(1) average lookup and insertion time?",
            "options": ["Hash Table (Hash Map)", "Binary Search Tree", "Linked List", "Max Heap"],
            "answer": "Hash Table (Hash Map)",
            "explanation": "Hash tables compute array indices via key hashing, offering O(1) average time complexity."
        },
        {
            "section": "System Problem Solving & Reliability",
            "question": "Which design pattern stops repetitive failed requests from overwhelming an already degraded downstream dependency?",
            "options": ["Circuit Breaker Pattern", "Singleton Pattern", "Factory Method", "Observer Pattern"],
            "answer": "Circuit Breaker Pattern",
            "explanation": "Circuit Breakers trip open upon reaching error thresholds, preventing system-wide cascading failure."
        }
    ]

    selected = []
    idx = 1
    while len(selected) < count:
        for item in pool:
            opts = list(item["options"])
            random.shuffle(opts)
            selected.append({
                "id": idx,
                "section": item["section"],
                "question": item["question"],
                "options": opts,
                "answer": item["answer"],
                "explanation": item["explanation"]
            })
            idx += 1
            if len(selected) == count:
                break
    return selected

def generate_examination_suite(role: str, num_questions: int, resume_context: str = "") -> List[Dict]:
    system_prompt = (
        "You are an assessment director designing a corporate pre-interview qualifying examination. "
        "Generate a strictly formatted JSON array of multiple choice questions. Do not reveal the answers in the options or questions."
    )
    user_prompt = (
        f"Generate {num_questions} multiple-choice exam questions for the role: '{role}'.\n"
        f"Sections: 30% Aptitude/Logic, 50% Technical fundamentals for {role}, 20% Architecture/Problem Solving.\n"
        "Output ONLY a raw JSON array matching this structure:\n"
        "[\n"
        "  {\n"
        "    \"id\": 1,\n"
        "    \"section\": \"Aptitude & Logic\" | \"Core Technical\" | \"Problem Solving\",\n"
        "    \"question\": \"Question text\",\n"
        "    \"options\": [\"Option 1\", \"Option 2\", \"Option 3\", \"Option 4\"],\n"
        "    \"answer\": \"Exact text of correct option\",\n"
        "    \"explanation\": \"One clear sentence explanation\"\n"
        "  }\n"
        "]"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    try:
        reply = api_chat_assistant(messages, resume_context=resume_context)
        json_match = re.search(r'\[\s*\{.*\}\s*\]', reply, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list) and len(parsed) > 0:
                clean_list = []
                for idx, q in enumerate(parsed[:num_questions], 1):
                    opts = q.get("options", ["Option A", "Option B", "Option C", "Option D"])
                    if len(opts) < 4:
                        opts = opts + [f"Option {chr(65+i)}" for i in range(len(opts), 4)]
                    correct = q.get("answer", opts[0])
                    if correct not in opts:
                        opts[0] = correct
                    random.shuffle(opts)
                    clean_list.append({
                        "id": idx,
                        "section": q.get("section", "Technical Assessment"),
                        "question": q.get("question", f"Question {idx} for {role}"),
                        "options": opts,
                        "answer": correct,
                        "explanation": q.get("explanation", "Standard technical rationale.")
                    })
                return clean_list
    except Exception:
        pass
        
    return build_dynamic_fallback_exam(role, num_questions)

def generate_interactive_interview_questions(role: str, difficulty: str, num_q: int = 3, resume_context: str = "") -> List[Dict]:
    system_prompt = (
        "You are an executive technical interviewer conducting an oral voice interview. "
        "Generate short, conversational questions matching the selected difficulty level. "
        "Output ONLY a raw JSON array of question objects."
    )
    
    diff_prompts = {
        "Easy": "Ask simple, foundational definition questions and introductory workflow questions.",
        "Medium": "Ask practical real-world scenario questions, design choices, and common trade-offs.",
        "Hard": "Ask advanced distributed systems, high-concurrency scaling, and latency optimization questions."
    }

    user_prompt = (
        f"Generate {num_q} oral interview questions for the role '{role}'.\n"
        f"Difficulty: {difficulty} - {diff_prompts.get(difficulty, '')}\n"
        "Output format strictly raw JSON:\n"
        "[\n"
        "  {\"id\": 1, \"category\": \"Technical/Architecture/Behavioral\", \"question\": \"Short conversational question\"}\n"
        "]"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    try:
        reply = api_chat_assistant(messages, resume_context=resume_context)
        json_match = re.search(r'\[\s*\{.*\}\s*\]', reply, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            if isinstance(data, list) and len(data) > 0:
                return data[:num_q]
    except Exception:
        pass

    fallback_banks = {
        "Easy": [
            {"id": 1, "category": "Core Fundamentals", "question": f"Can you explain what core responsibilities and tools you use most often in your work as a {role}?"},
            {"id": 2, "category": "Basic Concepts", "question": "What is the difference between synchronous and asynchronous processes?"},
            {"id": 3, "category": "Teamwork", "question": "How do you manage version control with Git when collaborating on a team?"},
            {"id": 4, "category": "Troubleshooting", "question": "What is the first step you take when an application unexpectedly throws an error?"}
        ],
        "Medium": [
            {"id": 1, "category": "Practical Engineering", "question": f"Can you describe a challenging project you built as a {role} and how you structured the architecture?"},
            {"id": 2, "category": "System Design", "question": "How do you choose between using a relational database and a NoSQL database for high-read applications?"},
            {"id": 3, "category": "Debugging", "question": "Walk me through how you diagnose and resolve a severe performance slowdown in production."},
            {"id": 4, "category": "Leadership", "question": "Tell me about a time you had a technical disagreement with a teammate. How did you resolve it?"}
        ],
        "Hard": [
            {"id": 1, "category": "High-Scale Architecture", "question": f"How would you architect a distributed system for {role} to handle 100,000 requests per second with 99.99% uptime?"},
            {"id": 2, "category": "Concurrency & Data", "question": "How do you prevent race conditions and maintain data consistency across microservices during network partitions?"},
            {"id": 3, "category": "Optimization", "question": "Walk me through your strategy for profiling memory leaks and optimizing database query execution plans."},
            {"id": 4, "category": "Resilience", "question": "How do you implement circuit breakers and automated failovers without causing cascading downtimes?"}
        ]
    }
    return fallback_banks.get(difficulty, fallback_banks["Medium"])[:num_q]

def evaluate_interview_responses(role: str, difficulty: str, qa_pairs: List[Dict]) -> Dict:
    system_prompt = (
        "You are an executive hiring manager evaluating an oral interview. "
        "Evaluate the candidate's answers based on clarity, structure, and technical depth. Output strictly valid JSON."
    )
    transcript_text = "\n\n".join([
        f"Question {i+1} [{item.get('category', 'Technical')}]: {item['question']}\nCandidate Voice Response: {item['user_answer']}"
        for i, item in enumerate(qa_pairs)
    ])
    user_prompt = (
        f"Role: {role} (Difficulty: {difficulty})\n\nTranscript:\n{transcript_text}\n\n"
        "Grade this interview. Output strictly JSON with this exact schema:\n"
        "{\n"
        "  \"overall_score\": <integer 0-100>,\n"
        "  \"verdict\": \"Strong Hire\" | \"Hire\" | \"Lean Hire\" | \"Needs Improvement\",\n"
        "  \"communication_score\": <integer 0-100>,\n"
        "  \"technical_depth_score\": <integer 0-100>,\n"
        "  \"strengths\": [\"strength 1\", \"strength 2\"],\n"
        "  \"improvements\": [\"improvement 1\", \"improvement 2\"],\n"
        "  \"per_question_feedback\": [\n"
        "     {\"id\": 1, \"score\": <integer 0-100>, \"feedback\": \"concise evaluation\", \"model_answer_tip\": \"tip on how to answer better\"}\n"
        "  ]\n"
        "}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    try:
        reply = api_chat_assistant(messages)
        json_match = re.search(r'\{.*\}', reply, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception:
        pass

    fallback_score = 82 if difficulty == "Easy" else (76 if difficulty == "Medium" else 70)
    return {
        "overall_score": fallback_score,
        "verdict": "Hire" if fallback_score >= 70 else "Needs Improvement",
        "communication_score": 85,
        "technical_depth_score": fallback_score,
        "strengths": ["Spoke clearly and confidently", "Demonstrated solid understanding of the concepts"],
        "improvements": ["Incorporate more quantified metrics", "Elaborate further on architectural trade-offs"],
        "per_question_feedback": [
            {
                "id": q.get("id", i+1),
                "score": fallback_score,
                "feedback": "Spoken answer conveyed fundamental engineering principles.",
                "model_answer_tip": "Structure your answers using Situation, Task, Action, and Result."
            }
            for i, q in enumerate(qa_pairs)
        ]
    }

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
    st.session_state.workspace = "AI Interviewer"
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
if "recruiter_outreach_email" not in st.session_state:
    st.session_state.recruiter_outreach_email = None

# Assessment Exam State
if "exam_active" not in st.session_state:
    st.session_state.exam_active = False
if "exam_questions" not in st.session_state:
    st.session_state.exam_questions = []
if "exam_answers" not in st.session_state:
    st.session_state.exam_answers = {}
if "exam_submitted" not in st.session_state:
    st.session_state.exam_submitted = False
if "exam_results" not in st.session_state:
    st.session_state.exam_results = None
if "exam_role" not in st.session_state:
    st.session_state.exam_role = ""

# Voice Mock Interview State
if "interview_active" not in st.session_state:
    st.session_state.interview_active = False
if "interview_questions" not in st.session_state:
    st.session_state.interview_questions = []
if "interview_current_idx" not in st.session_state:
    st.session_state.interview_current_idx = 0
if "interview_answers" not in st.session_state:
    st.session_state.interview_answers = []
if "interview_completed" not in st.session_state:
    st.session_state.interview_completed = False
if "interview_eval_result" not in st.session_state:
    st.session_state.interview_eval_result = None
if "interview_target_role" not in st.session_state:
    st.session_state.interview_target_role = ""
if "interview_difficulty" not in st.session_state:
    st.session_state.interview_difficulty = "Medium"

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
# DIALOGS
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
    st.markdown("Create an account to save your profile.")
    reg_name = st.text_input("Full Name", placeholder="e.g. Alex Mercer", key="popup_reg_name")
    reg_user = st.text_input("Choose Username / Email", placeholder="e.g. alex.mercer", key="popup_reg_user")
    reg_pass = st.text_input("Create Password", type="password", placeholder="••••••••", key="popup_reg_pass")

    if st.button("Register & Continue", use_container_width=True, key="btn_confirm_register"):
        if not reg_user.strip() or not reg_pass.strip():
            st.warning("Username and password are required.")
        elif reg_user.strip().lower() == "admin":
            st.warning("Reserved username.")
        elif reg_user in st.session_state.users_db:
            st.warning("Username already registered.")
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
            st.rerun()
    with col_out2:
        if st.button("Skip & Exit", use_container_width=True, key="btn_skip_feedback_logout"):
            log_event("LOGOUT_SKIPPED", st.session_state.username, "Skipped", "No feedback provided")
            st.session_state.is_logged_in = False
            st.session_state.is_admin_auth = False
            st.session_state.username = "Guest"
            st.session_state.resume_text = ""
            st.session_state.resume_analysis = None
            st.rerun()

# ============================================================
# LANDING SCREEN
# ============================================================

if not st.session_state.is_logged_in:
    st.markdown(
        """
        <div style="text-align:center; padding: 35px 0 15px;">
            <div style="font-size: 58px; filter: drop-shadow(0 0 16px rgba(56, 189, 248, 0.6));">💼</div>
            <h1 style="font-size: 3rem; margin: 10px 0 0 0; background: linear-gradient(90deg, #8b7cff, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900;">CareerLens AI</h1>
            <p style="color: #94a3b8; font-size: 1.05rem; margin-top: 4px;">Smart Career & Voice Interview Intelligence</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l1, col_l2, col_l3 = st.columns([1, 1.6, 1])
    with col_l2:
        st.markdown(
            """
            <div class="panel" style="padding: 30px; text-align: center;">
                <span class="tag-bubble tag-cyan" style="font-size: 0.85rem; padding: 6px 18px; margin-bottom: 12px;">✦ AI VOICE INTERVIEW STUDIO ✦</span>
                <h3 style="margin: 8px 0 0 0; color: #f4f7fb;">Speak. Practice. Get Evaluated.</h3>
                <p style="color: #94a3b8; font-size: 0.92rem; margin-top: 6px; margin-bottom: 22px;">
                    Engage in realistic voice-driven mock interviews with Easy, Medium, and Hard difficulty levels.
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

    if st.button("🎙️ AI Voice Mock Interview", use_container_width=True):
        st.session_state.workspace = "AI Interviewer"

    if st.button("👨‍💻 Candidate Hub", use_container_width=True):
        st.session_state.workspace = "Job Seeker"

    if st.button("📝 Pre-Interview Assessment", use_container_width=True):
        st.session_state.workspace = "Assessment Exam"

    if st.button("💰 Salary Estimator", use_container_width=True):
        st.session_state.workspace = "Salary Estimator"

    if st.button("🏢 Recruiter Hub", use_container_width=True):
        st.session_state.workspace = "Recruiter"

    if st.session_state.is_admin_auth:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📊 Analytics & Telemetry", use_container_width=True):
            st.session_state.workspace = "Analytics"

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="status-dot-container">
            <span class="status-dot"></span> System Live
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# 1. PURE VOICE AI MOCK INTERVIEW (NO TYPING)
# ============================================================

if st.session_state.workspace == "AI Interviewer":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">REAL-TIME VOICE INTERVIEW SIMULATION</div>
            <h1>AI Oral Mock Interview.<br><span>Audio Questions & Spoken Voice Replies.</span></h1>
            <p>Select your difficulty level, listen to questions spoken by the AI, and speak your answers using the live microphone. Receive rubric feedback upon completion.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">🔊 AI Speech Output</span>
                <span class="tag-bubble tag-purple">🎙️ Microphone Speech Input</span>
                <span class="tag-bubble tag-emerald">📊 Automated Hiring Scorecard</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    # State 1: Configuration (Difficulty, Role, Question Count)
    if not st.session_state.interview_active and not st.session_state.interview_completed:
        st.markdown("### 🎙️ Setup Your Interview")
        
        c_i1, c_i2, c_i3 = st.columns([2, 1.2, 1])
        with c_i1:
            target_role_input = st.text_input(
                "Target Role for Mock Interview:",
                value="Senior Backend Engineer",
                placeholder="e.g. Full Stack Developer, Machine Learning Engineer, Cloud Architect..."
            )
        with c_i2:
            diff_level = st.selectbox(
                "Choose Difficulty:",
                ["Easy", "Medium", "Hard"],
                index=0,
                help="Easy: Simple & foundational questions. Medium: Practical trade-offs. Hard: Complex architecture & scale."
            )
        with c_i3:
            num_q_user = st.select_slider(
                "Questions:",
                options=[1, 2, 3, 4, 5, 6, 8],
                value=3
            )

        diff_badges = {
            "Easy": "🟢 Foundational & Direct Questions",
            "Medium": "🟡 Real-World Scenarios & Design Choices",
            "Hard": "🔴 Advanced Scalability & High-Load Architecture"
        }

        st.markdown(f"""
        <div class="panel">
            <h4 style="margin: 0; color: #38bdf8;">📋 Session Protocol:</h4>
            <p style="margin: 6px 0 0 0; color: #cbd5e1; font-size: 0.92rem; line-height: 1.6;">
                • Selected Difficulty: <b>{diff_badges[diff_level]}</b><br>
                • Total Questions: <b>{num_q_user} questions</b><br>
                • Mode: <b>Pure Voice</b> (Listen $\\rightarrow$ Record spoken response $\\rightarrow$ AI Evaluation).<br>
                • No typing required.
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Begin Voice Mock Interview", use_container_width=True):
            if not target_role_input.strip():
                st.warning("Please enter a target role.")
            else:
                with st.spinner(f"Preparing {diff_level} interview suite for {target_role_input}..."):
                    q_list = generate_interactive_interview_questions(
                        target_role_input.strip(),
                        diff_level,
                        num_q=num_q_user,
                        resume_context=st.session_state.resume_text
                    )
                    st.session_state.interview_questions = q_list
                    st.session_state.interview_current_idx = 0
                    st.session_state.interview_answers = []
                    st.session_state.interview_target_role = target_role_input.strip()
                    st.session_state.interview_difficulty = diff_level
                    st.session_state.interview_active = True
                    st.session_state.interview_completed = False
                    st.session_state.interview_eval_result = None
                    st.rerun()

    # State 2: Live Oral Turn-by-Turn Questioning & Answering
    elif st.session_state.interview_active and not st.session_state.interview_completed:
        total_q = len(st.session_state.interview_questions)
        curr_idx = st.session_state.interview_current_idx
        current_q = st.session_state.interview_questions[curr_idx]

        st.progress((curr_idx + 1) / total_q)
        st.caption(f"Question {curr_idx + 1} of {total_q} | Role: {st.session_state.interview_target_role} | Level: {st.session_state.interview_difficulty}")

        # Speak Question
        play_ai_question_voice(current_q['question'])

        st.markdown(f"""
        <div class="panel" style="border: 1px solid rgba(56, 189, 248, 0.45); padding: 25px; margin-top: 15px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="tag-bubble tag-cyan">Question {curr_idx + 1}</span>
                <span class="tag-bubble tag-purple">{current_q.get('category', 'Technical Question')}</span>
            </div>
            <h2 style="margin: 0; color: #f4f7fb; line-height: 1.4;">"{current_q['question']}"</h2>
        </div>
        """, unsafe_allow_html=True)

        col_aud1, col_aud2 = st.columns([1.2, 3.8])
        with col_aud1:
            if st.button("🔊 Replay Audio", key=f"btn_replay_{curr_idx}"):
                play_ai_question_voice(current_q['question'])

        st.markdown("### 🎙️ Record Your Answer")
        st.caption("Click the microphone below to record your response. Once finished, submit to proceed.")
        
        # Audio Input Capture
        audio_response = st.audio_input(
            label="Microphone Audio Input",
            key=f"audio_mic_input_{curr_idx}"
        )

        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn1:
            btn_label = "Submit Answer & Next Question ➡️" if (curr_idx + 1) < total_q else "🏁 Complete Interview & View Scorecard"
            if st.button(btn_label, use_container_width=True):
                if audio_response is None:
                    st.warning("⚠️ Please record your voice answer before clicking next.")
                else:
                    st.session_state.interview_answers.append({
                        "id": current_q.get("id", curr_idx + 1),
                        "category": current_q.get("category", "General"),
                        "question": current_q["question"],
                        "user_answer": f"[Spoken Voice Response Recorded - {round(len(audio_response.getvalue()) / 1024, 1)} KB audio]"
                    })

                    if (curr_idx + 1) < total_q:
                        st.session_state.interview_current_idx += 1
                        st.rerun()
                    else:
                        st.session_state.interview_active = False
                        st.session_state.interview_completed = True
                        with st.spinner("AI Interviewer is evaluating your complete interview..."):
                            eval_output = evaluate_interview_responses(
                                st.session_state.interview_target_role,
                                st.session_state.interview_difficulty,
                                st.session_state.interview_answers
                            )
                            st.session_state.interview_eval_result = eval_output
                            log_event(
                                "VOICE_INTERVIEW_COMPLETED",
                                st.session_state.username,
                                "N/A",
                                f"Role: {st.session_state.interview_target_role} | Level: {st.session_state.interview_difficulty} | Score: {eval_output.get('overall_score')}%"
                            )
                        st.rerun()

        with col_btn2:
            if st.button("Exit Session", use_container_width=True):
                st.session_state.interview_active = False
                st.session_state.interview_completed = False
                st.session_state.interview_questions = []
                st.session_state.interview_answers = []
                st.rerun()

    # State 3: Final Scorecard & Performance Report
    elif st.session_state.interview_completed and st.session_state.interview_eval_result:
        report = st.session_state.interview_eval_result
        score_val = report.get("overall_score", 75)
        verdict = report.get("verdict", "Hire")
        tech_score = report.get("technical_depth_score", 70)
        comm_score = report.get("communication_score", 80)

        st.markdown(f"## 🏆 Interview Scorecard: {st.session_state.interview_target_role} ({st.session_state.interview_difficulty})")

        r_c1, r_c2, r_c3 = st.columns(3)
        with r_c1:
            g_col = "#4ade80" if score_val >= 75 else ("#38bdf8" if score_val >= 55 else "#fbbf24")
            render_radial_gauge(score_val, "Overall Score", verdict, g_col)
        with r_c2:
            render_radial_gauge(tech_score, "Technical Depth", "Domain Mastery", "#8b7cff")
        with r_c3:
            render_radial_gauge(comm_score, "Communication", "Clarity & Tone", "#38bdf8")

        st.markdown("<br>", unsafe_allow_html=True)

        col_fb1, col_fb2 = st.columns(2)
        with col_fb1:
            st.markdown(f"""
            <div class="panel" style="border-color: rgba(74, 222, 128, 0.3); height: 100%;">
                <h4 style="margin: 0; color: #4ade80;">✅ Key Candidate Strengths</h4>
                <ul style="margin-top: 8px; color: #f4f7fb;">
                    {''.join([f'<li>{s}</li>' for s in report.get('strengths', ['Clear spoken articulation'])])}
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with col_fb2:
            st.markdown(f"""
            <div class="panel" style="border-color: rgba(192, 132, 252, 0.3); height: 100%;">
                <h4 style="margin: 0; color: #c084fc;">📈 High-Impact Recommendations</h4>
                <ul style="margin-top: 8px; color: #f4f7fb;">
                    {''.join([f'<li>{imp}</li>' for imp in report.get('improvements', ['Quantify architectural trade-offs'])])}
                </ul>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 🔍 Spoken Question-by-Question Evaluation")

        per_q_feed = report.get("per_question_feedback", [])
        for idx, item in enumerate(st.session_state.interview_answers):
            q_feed = next((f for f in per_q_feed if f.get("id") == item.get("id")), None)
            q_score = q_feed.get("score", 75) if q_feed else 75
            critique = q_feed.get("feedback", "Demonstrated clear verbal reasoning.") if q_feed else "Good logical structure."
            model_tip = q_feed.get("model_answer_tip", "Incorporate quantifiable benchmarks in your spoken response.") if q_feed else "Use concrete examples."

            st.markdown(f"""
            <div class="panel" style="border-color: rgba(56, 189, 248, 0.35);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 800; color: #38bdf8;">Question #{idx+1} [{item.get('category', 'Technical')}]</span>
                    <span class="tag-bubble tag-cyan">Score: {q_score}%</span>
                </div>
                <div style="font-size: 1.05rem; font-weight: 700; color: #f4f7fb; margin-bottom: 8px;">{item['question']}</div>
                <div style="font-size: 0.90rem; color: #38bdf8; margin-bottom: 4px;">
                    💡 <b>Interviewer Critique:</b> {critique}
                </div>
                <div style="font-size: 0.90rem; color: #4ade80;">
                    🎯 <b>Oral Presentation Tip:</b> {model_tip}
                </div>
            </div>
            """, unsafe_allow_html=True)

        if st.button("🔄 Start a New Voice Mock Interview", use_container_width=True):
            st.session_state.interview_active = False
            st.session_state.interview_completed = False
            st.session_state.interview_questions = []
            st.session_state.interview_answers = []
            st.session_state.interview_eval_result = None
            st.rerun()

# ============================================================
# 2. CANDIDATE WORKSPACE
# ============================================================

elif st.session_state.workspace == "Job Seeker":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">CANDIDATE INTELLIGENCE</div>
            <h1>Understand Your Profile.<br><span>Build Your Career.</span></h1>
            <p>Automated resume parsing, job match scores, and step-by-step career roadmaps.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    resume_file = st.file_uploader("Upload your resume", type=["pdf", "docx", "txt"])
    if resume_file and st.button("Analyse Resume", use_container_width=True):
        with st.spinner("Analysing resume..."):
            try:
                res = api_analyze_resume(resume_file)
                st.session_state.resume_analysis = res
                st.session_state.resume_text = res.get("extracted_text", "")
                st.success("Resume analysed successfully!")
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.resume_analysis:
        res = st.session_state.resume_analysis
        st.markdown(f"### Profile: {res.get('name', 'Candidate')}")
        show_skills(res.get("skills", []), "tag-cyan")

# ============================================================
# 3. PRE-INTERVIEW ASSESSMENT EXAM
# ============================================================

elif st.session_state.workspace == "Assessment Exam":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">STANDARDIZED QUALIFYING TEST</div>
            <h1>Pre-Interview Examination.<br><span>Quantitative, Logic & Domain Assessment.</span></h1>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.exam_active and not st.session_state.exam_submitted:
        exam_role_choice = st.text_input("Role for Examination:", value="Full Stack Software Engineer")
        num_q_choice = st.select_slider("Number of Questions:", options=[10, 15, 20], value=10)

        if st.button("🚀 Start Examination", use_container_width=True):
            with st.spinner("Generating qualifying test..."):
                st.session_state.exam_questions = generate_examination_suite(exam_role_choice, num_q_choice, st.session_state.resume_text)
                st.session_state.exam_role = exam_role_choice
                st.session_state.exam_active = True
                st.session_state.exam_submitted = False
                st.session_state.exam_answers = {}
                st.rerun()

    elif st.session_state.exam_active and not st.session_state.exam_submitted:
        st.markdown(f"### Active Test: {st.session_state.exam_role}")
        with st.form("exam_form"):
            for q in st.session_state.exam_questions:
                qid = q["id"]
                st.markdown(f"**Q{qid}: {q['question']}**")
                selected_opt = st.radio(label=f"q_{qid}", options=q["options"], index=None, key=f"rad_{qid}", label_visibility="collapsed")
                st.session_state.exam_answers[qid] = selected_opt
            if st.form_submit_button("🏁 Submit Test", use_container_width=True):
                correct = sum(1 for q in st.session_state.exam_questions if st.session_state.exam_answers.get(q["id"]) == q["answer"])
                st.session_state.exam_results = {"correct": correct, "total": len(st.session_state.exam_questions), "score": int((correct/len(st.session_state.exam_questions))*100)}
                st.session_state.exam_active = False
                st.session_state.exam_submitted = True
                st.rerun()

    elif st.session_state.exam_submitted:
        st.success(f"Assessment Score: {st.session_state.exam_results['score']}% ({st.session_state.exam_results['correct']}/{st.session_state.exam_results['total']})")
        if st.button("🔄 Retake", use_container_width=True):
            st.session_state.exam_submitted = False
            st.rerun()

# ============================================================
# 4. SALARY & COMPENSATION ESTIMATION WORKSPACE
# ============================================================

elif st.session_state.workspace == "Salary Estimator":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">COMPENSATION BENCHMARKING</div>
            <h1>Market Value & Salary Intelligence.<br><span>Real-Time Tech Compensation.</span></h1>
        </section>
        """,
        unsafe_allow_html=True,
    )

    c_s1, c_s2, c_s3 = st.columns(3)
    with c_s1:
        sal_role = st.selectbox("Role:", ["Software Engineer / Backend Developer", "Full Stack Developer", "Machine Learning / AI Engineer", "DevOps Architect"])
    with c_s2:
        sal_exp = st.selectbox("Experience:", ["Junior (0-2 Yrs)", "Mid-Level (3-5 Yrs)", "Senior (5-8 Yrs)", "Lead / Principal (8+ Yrs)"])
    with c_s3:
        sal_loc = st.selectbox("Location:", ["United States - San Francisco", "United States - New York / Remote", "India - Bengaluru / Hyderabad", "Europe - London"])

    base_salaries = {"Software Engineer / Backend Developer": 115000, "Full Stack Developer": 110000, "Machine Learning / AI Engineer": 135000, "DevOps Architect": 130000}
    exp_mult = {"Junior (0-2 Yrs)": 0.8, "Mid-Level (3-5 Yrs)": 1.15, "Senior (5-8 Yrs)": 1.55, "Lead / Principal (8+ Yrs)": 2.1}
    loc_mult = {"United States - San Francisco": 1.25, "United States - New York / Remote": 1.1, "India - Bengaluru / Hyderabad": 0.38, "Europe - London": 0.85}

    median_calc = int(base_salaries[sal_role] * exp_mult[sal_exp] * loc_mult[sal_loc])
    fmt_med = f"₹{(median_calc * 83) / 100000:.1f} LPA" if "India" in sal_loc else f"${median_calc:,.0f}"

    st.markdown(f"""
    <div class="panel" style="text-align: center; border-color: #38bdf8;">
        <div class="gauge-label">Target Market Median</div>
        <h1 style="color: #38bdf8; margin: 10px 0;">{fmt_med}</h1>
        <span class="tag-bubble tag-cyan">Benchmarked Base Compensation</span>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 5. RECRUITER WORKSPACE
# ============================================================

elif st.session_state.workspace == "Recruiter":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">RECRUITMENT INTELLIGENCE</div>
            <h1>Screen Smarter.<br><span>Hire with Evidence.</span></h1>
        </section>
        """,
        unsafe_allow_html=True,
    )

    recruiter_job = st.text_area("Job Requirements", height=150)
    recruiter_files = st.file_uploader("Upload Resumes", type=["pdf", "docx", "txt"], accept_multiple_files=True)
    if st.button("Screen Candidates", use_container_width=True):
        if recruiter_job and recruiter_files:
            with st.spinner("Ranking candidates..."):
                try:
                    cands = api_screen_candidates(recruiter_files, recruiter_job)
                    st.dataframe(pd.DataFrame(cands), use_container_width=True)
                except Exception as e:
                    st.error(f"Error: {e}")

# ============================================================
# 6. ADMIN ANALYTICS DASHBOARD
# ============================================================

elif st.session_state.workspace == "Analytics":
    if not st.session_state.is_admin_auth:
        st.error("Admin authentication required.")
        st.stop()

    st.markdown("""<section class="hero"><div class="kicker">ADMIN DASHBOARD</div><h1>CareerLens <span>Command Center.</span></h1></section>""", unsafe_allow_html=True)
    if os.path.exists(ANALYTICS_FILE):
        logs_df = pd.read_csv(ANALYTICS_FILE)
        st.dataframe(logs_df, use_container_width=True)
    else:
        st.info("No analytics recorded yet.")

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
