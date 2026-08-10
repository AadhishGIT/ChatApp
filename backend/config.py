"""Runtime configuration for the API service."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# The project-level file is the documented default; keeping the backend-local
# fallback preserves compatibility with earlier installations.
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

PDF_DIR = BASE_DIR / "data" / "pdfs"
CHROMA_DIR = BASE_DIR / "data" / "chroma"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_QUESTION_LENGTH = int(os.getenv("MAX_QUESTION_LENGTH", "4000"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "8"))
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "5"))
OCR_MODEL = os.getenv("OCR_MODEL", "qwen/qwen3.6-27b")


def cors_origins() -> list[str]:
    """Return explicitly configured browser origins (never credentials + wildcard)."""
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
