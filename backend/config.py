"""Runtime configuration for the API service."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# The project-level file is the documented default; keeping the backend-local
# fallback preserves compatibility with earlier installations.
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

# Upload & processing settings
PDF_DIR = BASE_DIR / "data" / "pdfs"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_QUESTION_LENGTH = int(os.getenv("MAX_QUESTION_LENGTH", "4000"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "8"))
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "5"))

# Google Gemini settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
OCR_MODEL = os.getenv("OCR_MODEL", "gemini-2.5-flash-lite")

# Supabase settings (Postgres + pgvector)
_raw_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
if _raw_url.endswith("/rest/v1"):
    _raw_url = _raw_url[:-8].rstrip("/")
SUPABASE_URL = _raw_url

_raw_key = os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY", "")).strip()
if _raw_key.startswith("yey"):
    _raw_key = _raw_key[1:]
SUPABASE_KEY = _raw_key


def cors_origins() -> list[str]:
    """Return explicitly configured browser origins."""
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,https://localhost:5173",
    )
    # If wildcards or multiple domains are provided in production:
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins if origins else ["*"]
