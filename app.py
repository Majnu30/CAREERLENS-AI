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
# VOICE & AUDIO COMPONENTS (REAL-TIME TTS & STT)
# ============================================================

def play_ai_question_voice(text: str):
    """Executes browser speech synthesis to read question out loud automatically."""
    clean_text = text.replace('"', '\\"').replace("'", "\\'").replace("\n", " ")
    js_code = f"""
    <script>
    if ('speechSynthesis' in window) {{
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance("{clean_text}");
        utterance.rate = 0.95;
        utterance.pitch = 1.05;
        window.speechSynthesis.speak(utterance);
    }}
    </script>
    """
    components.html(js_code, height=0, width=0)

def render_realtime_speech_recorder():
    """Live HTML5 Web Speech Recognition for continuous voice replies."""
    html_code = """
    <div style="background: rgba(13, 26, 43, 0.9); border: 1px solid #213754; border-radius: 12px; padding: 14px; margin-top: 10px;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <span style="color: #38bdf8; font-weight: 700; font-size: 13.5px;">🎙️ Live Speech-to-Text Dictation</span>
            <div>
                <button id="start-record-btn" style="background: #0284c7; color: white; border: none; border-radius: 20px; padding: 6px 14px; font-weight: 700; cursor: pointer; font-size: 12px; margin-right: 6px;">▶️ Start Speaking</button>
                <button id="stop-record-btn" style="background: #ef4444; color: white; border: none; border-radius: 20px; padding: 6px 14px; font-weight: 700; cursor: pointer; font-size: 12px;">⏹️ Stop</button>
            </div>
        </div>
        <div id="recording-status" style="color: #94a3b8; font-size: 12px; margin-top: 6px;">Status: Microphone idle. Click 'Start Speaking'.</div>
        <div id="transcript-display" style="background: #081526; color: #f4f7fb; padding: 10px; border-radius: 8px; font-size: 13px; margin-top: 8px; min-height: 45px; border: 1px solid #1b304b;">Your transcribed speech will appear here...</div>
    </div>

    <script>
    const startBtn = document.getElementById('start-record-btn');
    const stopBtn = document.getElementById('stop-record-btn');
    const statusDiv = document.getElementById('recording-status');
    const transcriptDiv = document.getElementById('transcript-display');

    window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (window.SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        startBtn.onclick = () => {
            try {
                recognition.start();
                statusDiv.innerHTML = "<span style='color: #4ade80;'>🔴 Listening... Speak clearly into your microphone.</span>";
            } catch(e) {
                statusDiv.innerHTML = "Microphone is already active.";
            }
        };

        stopBtn.onclick = () => {
            recognition.stop();
            statusDiv.innerHTML = "<span style='color: #38bdf8;'>⏹️ Finished recording. Copy or paste below if needed.</span>";
        };

        recognition.onresult = (event) => {
            let finalTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                }
            }
            if (finalTranscript) {
                transcriptDiv.innerText = finalTranscript;
            }
        };

        recognition.onerror = (event) => {
            statusDiv.innerHTML = "Speech recognition error: " + event.error;
        };
    } else {
        statusDiv.innerHTML = "Speech recognition is not natively supported in this browser. Use Chrome/Edge or type your response.";
    }
    </script>
    """
    components.html(html_code, height=155)

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

