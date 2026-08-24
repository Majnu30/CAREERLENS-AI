# ============================================================
# CAREERLENS AI V2 - PROFESSIONAL STREAMLIT FRONTEND
# ============================================================
#
# Compatible with the existing CareerLens FastAPI backend:
#
# POST /api/resume/analyze
# POST /api/job/match
# POST /api/job/fraud
# POST /api/career/roadmap
# POST /api/recruiter/screen
# POST /api/chat/ask
#
# ============================================================

import os
import re
import io
import csv
import json
import uuid
import random
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

API_BASE_URL = os.getenv(
    "API_URL",
    "https://careerlens-ai-9dx8.onrender.com"
).rstrip("/")

ANALYTICS_FILE = "analytics.csv"

# Demo-only admin configuration.
# Move this to environment variables before production.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PIN = os.getenv("ADMIN_PIN", "1234")

st.set_page_config(
    page_title="CareerLens AI",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DESIGN SYSTEM
# ============================================================

st.markdown(
    """
<style>

:root {
    --bg: #050b16;
    --bg2: #081321;
    --panel: rgba(13, 24, 42, .88);
    --panel2: rgba(18, 32, 54, .92);
    --border: rgba(120, 150, 190, .18);

    --text: #f8fafc;
    --muted: #94a3b8;

    --cyan: #38bdf8;
    --blue: #3b82f6;
    --purple: #8b5cf6;
    --violet: #a78bfa;
    --green: #22c55e;
    --yellow: #f59e0b;
    --red: #ef4444;

    --shadow:
        0 20px 70px rgba(0,0,0,.35);
}

.stApp {
    background:
        radial-gradient(
            circle at 10% 0%,
            rgba(56,189,248,.12),
            transparent 28%
        ),
        radial-gradient(
            circle at 90% 0%,
            rgba(139,92,246,.14),
            transparent 30%
        ),
        linear-gradient(
            135deg,
            var(--bg),
            var(--bg2)
        );

    color: var(--text);
}

.block-container {
    max-width: 1500px;
    padding: 30px 42px 60px;
}

[data-testid="stSidebar"] {
    background:
        linear-gradient(
            180deg,
            #07111f,
            #050c17
        );

    border-right:
        1px solid
        rgba(120,150,190,.14);
}

[data-testid="stSidebar"] > div {
    padding-top: 22px;
}

h1,h2,h3,h4,h5 {
    color: var(--text) !important;
}

p,label,.stMarkdown {
    color: #c2cfdd;
}


/* ---------------- BRAND ---------------- */

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 25px;
}

.brand-icon {
    width: 46px;
    height: 46px;
    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 14px;

    background:
        linear-gradient(
            135deg,
            rgba(56,189,248,.25),
            rgba(139,92,246,.25)
        );

    border:
        1px solid
        rgba(56,189,248,.30);

    box-shadow:
        0 0 30px
        rgba(56,189,248,.16);

    font-size: 24px;
}

.brand-title {
    font-size: 21px;
    font-weight: 900;
    letter-spacing: -.5px;
}

.brand-title span {
    background:
        linear-gradient(
            90deg,
            var(--cyan),
            var(--violet)
        );

    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.brand-subtitle {
    font-size: 9px;
    letter-spacing: 2px;
    color: #64748b;
    margin-top: 2px;
}


/* ---------------- HERO ---------------- */

.hero {
    position: relative;

    background:
        linear-gradient(
            135deg,
            rgba(56,189,248,.09),
            rgba(139,92,246,.10)
        ),
        rgba(10,22,39,.92);

    border:
        1px solid
        rgba(120,150,190,.20);

    border-radius: 28px;

    padding: 42px;

    box-shadow: var(--shadow);

    overflow: hidden;

    margin-bottom: 28px;
}

.hero:after {
    content: "";
    position: absolute;

    width: 300px;
    height: 300px;

    right: -120px;
    top: -140px;

    border-radius: 50%;

    background:
        radial-gradient(
            circle,
            rgba(56,189,248,.18),
            transparent 68%
        );
}

.kicker {
    color: var(--cyan);

    font-size: 11px;
    font-weight: 900;

    letter-spacing: 2.5px;
    text-transform: uppercase;
}

.hero h1 {
    font-size: clamp(36px, 5vw, 62px);

    line-height: 1.05;

    letter-spacing: -2.5px;

    margin:
        12px 0 14px;
}

.gradient-text {
    background:
        linear-gradient(
            90deg,
            #38bdf8,
            #818cf8,
            #c084fc
        );

    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero p {
    max-width: 820px;

    color: #9fb0c4;

    font-size: 15px;

    line-height: 1.7;
}


/* ---------------- CARDS ---------------- */

.feature-card {
    min-height: 220px;

    padding: 26px;

    border-radius: 24px;

    background:
        linear-gradient(
            145deg,
            rgba(19,34,56,.95),
            rgba(9,20,35,.96)
        );

    border:
        1px solid
        rgba(120,150,190,.16);

    box-shadow:
        0 12px 45px
        rgba(0,0,0,.22);

    transition:
        transform .25s ease,
        border-color .25s ease,
        box-shadow .25s ease;
}

.feature-card:hover {
    transform: translateY(-4px);

    border-color:
        rgba(56,189,248,.42);

    box-shadow:
        0 20px 60px
        rgba(0,0,0,.38);
}

.feature-icon {
    width: 54px;
    height: 54px;

    border-radius: 17px;

    display: flex;
    align-items: center;
    justify-content: center;

    background:
        linear-gradient(
            135deg,
            rgba(56,189,248,.14),
            rgba(139,92,246,.18)
        );

    border:
        1px solid
        rgba(120,150,190,.20);

    font-size: 25px;

    margin-bottom: 18px;
}

.feature-title {
    font-size: 20px;
    font-weight: 900;

    color: #f8fafc;

    margin-bottom: 8px;
}

.feature-description {
    color: #8fa2b8;

    font-size: 13px;

    line-height: 1.6;

    min-height: 62px;
}


/* ---------------- WORKSPACE CARDS ---------------- */

.workspace-card {
    padding: 38px;

    border-radius: 30px;

    min-height: 320px;

    background:
        linear-gradient(
            145deg,
            rgba(18,34,56,.96),
            rgba(8,19,34,.98)
        );

    border:
        1px solid
        rgba(120,150,190,.18);

    box-shadow:
        0 25px 80px
        rgba(0,0,0,.32);

    text-align: left;
}

.workspace-icon {
    font-size: 55px;
    margin-bottom: 20px;
}

.workspace-title {
    font-size: 30px;
    font-weight: 950;
    margin-bottom: 10px;
}

.workspace-description {
    color: #91a3b7;
    line-height: 1.7;
    min-height: 75px;
}


/* ---------------- PANELS ---------------- */

.panel {
    background:
        rgba(12,25,43,.86);

    border:
        1px solid
        var(--border);

    border-radius: 20px;

    padding: 22px;

    margin:
        12px 0;
}


/* ---------------- BUTTONS ---------------- */

.stButton > button {
    min-height: 48px;

    border-radius: 14px !important;

    background:
        linear-gradient(
            135deg,
            #0284c7,
            #4f46e5,
            #7c3aed
        ) !important;

    border:
        1px solid
        rgba(255,255,255,.14) !important;

    color: white !important;

    font-weight: 850 !important;

    box-shadow:
        0 8px 25px
        rgba(79,70,229,.24) !important;

    transition:
        transform .2s ease,
        box-shadow .2s ease !important;
}

.stButton > button:hover {
    transform:
        translateY(-2px) !important;

    box-shadow:
        0 14px 40px
        rgba(56,189,248,.28) !important;
}


/* ---------------- TAGS ---------------- */

.tag {
    display: inline-block;

    padding: 5px 11px;

    border-radius: 999px;

    margin: 3px;

    font-size: 11px;

    font-weight: 800;

    background:
        rgba(56,189,248,.10);

    border:
        1px solid
        rgba(56,189,248,.25);

    color:
        #7dd3fc;
}


/* ---------------- STATUS ---------------- */

.status {
    display: flex;
    align-items: center;
    gap: 8px;

    font-size: 12px;
    font-weight: 800;

    color: #4ade80;
}

.status-dot {
    width: 8px;
    height: 8px;

    border-radius: 50%;

    background: #22c55e;

    box-shadow:
        0 0 12px
        #22c55e;
}


/* ---------------- METRIC ---------------- */

.metric {
    background:
        rgba(13,27,46,.90);

    border:
        1px solid
        rgba(120,150,190,.16);

    border-radius: 20px;

    padding: 22px;

    text-align: center;
}

.metric-value {
    font-size: 34px;
    font-weight: 950;

    background:
        linear-gradient(
            90deg,
            #38bdf8,
            #a78bfa
        );

    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.metric-label {
    color: #8193a8;

    font-size: 11px;

    font-weight: 800;

    letter-spacing: 1.2px;

    text-transform: uppercase;
}


/* ---------------- PROGRESS ---------------- */

.progress-track {
    width: 100%;
    height: 9px;

    border-radius: 99px;

    background: #17253a;

    overflow: hidden;
}

.progress-fill {
    height: 100%;

    border-radius: 99px;

    background:
        linear-gradient(
            90deg,
            #38bdf8,
            #6366f1,
            #a855f7
        );
}


/* ---------------- FOOTER ---------------- */

.footer {
    text-align: center;

    color: #52657d;

    font-size: 11px;

    padding: 35px 0 10px;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# ANALYTICS
# ============================================================

def log_event(
    event_type: str,
    username: str,
    rating: str = "N/A",
    details: str = "",
):
    try:
        exists = os.path.isfile(ANALYTICS_FILE)

        with open(
            ANALYTICS_FILE,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.writer(file)

            if not exists:
                writer.writerow(
                    [
                        "Timestamp",
                        "Event",
                        "Username",
                        "Rating",
                        "Details",
                    ]
                )

            writer.writerow(
                [
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    event_type,
                    username,
                    rating,
                    details,
                ]
            )

    except Exception:
        pass


# ============================================================
# API CLIENT
# ============================================================

def api_request(
    method: str,
    endpoint: str,
    *,
    timeout: int = 60,
    **kwargs,
):
    url = f"{API_BASE_URL}{endpoint}"

    response = requests.request(
        method,
        url,
        timeout=timeout,
        **kwargs,
    )

    response.raise_for_status()

    return response.json()


def api_analyze_resume(file):
    return api_request(
        "POST",
        "/api/resume/analyze",
        timeout=60,
        files={
            "file": (
                file.name,
                file.getvalue(),
                file.type,
            )
        },
    )


def api_match_job(
    resume_text: str,
    job_description: str,
):
    return api_request(
        "POST",
        "/api/job/match",
        timeout=45,
        json={
            "resume_text": resume_text,
            "job_description": job_description,
        },
    )


def api_detect_fraud(text: str):
    return api_request(
        "POST",
        "/api/job/fraud",
        timeout=45,
        json={"text": text},
    )


def api_career_roadmap(
    resume_text: str,
    target_role: str,
):
    return api_request(
        "POST",
        "/api/career/roadmap",
        timeout=60,
        json={
            "resume_text": resume_text,
            "target_role": target_role,
        },
    )


def api_screen_candidates(
    files,
    job_description: str,
):
    payload = [
        (
            "files",
            (
                file.name,
                file.getvalue(),
                file.type,
            ),
        )
        for file in files
    ]

    return api_request(
        "POST",
        "/api/recruiter/screen",
        timeout=180,
        files=payload,
        data={
            "job_description": job_description
        },
    )


def api_chat(
    messages: List[Dict],
    resume_context: str = "",
):
    try:
        result = api_request(
            "POST",
            "/api/chat/ask",
            timeout=90,
            json={
                "messages": messages,
                "resume_context": resume_context,
            },
        )

        return result.get("reply", "")

    except Exception as exc:
        return (
            "The AI service is temporarily unavailable. "
            f"Please try again. ({exc})"
        )


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "is_logged_in": False,
    "username": "Guest",
    "email": "",
    "role": "",
    "workspace": None,
    "page": "home",

    "users_db": {},

    "resume_text": "",
    "resume_analysis": None,
    "current_job_match": None,
    "salary_result": None,

    "recruiter_df": None,
    "recruiter_duplicates": [],

    "chat_messages": [],

    "assessment_questions": [],
    "assessment_answers": {},
    "assessment_role": "",
    "assessment_active": False,
    "assessment_submitted": False,
    "assessment_results": None,

    "mock_role": "",
    "mock_questions": [],
    "mock_answers": {},
    "mock_active": False,
    "mock_results": None,

    "assessment_campaign": None,
}


for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# HELPERS
# ============================================================

def reset_session_data():
    preserve = {
        "users_db": st.session_state.get(
            "users_db", {}
        )
    }

    for key, value in DEFAULT_STATE.items():
        if key == "users_db":
            continue

        st.session_state[key] = value

    st.session_state.users_db = preserve["users_db"]


def render_logo():
    st.markdown(
        """
        <div class="brand">
            <div class="brand-icon">💼</div>
            <div>
                <div class="brand-title">
                    Career<span>Lens</span> AI
                </div>
                <div class="brand-subtitle">
                    CAREER INTELLIGENCE PLATFORM
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero(
    kicker: str,
    title: str,
    subtitle: str,
):
    st.markdown(
        f"""
        <section class="hero">
            <div class="kicker">{kicker}</div>

            <h1>
                {title}
            </h1>

            <p>
                {subtitle}
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_metric(
    label: str,
    value: str,
):
    st.markdown(
        f"""
        <div class="metric">
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feature_card(
    icon: str,
    title: str,
    description: str,
):
    st.markdown(
        f"""
        <div class="feature-card">
            <div class="feature-icon">{icon}</div>

            <div class="feature-title">
                {title}
            </div>

            <div class="feature-description">
                {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_card(
    icon: str,
    title: str,
    description: str,
):
    st.markdown(
        f"""
        <div class="workspace-card">
            <div class="workspace-icon">
                {icon}
            </div>

            <div class="workspace-title">
                {title}
            </div>

            <div class="workspace-description">
                {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def navigate(page: str):
    st.session_state.page = page
    st.rerun()


def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


# ============================================================
# EXAM BLUEPRINT
# ============================================================

ROLE_BLUEPRINTS = {
    "Software Engineer / Full Stack Developer": [
        ("Aptitude & Logical Reasoning", 10),
        ("Programming & Data Structures", 20),
        ("Web & Full Stack Engineering", 15),
        ("Databases & SQL", 15),
        ("Software Engineering & Testing", 15),
        ("System Design & Real-World Scenarios", 15),
        ("Communication & Workplace Reasoning", 10),
    ],

    "Data Scientist / AI Engineer": [
        ("Aptitude & Logical Reasoning", 10),
        ("Mathematics & Statistics", 15),
        ("Python & Data Programming", 15),
        ("Machine Learning", 20),
        ("Deep Learning & Generative AI", 15),
        ("Data & SQL", 15),
        ("Communication & Workplace Reasoning", 10),
    ],

    "Cloud DevOps & SRE Engineer": [
        ("Aptitude & Logical Reasoning", 10),
        ("Linux, Networking & Systems", 15),
        ("Cloud Platforms & Infrastructure", 15),
        ("DevOps & CI/CD", 20),
        ("Containers & Infrastructure as Code", 15),
        ("Monitoring, Reliability & SRE", 15),
        ("Communication & Workplace Reasoning", 10),
    ],

    "Frontend / UI Engineer": [
        ("Aptitude & Logical Reasoning", 10),
        ("HTML & CSS", 15),
        ("JavaScript & TypeScript", 20),
        ("Frontend Frameworks", 20),
        ("UI/UX & Accessibility", 15),
        ("Performance & Testing", 10),
        ("Communication & Workplace Reasoning", 10),
    ],

    "Backend / Microservices Engineer": [
        ("Aptitude & Logical Reasoning", 10),
        ("Programming & Data Structures", 15),
        ("Backend APIs & Services", 15),
        ("Databases, SQL & Caching", 15),
        ("Distributed Systems & Microservices", 20),
        ("System Design & Architecture", 15),
        ("Communication & Workplace Reasoning", 10),
    ],

    "General / Non-IT Professional": [
        ("Quantitative Aptitude", 15),
        ("Logical Reasoning", 15),
        ("Verbal Ability", 15),
        ("Communication", 15),
        ("Role Knowledge", 20),
        ("Situational Judgement", 10),
        ("Workplace Reasoning", 10),
    ],
}


def get_blueprint(role: str):
    return ROLE_BLUEPRINTS.get(
        role,
        ROLE_BLUEPRINTS[
            "General / Non-IT Professional"
        ],
    )


# ============================================================
# FALLBACK EXAM QUESTION GENERATOR
# ============================================================

GENERIC_QUESTIONS = {
    "Aptitude & Logical Reasoning": [
        {
            "q": "If 12 workers complete a task in 14 days, how many days would 8 workers need at the same rate?",
            "o": ["21 days", "18 days", "16 days", "24 days"],
            "a": "21 days",
            "e": "Total work is 12 × 14 = 168 worker-days. 168 ÷ 8 = 21 days."
        },
        {
            "q": "What is the next number in the sequence 2, 6, 12, 20, 30, ?",
            "o": ["36", "40", "42", "44"],
            "a": "42",
            "e": "The differences are 4, 6, 8, 10, so the next difference is 12."
        },
        {
            "q": "A product costs ₹800 and receives a 15% discount. What is the selling price?",
            "o": ["₹680", "₹700", "₹720", "₹740"],
            "a": "₹680",
            "e": "15% of ₹800 is ₹120. ₹800 − ₹120 = ₹680."
        },
    ],

    "Programming & Data Structures": [
        {
            "q": "Which data structure provides average O(1) lookup by key?",
            "o": ["Hash table", "Linked list", "Binary tree", "Stack"],
            "a": "Hash table",
            "e": "Hash tables provide average constant-time lookup using hashing."
        },
        {
            "q": "Which data structure follows LIFO ordering?",
            "o": ["Queue", "Stack", "Heap", "Graph"],
            "a": "Stack",
            "e": "A stack follows Last-In, First-Out ordering."
        },
        {
            "q": "What is the average time complexity of binary search on a sorted array?",
            "o": ["O(log n)", "O(n)", "O(n log n)", "O(n²)"],
            "a": "O(log n)",
            "e": "Binary search halves the search space at each step."
        },
    ],

    "Databases & SQL": [
        {
            "q": "Which SQL command retrieves rows from a database?",
            "o": ["SELECT", "PUSH", "FETCHROW", "READ"],
            "a": "SELECT",
            "e": "SELECT is used to query data from relational tables."
        },
        {
            "q": "Which SQL clause filters rows before grouping?",
            "o": ["WHERE", "HAVING", "GROUP BY", "ORDER BY"],
            "a": "WHERE",
            "e": "WHERE filters rows before GROUP BY is applied."
        },
    ],

    "Machine Learning": [
        {
            "q": "Which metric is commonly used for classification accuracy?",
            "o": ["Accuracy", "RMSE", "MAE", "MSE"],
            "a": "Accuracy",
            "e": "Accuracy measures the proportion of correctly classified samples."
        },
        {
            "q": "What is overfitting?",
            "o": [
                "Excellent training performance but poor generalization",
                "Poor training and test performance",
                "Removing all features",
                "Increasing dataset size"
            ],
            "a": "Excellent training performance but poor generalization",
            "e": "Overfitting occurs when a model learns training-specific patterns and fails to generalize."
        },
    ],

    "Communication & Workplace Reasoning": [
        {
            "q": "A teammate disagrees with your technical approach. What is the best first response?",
            "o": [
                "Discuss the trade-offs objectively",
                "Ignore the teammate",
                "Escalate immediately",
                "Insist your approach is correct"
            ],
            "a": "Discuss the trade-offs objectively",
            "e": "Professional disagreement should begin with evidence and collaborative discussion."
        }
    ],

    "Verbal Ability": [
        {
            "q": "Choose the grammatically correct sentence.",
            "o": [
                "The team has completed the project.",
                "The team have completed the project.",
                "The team completing the project.",
                "The team has complete the project."
            ],
            "a": "The team has completed the project.",
            "e": "The singular collective noun 'team' takes 'has' in this construction."
        }
    ],

    "Situational Judgement": [
        {
            "q": "You discover a serious issue shortly before release. What should you do?",
            "o": [
                "Report it and assess release impact",
                "Hide it",
                "Delete the evidence",
                "Wait until after release"
            ],
            "a": "Report it and assess release impact",
            "e": "Critical issues should be communicated transparently and assessed before release."
        }
    ],

    "Role Knowledge": [
        {
            "q": "What is the best way to evaluate a professional decision?",
            "o": [
                "Use evidence, requirements and measurable outcomes",
                "Choose the fastest option regardless of risk",
                "Follow personal preference only",
                "Avoid measuring results"
            ],
            "a": "Use evidence, requirements and measurable outcomes",
            "e": "Professional decisions should be grounded in requirements, evidence and outcomes."
        }
    ],
}


def fallback_questions_for_section(
    section: str,
    role: str,
    count: int,
):
    pool = GENERIC_QUESTIONS.get(
        section,
        GENERIC_QUESTIONS[
            "Communication & Workplace Reasoning"
        ],
    )

    result = []

    for i in range(count):
        item = pool[i % len(pool)]

        result.append(
            {
                "section": section,
                "question": item["q"],
                "options": list(item["o"]),
                "answer": item["a"],
                "explanation": item["e"],
            }
        )

    return result


# ============================================================
# AI EXAM GENERATION
# ============================================================

def generate_exam(
    role: str,
    resume_context: str = "",
):
    blueprint = get_blueprint(role)

    total = sum(
        count
        for _, count in blueprint
    )

    system_prompt = """
You are a professional corporate assessment designer.

Create a role-specific multiple-choice examination.

STRICT RULES:

1. Return ONLY valid JSON.
2. Exactly the requested number of questions.
3. Four options per question.
4. One correct answer.
5. Include an explanation.
6. Questions must follow the section order supplied.
7. NEVER shuffle sections.
8. IDs must be sequential from 1.
9. Do not reveal the answer before submission.
10. Questions must be realistic hiring-assessment questions.
"""

    section_text = "\n".join(
        f"{idx + 1}. {name}: {count} questions"
        for idx, (name, count)
        in enumerate(blueprint)
    )

    user_prompt = f"""
ROLE:
{role}

TOTAL QUESTIONS:
{total}

SECTION BREAKDOWN:
{section_text}

Return:

[
  {{
    "id": 1,
    "section": "Section Name",
    "question": "Question",
    "options": [
      "Option A",
      "Option B",
      "Option C",
      "Option D"
    ],
    "answer": "Exact correct option",
    "explanation": "Short explanation"
  }}
]
"""

    try:
        response = api_chat(
            [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            resume_context=resume_context,
        )

        match = re.search(
            r"\[\s*\{.*\}\s*\]",
            response,
            re.DOTALL,
        )

        if match:
            data = json.loads(
                match.group(0)
            )

            cleaned = []

            for index, item in enumerate(
                data[:total],
                start=1,
            ):
                options = [
                    str(x).strip()
                    for x in item.get(
                        "options",
                        []
                    )
                ]

                answer = str(
                    item.get(
                        "answer",
                        options[0]
                        if options
                        else "",
                    )
                ).strip()

                if len(options) < 4:
                    continue

                if answer not in options:
                    continue

                cleaned.append(
                    {
                        "id": index,
                        "section": str(
                            item.get(
                                "section",
                                "General",
                            )
                        ),
                        "question": str(
                            item.get(
                                "question",
                                "",
                            )
                        ),
                        "options": options[:4],
                        "answer": answer,
                        "explanation": str(
                            item.get(
                                "explanation",
                                "",
                            )
                        ),
                    }
                )

            # Verify section order and count.
            if len(cleaned) == total:
                expected_sections = []

                for section, count in blueprint:
                    expected_sections.extend(
                        [section] * count
                    )

                actual_sections = [
                    q["section"]
                    for q in cleaned
                ]

                if actual_sections == expected_sections:
                    return cleaned

    except Exception:
        pass

    # Deterministic fallback.
    questions = []

    question_id = 1

    for section, count in blueprint:
        section_questions = fallback_questions_for_section(
            section,
            role,
            count,
        )

        for item in section_questions:
            options = list(
                item["options"]
            )

            # Shuffle ONLY options.
            random.shuffle(options)

            questions.append(
                {
                    "id": question_id,
                    "section": section,
                    "question": item["question"],
                    "options": options,
                    "answer": item["answer"],
                    "explanation": item["explanation"],
                }
            )

            question_id += 1

    return questions


# ============================================================
# LOGIN / REGISTER
# ============================================================

@st.dialog("Sign In")
def signin_dialog():

    st.markdown(
        "### Welcome back"
    )

    username = st.text_input(
        "Username / Email",
        key="login_username",
    )

    password = st.text_input(
        "Password",
        type="password",
        key="login_password",
    )

    if st.button(
        "Sign In",
        use_container_width=True,
    ):

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PIN
        ):
            st.session_state.is_logged_in = True
            st.session_state.username = "Administrator"
            st.session_state.email = ""
            st.session_state.role = "Admin"
            st.session_state.workspace = "Admin"
            st.session_state.page = "analytics"

            log_event(
                "ADMIN_LOGIN",
                "Administrator",
            )

            st.rerun()

        elif username not in st.session_state.users_db:
            st.error(
                "Account not found."
            )

        elif (
            st.session_state.users_db[
                username
            ]["password"]
            != password
        ):
            st.error(
                "Incorrect password."
            )

        else:
            user = st.session_state.users_db[
                username
            ]

            st.session_state.is_logged_in = True
            st.session_state.username = user["name"]
            st.session_state.email = user["email"]
            st.session_state.role = "User"

            log_event(
                "LOGIN",
                user["name"],
            )

            st.rerun()


@st.dialog("Create Account")
def register_dialog():

    st.markdown(
        "### Create your CareerLens account"
    )

    name = st.text_input(
        "Full Name",
        placeholder="Enter your full name",
    )

    email = st.text_input(
        "Email",
        placeholder="you@example.com",
    )

    password = st.text_input(
        "Password",
        type="password",
    )

    if st.button(
        "Create Account",
        use_container_width=True,
    ):

        if not name.strip():
            st.warning(
                "Please enter your name."
            )
            return

        if not email.strip():
            st.warning(
                "Please enter your email."
            )
            return

        if not password:
            st.warning(
                "Please create a password."
            )
            return

        if email in st.session_state.users_db:
            st.warning(
                "This email is already registered."
            )
            return

        st.session_state.users_db[email] = {
            "name": name.strip(),
            "email": email.strip(),
            "password": password,
        }

        st.session_state.is_logged_in = True
        st.session_state.username = name.strip()
        st.session_state.email = email.strip()
        st.session_state.role = "User"

        log_event(
            "REGISTER",
            name.strip(),
        )

        st.rerun()


@st.dialog("Logout")
def logout_dialog():

    st.markdown(
        "### Are you sure you want to log out?"
    )

    rating = st.feedback("stars")

    feedback = st.text_area(
        "Optional feedback"
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "Logout",
            use_container_width=True,
        ):

            rating_text = (
                f"{rating + 1} Stars"
                if rating is not None
                else "No Rating"
            )

            log_event(
                "LOGOUT",
                st.session_state.username,
                rating_text,
                feedback,
            )

            reset_session_data()

            st.rerun()

    with col2:
        if st.button(
            "Cancel",
            use_container_width=True,
        ):
            st.rerun()


# ============================================================
# LOGIN SCREEN
# ============================================================

def render_login():

    st.markdown(
        """
        <div style="
            text-align:center;
            padding:80px 0 35px;
        ">

            <div style="
                font-size:70px;
                filter:
                    drop-shadow(
                        0 0 25px
                        rgba(56,189,248,.55)
                    );
            ">
                💼
            </div>

            <h1 style="
                font-size:64px;
                font-weight:950;
                letter-spacing:-3px;
                margin:10px 0;
                background:
                    linear-gradient(
                        90deg,
                        #38bdf8,
                        #818cf8,
                        #c084fc
                    );
                -webkit-background-clip:text;
                -webkit-text-fill-color:transparent;
            ">
                CareerLens AI
            </h1>

            <p style="
                font-size:17px;
                color:#94a3b8;
            ">
                Intelligent Career & Recruitment Platform
            </p>

        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(
        [1, 1.25, 1]
    )

    with col2:

        st.markdown(
            """
            <div class="panel"
                 style="
                    text-align:center;
                    padding:35px;
                 ">

                <div class="tag">
                    AI-POWERED CAREER INTELLIGENCE
                </div>

                <h2>
                    Your career,
                    intelligently managed.
                </h2>

                <p>
                    Resume intelligence,
                    interview preparation,
                    job matching,
                    recruitment analytics
                    and AI career guidance.
                </p>

            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "Sign In",
                use_container_width=True,
            ):
                signin_dialog()

        with c2:
            if st.button(
                "Create Account",
                use_container_width=True,
            ):
                register_dialog()

        if st.button(
            "Continue as Guest",
            use_container_width=True,
        ):
            st.session_state.is_logged_in = True
            st.session_state.username = "Guest"
            st.session_state.email = ""
            st.session_state.role = "Guest"

            log_event(
                "GUEST_ACCESS",
                "Guest",
            )

            st.rerun()


# ============================================================
# WORKSPACE SELECTOR
# ============================================================

def render_workspace_selector():

    render_hero(
        "WELCOME TO CAREERLENS AI",
        "Choose Your Workspace",
        "Select how you want to use CareerLens AI. "
        "You can enter either the Job Seeker or Recruiter workspace.",
    )

    col1, col2 = st.columns(
        2,
        gap="large",
    )

    with col1:

        render_workspace_card(
            "🎯",
            "Job Seeker",
            "Build your professional profile, "
            "analyze your resume, practice interviews, "
            "take assessments, discover jobs and "
            "plan your career.",
        )

        if st.button(
            "Enter Job Seeker Workspace →",
            use_container_width=True,
            key="workspace_job_seeker",
        ):
            st.session_state.workspace = "Job Seeker"
            st.session_state.page = "job_seeker_home"
            st.rerun()

    with col2:

        render_workspace_card(
            "🏢",
            "Recruiter",
            "Screen candidates, detect duplicate resumes, "
            "rank applicants, assign assessments and "
            "manage your recruitment pipeline.",
        )

        if st.button(
            "Enter Recruiter Workspace →",
            use_container_width=True,
            key="workspace_recruiter",
        ):
            st.session_state.workspace = "Recruiter"
            st.session_state.page = "recruiter_home"
            st.rerun()


# ============================================================
# SIDEBAR
# ============================================================

def render_sidebar():

    with st.sidebar:

        render_logo()

        st.markdown(
            f"""
            <div class="panel">

                <div style="
                    font-size:10px;
                    color:#64748b;
                    text-transform:uppercase;
                    letter-spacing:1px;
                    font-weight:900;
                ">
                    Signed in as
                </div>

                <div style="
                    font-size:17px;
                    font-weight:900;
                    color:#f8fafc;
                    margin-top:4px;
                ">
                    {st.session_state.username}
                </div>

                <div class="status"
                     style="margin-top:10px;">

                    <span class="status-dot"></span>
                    Online

                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("")

        if st.button(
            "🤖 Career Assistant",
            use_container_width=True,
        ):
            st.session_state.page = "assistant"
            st.rerun()

        if st.session_state.workspace:

            st.markdown("")

            if st.button(
                "⌂ Workspace Home",
                use_container_width=True,
            ):

                if (
                    st.session_state.workspace
                    == "Job Seeker"
                ):
                    st.session_state.page = (
                        "job_seeker_home"
                    )

                elif (
                    st.session_state.workspace
                    == "Recruiter"
                ):
                    st.session_state.page = (
                        "recruiter_home"
                    )

                st.rerun()

        st.markdown("")

        if st.button(
            "↩ Change Workspace",
            use_container_width=True,
        ):
            st.session_state.workspace = None
            st.session_state.page = "workspace_selector"
            st.rerun()

        st.markdown("")

        if st.button(
            "Logout",
            use_container_width=True,
        ):
            logout_dialog()


# ============================================================
# JOB SEEKER HOME
# ============================================================

def render_job_seeker_home():

    render_hero(
        "JOB SEEKER WORKSPACE",
        "Build Your Career.",
        "Everything you need to understand your profile, "
        "prepare for interviews, discover opportunities "
        "and accelerate your career.",
    )

    analysis = (
        st.session_state.resume_analysis
        or {}
    )

    score = safe_int(
        analysis.get(
            "resume_score",
            0,
        )
    )

    readiness = safe_int(
        analysis.get(
            "readiness",
            0,
        )
    )

    skills = len(
        analysis.get(
            "skills",
            [],
        )
    )

    m1, m2, m3 = st.columns(3)

    with m1:
        render_metric(
            "Resume Score",
            f"{score}%",
        )

    with m2:
        render_metric(
            "Career Readiness",
            f"{readiness}%",
        )

    with m3:
        render_metric(
            "Detected Skills",
            str(skills),
        )

    st.markdown("### Explore Career Tools")

    features = [
        (
            "📄",
            "Analyze Resume",
            "AI-powered resume analysis, "
            "skills and ATS insights.",
            "resume_analyzer",
        ),
        (
            "📝",
            "Resume Builder",
            "Create a professional resume "
            "from completely empty fields.",
            "resume_builder",
        ),
        (
            "🧪",
            "Pre-Interview Assessment",
            "100-question, 100-mark role-based "
            "assessment with section-wise evaluation.",
            "assessment",
        ),
        (
            "🎙️",
            "AI Mock Interview",
            "Practice realistic role-specific "
            "interviews with AI feedback.",
            "mock_interview",
        ),
        (
            "🎯",
            "Job Match",
            "Compare your resume with any "
            "job description.",
            "job_match",
        ),
        (
            "💰",
            "Salary Estimation",
            "Explore role, experience and "
            "location-based salary benchmarks.",
            "salary",
        ),
        (
            "🗺️",
            "Career Roadmap",
            "Generate a personalized path "
            "toward your target role.",
            "roadmap",
        ),
        (
            "🛡️",
            "Job Safety",
            "Analyze suspicious job posts "
            "and detect potential fraud signals.",
            "job_safety",
        ),
    ]

    for row in range(
        0,
        len(features),
        2,
    ):

        cols = st.columns(
            2,
            gap="large",
        )

        for col, feature in zip(
            cols,
            features[row:row + 2],
        ):

            icon, title, desc, page = feature

            with col:

                render_feature_card(
                    icon,
                    title,
                    desc,
                )

                if st.button(
                    f"Open {title} →",
                    use_container_width=True,
                    key=f"feature_{page}",
                ):
                    st.session_state.page = page
                    st.rerun()


# ============================================================
# RESUME ANALYZER
# ============================================================

def render_resume_analyzer():

    render_hero(
        "RESUME INTELLIGENCE",
        "Understand Your Resume.",
        "Upload your resume and let CareerLens AI "
        "extract skills, evaluate readiness and "
        "identify opportunities for improvement.",
    )

    file = st.file_uploader(
        "Upload Resume",
        type=[
            "pdf",
            "docx",
            "txt",
        ],
        key="resume_analyzer_upload",
    )

    if file:

        if st.button(
            "Analyze Resume",
            use_container_width=True,
        ):

            with st.spinner(
                "Analyzing your resume..."
            ):

                try:
                    result = api_analyze_resume(
                        file
                    )

                    st.session_state.resume_analysis = result

                    st.session_state.resume_text = (
                        result.get(
                            "extracted_text",
                            "",
                        )
                    )

                    log_event(
                        "RESUME_ANALYZED",
                        st.session_state.username,
                    )

                    st.success(
                        "Resume analyzed successfully."
                    )

                except Exception as exc:
                    st.error(
                        f"Resume analysis failed: {exc}"
                    )

    if st.session_state.resume_analysis:

        result = (
            st.session_state.resume_analysis
        )

        st.markdown("### Resume Intelligence")

        c1, c2, c3 = st.columns(3)

        with c1:
            render_metric(
                "Resume Score",
                f"{safe_int(result.get('resume_score', 0))}%",
            )

        with c2:
            render_metric(
                "Readiness",
                f"{safe_int(result.get('readiness', 0))}%",
            )

        with c3:
            render_metric(
                "Skills",
                str(
                    len(
                        result.get(
                            "skills",
                            [],
                        )
                    )
                ),
            )

        st.markdown("### Profile")

        st.markdown(
            f"""
            <div class="panel">

                <h3>
                    {result.get(
                        "name",
                        "Profile"
                    )}
                </h3>

                <p>
                    📧 {result.get(
                        "email",
                        "Not found"
                    )}
                </p>

                <p>
                    📱 {result.get(
                        "phone",
                        "Not found"
                    )}
                </p>

                <p>
                    💼 {result.get(
                        "experience",
                        "Not detected"
                    )}
                </p>

            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "### Detected Skills"
        )

        skills = result.get(
            "skills",
            [],
        )

        for skill in skills:
            st.markdown(
                f'<span class="tag">{skill}</span>',
                unsafe_allow_html=True,
            )


# ============================================================
# RESUME BUILDER
# ============================================================

def render_resume_builder():

    render_hero(
        "RESUME ARCHITECT",
        "Build Your Professional Resume.",
        "Start completely blank. Enter your information "
        "and watch your resume update live.",
    )

    col1, col2 = st.columns(
        [1, 1.25],
        gap="large",
    )

    with col1:

        st.markdown(
            "### Resume Information"
        )

        template = st.selectbox(
            "Resume Style",
            [
                "Modern Professional",
                "Executive Classic",
                "Skills First",
                "Nordic Minimal",
                "Dark Professional",
            ],
        )

        name = st.text_input(
            "Full Name",
            value="",
            placeholder="Enter your full name",
        )

        title = st.text_input(
            "Target Role / Headline",
            value="",
            placeholder="e.g. Software Engineer",
        )

        email = st.text_input(
            "Email",
            value="",
            placeholder="you@example.com",
        )

        phone = st.text_input(
            "Phone",
            value="",
            placeholder="+91 XXXXX XXXXX",
        )

        location = st.text_input(
            "Location",
            value="",
            placeholder="City, Country",
        )

        links = st.text_input(
            "LinkedIn / GitHub / Portfolio",
            value="",
            placeholder="Links",
        )

        summary = st.text_area(
            "Professional Summary",
            value="",
            placeholder="Write your professional summary...",
            height=120,
        )

        skills = st.text_area(
            "Skills",
            value="",
            placeholder="Python, SQL, AWS, React...",
            height=90,
        )

        projects = st.text_area(
            "Projects",
            value="",
            placeholder="Project name and impact...",
            height=120,
        )

        experience = st.text_area(
            "Work Experience",
            value="",
            placeholder="Company, role, dates and achievements...",
            height=170,
        )

        education = st.text_area(
            "Education & Certifications",
            value="",
            placeholder="Degree, university, certifications...",
            height=110,
        )

    with col2:

        st.markdown(
            "### Live Preview"
        )

        skills_html = "".join(
            f"""
            <span style="
                display:inline-block;
                padding:4px 9px;
                margin:3px;
                border-radius:5px;
                background:#e0f2fe;
                color:#0369a1;
                font-size:11px;
                font-weight:700;
            ">
                {skill.strip()}
            </span>
            """
            for skill in skills.split(",")
            if skill.strip()
        )

        def format_lines(text):
            result = []

            for line in text.splitlines():

                if not line.strip():
                    continue

                if line.strip().startswith("•"):
                    result.append(
                        f"""
                        <div style="
                            margin:4px 0;
                            font-size:12px;
                        ">
                            {line}
                        </div>
                        """
                    )
                else:
                    result.append(
                        f"""
                        <div style="
                            margin-top:8px;
                            font-weight:800;
                            font-size:12px;
                        ">
                            {line}
                        </div>
                        """
                    )

            return "".join(result)

        preview = f"""
        <div style="
            background:#ffffff;
            color:#0f172a;
            padding:32px;
            border-radius:12px;
            min-height:900px;
            box-shadow:
                0 20px 70px rgba(0,0,0,.35);
            font-family:Arial,sans-serif;
        ">

            <div style="
                border-bottom:3px solid #0284c7;
                padding-bottom:12px;
                margin-bottom:18px;
            ">

                <div style="
                    font-size:28px;
                    font-weight:900;
                    color:#0284c7;
                ">
                    {name or "Your Name"}
                </div>

                <div style="
                    color:#6366f1;
                    font-weight:800;
                    margin-top:3px;
                ">
                    {title or "Target Role"}
                </div>

                <div style="
                    margin-top:8px;
                    font-size:11px;
                    color:#64748b;
                ">
                    {email or "email@example.com"}
                    &nbsp; | &nbsp;
                    {phone or "Phone"}
                    &nbsp; | &nbsp;
                    {location or "Location"}
                </div>

                <div style="
                    margin-top:4px;
                    font-size:11px;
                    color:#64748b;
                ">
                    {links}
                </div>

            </div>

            <div style="margin-bottom:18px;">
                <div style="
                    color:#0284c7;
                    font-size:11px;
                    font-weight:900;
                    text-transform:uppercase;
                ">
                    Summary
                </div>

                <p style="
                    font-size:12px;
                    line-height:1.6;
                ">
                    {summary}
                </p>
            </div>

            <div style="margin-bottom:18px;">
                <div style="
                    color:#0284c7;
                    font-size:11px;
                    font-weight:900;
                    text-transform:uppercase;
                ">
                    Skills
                </div>

                <div>
                    {skills_html}
                </div>
            </div>

            <div style="margin-bottom:18px;">
                <div style="
                    color:#0284c7;
                    font-size:11px;
                    font-weight:900;
                    text-transform:uppercase;
                ">
                    Projects
                </div>

                {format_lines(projects)}
            </div>

            <div style="margin-bottom:18px;">
                <div style="
                    color:#0284c7;
                    font-size:11px;
                    font-weight:900;
                    text-transform:uppercase;
                ">
                    Experience
                </div>

                {format_lines(experience)}
            </div>

            <div>
                <div style="
                    color:#0284c7;
                    font-size:11px;
                    font-weight:900;
                    text-transform:uppercase;
                ">
                    Education & Certifications
                </div>

                {format_lines(education)}
            </div>

        </div>
        """

        st.markdown(
            preview,
            unsafe_allow_html=True,
        )

        resume_text = f"""
{name}
{title}
{email} | {phone} | {location}
{links}

SUMMARY
{summary}

SKILLS
{skills}

PROJECTS
{projects}

EXPERIENCE
{experience}

EDUCATION
{education}
"""

        st.download_button(
            "Download Resume",
            resume_text.encode(
                "utf-8"
            ),
            file_name=(
                f"{name or 'resume'}_resume.txt"
            ),
            mime="text/plain",
            use_container_width=True,
        )


# ============================================================
# PRE-INTERVIEW ASSESSMENT
# ============================================================

def render_assessment():

    render_hero(
        "PRE-INTERVIEW ASSESSMENT",
        "Prove What You Know.",
        "100 questions. 100 marks. Role-specific sections. "
        "Questions appear in exact section order and "
        "correct answers remain hidden until submission.",
    )

    # ---------------- SETUP ----------------

    if (
        not st.session_state.assessment_active
        and not st.session_state.assessment_submitted
    ):

        role = st.selectbox(
            "Select Assessment Role",
            list(
                ROLE_BLUEPRINTS.keys()
            ),
        )

        st.markdown(
            "### Examination Structure"
        )

        blueprint = get_blueprint(role)

        for index, (
            section,
            count,
        ) in enumerate(
            blueprint,
            start=1,
        ):

            st.markdown(
                f"""
                <div class="panel">

                    <span class="tag">
                        SECTION {index}
                    </span>

                    <strong>
                        {section}
                    </strong>

                    <span style="
                        float:right;
                        color:#38bdf8;
                        font-weight:900;
                    ">
                        {count} Questions
                    </span>

                </div>
                """,
                unsafe_allow_html=True,
            )

        st.info(
            "Each question is worth 1 mark. "
            "Total: 100 questions / 100 marks."
        )

        if st.button(
            "Start 100-Question Examination",
            use_container_width=True,
        ):

            with st.spinner(
                "Generating your role-specific examination..."
            ):

                questions = generate_exam(
                    role,
                    st.session_state.resume_text,
                )

            st.session_state.assessment_questions = questions
            st.session_state.assessment_answers = {}
            st.session_state.assessment_role = role
            st.session_state.assessment_active = True
            st.session_state.assessment_submitted = False
            st.session_state.assessment_results = None

            st.rerun()

        return

    # ---------------- ACTIVE EXAM ----------------

    if (
        st.session_state.assessment_active
        and not st.session_state.assessment_submitted
    ):

        questions = (
            st.session_state.assessment_questions
        )

        role = (
            st.session_state.assessment_role
        )

        answered = sum(
            1
            for value
            in st.session_state.assessment_answers.values()
            if value
        )

        st.markdown(
            f"""
            <div class="panel">

                <h2>
                    {role}
                </h2>

                <div>
                    <span class="tag">
                        100 Questions
                    </span>

                    <span class="tag">
                        100 Marks
                    </span>

                    <span class="tag">
                        {answered} Answered
                    </span>

                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )

        blueprint = get_blueprint(role)

        # IMPORTANT:
        # We DO NOT shuffle questions here.
        # They remain exactly in generated section order.

        for section_index, (
            section,
            section_count,
        ) in enumerate(
            blueprint,
            start=1,
        ):

            section_questions = [
                q
                for q in questions
                if q["section"] == section
            ]

            st.markdown(
                f"""
                <div class="hero"
                     style="
                        padding:25px;
                        margin-top:25px;
                     ">

                    <div class="kicker">
                        SECTION {section_index:02d}
                    </div>

                    <h2 style="
                        margin-bottom:5px;
                    ">
                        {section}
                    </h2>

                    <p>
                        {len(section_questions)}
                        questions
                    </p>

                </div>
                """,
                unsafe_allow_html=True,
            )

            for local_index, q in enumerate(
                section_questions,
                start=1,
            ):

                qid = q["id"]

                st.markdown(
                    f"""
                    <div class="panel">

                        <span class="tag">
                            Question {qid}
                        </span>

                        <div style="
                            font-size:17px;
                            font-weight:800;
                            color:#f8fafc;
                            margin-top:12px;
                            line-height:1.6;
                        ">
                            {q['question']}
                        </div>

                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                current = (
                    st.session_state
                    .assessment_answers
                    .get(qid)
                )

                selected = st.radio(
                    "Select one answer",
                    q["options"],
                    index=(
                        q["options"].index(
                            current
                        )
                        if current in q["options"]
                        else None
                    ),
                    key=f"assessment_{qid}",
                    label_visibility="collapsed",
                )

                st.session_state.assessment_answers[
                    qid
                ] = selected

        unanswered = len(
            questions
        ) - sum(
            1
            for q in questions
            if st.session_state.assessment_answers.get(
                q["id"]
            )
        )

        if unanswered:
            st.warning(
                f"{unanswered} questions remain unanswered."
            )
        else:
            st.success(
                "All 100 questions answered."
            )

        if st.button(
            "Submit Examination",
            use_container_width=True,
        ):

            correct = 0
            breakdown = {}
            details = []

            for q in questions:

                user_answer = (
                    st.session_state
                    .assessment_answers
                    .get(q["id"])
                )

                correct_answer = q["answer"]

                is_correct = (
                    user_answer
                    == correct_answer
                )

                if is_correct:
                    correct += 1

                section = q["section"]

                if section not in breakdown:
                    breakdown[section] = {
                        "correct": 0,
                        "total": 0,
                    }

                breakdown[section]["total"] += 1

                if is_correct:
                    breakdown[
                        section
                    ]["correct"] += 1

                details.append(
                    {
                        "id": q["id"],
                        "section": section,
                        "question": q["question"],
                        "user_answer": (
                            user_answer
                            or "Not Answered"
                        ),
                        "correct_answer": correct_answer,
                        "is_correct": is_correct,
                        "explanation": q.get(
                            "explanation",
                            "",
                        ),
                    }
                )

            percentage = int(
                (correct / len(questions))
                * 100
            )

            st.session_state.assessment_results = {
                "score": percentage,
                "correct": correct,
                "total": len(questions),
                "breakdown": breakdown,
                "details": details,
            }

            st.session_state.assessment_active = False
            st.session_state.assessment_submitted = True

            log_event(
                "ASSESSMENT_COMPLETED",
                st.session_state.username,
                "N/A",
                f"{role}: {percentage}%",
            )

            st.rerun()

        return

    # ---------------- RESULTS ----------------

    if (
        st.session_state.assessment_submitted
        and st.session_state.assessment_results
    ):

        result = (
            st.session_state.assessment_results
        )

        score = result["score"]

        render_hero(
            "ASSESSMENT COMPLETE",
            f"You Scored {score}%.",
            "Your complete performance report is shown below. "
            "Correct answers are now revealed because the examination has ended.",
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            render_metric(
                "Score",
                f"{score}%",
            )

        with c2:
            render_metric(
                "Correct",
                f"{result['correct']}/{result['total']}",
            )

        with c3:
            status = (
                "Excellent"
                if score >= 80
                else (
                    "Good"
                    if score >= 60
                    else "Needs Improvement"
                )
            )

            render_metric(
                "Performance",
                status,
            )

        st.markdown(
            "### Section Performance"
        )

        for (
            section,
            data,
        ) in result[
            "breakdown"
        ].items():

            percentage = int(
                data["correct"]
                / data["total"]
                * 100
            )

            st.markdown(
                f"""
                <div class="panel">

                    <strong>
                        {section}
                    </strong>

                    <span style="
                        float:right;
                        color:#38bdf8;
                        font-weight:900;
                    ">
                        {percentage}%
                    </span>

                    <div class="progress-track"
                         style="
                            margin-top:12px;
                         ">

                        <div
                            class="progress-fill"
                            style="
                                width:{percentage}%;
                            ">
                        </div>

                    </div>

                    <small>
                        {data['correct']}
                        /
                        {data['total']}
                        correct
                    </small>

                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "### Answer Review"
        )

        for item in result[
            "details"
        ]:

            if item["is_correct"]:

                status = (
                    '<span class="tag" '
                    'style="color:#4ade80;">'
                    '✓ Correct'
                    '</span>'
                )

            else:

                status = (
                    '<span class="tag" '
                    'style="color:#f87171;">'
                    '✗ Incorrect'
                    '</span>'
                )

            st.markdown(
                f"""
                <div class="panel">

                    <div>
                        <span class="tag">
                            Q{item['id']}
                        </span>

                        {status}
                    </div>

                    <h4>
                        {item['question']}
                    </h4>

                    <p>
                        <b>Your Answer:</b>
                        {item['user_answer']}
                    </p>

                    <p style="
                        color:#4ade80;
                    ">
                        <b>Correct Answer:</b>
                        {item['correct_answer']}
                    </p>

                    <div style="
                        background:
                            rgba(15,23,42,.7);
                        padding:12px;
                        border-radius:10px;
                    ">
                        💡
                        {item['explanation']}
                    </div>

                </div>
                """,
                unsafe_allow_html=True,
            )

        if st.button(
            "Retake Assessment",
            use_container_width=True,
        ):

            st.session_state.assessment_questions = []
            st.session_state.assessment_answers = {}
            st.session_state.assessment_active = False
            st.session_state.assessment_submitted = False
            st.session_state.assessment_results = None

            st.rerun()


# ============================================================
# AI MOCK INTERVIEW
# ============================================================

def generate_mock_questions(
    role: str,
    count: int,
):

    system = """
You are an expert human interviewer.

Create realistic mock interview questions
for the selected professional role.

Mix:
- introduction
- motivation
- role-specific knowledge
- behavioral questions
- situational questions
- problem solving
- communication
- career goals

Return ONLY JSON:
[
  {
    "id": 1,
    "question": "..."
  }
]
"""

    user = f"""
ROLE:
{role}

NUMBER OF QUESTIONS:
{count}
"""

    try:

        response = api_chat(
            [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": user,
                },
            ],
            st.session_state.resume_text,
        )

        match = re.search(
            r"\[\s*\{.*\}\s*\]",
            response,
            re.DOTALL,
        )

        if match:

            data = json.loads(
                match.group(0)
            )

            result = []

            for index, item in enumerate(
                data[:count],
                start=1,
            ):

                result.append(
                    {
                        "id": index,
                        "question": str(
                            item.get(
                                "question",
                                "",
                            )
                        ),
                    }
                )

            if len(result) == count:
                return result

    except Exception:
        pass

    fallback = [
        "Tell me about yourself.",
        "Why are you interested in this role?",
        "Why should we hire you?",
        "What is your biggest professional strength?",
        "What is an area you are currently improving?",
        "Tell me about a difficult problem you solved.",
        "Describe a time you worked under pressure.",
        "How do you handle disagreement with a teammate?",
        "Where do you see yourself in five years?",
        "Why do you want to work in this industry?",
    ]

    return [
        {
            "id": index + 1,
            "question": fallback[
                index % len(fallback)
            ],
        }
        for index in range(count)
    ]


def evaluate_mock_interview(
    role: str,
    questions: List[Dict],
    answers: Dict,
):

    transcript = []

    for q in questions:

        transcript.append(
            f"""
Question:
{q['question']}

Candidate Answer:
{answers.get(q['id'], '')}
"""
        )

    prompt = f"""
Evaluate this mock interview.

ROLE:
{role}

TRANSCRIPT:
{''.join(transcript)}

Return JSON:

{{
  "overall_score": 0,
  "confidence_score": 0,
  "technical_score": 0,
  "communication_score": 0,
  "clarity_score": 0,
  "strengths": [],
  "improvements": [],
  "final_feedback": ""
}}

Scores must be from 0 to 100.
"""

    try:

        response = api_chat(
            [
                {
                    "role": "system",
                    "content":
                        "You are an expert interview evaluator. "
                        "Return valid JSON only.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            st.session_state.resume_text,
        )

        match = re.search(
            r"\{.*\}",
            response,
            re.DOTALL,
        )

        if match:
            return json.loads(
                match.group(0)
            )

    except Exception:
        pass

    return {
        "overall_score": 50,
        "confidence_score": 50,
        "technical_score": 50,
        "communication_score": 50,
        "clarity_score": 50,
        "strengths": [
            "Completed the interview.",
        ],
        "improvements": [
            "Provide more specific examples.",
            "Use measurable achievements.",
        ],
        "final_feedback":
            "Continue practicing role-specific answers.",
    }


def render_mock_interview():

    render_hero(
        "AI MOCK INTERVIEW",
        "Practice Before the Real Interview.",
        "Choose your role and number of questions. "
        "The AI interviewer asks one question at a time "
        "and evaluates your confidence, correctness, clarity "
        "and communication.",
    )

    if (
        not st.session_state.mock_active
        and not st.session_state.mock_results
    ):

        role = st.selectbox(
            "Interview Role",
            [
                "Software Engineer",
                "Data Scientist",
                "AI Engineer",
                "Data Analyst",
                "DevOps Engineer",
                "Cloud Engineer",
                "Product Manager",
                "UI/UX Designer",
                "HR / Business Role",
            ],
        )

        count = st.slider(
            "Number of Questions",
            min_value=1,
            max_value=40,
            value=10,
        )

        st.info(
            "The AI will generate questions specifically "
            "for the selected role."
        )

        if st.button(
            "Start AI Mock Interview",
            use_container_width=True,
        ):

            with st.spinner(
                "Preparing your interviewer..."
            ):

                questions = (
                    generate_mock_questions(
                        role,
                        count,
                    )
                )

            st.session_state.mock_role = role
            st.session_state.mock_questions = questions
            st.session_state.mock_answers = {}
            st.session_state.mock_active = True
            st.session_state.mock_results = None

            st.rerun()

        return

    if (
        st.session_state.mock_active
        and not st.session_state.mock_results
    ):

        role = st.session_state.mock_role

        st.markdown(
            f"""
            <div class="panel">

                <h2>
                    AI Interviewer
                </h2>

                <span class="tag">
                    {role}
                </span>

            </div>
            """,
            unsafe_allow_html=True,
        )

        for index, question in enumerate(
            st.session_state.mock_questions,
            start=1,
        ):

            st.markdown(
                f"""
                <div class="panel">

                    <span class="tag">
                        Question {index}
                    </span>

                    <h3>
                        {question['question']}
                    </h3>

                </div>
                """,
                unsafe_allow_html=True,
            )

            answer = st.text_area(
                "Your Answer",
                value=st.session_state.mock_answers.get(
                    question["id"],
                    "",
                ),
                key=f"mock_answer_{question['id']}",
                height=140,
            )

            st.session_state.mock_answers[
                question["id"]
            ] = answer

        if st.button(
            "Finish Interview & Get AI Evaluation",
            use_container_width=True,
        ):

            with st.spinner(
                "Evaluating your interview performance..."
            ):

                result = evaluate_mock_interview(
                    role,
                    st.session_state.mock_questions,
                    st.session_state.mock_answers,
                )

            st.session_state.mock_results = result
            st.session_state.mock_active = False

            st.rerun()

        return

    if st.session_state.mock_results:

        result = (
            st.session_state.mock_results
        )

        render_hero(
            "AI INTERVIEW REPORT",
            f"Your Interview Score: {safe_int(result.get('overall_score'))}%",
            "This score estimates your current interview readiness "
            "based on the answers you provided.",
        )

        cols = st.columns(4)

        metrics = [
            (
                "Overall",
                result.get(
                    "overall_score",
                    0,
                ),
            ),
            (
                "Confidence",
                result.get(
                    "confidence_score",
                    0,
                ),
            ),
            (
                "Technical",
                result.get(
                    "technical_score",
                    0,
                ),
            ),
            (
                "Communication",
                result.get(
                    "communication_score",
                    0,
                ),
            ),
        ]

        for col, (
            label,
            value,
        ) in zip(
            cols,
            metrics,
        ):

            with col:
                render_metric(
                    label,
                    f"{safe_int(value)}%",
                )

        st.markdown(
            "### Strengths"
        )

        for strength in result.get(
            "strengths",
            [],
        ):
            st.success(
                f"✓ {strength}"
            )

        st.markdown(
            "### Improvements"
        )

        for improvement in result.get(
            "improvements",
            [],
        ):
            st.warning(
                f"→ {improvement}"
            )

        st.markdown(
            "### AI Interviewer Feedback"
        )

        st.markdown(
            f"""
            <div class="panel">
                {result.get(
                    "final_feedback",
                    ""
                )}
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "Start New Mock Interview",
            use_container_width=True,
        ):

            st.session_state.mock_questions = []
            st.session_state.mock_answers = {}
            st.session_state.mock_active = False
            st.session_state.mock_results = None

            st.rerun()


# ============================================================
# JOB MATCH
# ============================================================

def render_job_match():

    render_hero(
        "JOB INTELLIGENCE",
        "Find Your Match.",
        "Compare your resume against any job description "
        "and identify matched and missing skills.",
    )

    job = st.text_area(
        "Paste Job Description",
        height=230,
    )

    if st.button(
        "Analyze Job Match",
        use_container_width=True,
    ):

        if not st.session_state.resume_text:
            st.warning(
                "Analyze your resume first."
            )
            return

        if not job.strip():
            st.warning(
                "Paste a job description."
            )
            return

        with st.spinner(
            "Calculating semantic job match..."
        ):

            try:

                result = api_match_job(
                    st.session_state.resume_text,
                    job,
                )

                st.session_state.current_job_match = result

            except Exception as exc:
                st.error(
                    f"Job match failed: {exc}"
                )

    if st.session_state.current_job_match:

        result = (
            st.session_state.current_job_match
        )

        score = safe_int(
            result.get(
                "overall",
                result.get(
                    "score",
                    0,
                ),
            )
        )

        render_metric(
            "Overall Match",
            f"{score}%",
        )

        st.markdown(
            "### Matched Skills"
        )

        for skill in result.get(
            "matched",
            [],
        ):
            st.markdown(
                f'<span class="tag">{skill}</span>',
                unsafe_allow_html=True,
            )

        st.markdown(
            "### Missing Skills"
        )

        for skill in result.get(
            "missing",
            [],
        ):
            st.markdown(
                f"""
                <span class="tag"
                      style="
                        color:#c084fc;
                        border-color:
                            rgba(192,132,252,.3);
                      ">
                    {skill}
                </span>
                """,
                unsafe_allow_html=True,
            )


# ============================================================
# SALARY
# ============================================================

SALARY_DATABASE = {
    "data analyst": {
        "fresher": (3.5, 5.5, 7.5),
        "mid": (7, 11, 16),
        "senior": (14, 20, 28),
        "lead": (22, 32, 45),
    },

    "data scientist": {
        "fresher": (6.5, 9.5, 14),
        "mid": (13, 19, 28),
        "senior": (24, 35, 52),
        "lead": (38, 55, 80),
    },

    "software engineer": {
        "fresher": (4, 6.5, 10),
        "mid": (10, 16, 24),
        "senior": (20, 30, 45),
        "lead": (32, 48, 68),
    },

    "ai engineer": {
        "fresher": (7.5, 11, 16.5),
        "mid": (15, 24, 36),
        "senior": (28, 42, 65),
        "lead": (45, 68, 100),
    },

    "machine learning engineer": {
        "fresher": (7, 10.5, 15.5),
        "mid": (14, 22, 34),
        "senior": (26, 38, 60),
        "lead": (42, 62, 90),
    },

    "devops engineer": {
        "fresher": (5, 7.5, 11.5),
        "mid": (11, 17.5, 26),
        "senior": (22, 34, 50),
        "lead": (35, 52, 75),
    },
}


def salary_estimate(
    role,
    level,
    city,
):

    role_lower = role.lower()

    matched = None

    for key in SALARY_DATABASE:

        if key in role_lower:
            matched = key
            break

    if matched is None:
        matched = "software engineer"

    if "0-2" in level:
        tier = "fresher"
    elif "3-5" in level:
        tier = "mid"
    elif "6-8" in level:
        tier = "senior"
    else:
        tier = "lead"

    low, median, high = (
        SALARY_DATABASE[
            matched
        ][tier]
    )

    factors = {
        "India Overall": 1.0,
        "Bengaluru": 1.15,
        "Hyderabad": 1.10,
        "Pune": 1.06,
        "Mumbai": 1.10,
        "Delhi NCR": 1.08,
        "Chennai": 1.04,
        "Tier-2 / Other Cities": .85,
    }

    factor = factors.get(
        city,
        1.0,
    )

    return {
        "role": matched.title(),
        "low": round(
            low * factor,
            1,
        ),
        "median": round(
            median * factor,
            1,
        ),
        "high": round(
            high * factor,
            1,
        ),
    }


def render_salary():

    render_hero(
        "COMPENSATION INTELLIGENCE",
        "Understand Your Market Value.",
        "Explore indicative India salary ranges based on role, "
        "experience and location.",
    )

    role = st.text_input(
        "Role",
        placeholder="AI Engineer",
    )

    level = st.selectbox(
        "Experience",
        [
            "Entry Level (0-2 yrs)",
            "Mid Level (3-5 yrs)",
            "Senior Level (6-8 yrs)",
            "Lead / Principal (9+ yrs)",
        ],
    )

    city = st.selectbox(
        "Location",
        [
            "India Overall",
            "Bengaluru",
            "Hyderabad",
            "Pune",
            "Mumbai",
            "Delhi NCR",
            "Chennai",
            "Tier-2 / Other Cities",
        ],
    )

    if st.button(
        "Calculate Salary",
        use_container_width=True,
    ):

        if not role.strip():
            st.warning(
                "Enter a role."
            )
            return

        st.session_state.salary_result = (
            salary_estimate(
                role,
                level,
                city,
            )
        )

    if st.session_state.salary_result:

        result = (
            st.session_state.salary_result
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            render_metric(
                "Starting",
                f"₹{result['low']} LPA",
            )

        with c2:
            render_metric(
                "Median",
                f"₹{result['median']} LPA",
            )

        with c3:
            render_metric(
                "Top Range",
                f"₹{result['high']} LPA",
            )


# ============================================================
# ROADMAP
# ============================================================

def render_roadmap():

    render_hero(
        "CAREER ROADMAP",
        "Know What To Learn Next.",
        "Generate a personalized roadmap from your current "
        "resume toward your target role.",
    )

    role = st.text_input(
        "Target Role",
        placeholder="Machine Learning Engineer",
    )

    if st.button(
        "Generate Career Roadmap",
        use_container_width=True,
    ):

        if not st.session_state.resume_text:
            st.warning(
                "Analyze your resume first."
            )
            return

        if not role.strip():
            st.warning(
                "Enter a target role."
            )
            return

        with st.spinner(
            "Building your roadmap..."
        ):

            try:

                result = api_career_roadmap(
                    st.session_state.resume_text,
                    role,
                )

                steps = result.get(
                    "steps",
                    [],
                )

                for index, step in enumerate(
                    steps,
                    start=1,
                ):

                    st.markdown(
                        f"""
                        <div class="panel">

                            <span class="tag">
                                STEP {index:02d}
                            </span>

                            <div style="
                                margin-top:10px;
                                font-size:16px;
                                font-weight:800;
                            ">
                                {step}
                            </div>

                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            except Exception as exc:
                st.error(
                    f"Roadmap failed: {exc}"
                )


# ============================================================
# JOB SAFETY
# ============================================================

def render_job_safety():

    render_hero(
        "JOB SAFETY",
        "Check Before You Apply.",
        "Analyze suspicious job descriptions and identify "
        "potential fraud indicators.",
    )

    text = st.text_area(
        "Paste Job Posting",
        height=240,
    )

    if st.button(
        "Analyze Job Safety",
        use_container_width=True,
    ):

        if not text.strip():
            st.warning(
                "Paste a job posting."
            )
            return

        with st.spinner(
            "Analyzing job safety..."
        ):

            try:

                result = api_detect_fraud(
                    text
                )

                score = safe_int(
                    result.get(
                        "score",
                        0,
                    )
                )

                level = result.get(
                    "level",
                    "UNKNOWN",
                )

                c1, c2 = st.columns(2)

                with c1:
                    render_metric(
                        "Risk Score",
                        f"{score}%",
                    )

                with c2:
                    render_metric(
                        "Verdict",
                        level,
                    )

                st.markdown(
                    f"""
                    <div class="panel">

                        <h3>
                            {level}
                        </h3>

                        <p>
                            Signals detected:
                            <strong>
                                {result.get(
                                    "signals",
                                    0
                                )}
                            </strong>
                        </p>

                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            except Exception as exc:
                st.error(
                    f"Safety analysis failed: {exc}"
                )


# ============================================================
# CAREER ASSISTANT
# ============================================================

def render_assistant():

    render_hero(
        "CAREER ASSISTANT",
        "Your AI Career Partner.",
        "Ask about resumes, interviews, skills, job searches "
        "or career decisions.",
    )

    if not st.session_state.chat_messages:

        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content":
                    "Hi! I'm your CareerLens AI assistant. "
                    "How can I help with your career today?",
            }
        ]

    for message in (
        st.session_state.chat_messages
    ):

        with st.chat_message(
            message["role"]
        ):

            st.write(
                message["content"]
            )

    prompt = st.chat_input(
        "Ask CareerLens AI..."
    )

    if prompt:

        st.session_state.chat_messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "Thinking..."
            ):

                answer = api_chat(
                    st.session_state.chat_messages,
                    st.session_state.resume_text,
                )

                st.write(answer)

        st.session_state.chat_messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        st.rerun()


# ============================================================
# RESUME DUPLICATE DETECTION
# ============================================================

def normalize_resume_text(text: str):

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9@.+ ]",
        "",
        text,
    )

    return text.strip()


def resume_hash(text: str):

    normalized = normalize_resume_text(
        text
    )

    return hashlib.sha256(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()


def extract_emails(text: str):

    return list(
        dict.fromkeys(
            re.findall(
                r"""
                [A-Za-z0-9._%+-]+
                @
                [A-Za-z0-9.-]+\.[A-Za-z]{2,}
                """,
                text,
                re.VERBOSE,
            )
        )
    )


# ============================================================
# RECRUITER HOME
# ============================================================

def render_recruiter_home():

    render_hero(
        "RECRUITMENT INTELLIGENCE",
        "Hire With Evidence.",
        "Screen candidates, remove duplicate applications, "
        "rank applicants and prepare assessments.",
    )

    df = st.session_state.recruiter_df

    total = (
        len(df)
        if df is not None
        else 0
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        render_metric(
            "Candidates",
            str(total),
        )

    with c2:
        render_metric(
            "Duplicates Removed",
            str(
                len(
                    st.session_state
                    .recruiter_duplicates
                )
            ),
        )

    with c3:
        render_metric(
            "Assessment Status",
            "Ready",
        )

    st.markdown(
        "### Recruitment Tools"
    )

    features = [
        (
            "📥",
            "Candidate Screening",
            "Upload resumes and automatically "
            "rank candidates.",
            "candidate_screening",
        ),
        (
            "🧪",
            "Assessment Center",
            "Send role-based assessments "
            "to candidates.",
            "recruiter_assessment",
        ),
        (
            "📊",
            "Candidate Results",
            "Review recruitment intelligence "
            "and assessment outcomes.",
            "recruiter_results",
        ),
    ]

    cols = st.columns(3)

    for col, feature in zip(
        cols,
        features,
    ):

        icon, title, desc, page = feature

        with col:

            render_feature_card(
                icon,
                title,
                desc,
            )

            if st.button(
                f"Open {title} →",
                use_container_width=True,
                key=f"recruiter_{page}",
            ):
                st.session_state.page = page
                st.rerun()


# ============================================================
# RECRUITER SCREENING
# ============================================================

def render_candidate_screening():

    render_hero(
        "CANDIDATE SCREENING",
        "Screen Smarter.",
        "Upload candidate resumes. CareerLens automatically "
        "removes exact duplicates before ranking.",
    )

    job = st.text_area(
        "Job Requirements",
        height=220,
    )

    files = st.file_uploader(
        "Candidate Resumes",
        type=[
            "pdf",
            "docx",
            "txt",
        ],
        accept_multiple_files=True,
    )

    shortlist_size = st.number_input(
        "Shortlist Size",
        min_value=1,
        max_value=100,
        value=20,
    )

    if st.button(
        "Screen Candidates",
        use_container_width=True,
    ):

        if not job.strip():
            st.warning(
                "Enter the job requirements."
            )
            return

        if not files:
            st.warning(
                "Upload candidate resumes."
            )
            return

        with st.spinner(
            "Screening candidates..."
        ):

            try:

                # ------------------------------------------------
                # Exact file-level duplicate detection.
                # ------------------------------------------------

                unique_files = []
                seen_hashes = set()
                duplicate_names = []

                for file in files:

                    raw = file.getvalue()

                    digest = hashlib.sha256(
                        raw
                    ).hexdigest()

                    if digest in seen_hashes:

                        duplicate_names.append(
                            file.name
                        )

                        continue

                    seen_hashes.add(
                        digest
                    )

                    unique_files.append(
                        file
                    )

                candidates = api_screen_candidates(
                    unique_files,
                    job,
                )

                df = pd.DataFrame(
                    candidates
                )

                # ------------------------------------------------
                # Second-level duplicate detection based on
                # returned email/name/text fields.
                # ------------------------------------------------

                if not df.empty:

                    duplicate_rows = []

                    seen_identity = set()

                    for index, row in df.iterrows():

                        email = str(
                            row.get(
                                "email",
                                "",
                            )
                        ).strip().lower()

                        name = str(
                            row.get(
                                "name",
                                "",
                            )
                        ).strip().lower()

                        identity = (
                            email
                            if email
                            else name
                        )

                        if (
                            identity
                            and identity
                            in seen_identity
                        ):

                            duplicate_rows.append(
                                index
                            )

                        else:

                            if identity:
                                seen_identity.add(
                                    identity
                                )

                    if duplicate_rows:

                        df = df.drop(
                            duplicate_rows
                        )

                st.session_state.recruiter_df = df

                st.session_state.recruiter_duplicates = (
                    duplicate_names
                )

                log_event(
                    "RECRUITER_SCREEN",
                    st.session_state.username,
                    details=(
                        f"Uploaded: {len(files)}, "
                        f"unique: {len(unique_files)}, "
                        f"duplicates removed: "
                        f"{len(duplicate_names)}"
                    ),
                )

                if duplicate_names:

                    st.info(
                        "Duplicate resumes were automatically removed: "
                        + ", ".join(
                            duplicate_names
                        )
                    )

                st.success(
                    f"{len(df)} unique candidates processed."
                )

            except Exception as exc:
                st.error(
                    f"Screening failed: {exc}"
                )

    df = st.session_state.recruiter_df

    if (
        df is not None
        and not df.empty
    ):

        st.markdown(
            "### Candidate Ranking"
        )

        display_df = df.head(
            int(shortlist_size)
        )

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download Candidate Ranking",
            display_df.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="candidate_ranking.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ============================================================
# RECRUITER ASSESSMENT ASSIGNMENT
# ============================================================

def render_recruiter_assessment():

    render_hero(
        "ASSESSMENT CENTER",
        "Evaluate Candidates.",
        "Assign role-specific assessments either to every "
        "candidate or only to your shortlisted candidates.",
    )

    df = st.session_state.recruiter_df

    if df is None or df.empty:

        st.info(
            "Screen candidates first."
        )

        return

    mode = st.radio(
        "Assessment Audience",
        [
            "Send to All Candidates",
            "Send to Shortlisted Candidates",
        ],
        horizontal=True,
    )

    role = st.selectbox(
        "Assessment Role",
        list(
            ROLE_BLUEPRINTS.keys()
        ),
    )

    duration = st.selectbox(
        "Exam Duration",
        [
            "30 minutes",
            "45 minutes",
            "60 minutes",
            "90 minutes",
        ],
        index=2,
    )

    st.markdown(
        "### Candidate Emails"
    )

    st.caption(
        "Emails should be extracted from resume "
        "analysis/backend candidate data. "
        "No manual email entry is required."
    )

    candidate_rows = (
        df
        if mode == "Send to All Candidates"
        else df.head(20)
    )

    emails = []

    for _, row in candidate_rows.iterrows():

        email = str(
            row.get(
                "email",
                "",
            )
        ).strip()

        if email:

            emails.append(
                email.lower()
            )

    emails = list(
        dict.fromkeys(
            emails
        )
    )

    if emails:

        for email in emails:

            st.markdown(
                f"""
                <span class="tag">
                    ✉ {email}
                </span>
                """,
                unsafe_allow_html=True,
            )

    else:

        st.warning(
            "No candidate emails were returned by "
            "the current screening API."
        )

    st.markdown(
        "### Assessment Configuration"
    )

    blueprint = get_blueprint(
        role
    )

    total_questions = sum(
        count
        for _, count in blueprint
    )

    st.info(
        f"{total_questions} questions / "
        f"{total_questions} marks / "
        f"{duration}"
    )

    if st.button(
        "Generate Assessment Campaign",
        use_container_width=True,
    ):

        campaign_id = uuid.uuid4().hex

        st.session_state.assessment_campaign = {
            "id": campaign_id,
            "role": role,
            "duration": duration,
            "mode": mode,
            "emails": emails,
            "status": "Prepared",
            "created_at": datetime.now().isoformat(),
        }

        log_event(
            "ASSESSMENT_CAMPAIGN_CREATED",
            st.session_state.username,
            details=(
                f"{role} | {mode} | "
                f"{len(emails)} candidates"
            ),
        )

        st.success(
            "Assessment campaign prepared."
        )

    if st.session_state.assessment_campaign:

        campaign = (
            st.session_state.assessment_campaign
        )

        st.markdown(
            f"""
            <div class="panel">

                <h3>
                    Assessment Campaign
                </h3>

                <p>
                    <b>Role:</b>
                    {campaign['role']}
                </p>

                <p>
                    <b>Audience:</b>
                    {campaign['mode']}
                </p>

                <p>
                    <b>Candidates:</b>
                    {len(campaign['emails'])}
                </p>

                <p>
                    <b>Status:</b>
                    {campaign['status']}
                </p>

                <p>
                    <b>Campaign ID:</b>
                    {campaign['id']}
                </p>

            </div>
            """,
            unsafe_allow_html=True,
        )

        st.warning(
            "Email delivery and persistent candidate "
            "assessment results require the FastAPI backend "
            "to store campaigns/submissions and connect "
            "to an email provider. The current frontend "
            "does not fake successful delivery."
        )


# ============================================================
# RECRUITER RESULTS
# ============================================================

def render_recruiter_results():

    render_hero(
        "RECRUITER RESULTS",
        "Candidate Intelligence.",
        "This area is reserved for recruiter-only assessment "
        "results. Candidate scores must never be exposed "
        "to candidates.",
    )

    if (
        st.session_state.assessment_campaign
        is None
    ):

        st.info(
            "No assessment campaign created yet."
        )

        return

    campaign = (
        st.session_state.assessment_campaign
    )

    st.markdown(
        f"""
        <div class="panel">

            <h3>
                Active Assessment
            </h3>

            <p>
                Role:
                <strong>
                    {campaign['role']}
                </strong>
            </p>

            <p>
                Audience:
                <strong>
                    {campaign['mode']}
                </strong>
            </p>

            <p>
                Candidates invited:
                <strong>
                    {len(campaign['emails'])}
                </strong>
            </p>

        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "When backend persistence is added, this dashboard "
        "will show candidate resume details, completion "
        "status, assessment score, section scores and "
        "recruiter recommendations here. Candidates will "
        "only receive a submission confirmation."
    )


# ============================================================
# ADMIN ANALYTICS
# ============================================================

def render_analytics():

    if st.session_state.role != "Admin":

        st.error(
            "Administrator access required."
        )

        return

    render_hero(
        "ADMIN ANALYTICS",
        "Platform Intelligence.",
        "Review system activity, registrations and "
        "user feedback.",
    )

    if not os.path.exists(
        ANALYTICS_FILE
    ):

        st.info(
            "No analytics data yet."
        )

        return

    try:

        df = pd.read_csv(
            ANALYTICS_FILE
        )

    except Exception as exc:

        st.error(
            f"Could not read analytics: {exc}"
        )

        return

    total = len(df)

    registrations = len(
        df[
            df["Event"]
            == "REGISTER"
        ]
    )

    logins = len(
        df[
            df["Event"].isin(
                [
                    "LOGIN",
                    "GUEST_ACCESS",
                ]
            )
        ]
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        render_metric(
            "Events",
            str(total),
        )

    with c2:
        render_metric(
            "Registrations",
            str(registrations),
        )

    with c3:
        render_metric(
            "Visits",
            str(logins),
        )

    st.dataframe(
        df.sort_values(
            "Timestamp",
            ascending=False,
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Analytics",
        df.to_csv(
            index=False
        ).encode("utf-8"),
        file_name="analytics.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# PAGE ROUTER
# ============================================================

def render_page():

    page = st.session_state.page

    if page == "workspace_selector":
        render_workspace_selector()

    elif page == "job_seeker_home":
        render_job_seeker_home()

    elif page == "resume_analyzer":
        render_resume_analyzer()

    elif page == "resume_builder":
        render_resume_builder()

    elif page == "assessment":
        render_assessment()

    elif page == "mock_interview":
        render_mock_interview()

    elif page == "job_match":
        render_job_match()

    elif page == "salary":
        render_salary()

    elif page == "roadmap":
        render_roadmap()

    elif page == "job_safety":
        render_job_safety()

    elif page == "recruiter_home":
        render_recruiter_home()

    elif page == "candidate_screening":
        render_candidate_screening()

    elif page == "recruiter_assessment":
        render_recruiter_assessment()

    elif page == "recruiter_results":
        render_recruiter_results()

    elif page == "assistant":
        render_assistant()

    elif page == "analytics":
        render_analytics()

    else:

        st.session_state.page = (
            "workspace_selector"
        )

        render_workspace_selector()


# ============================================================
# APPLICATION ENTRY
# ============================================================

if not st.session_state.is_logged_in:

    render_login()

else:

    render_sidebar()

    if (
        st.session_state.workspace
        is None
    ):

        st.session_state.page = (
            "workspace_selector"
        )

    render_page()


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
    <div class="footer">
        CareerLens AI • Career Intelligence Platform
    </div>
    """,
    unsafe_allow_html=True,
)
