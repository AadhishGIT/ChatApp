"""Production FastAPI application for RAG ChatApp with Supabase pgvector and Google Gemini."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MAX_QUESTION_LENGTH,
    MAX_UPLOAD_BYTES,
    PDF_DIR,
    SUPABASE_KEY,
    SUPABASE_URL,
    cors_origins,
)
from ingest import ingest_pdf_bytes
from rag_pipeline import Document, get_gemini_client, get_store

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    sources: list[str] | None = Field(default=None, max_length=100)
    session_id: str = Field(default="default", max_length=100)


@asynccontextmanager
async def lifespan(_: FastAPI):
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="DocuMind RAG API",
    version="2.0.0",
    description="Production RAG API powered by Google Gemini and Supabase pgvector",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _safe_pdf_name(filename: str | None) -> str:
    name = Path(filename or "").name
    if not name or name in {".", ".."} or not name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Only PDF files with a valid filename are allowed."
        )
    return name


def _is_pdf(upload: UploadFile, initial_bytes: bytes) -> bool:
    return (
        upload.content_type in {"application/pdf", "application/x-pdf", "binary/octet-stream"}
        or initial_bytes.startswith(b"%PDF-")
    )


def _parse_completion(content: str | None) -> tuple[str, dict[str, Any] | None]:
    """Parse JSON answer or fallback to plain text if format deviates."""
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
            or not (1 <= len(visual["labels"]) <= 12)
        ):
            visual = None
        return answer, visual
    except (ValueError, TypeError, json.JSONDecodeError):
        return content.strip(), None


@app.get("/health")
def health() -> dict[str, Any]:
    client = get_gemini_client()
    has_supabase = bool(SUPABASE_URL and SUPABASE_KEY)
    return {
        "status": "ok",
        "llmConfigured": client is not None,
        "supabaseConfigured": has_supabase,
        "vectorStore": "supabase" if has_supabase else "local_memory",
        "model": GEMINI_MODEL,
    }


@app.get("/documents")
async def list_documents(session_id: str = Query("default")) -> list[dict[str, Any]]:
    """List all documents indexed for the specified session."""
    store = get_store()
    docs = await run_in_threadpool(store.list_documents, session_id=session_id)
    return docs


@app.post("/upload", status_code=201)
async def upload_pdf(
    file: UploadFile = File(...),
    session_id: str = Form("default"),
) -> dict[str, Any]:
    """Upload and index a PDF file using Gemini embeddings and Supabase pgvector."""
    filename = _safe_pdf_name(file.filename)
    initial_bytes = await file.read(8192)
    if not _is_pdf(file, initial_bytes):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF")

    pdf_chunks = [initial_bytes]
    total_bytes = len(initial_bytes)
    while chunk := await file.read(1024 * 1024):
        total_bytes += len(chunk)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PDF exceeds maximum allowed upload size")
        pdf_chunks.append(chunk)

    full_pdf_bytes = b"".join(pdf_chunks)
    await file.close()

    gemini_client = get_gemini_client()
    try:
        chunks_count = await run_in_threadpool(
            ingest_pdf_bytes,
            pdf_bytes=full_pdf_bytes,
            filename=filename,
            session_id=session_id,
            gemini_client=gemini_client,
        )
    except ValueError as e:
        logger.warning("Ingestion error for %s: %s", filename, e)
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        logger.exception("Supabase HTTP error during upload of %s", filename)
        err_msg = "Database error"
        try:
            payload = e.response.json()
            err_msg = payload.get("message") or payload.get("hint") or str(e)
        except Exception:
            err_msg = str(e)
        raise HTTPException(
            status_code=500,
            detail=f"Supabase error: {err_msg}. Tip: Use your service_role key or run the GRANT SQL in Supabase.",
        )
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            logger.warning("Quota/Rate-limit reached during ingestion: %s", err_str)
            raise HTTPException(
                status_code=429,
                detail="Google AI Studio Free Tier rate limit reached (15 RPM burst limit). Please wait 30 seconds and retry, or upload documents under 25-30 pages.",
            )
        logger.exception("Failed to ingest %s into vector store", filename)
        raise HTTPException(
            status_code=500, detail=f"Failed to process and index PDF: {str(e)}"
        )

    return {
        "message": f"Successfully indexed {filename}",
        "filename": filename,
        "chunks": chunks_count,
        "ready": True,
    }


@app.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    session_id: str = Query("default"),
) -> dict[str, str]:
    """Delete a specific document and its embeddings from the vector store."""
    safe_name = _safe_pdf_name(filename)
    store = get_store()
    await run_in_threadpool(store.delete_document, document_name=safe_name, session_id=session_id)
    return {"message": f"Document '{safe_name}' deleted."}


@app.delete("/reset")
async def reset(session_id: str = Query("default")) -> dict[str, str]:
    """Reset all documents and vector embeddings for the specified session."""
    store = get_store()
    await run_in_threadpool(store.reset, session_id=session_id)
    return {"message": f"All indexed documents for session '{session_id}' were reset."}


@app.post("/ask")
async def ask_question(payload: Question) -> dict[str, Any]:
    """Ask a question grounded in the selected PDF context."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    client = get_gemini_client()
    if not client:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured on the server.",
        )

    selected_sources = list(
        dict.fromkeys(_safe_pdf_name(source) for source in payload.sources or [])
    )
    store = get_store()

    try:
        docs: list[Document] = await run_in_threadpool(
            store.search,
            question=question,
            sources=selected_sources or None,
            session_id=payload.session_id,
        )
    except Exception:
        logger.exception("Document retrieval failed")
        raise HTTPException(
            status_code=503, detail="Document search is temporarily unavailable"
        )

    if not docs:
        return {
            "answer": "I couldn't find relevant information in the selected PDFs.",
            "sources": [],
            "visualization": None,
        }

    context = "\n\n---\n\n".join(
        f"[Document: {doc.metadata.get('source_name', 'Unknown')}, Page: {doc.metadata.get('page', 1)}]\n{doc.page_content}"
        for doc in docs
    )

    prompt = (
        "Answer only from the supplied document context. If the answer is not present, "
        "say you do not know based on these documents. Return a JSON object with exactly "
        "two keys: `answer` (a clear grounded answer with markdown formatting if helpful) "
        "and `visualization`. Set visualization to null unless the user asks for a chart, "
        "graph, visual statistics, distribution, or comparison AND the context contains reliable "
        "numeric values. When appropriate, visualization must be an object with kind (`bar`), "
        "title, labels (1-12 short strings), values (same-length numbers), and summary.\n\n"
        f"Document context:\n{context}\n\nQuestion: {question}"
    )

    try:
        completion = await run_in_threadpool(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a precise, professional document assistant. Return valid JSON only.",
                temperature=0.2,
                max_output_tokens=1500,
                response_mime_type="application/json",
            ),
        )
        answer, visualization = _parse_completion(completion.text)
    except Exception:
        logger.exception("LLM generation request failed")
        raise HTTPException(status_code=502, detail="The language model request failed.")

    return {
        "answer": answer,
        "sources": [doc.metadata for doc in docs],
        "visualization": visualization,
    }