def generate_interactive_interview_questions(role: str, track: str, num_q: int = 4, resume_context: str = "") -> List[Dict]:
    system_prompt = (
        "You are an executive interviewer at a top tech company. "
        "Generate realistic, spoken interview questions. Output ONLY a valid JSON array of questions with 'id', 'category', and 'question'."
    )
    user_prompt = (
        f"Generate {num_q} interview questions for the role '{role}' in the track '{track}'.\n"
        f"Candidate context: {resume_context[:600]}\n"
        "Output format strictly raw JSON:\n"
        "[\n"
        "  {\"id\": 1, \"category\": \"Technical/Behavioral/Design\", \"question\": \"Question text here...\"}\n"
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

    fallback_bank = [
        {"id": 1, "category": "Experience & Architecture", "question": f"Can you walk me through an end-to-end technical system you architected relevant to {role}, and how you handled latency or scaling issues?"},
        {"id": 2, "category": "Problem Solving", "question": "Describe a difficult technical bug or outage you diagnosed in production. What was your root cause analysis methodology?"},
        {"id": 3, "category": "Behavioral & Leadership", "question": "Tell me about a time you had a strong technical disagreement with a teammate or stakeholder. How did you resolve it?"},
        {"id": 4, "category": "Domain Mastery", "question": f"What are the top 3 best practices you strictly enforce when designing and deploying services for a {role}?"},
        {"id": 5, "category": "System Reliability", "question": "How do you approach database schema migrations and zero-downtime deployments under active production traffic?"},
        {"id": 6, "category": "Code Quality", "question": "What is your philosophy on automated testing vs speed to market, and where do integration tests fit in?"}
    ]
    return fallback_bank[:num_q]

def evaluate_interview_responses(role: str, qa_pairs: List[Dict]) -> Dict:
    system_prompt = (
        "You are a Senior Principal Interviewer grading a candidate's complete voice mock interview. "
        "Evaluate their answers thoroughly. Output ONLY a valid JSON object."
    )
    transcript_text = "\n\n".join([
        f"Question {i+1} [{item.get('category', 'General')}]: {item['question']}\nCandidate Answer: {item['user_answer']}"
        for i, item in enumerate(qa_pairs)
    ])
    user_prompt = (
        f"Role: {role}\n\nTranscript:\n{transcript_text}\n\n"
        "Grade this interview. Output strictly JSON with this exact schema:\n"
        "{\n"
        "  \"overall_score\": <integer 0-100>,\n"
        "  \"verdict\": \"Strong Hire\" | \"Hire\" | \"Lean Hire\" | \"Needs Improvement\",\n"
        "  \"communication_score\": <integer 0-100>,\n"
        "  \"technical_depth_score\": <integer 0-100>,\n"
        "  \"strengths\": [\"strength 1\", \"strength 2\"],\n"
        "  \"improvements\": [\"improvement 1\", \"improvement 2\"],\n"
        "  \"per_question_feedback\": [\n"
        "     {\"id\": 1, \"score\": <integer 0-100>, \"feedback\": \"brief constructive critique\", \"model_answer_tip\": \"tip on how to answer better\"}\n"
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

    total_len = sum(len(q["user_answer"].strip()) for q in qa_pairs)
    fallback_score = min(88, max(55, int(total_len / 12)))
    return {
        "overall_score": fallback_score,
        "verdict": "Hire" if fallback_score >= 70 else "Needs Improvement",
        "communication_score": min(92, fallback_score + 5),
        "technical_depth_score": max(50, fallback_score - 4),
        "strengths": ["Clear voice communication", "Addressed question requirements systematically"],
        "improvements": ["Incorporate more quantified business metrics (STAR framework)", "Deepen architectural specifics and trade-offs"],
        "per_question_feedback": [
            {
                "id": q.get("id", i+1),
                "score": fallback_score,
                "feedback": "Answer demonstrates foundational knowledge. Elaborate further on production trade-offs.",
                "model_answer_tip": "Structure using Situation, Task, Action, and Measurable Result."
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

# Live Interactive Mock Interview State
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
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True

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
                    Review your resume, take live pre-interview assessment exams, simulate interactive AI voice mock interviews, and benchmark compensation.
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

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        if st.button("👨‍💻 Candidate", use_container_width=True):
            st.session_state.workspace = "Job Seeker"
    with col_w2:
        if st.button("🏢 Recruiter", use_container_width=True):
            st.session_state.workspace = "Recruiter"

    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🎙️ AI Voice Mock Interview", use_container_width=True):
        st.session_state.workspace = "AI Interviewer"

    if st.button("📝 Assessment Exam", use_container_width=True):
        st.session_state.workspace = "Assessment Exam"

    if st.button("💰 Salary Estimator", use_container_width=True):
        st.session_state.workspace = "Salary Estimator"

    if st.button("📄 Resume Builder", use_container_width=True):
        st.session_state.workspace = "Resume Builder"

    if st.button("💼 Career Assistant", use_container_width=True):
        st.session_state.workspace = "Assistant"

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
# 1. CANDIDATE WORKSPACE
# ============================================================

if st.session_state.workspace == "Job Seeker":

    st.markdown(
        """
        <section class="hero">
            <div class="kicker">CANDIDATE INTELLIGENCE</div>
            <h1>Understand Your Profile.<br><span>Build Your Career.</span></h1>
            <p>Automated resume parsing, job match scores, and step-by-step career roadmaps.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Resume Scoring</span>
                <span class="tag-bubble tag-purple">✦ Profile Diagnostics</span>
                <span class="tag-bubble tag-emerald">✦ Career Roadmaps</span>
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
        "📄 Analyse Resume",
        "🎯 Job Match",
        "🗺️ Career Road Map",
        "🛡️ Real Time Job Detection"
    ])

    # 1. Analyse Resume
    with tabs[0]:
        st.subheader("Analyse Resume")
        resume_file = st.file_uploader(
            "Upload your resume", type=["pdf", "docx", "txt"], key="resume_upload"
        )

        if resume_file and st.button("Analyse Resume", use_container_width=True):
            with st.spinner("Analysing your resume..."):
                try:
                    result = api_analyze_resume(resume_file)
                    st.session_state.resume_analysis = result
                    st.session_state.resume_text = result.get("extracted_text", "")
                    log_event("RESUME_ANALYZED", st.session_state.username, "N/A", f"Skills: {len(result.get('skills', []))}")
                    st.success("Resume analysed successfully!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")

        if st.session_state.resume_analysis:
            res = st.session_state.resume_analysis
            st.markdown(
                f"""
                <div class="panel">
                    <h3 style="margin:0; color:#38bdf8; font-weight:800;">{res.get('name', 'Candidate Profile')}</h3>
                    <p style="margin:6px 0 0 0; color:#b8c6d8;">
                        📧 <b>Email:</b> {res.get('email', 'Not found')} &nbsp;|&nbsp; 
                        📱 <b>Phone:</b> {res.get('phone', 'Not found')} &nbsp;|&nbsp; 
                        ⏳ <b>Experience:</b> <b>{res.get('experience', 'Detected')}</b>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("#### Detected Skills")
            show_skills(res.get("skills", []), "tag-cyan")

    # 2. Job Match
    with tabs[1]:
        st.subheader("Job Match")
        job_desc = st.text_area("Paste Job Description", height=180, key="jobmatch")

        if st.button("Check Match", use_container_width=True):
            if not st.session_state.resume_text:
                st.warning("Please upload and analyse your resume first.")
            elif not job_desc.strip():
                st.warning("Please paste a job description.")
            else:
                with st.spinner("Checking job match..."):
                    try:
                        result = api_match_job(st.session_state.resume_text, job_desc)
                        st.session_state.current_job_match = result
                        overall_score = result.get("overall", 0)
                        
                        col_s1, col_s2 = st.columns([1, 2])
                        with col_s1:
                            render_radial_gauge(overall_score, "Job Match", "Overall Score", "#38bdf8")
                        with col_s2:
                            st.markdown("#### Matching Skills")
                            show_skills(result.get("matched", []), "tag-cyan")
                            st.markdown("#### Missing Skills")
                            show_skills(result.get("missing", []), "tag-purple")
                    except Exception as exc:
                        st.error(f"Error: {exc}")

        if "current_job_match" in st.session_state:
            match_res = st.session_state.current_job_match
            missing_skills = match_res.get("missing", [])
            
            st.markdown("---")
            st.markdown("#### ⚡ Improve Resume Bullet Points")
            
            if st.button("Generate Bullet Points for This Job", use_container_width=True):
                with st.spinner("Writing bullet points..."):
                    prompt = [
                        {"role": "system", "content": "Write 3 high-impact resume bullet points using the format: Accomplished [X], measured by [Y], by doing [Z]. Incorporate missing skills naturally."},
                        {"role": "user", "content": f"Candidate Skills: {st.session_state.resume_analysis.get('skills', []) if st.session_state.resume_analysis else ''}\nMissing Skills: {missing_skills}\nJob: {job_desc}"}
                    ]
                    rewritten = api_chat_assistant(prompt, resume_context=st.session_state.resume_text)
                    st.session_state.ats_generated_bullets = rewritten

            if st.session_state.ats_generated_bullets:
                st.markdown("""
                <div class="panel" style="border: 1px solid rgba(56, 189, 248, 0.4);">
                    <div style="font-weight: 800; color: #38bdf8; margin-bottom: 6px;">Suggested Bullet Points:</div>
                </div>
                """, unsafe_allow_html=True)
                st.code(st.session_state.ats_generated_bullets, language="markdown")

    # 3. Career Road Map
    with tabs[2]:
        st.subheader("Career Road Map")
        role = st.text_input("Target Dream Role", "Machine Learning Engineer", key="roadmap_target_input")

        if st.button("Build Career Road Map", use_container_width=True):
            with st.spinner("Creating your road map..."):
                try:
                    res = api_career_roadmap(st.session_state.resume_text, role)
                    steps = res.get("steps", [])
                    for idx, step in enumerate(steps, 1):
                        st.markdown(
                            f"""
                            <div class="panel">
                                <span class="tag-bubble tag-cyan">STEP {idx:02d}</span>
                                <div style="font-size: 1.05rem; font-weight: 800; color: #f4f7fb; margin-top: 6px;">{step}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                except Exception as exc:
                    st.error(f"Error: {exc}")

    # 4. Real Time Job Detection
    with tabs[3]:
        st.subheader("Real Time Job Detection")
        jobrisk = st.text_area("Paste Job Post or Offer to Check", height=180, key="risk")

        if st.button("Check Safety", use_container_width=True):
            if not jobrisk.strip():
                st.warning("Please paste text to check.")
            else:
                with st.spinner("Checking posting in real time..."):
                    try:
                        res = api_detect_fraud(jobrisk)
                        score_risk = res.get('score', 0)
                        level_risk = res.get('level', 'LOW RISK')
                        
                        col_f1, col_f2 = st.columns([1, 2])
                        with col_f1:
                            render_radial_gauge(score_risk, "Risk Score", level_risk, "#fbbf24" if level_risk == "HIGH RISK" else "#4ade80")
                        with col_f2:
                            st.markdown(f"""
                            <div class="panel">
                                <h4 style="margin: 0; color: {'#fbbf24' if level_risk == 'HIGH RISK' else '#4ade80'};">Verdict: {level_risk}</h4>
                                <p style="margin: 6px 0 0 0; color: #cbd5e1;">Flags found: <b>{res.get('signals', 0)}</b></p>
                            </div>
                            """, unsafe_allow_html=True)
                            if level_risk == "HIGH RISK":
                                st.warning("⚠️ Warning: Suspicious signs detected in this job post.")
                            else:
                                st.success("✅ Looks safe. No obvious red flags found.")
                    except Exception as exc:
                        st.error(f"Error: {exc}")

# ============================================================
# 2. REAL-TIME AI VOICE MOCK INTERVIEWER (SPEECH IN & SPEECH OUT)
# ============================================================

elif st.session_state.workspace == "AI Interviewer":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">REAL-TIME AI VOICE INTERVIEWER</div>
            <h1>Live AI Voice Mock Interview.<br><span>Spoken Questions, Voice Speech Input & Comprehensive Rubric.</span></h1>
            <p>Experience an authentic interview simulation. The AI speaks questions out loud, listens to your spoken answers in real time, and scores your performance.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">🔊 AI Speech Output</span>
                <span class="tag-bubble tag-purple">🎙️ Live Voice Dictation</span>
                <span class="tag-bubble tag-emerald">📊 Executive Rubric Scoring</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    # State 1: Configuration & Question Count Setup
    if not st.session_state.interview_active and not st.session_state.interview_completed:
        st.markdown("### 🎙️ Setup Your Mock Interview")
        
        c_i1, c_i2, c_i3 = st.columns([2, 1.2, 1])
        with c_i1:
            target_role_input = st.text_input(
                "Target Role for Mock Interview:",
                value="Senior Backend Engineer",
                placeholder="e.g. Full Stack Developer, Machine Learning Engineer, DevOps Architect..."
            )
        with c_i2:
            track_choice = st.selectbox(
                "Interview Track Focus:",
                [
                    "🚀 Full 360° Tech & Behavioral Mix",
                    "💻 Core Technical & System Coding",
                    "🏗️ Distributed Systems & Architecture",
                    "🤝 Behavioral & Leadership (STAR Framework)"
                ]
            )
        with c_i3:
            num_q_user = st.select_slider(
                "Select Question Count:",
                options=[1, 2, 3, 4, 5, 6, 8, 10],
                value=4
            )

        st.session_state.voice_enabled = st.checkbox("🔊 Enable AI Audio Narration (Text-to-Speech)", value=True)

        st.markdown(f"""
        <div class="panel">
            <h4 style="margin: 0; color: #38bdf8;">📋 Interactive Voice Protocol:</h4>
            <p style="margin: 6px 0 0 0; color: #cbd5e1; font-size: 0.92rem; line-height: 1.6;">
                • Selected Questions: <b>{num_q_user} questions</b><br>
                • The AI interviewer speaks each question out loud.<br>
                • Use the <b>'Start Speaking'</b> microphone button or the text field to submit your response.<br>
                • Upon completing all questions, you receive a full scorecard with Communication and Technical Depth metrics.
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Begin Voice Mock Interview", use_container_width=True):
            if not target_role_input.strip():
                st.warning("Please specify a target role.")
            else:
                with st.spinner(f"Architecting {num_q_user} interview questions for {target_role_input}..."):
                    q_list = generate_interactive_interview_questions(
                        target_role_input.strip(),
                        track_choice,
                        num_q=num_q_user,
                        resume_context=st.session_state.resume_text
                    )
                    st.session_state.interview_questions = q_list
                    st.session_state.interview_current_idx = 0
                    st.session_state.interview_answers = []
                    st.session_state.interview_target_role = target_role_input.strip()
                    st.session_state.interview_active = True
                    st.session_state.interview_completed = False
                    st.session_state.interview_eval_result = None
                    st.rerun()

    # State 2: Live Turn-by-Turn Voice Questioning & Answering
    elif st.session_state.interview_active and not st.session_state.interview_completed:
        total_q = len(st.session_state.interview_questions)
        curr_idx = st.session_state.interview_current_idx
        current_q = st.session_state.interview_questions[curr_idx]

        st.progress((curr_idx + 1) / total_q)
        st.caption(f"Question {curr_idx + 1} of {total_q} | Role: {st.session_state.interview_target_role}")

        # Speak Question Aloud
        if st.session_state.voice_enabled:
            play_ai_question_voice(current_q['question'])

        st.markdown(f"""
        <div class="panel" style="border: 1px solid rgba(56, 189, 248, 0.45); padding: 25px; margin-top: 15px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="tag-bubble tag-cyan">Question {curr_idx + 1}</span>
                <span class="tag-bubble tag-purple">{current_q.get('category', 'Technical Inquiry')}</span>
            </div>
            <h3 style="margin: 0; color: #f4f7fb; line-height: 1.4;">"{current_q['question']}"</h3>
        </div>
        """, unsafe_allow_html=True)

        col_aud1, col_aud2 = st.columns([1.2, 3.8])
        with col_aud1:
            if st.button("🔊 Replay Question Audio", key=f"btn_replay_{curr_idx}"):
                play_ai_question_voice(current_q['question'])

        st.markdown("#### 🎙️ Speak Your Answer")
        render_realtime_speech_recorder()

        user_resp = st.text_area(
            "Your Answer (Type or paste spoken answer from the recorder above):",
            height=140,
            key=f"interviewer_ans_box_{curr_idx}",
            placeholder="Structure your answer clearly (Context -> Strategy -> Execution -> Impact)..."
        )

        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn1:
            btn_label = "Submit Answer & Next Question ➡️" if (curr_idx + 1) < total_q else "🏁 Complete Interview & View Scorecard"
            if st.button(btn_label, use_container_width=True):
                if not user_resp.strip():
                    st.warning("Please provide an answer (speak or type) before submitting.")
                else:
                    st.session_state.interview_answers.append({
                        "id": current_q.get("id", curr_idx + 1),
                        "category": current_q.get("category", "General"),
                        "question": current_q["question"],
                        "user_answer": user_resp.strip()
                    })

                    if (curr_idx + 1) < total_q:
                        st.session_state.interview_current_idx += 1
                        st.rerun()
                    else:
                        st.session_state.interview_active = False
                        st.session_state.interview_completed = True
                        with st.spinner("AI Interviewer is grading your complete voice session..."):
                            eval_output = evaluate_interview_responses(
                                st.session_state.interview_target_role,
                                st.session_state.interview_answers
                            )
                            st.session_state.interview_eval_result = eval_output
                            log_event(
                                "MOCK_INTERVIEW_COMPLETED",
                                st.session_state.username,
                                "N/A",
                                f"Role: {st.session_state.interview_target_role} | Questions: {total_q} | Score: {eval_output.get('overall_score')}%"
                            )
                        st.rerun()

        with col_btn2:
            if st.button("Quit Session", use_container_width=True):
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

        st.markdown(f"## 🏆 Interview Scorecard: {st.session_state.interview_target_role}")

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
                    {''.join([f'<li>{s}</li>' for s in report.get('strengths', ['Strong domain knowledge'])])}
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with col_fb2:
            st.markdown(f"""
            <div class="panel" style="border-color: rgba(192, 132, 252, 0.3); height: 100%;">
                <h4 style="margin: 0; color: #c084fc;">📈 High-Impact Recommendations</h4>
                <ul style="margin-top: 8px; color: #f4f7fb;">
                    {''.join([f'<li>{imp}</li>' for imp in report.get('improvements', ['Quantify business results using metrics'])])}
                </ul>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 🔍 Question-by-Question Deep Evaluation")

        per_q_feed = report.get("per_question_feedback", [])
        for idx, item in enumerate(st.session_state.interview_answers):
            q_feed = next((f for f in per_q_feed if f.get("id") == item.get("id")), None)
            q_score = q_feed.get("score", 75) if q_feed else 75
            critique = q_feed.get("feedback", "Demonstrated good structural approach.") if q_feed else "Good logical structure."
            model_tip = q_feed.get("model_answer_tip", "Include explicit production metrics.") if q_feed else "Use concrete examples."

            st.markdown(f"""
            <div class="panel" style="border-color: rgba(56, 189, 248, 0.35);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 800; color: #38bdf8;">Question #{idx+1} [{item.get('category', 'Technical')}]</span>
                    <span class="tag-bubble tag-cyan">Score: {q_score}%</span>
                </div>
                <div style="font-size: 1.05rem; font-weight: 700; color: #f4f7fb; margin-bottom: 8px;">{item['question']}</div>
                <div style="font-size: 0.92rem; color: #cbd5e1; background: rgba(15, 23, 42, 0.6); padding: 10px 14px; border-radius: 8px; margin-bottom: 10px;">
                    <b>Your Response:</b><br>{item['user_answer']}
                </div>
                <div style="font-size: 0.90rem; color: #38bdf8; margin-bottom: 4px;">
                    💡 <b>Interviewer Critique:</b> {critique}
                </div>
                <div style="font-size: 0.90rem; color: #4ade80;">
                    🎯 <b>Model Solution Strategy:</b> {model_tip}
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
# 3. PRE-INTERVIEW ASSESSMENT EXAM
# ============================================================

elif st.session_state.workspace == "Assessment Exam":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">STANDARDIZED QUALIFYING TEST</div>
            <h1>Pre-Interview Examination.<br><span>Quantitative, Logic & Domain Assessment.</span></h1>
            <p>Corporate-grade qualifying examination (Aptitude, Quantitative Reasoning, Core Technical & Problem Solving) with unselected options and automatic scoring.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Unlimited Custom Roles</span>
                <span class="tag-bubble tag-purple">✦ 10 to 50 Configurable Questions</span>
                <span class="tag-bubble tag-emerald">✦ Unbiased Blank Choice Radio</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.exam_active and not st.session_state.exam_submitted:
        st.markdown("### ⚙️ Examination Configuration")
        
        c_e1, c_e2 = st.columns([2, 1])
        with c_e1:
            exam_role_choice = st.text_input(
                "Search or Type ANY Role for the Examination:",
                value="Full Stack Software Engineer",
                placeholder="e.g. Data Scientist, DevOps Engineer, Android Developer, Cloud Architect, Java Developer..."
            )
        with c_e2:
            num_q_choice = st.select_slider(
                "Number of Questions:",
                options=[10, 15, 20, 30, 40, 50],
                value=10
            )

        st.markdown(f"""
        <div class="panel">
            <h4 style="margin: 0; color: #38bdf8;">📋 Examination Pattern:</h4>
            <p style="margin: 6px 0 0 0; color: #cbd5e1; font-size: 0.92rem;">
                • <b>Quantitative Aptitude:</b> Mathematical speed, work & time, speed-distance-time, series.<br>
                • <b>Logical Reasoning:</b> Pattern analysis, deduction, critical problem solving.<br>
                • <b>Core Technical Domain:</b> Architecture, algorithms, database operations, reliability.<br>
                • <b>Blank Radio Options:</b> No options are pre-selected. You must choose your own answer for each question.
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Start Examination", use_container_width=True):
            if not exam_role_choice.strip():
                st.warning("Please type a role name to generate your examination.")
            else:
                with st.spinner(f"Synthesizing {num_q_choice} questions for {exam_role_choice}..."):
                    questions = generate_examination_suite(exam_role_choice.strip(), num_q_choice, st.session_state.resume_text)
                    st.session_state.exam_questions = questions
                    st.session_state.exam_answers = {}
                    st.session_state.exam_role = exam_role_choice.strip()
                    st.session_state.exam_active = True
                    st.session_state.exam_submitted = False
                    st.session_state.exam_results = None
                    st.rerun()

    elif st.session_state.exam_active and not st.session_state.exam_submitted:
        st.markdown(f"### 📝 Active Test: {st.session_state.exam_role}")
        st.caption(f"Total Questions: {len(st.session_state.exam_questions)}. All radio options start completely unselected.")
        
        with st.form("exam_form"):
            for q in st.session_state.exam_questions:
                qid = q["id"]
                section_tag = q.get("section", "General Assessment")
                st.markdown(f"""
                <div style="margin-top: 18px; margin-bottom: 6px;">
                    <span class="tag-bubble tag-cyan">Question {qid}</span>
                    <span class="tag-bubble tag-purple">{section_tag}</span>
                    <div style="font-size: 1.05rem; font-weight: 700; color: #f4f7fb; margin-top: 8px;">
                        {q['question']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                selected_opt = st.radio(
                    label=f"q_{qid}",
                    options=q["options"],
                    index=None,
                    key=f"exam_radio_{qid}",
                    label_visibility="collapsed"
                )
                st.session_state.exam_answers[qid] = selected_opt
                st.markdown("<hr style='border-color: #1e293b; margin: 12px 0;'>", unsafe_allow_html=True)

            submitted = st.form_submit_button("🏁 Submit Examination & View Score", use_container_width=True)
            if submitted:
                correct_count = 0
                section_breakdown = {}
                detailed_eval = []

                for q in st.session_state.exam_questions:
                    qid = q["id"]
                    user_ans = st.session_state.exam_answers.get(qid)
                    user_ans_str = str(user_ans) if user_ans is not None else "Not Answered"
                    correct_ans = str(q["answer"]).strip()
                    is_correct = (user_ans is not None and user_ans.strip() == correct_ans)
                    
                    if is_correct:
                        correct_count += 1
                        
                    sec = q.get("section", "General")
                    if sec not in section_breakdown:
                        section_breakdown[sec] = {"correct": 0, "total": 0}
                    section_breakdown[sec]["total"] += 1
                    if is_correct:
                        section_breakdown[sec]["correct"] += 1

                    detailed_eval.append({
                        "id": qid,
                        "question": q["question"],
                        "user_answer": user_ans_str,
                        "correct_answer": correct_ans,
                        "is_correct": is_correct,
                        "explanation": q.get("explanation", "Standard domain answer key.")
                    })

                total_q = len(st.session_state.exam_questions)
                percentage = int((correct_count / total_q) * 100) if total_q > 0 else 0
                
                st.session_state.exam_results = {
                    "score": percentage,
                    "correct": correct_count,
                    "total": total_q,
                    "breakdown": section_breakdown,
                    "details": detailed_eval
                }
                st.session_state.exam_active = False
                st.session_state.exam_submitted = True
                log_event("EXAM_COMPLETED", st.session_state.username, "N/A", f"Role: {st.session_state.exam_role}, Score: {percentage}% ({correct_count}/{total_q})")
                st.rerun()

    elif st.session_state.exam_submitted and st.session_state.exam_results:
        res = st.session_state.exam_results
        score_pct = res["score"]
        
        st.markdown("## 🏆 Assessment Score & Performance Report")
        
        col_res1, col_res2, col_res3 = st.columns(3)
        with col_res1:
            gauge_c = "#4ade80" if score_pct >= 75 else ("#38bdf8" if score_pct >= 50 else "#fbbf24")
            render_radial_gauge(score_pct, "Executive Score", "Qualifying Metric", gauge_c)
        with col_res2:
            st.markdown(f"""
            <div class="gauge-box">
                <div class="gauge-label">Questions Correct</div>
                <div style="font-size: 2.5rem; font-weight: 900; color: #38bdf8; margin: 8px 0;">
                    {res['correct']} / {res['total']}
                </div>
                <span class="tag-bubble tag-cyan">Accuracy Index</span>
            </div>
            """, unsafe_allow_html=True)
        with col_res3:
            verdict_text = "QUALIFIED (Top Tier)" if score_pct >= 75 else ("INTERVIEW READY" if score_pct >= 50 else "IMPROVEMENT NEEDED")
            verdict_color = "#4ade80" if score_pct >= 75 else ("#38bdf8" if score_pct >= 50 else "#fbbf24")
            st.markdown(f"""
            <div class="gauge-box">
                <div class="gauge-label">Corporate Assessment</div>
                <div style="font-size: 1.35rem; font-weight: 900; color: {verdict_color}; margin: 18px 0;">
                    {verdict_text}
                </div>
                <span class="tag-bubble tag-purple">Benchmark Status</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("### 📊 Section-Wise Performance")
        s_cols = st.columns(len(res["breakdown"]))
        for idx, (sec_name, sec_data) in enumerate(res["breakdown"].items()):
            sec_pct = int((sec_data["correct"] / sec_data["total"]) * 100) if sec_data["total"] > 0 else 0
            with s_cols[idx]:
                st.markdown(f"""
                <div class="panel" style="text-align: center;">
                    <div style="font-size: 0.82rem; font-weight: 800; color: #94a3b8; text-transform: uppercase;">{sec_name}</div>
                    <div style="font-size: 1.8rem; font-weight: 900; color: #38bdf8; margin: 6px 0;">{sec_pct}%</div>
                    <span class="tag-bubble tag-emerald">{sec_data['correct']} / {sec_data['total']} Correct</span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("### 🔍 Answer Key & Detailed Explanations")
        for item in res["details"]:
            status_badge = '<span class="tag-bubble tag-emerald">✓ Correct</span>' if item["is_correct"] else '<span class="tag-bubble tag-purple">✗ Incorrect</span>'
            st.markdown(f"""
            <div class="panel" style="border-color: {'rgba(74, 222, 128, 0.3)' if item['is_correct'] else 'rgba(139, 124, 255, 0.3)'};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; color: #38bdf8;">Question {item['id']}</span>
                    {status_badge}
                </div>
                <div style="font-size: 1rem; font-weight: 700; color: #f4f7fb; margin-bottom: 8px;">{item['question']}</div>
                <div style="font-size: 0.92rem; color: #cbd5e1; margin-bottom: 4px;">• <b>Your Answer:</b> {item['user_answer']}</div>
                <div style="font-size: 0.92rem; color: #4ade80; margin-bottom: 6px;">• <b>Correct Answer:</b> {item['correct_answer']}</div>
                <div style="font-size: 0.85rem; color: #94a3b8; background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px;">
                    💡 <b>Explanation:</b> {item['explanation']}
                </div>
            </div>
            """, unsafe_allow_html=True)

        if st.button("🔄 Retake Examination / Choose New Role", use_container_width=True):
            st.session_state.exam_active = False
            st.session_state.exam_submitted = False
            st.session_state.exam_questions = []
            st.session_state.exam_answers = {}
            st.session_state.exam_results = None
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
            <p>Benchmark your expected compensation across Tier-1 tech hubs, seniority bands, and tech stacks with clear percentiles and equity insights.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Base Salary Percentiles (25th - 90th)</span>
                <span class="tag-bubble tag-purple">✦ Equity & Stock Grids</span>
                <span class="tag-bubble tag-emerald">✦ Location Cost Adjustment</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    c_s1, c_s2, c_s3 = st.columns(3)
    with c_s1:
        sal_role = st.selectbox(
            "Job Title / Role:",
            [
                "Software Engineer / Backend Developer",
                "Full Stack Developer",
                "Machine Learning / AI Engineer",
                "DevOps / Cloud Platform Architect",
                "Data Scientist / Analytics Lead",
                "Product Manager (Tech)",
                "Cybersecurity / InfoSec Engineer"
            ]
        )
    with c_s2:
        sal_exp = st.selectbox(
            "Seniority & Experience Level:",
            [
                "Junior / Entry-Level (0-2 Yrs)",
                "Mid-Level (3-5 Yrs)",
                "Senior (5-8 Yrs)",
                "Staff / Lead Engineer (8-12 Yrs)",
                "Principal / Engineering Director (12+ Yrs)"
            ]
        )
    with c_s3:
        sal_loc = st.selectbox(
            "Location / Market Region:",
            [
                "United States - San Francisco / Bay Area",
                "United States - New York / Seattle / Remote",
                "Europe - London / Berlin / Amsterdam",
                "India - Bengaluru / Hyderabad / NCR",
                "Remote - Global (Tier 1 Benchmarked)"
            ]
        )

    base_salaries = {
        "Software Engineer / Backend Developer": 115000,
        "Full Stack Developer": 110000,
        "Machine Learning / AI Engineer": 135000,
        "DevOps / Cloud Platform Architect": 130000,
        "Data Scientist / Analytics Lead": 125000,
        "Product Manager (Tech)": 128000,
        "Cybersecurity / InfoSec Engineer": 122000
    }
    exp_multipliers = {
        "Junior / Entry-Level (0-2 Yrs)": 0.8,
        "Mid-Level (3-5 Yrs)": 1.15,
        "Senior (5-8 Yrs)": 1.55,
        "Staff / Lead Engineer (8-12 Yrs)": 1.95,
        "Principal / Engineering Director (12+ Yrs)": 2.45
    }
    loc_multipliers = {
        "United States - San Francisco / Bay Area": 1.25,
        "United States - New York / Seattle / Remote": 1.12,
        "Europe - London / Berlin / Amsterdam": 0.85,
        "India - Bengaluru / Hyderabad / NCR": 0.38,
        "Remote - Global (Tier 1 Benchmarked)": 0.95
    }

    median_calc = int(base_salaries[sal_role] * exp_multipliers[sal_exp] * loc_multipliers[sal_loc])
    p25_calc = int(median_calc * 0.85)
    p75_calc = int(median_calc * 1.20)
    p90_calc = int(median_calc * 1.45)
    currency_symbol = "₹" if "India" in sal_loc else ("£" if "London" in sal_loc else "$")
    
    if "India" in sal_loc:
        fmt_25 = f"₹{(p25_calc * 83) / 100000:.1f} LPA"
        fmt_med = f"₹{(median_calc * 83) / 100000:.1f} LPA"
        fmt_75 = f"₹{(p75_calc * 83) / 100000:.1f} LPA"
        fmt_90 = f"₹{(p90_calc * 83) / 100000:.1f} LPA"
    else:
        fmt_25 = f"{currency_symbol}{p25_calc:,.0f}"
        fmt_med = f"{currency_symbol}{median_calc:,.0f}"
        fmt_75 = f"{currency_symbol}{p75_calc:,.0f}"
        fmt_90 = f"{currency_symbol}{p90_calc:,.0f}"

    st.markdown("### 📊 Market Compensation Distribution")
    col_sal1, col_sal2, col_sal3, col_sal4 = st.columns(4)
    with col_sal1:
        st.markdown(f"""<div class="panel" style="text-align:center;"><div class="gauge-label">25th Percentile</div><h2 style="color:#94a3b8; margin:6px 0;">{fmt_25}</h2><span class="tag-bubble">Entry Range</span></div>""", unsafe_allow_html=True)
    with col_sal2:
        st.markdown(f"""<div class="panel" style="text-align:center; border-color:#38bdf8;"><div class="gauge-label" style="color:#38bdf8;">Median (50th)</div><h2 style="color:#38bdf8; margin:6px 0;">{fmt_med}</h2><span class="tag-bubble tag-cyan">Target Median</span></div>""", unsafe_allow_html=True)
    with col_sal3:
        st.markdown(f"""<div class="panel" style="text-align:center;"><div class="gauge-label">75th Percentile</div><h2 style="color:#c084fc; margin:6px 0;">{fmt_75}</h2><span class="tag-bubble tag-purple">High Performer</span></div>""", unsafe_allow_html=True)
    with col_sal4:
        st.markdown(f"""<div class="panel" style="text-align:center;"><div class="gauge-label">90th Percentile</div><h2 style="color:#4ade80; margin:6px 0;">{fmt_90}</h2><span class="tag-bubble tag-emerald">Top 10% Bracket</span></div>""", unsafe_allow_html=True)

    st.markdown("### 💡 Negotiation Insights & Tech Equity Trends")
    st.markdown(f"""
    <div class="panel">
        <h4 style="margin: 0; color: #38bdf8;">Negotiation Strategy for {sal_role} ({sal_exp}):</h4>
        <p style="margin: 8px 0 0 0; color: #cbd5e1; font-size: 0.95rem; line-height: 1.6;">
            • <b>Target Anchoring:</b> Aim to anchor your initial target at the <b>75th percentile ({fmt_75})</b> during final recruiter calls.<br>
            • <b>Variable Bonus & Equity:</b> Top tier employers typically offer an additional <b>15% - 30% performance bonus</b> and 4-year RSUs on top of the base salary.<br>
            • <b>High-Leverage Skills:</b> Demonstrating verified competency in Distributed Systems, LLM deployment, and high-load database sharding pushes offers directly toward the 90th percentile.
        </p>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 5. RESUME BUILDER WORKSPACE
# ============================================================

elif st.session_state.workspace == "Resume Builder":
    st.markdown(
        """
        <section class="hero">
            <div class="kicker">RESUME ARCHITECT</div>
            <h1>Build Your Resume.<br><span>Professional & ATS-Ready.</span></h1>
            <p>Design a job-winning resume with instant live previews and 1-click document download.</p>
            <div style="margin-top: 14px;">
                <span class="tag-bubble tag-cyan">✦ Silicon Valley Modern</span>
                <span class="tag-bubble tag-purple">✦ Ivy League Executive</span>
                <span class="tag-bubble tag-emerald">✦ Hybrid Skills-First</span>
                <span class="tag-bubble tag-cyan">✦ Nordic Minimalist</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    def_name = st.session_state.resume_analysis.get("name", "Alex Mercer") if st.session_state.resume_analysis else "Alex Mercer"
    def_email = st.session_state.resume_analysis.get("email", "alex.mercer@innovate.dev") if st.session_state.resume_analysis else "alex.mercer@innovate.dev"
    def_phone = st.session_state.resume_analysis.get("phone", "+1 (555) 019-2834") if st.session_state.resume_analysis else "+1 (555) 019-2834"
    def_skills = ", ".join(st.session_state.resume_analysis.get("skills", ["Python", "FastAPI", "React", "Docker", "Machine Learning", "PostgreSQL", "AWS", "Distributed Systems"])) if st.session_state.resume_analysis else "Python, FastAPI, React, Docker, Machine Learning, PostgreSQL, AWS, Distributed Systems"

    builder_col1, builder_col2 = st.columns([1.1, 1.3], gap="large")

    with builder_col1:
        st.markdown("### ⚙️ Template & Profile Editor")
        
        template_style = st.selectbox(
            "Select Resume Formation:",
            [
                "🚀 Silicon Valley (Cyan & Tech Accents)",
                "🏛️ Ivy League Executive (Classic Navy & Serif)",
                "⚡ Hybrid Skills-First (Modern Tech & Startup)",
                "🌿 Nordic Minimalist (Emerald & Clean Whitespace)",
                "🌑 Dark Cyberpunk Pro (Modern High-Contrast Slate)"
            ]
        )
        
        rb_name = st.text_input("Full Name", value=def_name, key="rb_name")
        rb_title = st.text_input("Target Role / Headline", value="Senior Software & AI Systems Engineer", key="rb_title")
        
        c_c1, c_c2 = st.columns(2)
        with c_c1:
            rb_email = st.text_input("Email", value=def_email, key="rb_email")
            rb_loc = st.text_input("Location", value="San Francisco, CA", key="rb_loc")
        with c_c2:
            rb_phone = st.text_input("Phone", value=def_phone, key="rb_phone")
            rb_links = st.text_input("GitHub / LinkedIn / Portfolio", value="github.com/alex-mercer | linkedin.com/in/alex-mercer", key="rb_links")

        rb_summary = st.text_area(
            "Executive Summary",
            value="High-impact engineer with 5+ years of experience designing scalable backend architectures, AI workflows, and distributed microservices. Proven track record of optimizing system throughput by 40% and deploying LLM inference pipelines to production.",
            height=100,
            key="rb_summary"
        )
        
        rb_skills = st.text_area("Core Skills (comma separated)", value=def_skills, height=75, key="rb_skills")
        
        rb_projects = st.text_area(
            "Featured Projects & Key Impact",
            value="""• AI CareerLens Engine: Built scalable resume parsing microservice with 95%+ precision using FastAPI & Transformers.
• Distributed Cache Layer: Designed low-latency Redis cluster handling 50k+ req/sec with sub-5ms latency.""",
            height=90,
            key="rb_projects"
        )

        rb_exp = st.text_area(
            "Work Experience",
            value="""Senior Software Engineer — TechCorp (2022 - Present)
• Architected scalable FastAPI microservices handling 4M+ daily active API requests with 99.98% uptime.
• Reduced database query latency by 42% through Redis caching and PostgreSQL indexing strategies.
• Mentored a team of 6 engineers and standardized CI/CD automated deployment pipelines.

Full Stack Developer — Nexus Labs (2020 - 2022)
• Built interactive client-facing dashboards using React and TypeScript, boosting user engagement by 28%.
• Integrated machine learning recommendation pipelines into core customer checkout workflows.""",
            height=150,
            key="rb_exp"
        )
        
        rb_edu = st.text_area(
            "Education & Certifications",
            value="""B.S. in Computer Science — Stanford University (2016 - 2020)
AWS Certified Solutions Architect — Associate (2024)""",
            height=80,
            key="rb_edu"
        )

    with builder_col2:
        st.markdown("### 👁️ Live Resume Preview")
        
        if "Silicon Valley" in template_style:
            primary_c = "#0284c7"
            accent_c = "#6366f1"
            bg_c = "#ffffff"
            text_c = "#0f172a"
            tag_bg = "#e0f2fe"
            tag_text = "#0369a1"
            border_header = f"3px solid {primary_c}"
            font_family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        elif "Ivy League" in template_style:
            primary_c = "#1e293b"
            accent_c = "#475569"
            bg_c = "#fdfdfd"
            text_c = "#1e293b"
            tag_bg = "#f1f5f9"
            tag_text = "#334155"
            border_header = "1px solid #94a3b8"
            font_family = "Georgia, 'Times New Roman', serif"
        elif "Hybrid Skills-First" in template_style:
            primary_c = "#7c3aed"
            accent_c = "#0284c7"
            bg_c = "#ffffff"
            text_c = "#111827"
            tag_bg = "#ede9fe"
            tag_text = "#6d28d9"
            border_header = f"2px dashed {primary_c}"
            font_family = "'Inter', -apple-system, sans-serif"
        elif "Nordic Minimalist" in template_style:
            primary_c = "#059669"
            accent_c = "#10b981"
            bg_c = "#ffffff"
            text_c = "#18181b"
            tag_bg = "#ecfdf5"
            tag_text = "#047857"
            border_header = "none"
            font_family = "'Helvetica Neue', Arial, sans-serif"
        else:
            primary_c = "#38bdf8"
            accent_c = "#a855f7"
            bg_c = "#0f172a"
            text_c = "#f8fafc"
            tag_bg = "#1e293b"
            tag_text = "#38bdf8"
            border_header = f"2px solid {primary_c}"
            font_family = "'Segoe UI', Roboto, sans-serif"

        skills_list = [s.strip() for s in rb_skills.split(",") if s.strip()]
        skills_html = "".join([f"""<span style="background:{tag_bg}; color:{tag_text}; padding:3px 8px; border-radius:4px; margin:2px 4px 2px 0; display:inline-block; font-size:11px; font-weight:700;">{s}</span>""" for s in skills_list])
        
        exp_formatted = "<br>".join([f"<span style='display:block; margin-bottom:4px; font-size:11.5px;'>{line}</span>" if line.strip().startswith("•") else f"<strong style='display:block; margin-top:7px; color:{text_c}; font-size:12px;'>{line}</strong>" for line in rb_exp.split("\n") if line.strip()])
        proj_formatted = "<br>".join([f"<span style='display:block; margin-bottom:3px; font-size:11.5px;'>{line}</span>" for line in rb_projects.split("\n") if line.strip()])
        edu_formatted = "<br>".join([f"<span style='display:block; margin-bottom:3px; font-size:11.5px;'>{line}</span>" for line in rb_edu.split("\n") if line.strip()])

        resume_preview_html = f"""<div style="background:{bg_c}; color:{text_c}; font-family:{font_family}; padding:30px; border-radius:12px; box-shadow:0 15px 40px rgba(0,0,0,0.45); line-height:1.45;"><div style="border-bottom:{border_header}; padding-bottom:10px; margin-bottom:12px;"><h1 style="color:{primary_c}; margin:0; font-size:24px; font-weight:900; letter-spacing:-0.5px;">{rb_name}</h1><div style="color:{accent_c}; font-size:13.5px; font-weight:700; margin-top:2px;">{rb_title}</div><div style="font-size:11px; color:#64748b; margin-top:6px; display:flex; flex-wrap:wrap; gap:10px;"><span>📧 {rb_email}</span><span>📱 {rb_phone}</span><span>📍 {rb_loc}</span><span>🔗 {rb_links}</span></div></div><div style="margin-bottom:12px;"><div style="font-size:11.5px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:3px;">Summary</div><p style="font-size:11.5px; color:{text_c}; opacity:0.9; margin:0;">{rb_summary}</p></div><div style="margin-bottom:12px;"><div style="font-size:11.5px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:5px;">Core Stack</div><div>{skills_html}</div></div><div style="margin-bottom:12px;"><div style="font-size:11.5px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:4px;">Featured Projects</div><div style="color:{text_c}; opacity:0.9;">{proj_formatted}</div></div><div style="margin-bottom:12px;"><div style="font-size:11.5px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:4px;">Experience</div><div style="line-height:1.45;">{exp_formatted}</div></div><div style="margin-bottom:4px;"><div style="font-size:11.5px; font-weight:800; text-transform:uppercase; color:{primary_c}; letter-spacing:1px; margin-bottom:4px;">Education</div><div style="color:{text_c}; opacity:0.9;">{edu_formatted}</div></div></div>"""
        
        st.markdown(resume_preview_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        full_download_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{rb_name} - Resume</title>
<style>
@page {{ size: A4; margin: 12mm; }}
body {{ background: #ffffff; color: {text_c if "Dark" not in template_style else "#0f172a"}; font-family: {font_family}; margin: 0; padding: 15px; }}
h1 {{ color: {primary_c if "Dark" not in template_style else "#0284c7"}; font-size: 24px; margin: 0; }}
.header {{ border-bottom: 2px solid {primary_c if "Dark" not in template_style else "#0284c7"}; padding-bottom: 10px; margin-bottom: 12px; }}
.title {{ color: {accent_c if "Dark" not in template_style else "#6366f1"}; font-size: 13.5px; font-weight: bold; margin-top: 2px; }}
.contacts {{ font-size: 11px; color: #64748b; margin-top: 6px; }}
.section-title {{ font-size: 11.5px; font-weight: 800; text-transform: uppercase; color: {primary_c if "Dark" not in template_style else "#0284c7"}; letter-spacing: 1px; margin-top: 12px; margin-bottom: 5px; border-bottom: 1px solid #e2e8f0; padding-bottom: 2px; }}
.tag {{ background: {tag_bg if "Dark" not in template_style else "#e0f2fe"}; color: {tag_text if "Dark" not in template_style else "#0369a1"}; padding: 2px 7px; border-radius: 4px; margin: 2px 3px 2px 0; display: inline-block; font-size: 10.5px; font-weight: 700; }}
p, div {{ font-size: 11.5px; color: #334155; line-height: 1.45; }}
</style>
</head>
<body onload="window.print()">
<div class="header">
    <h1>{rb_name}</h1>
    <div class="title">{rb_title}</div>
    <div class="contacts">📧 {rb_email} | 📱 {rb_phone} | 📍 {rb_loc} | 🔗 {rb_links}</div>
</div>
<div class="section-title">Summary</div>
<p>{rb_summary}</p>
<div class="section-title">Core Stack</div>
<div>{skills_html}</div>
<div class="section-title">Featured Projects</div>
<div>{proj_formatted}</div>
<div class="section-title">Experience</div>
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
                data=f"{rb_name}\n{rb_title}\n{rb_email} | {rb_phone} | {rb_loc}\n\nSUMMARY\n{rb_summary}\n\nSKILLS\n{rb_skills}\n\nPROJECTS\n{rb_projects}\n\nEXPERIENCE\n{rb_exp}\n\nEDUCATION\n{rb_edu}".encode("utf-8"),
                file_name=f"{rb_name.replace(' ', '_')}_Resume.txt",
                mime="text/plain",
                use_container_width=True
            )

# ============================================================
# 6. RECRUITER WORKSPACE
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
# 7. AI CAREER ASSISTANT
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
            "content": "Hi! Ask me anything about optimizing your resume, career trajectories, or ATS keywords."
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
# 8. PRIVATE ADMIN & ANALYTICS DASHBOARD
# ============================================================

elif st.session_state.workspace == "Analytics":
    if not st.session_state.is_admin_auth:
        st.error("Unauthorized access. Admin privileges required.")
        st.stop()

    st.markdown("""<section class="hero"><div class="kicker">ADMIN CONTROL CENTER</div><h1>CareerLens <span>Command Center.</span></h1><p>Monitor platform health, users, recruiters, AI activity, feedback and audit events from one responsive dashboard.</p></section>""", unsafe_allow_html=True)

    if os.path.exists(ANALYTICS_FILE):
        logs_df = pd.read_csv(ANALYTICS_FILE)
    else:
        logs_df = pd.DataFrame(columns=["Timestamp","Event","Username","Rating","Details"])

    if not logs_df.empty:
        logs_df["Timestamp"] = pd.to_datetime(logs_df["Timestamp"], errors="coerce")
        events = logs_df["Event"].fillna("").astype(str)
        users = logs_df["Username"].fillna("").astype(str)
        total_events = len(logs_df)
        unique_users = users.replace("", pd.NA).nunique()
        visits = int(events.isin(["LOGIN","GUEST_ACCESS"]).sum())
        registrations = int((events == "REGISTER").sum())
        admin_logins = int((events == "ADMIN_LOGIN").sum())
        ratings = logs_df[events == "LOGOUT_WITH_RATING"]
        ai_events = logs_df[events.str.contains("RESUME|MATCH|ROADMAP|CHAT|SCREEN|FRAUD|ASSESS|INTERVIEW", case=False, regex=True)]
    else:
        total_events = unique_users = visits = registrations = admin_logins = 0
        ratings = pd.DataFrame(columns=logs_df.columns)
        ai_events = pd.DataFrame(columns=logs_df.columns)

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("👥 Users", unique_users)
    k2.metric("📈 Visits", visits)
    k3.metric("📝 Sign-ups", registrations)
    k4.metric("🤖 AI Events", len(ai_events))
    k5.metric("⭐ Reviews", len(ratings))

    st.markdown("### 📊 Platform Overview")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("#### Activity by Event")
        if not logs_df.empty:
            counts = logs_df["Event"].value_counts().head(12)
            st.bar_chart(counts)
        else:
            st.info("No activity recorded yet.")
    with c2:
        st.markdown("#### Daily Activity")
        if not logs_df.empty and logs_df["Timestamp"].notna().any():
            daily = logs_df.dropna(subset=["Timestamp"]).assign(Date=lambda x: x["Timestamp"].dt.date).groupby("Date").size()
            st.line_chart(daily)
        else:
            st.info("No daily activity available.")

    st.markdown("### 🧠 AI & Product Usage")
    a1,a2,a3 = st.columns(3)
    a1.metric("AI Operations", len(ai_events))
    a2.metric("Admin Sessions", admin_logins)
    a3.metric("Total Events", total_events)

    if not ai_events.empty:
        usage = ai_events["Event"].value_counts().rename_axis("Feature").reset_index(name="Uses")
        st.dataframe(usage, use_container_width=True, hide_index=True)

    st.markdown("### ⭐ User Feedback")
    if not ratings.empty:
        feedback_cols = [c for c in ["Timestamp","Username","Rating","Details"] if c in ratings.columns]
        st.dataframe(ratings[feedback_cols].sort_values("Timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No user feedback recorded yet.")

    st.markdown("### 👤 User Activity")
    if not logs_df.empty:
        user_summary = logs_df.groupby("Username", dropna=False).agg(Events=("Event","count"), Last_Activity=("Timestamp","max")).reset_index()
        user_summary = user_summary.sort_values("Events", ascending=False).head(100)
        st.dataframe(user_summary, use_container_width=True, hide_index=True)

    st.markdown("### 🔎 Audit Log")
    search = st.text_input("Search audit events", placeholder="username, event, action...")
    filtered = logs_df.copy()
    if search.strip() and not filtered.empty:
        mask = filtered.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
        filtered = filtered[mask]
    if not filtered.empty:
        st.dataframe(filtered.sort_values("Timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No matching audit events.")

    e1,e2,e3 = st.columns(3)
    with e1:
        st.download_button("⬇️ Export Audit CSV", logs_df.to_csv(index=False).encode("utf-8"), "careerlens_audit.csv", "text/csv", use_container_width=True)
    with e2:
        st.download_button("⬇️ Export Users CSV", user_summary.to_csv(index=False).encode("utf-8") if not logs_df.empty else b"Username,Events,Last_Activity\n", "careerlens_users.csv", "text/csv", use_container_width=True)
    with e3:
        if st.button("🔄 Refresh Dashboard", use_container_width=True):
            st.rerun()

    st.markdown("### 🔐 Admin Security")
    s1,s2 = st.columns(2)
    with s1:
        st.success("Admin session authenticated")
    with s2:
        if st.button("🚪 Lock Admin Session", use_container_width=True):
            st.session_state.is_admin_auth = False
            st.session_state.is_logged_in = False
            st.session_state.workspace = "Job Seeker"
            log_event("ADMIN_LOGOUT", "Administrator", "N/A", "Admin session locked")
            st.rerun()

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
