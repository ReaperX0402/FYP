from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
    FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    DATA_ROOT = os.getenv("DATA_ROOT", "./data")
    INCOMING_DIR = os.getenv("INCOMING_DIR", "./data/incoming")
    ARCHIVE_DIR = os.getenv("ARCHIVE_DIR", "./data/archive")
    EXPORT_DIR = os.getenv("EXPORT_DIR", "./data/exports")
    AI_REVIEW_DIR = os.getenv("AI_REVIEW_DIR", "./data/ai_review")