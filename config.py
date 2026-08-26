"""Centralized CareerLens AI configuration.

Production secrets must be supplied as environment variables.
Never commit real credentials to this file or source control.
"""

from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# Application
API_BASE_URL = _env(
    "API_URL",
    "http://localhost:8000",
).rstrip("/")

APP_DB_FILE = _env(
    "CAREERLENS_DB",
    "careerlens.db",
)

ADMIN_PIN = _env("ADMIN_PIN")

PUBLIC_APP_URL = _env(
    "PUBLIC_APP_URL",
    "http://localhost:8501",
).rstrip("/")

ANALYTICS_FILE = _env(
    "ANALYTICS_FILE",
    "analytics.csv",
)


# SendGrid
# IMPORTANT:
# The actual API key must be stored in Render Environment Variables.
SENDGRID_API_KEY = _env("SENDGRID_API_KEY")

SENDGRID_FROM_EMAIL = _env(
    "SENDGRID_FROM_EMAIL",
    "careerlenssai@gmail.com",
)


# CORS
CORS_ORIGINS = _env(
    "CORS_ORIGINS",
    "*",
)


# Resume limits
MAX_RESUME_BYTES = _env(
    "MAX_RESUME_BYTES",
    str(10 * 1024 * 1024),
)

MAX_BULK_FILES = _env(
    "MAX_BULK_FILES",
    "50",
)


# IT roles
IT_ROLES = [
    "Software Developer",
    "Data Scientist",
    "Data Analyst",
    "DevOps Engineer",
    "Cybersecurity Analyst",
    "Cloud Engineer",
    "QA Engineer",
]


# Non-IT roles
NON_IT_ROLES = [
    "HR Specialist",
    "Sales Executive",
    "Marketing Manager",
    "Finance Analyst",
    "Operations Manager",
    "Customer Support Specialist",
]
