import logging
import os
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field

from config import CHROMA_DIR, MAX_QUESTION_LENGTH, MAX_UPLOAD_BYTES, PDF_DIR, cors_origins
from ingest import ingest_documents
from rag_pipeline import DocumentStore, get_store

logging.getLogger("chromadb.telemetry").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

store: DocumentStore | None = None
groq_client: Groq | None = None
index_lock = threading.RLock()


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    sources: list[str] | None = Field(default=None, max_length=100)


class Visualization(BaseModel):
    kind: str = Field(pattern="^bar$")
    title: str = Field(min_length=1, max_length=120)
    labels: list[str] = Field(min_length=1, max_length=12)
    values: list[float] = Field(min_length=1, max_length=12)
    summary: str = Field(default="", max_length=500)


def load_services() -> None:
    global store, groq_client
    # Loading the embedding model can require a large local cache/download. Keep
    # startup responsive and initialize the search store on the first real query.
    store = None
    api_key = os.getenv("GROQ_API_KEY")
    groq_client = Groq(api_key=api_key) if api_key else None
    if not api_key:
        logger.warning("GROQ_API_KEY is not configured; /ask will be unavailable")


@asynccontextmanager
async def lifespan(_: FastAPI):
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.parent.mkdir(parents=True, exist_ok=True)
    load_services()
    yield


app = FastAPI(title="RAG ChatApp API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


def _safe_pdf_name(filename: str | None) -> str:
    name = Path(filename or "").name
    if not name or name in {".", ".."} or not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files with a valid filename are allowed")
    return name


def _is_pdf(upload: UploadFile, initial_bytes: bytes) -> bool:
    return upload.content_type in {"application/pdf", "application/x-pdf"} and initial_bytes.startswith(b"%PDF-")


def _rebuild_index() -> int:
    global store
    with index_lock:
        count = ingest_documents()
        store = get_store()
        return count


def _search(question: str, sources: list[str] | None):
    global store
    with index_lock:
        if store is None:
            store = get_store()
        return store.search(question, sources)


def _parse_completion(content: str | None) -> tuple[str, dict[str, Any] | None]:
    """Accept the structured response while gracefully handling model drift."""
    import json

    if not content:
        return "I could not generate an answer.", None
    try:
        parsed = json.loads(content)
        answer = str(parsed.get("answer", "")).strip()
        visual = parsed.get("visualization")
        if not answer:
            raise ValueError("missing answer")
        if visual and (
            not isinstance(visual, dict)
            or visual.get("kind") != "bar"
            or not isinstance(visual.get("labels"), list)
            or not isinstance(visual.get("values"), list)
            or len(visual["labels"]) != len(visual["values"])
            or not 1 <= len(visual["labels"]) <= 12
        ):
            visual = None
        return answer, visual
    except (ValueError, TypeError, json.JSONDecodeError):
        return content.strip(), None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llmConfigured": groq_client is not None}


@app.post("/upload", status_code=201)
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = _safe_pdf_name(file.filename)
    destination = PDF_DIR / filename
    temporary = PDF_DIR / f".{filename}.uploading"
    previous = PDF_DIR / f".{filename}.previous"
    total = 0
    replaced_existing = False
    try:
        with temporary.open("wb") as output:
            first_chunk = await file.read(8192)
            if not _is_pdf(file, first_chunk):
                raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF")
            output.write(first_chunk)
            total += len(first_chunk)
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF exceeds the upload size limit")
                output.write(chunk)
        if destination.exists():
            previous.unlink(missing_ok=True)
            os.replace(destination, previous)
            replaced_existing = True
        os.replace(temporary, destination)
        chunks = await run_in_threadpool(_rebuild_index)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except Exception:
        temporary.unlink(missing_ok=True)
        if replaced_existing and previous.exists():
            destination.unlink(missing_ok=True)
            os.replace(previous, destination)
        logger.exception("Failed to upload or index %s", filename)
        raise HTTPException(status_code=500, detail="The PDF could not be indexed")
    finally:
        previous.unlink(missing_ok=True)
        await file.close()
    return {"message": "PDF uploaded and indexed", "filename": filename, "chunks": chunks, "ready": True}


@app.delete("/reset")
async def reset() -> dict[str, str]:
    # This endpoint is intentionally unauthenticated for the local single-user app.
    # Protect it with authentication before exposing the service publicly.
    def clear() -> None:
        global store
        with index_lock:
            shutil.rmtree(PDF_DIR, ignore_errors=True)
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            store = None

    await run_in_threadpool(clear)
    return {"message": "All PDFs and the vector index were reset."}


@app.post("/ask")
async def ask_question(payload: Question) -> dict[str, Any]:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    if groq_client is None:
        raise HTTPException(status_code=503, detail="The language model is not configured")

    selected_sources = list(dict.fromkeys(_safe_pdf_name(source) for source in payload.sources or []))
    try:
        docs = await run_in_threadpool(_search, question, selected_sources or None)
    except Exception:
        logger.exception("Document retrieval failed")
        raise HTTPException(status_code=503, detail="Document search is temporarily unavailable")
    if not docs:
        return {"answer": "I couldn't find relevant information in the selected PDFs.", "sources": []}

    context = "\n\n---\n\n".join(doc.page_content for doc in docs)
    prompt = (
        "Answer only from the supplied document context. If the answer is not present, "
        "say you do not know based on these documents. Return a JSON object with exactly "
        "two keys: `answer` (a clear grounded answer) and `visualization`. Set visualization "
        "to null unless the user asks for a chart, graph, visual statistics, distribution, or "
        "comparison AND the context contains reliable numeric values. When it is appropriate, "
        "visualization must be an object with kind (`bar`), title, labels (1-12 short "
        "strings), values (same-length numbers), and summary. Never invent data.\n\n"
        f"Document context:\n{context}\n\nQuestion: {question}"
    )
    try:
        completion = await run_in_threadpool(
            groq_client.chat.completions.create,
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "system", "content": "You are a precise document assistant."}, {"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        answer, visualization = _parse_completion(completion.choices[0].message.content)
    except Exception:
        logger.exception("LLM request failed")
        raise HTTPException(status_code=502, detail="The language model request failed")
    return {
        "answer": answer,
        "sources": [doc.metadata for doc in docs],
        "visualization": visualization,
    }