@app.post("/ask/stream")
async def ask_question_stream(payload: Question):
    """Stream response tokens using Server-Sent Events (SSE) for low latency."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    client = get_gemini_client()
    if not client:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")

    selected_sources = list(
        dict.fromkeys(_safe_pdf_name(source) for source in payload.sources or [])
    )
    store = get_store()

    try:
        docs: list[Document] = await run_in_threadpool(
            store.search,
            question=question,
            sources=selected_sources or None,
            session_id=payload.session_id,
        )
    except Exception as e:
        logger.exception("Search failed during streaming: %s", e)
        docs = []

    async def event_generator() -> AsyncGenerator[str, None]:
        if not docs:
            msg = json.dumps(
                {
                    "type": "error",
                    "text": "I couldn't find relevant information in the selected PDFs.",
                    "sources": [],
                }
            )
            yield f"data: {msg}\n\n"
            return

        context = "\n\n---\n\n".join(
            f"[Document: {doc.metadata.get('source_name', 'Unknown')}, Page: {doc.metadata.get('page', 1)}]\n{doc.page_content}"
            for doc in docs
        )

        sources_metadata = [doc.metadata for doc in docs]
        prompt = (
            "Answer the question directly, accurately, and thoroughly using only the supplied context. "
            "Use clear Markdown formatting with headers, lists, or bolding where appropriate. "
            "If the information is not in the context, explicitly say that it is not available in the documents.\n\n"
            f"Document context:\n{context}\n\nQuestion: {question}"
        )

        try:
            stream = client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a helpful, precise document AI assistant.",
                    temperature=0.2,
                    max_output_tokens=2000,
                ),
            )

            for chunk in stream:
                if chunk.text:
                    payload_chunk = json.dumps({"type": "token", "token": chunk.text})
                    yield f"data: {payload_chunk}\n\n"
                    await asyncio.sleep(0.01)

            # Signal completion with sources metadata
            done_payload = json.dumps({
                "type": "done",
                "sources": sources_metadata,
            })
            yield f"data: {done_payload}\n\n"

        except Exception as err:
            logger.exception("Error while streaming completion: %s", err)
            err_payload = json.dumps({
                "type": "error",
                "text": "An error occurred while generating the answer.",
            })
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
