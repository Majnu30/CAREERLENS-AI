import os

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
APP_DB_FILE = os.getenv("CAREERLENS_DB", "careerlens.db")
ADMIN_PIN = os.getenv("ADMIN_PIN", "")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8501")
ANALYTICS_FILE = "analytics.csv"

# SendGrid Configuration
SENDGRID_API_KEY = os.getenv(
    "SENDGRID_API_KEY",
    "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"
)
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "noreply@careerlens.ai")

IT_ROLES = [
    "Software Developer",
    "Data Scientist",
    "Data Analyst",
    "DevOps Engineer",
    "Cybersecurity Analyst",
    "Cloud Engineer",
    "QA Engineer",
]

NON_IT_ROLES = [
    "HR Specialist",
    "Sales Executive",
    "Marketing Manager",
    "Finance Analyst",
    "Operations Manager",
    "Customer Support Specialist",
]
