import os
import shutil
import subprocess
import logging
from typing import Dict, List, Any, Optional
import os

logging.getLogger("chromadb.telemetry").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

from rag_pipeline import get_retriever

# ---- Env & paths ----
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")
INGEST_SCRIPT = os.path.join(BASE_DIR, "ingest.py")

os.makedirs(PDF_DIR, exist_ok=True)

# ---- FastAPI app ----
app = FastAPI(title="RAG ChatApp Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---- Global objects ----
retriever = None
groq_client = None

class Question(BaseModel):
    question: str
    # list of PDF filenames that this chat is allowed to use
    sources: Optional[List[str]] = None

def load_retriever():
    global retriever
    print("[app] Loading retriever from Chroma...")
    retriever = get_retriever()
    print("[app] Retriever loaded.")


def load_groq_client():
    global groq_client
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY not set in environment or .env")
    groq_client = Groq(api_key=groq_api_key)
    print("[app] Groq client initialized.")


@app.on_event("startup")
def startup_event():
    load_groq_client()
    load_retriever()


def run_ingest_blocking():
    """
    Run ingest.py synchronously and reload the retriever afterwards.
    """
    print("[app] Running ingestion...")
    python_exec = os.environ.get("PYTHON_EXECUTABLE", "python3")
    result = subprocess.run(
        [python_exec, INGEST_SCRIPT],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("Ingestion failed")
    load_retriever()
    print("[app] Ingestion and retriever reload complete.")


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> Dict:
    """
    Upload a PDF, save to data/pdfs, then re-run ingestion and reload retriever.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    save_path = os.path.join(PDF_DIR, file.filename)

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    try:
        run_ingest_blocking()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return {
        "message": "PDF uploaded and processed successfully",
        "filename": file.filename,
        "ready": True,
    }


@app.post("/ask")
def ask_question(payload: Question) -> Dict:
    """
    Retrieve relevant chunks and send ONLY those to Groq LLM.
    Optionally restrict to specific PDF filenames from `payload.sources`.
    """
    global retriever, groq_client
    if retriever is None or groq_client is None:
        raise HTTPException(status_code=503, detail="Backend not initialized")

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    # 1) Retrieve relevant chunks
    docs = retriever.get_relevant_documents(question)
    print("[ask] Retrieved", len(docs), "documents for question:", question)

    # Only filter if we actually have at least one selected PDF
    if payload.sources:
        allowed = set(payload.sources)
        filtered_docs = []
        for d in docs:
            meta = getattr(d, "metadata", {}) or {}
            src_path = meta.get("source", "")
            name = os.path.basename(src_path) if src_path else ""
            if name in allowed:
                filtered_docs.append(d)
        docs = filtered_docs
        print("[ask] After source filter, remaining docs:", len(docs))


    for i, d in enumerate(docs[:3]):
        print(f"[ask] Doc {i} snippet:", (d.page_content or "").replace("\n", " ")[:200])
        print(f"[ask] Doc {i} metadata:", getattr(d, "metadata", {}))

    if not docs:
        return {
            "answer": "I couldn't find anything in the selected PDFs for this question.",
            "sources": [],
        }

    # 2) Build context
    context_parts: List[str] = []
    sources: List[Dict] = []

    for d in docs:
        context_parts.append(d.page_content)
        sources.append(getattr(d, "metadata", {}) or {})

    context_text = "\n\n---\n\n".join(context_parts)

    # 3) Build prompt for Groq
    prompt = f"""
    You are a helpful assistant. Use the document context below to answer the question.

    - The context may come from multiple documents.
    - Combine information from different parts of the context when helpful.
    - Prefer using the context when it is relevant.
    - If the context is only partially relevant, still answer as well as you can and say when you are unsure.
    - Only if the context is completely unrelated to the question, say: "I don't know based on this document."

    Context:
    {context_text}

    Question:
    {question}

    Answer in a clear paragraph:
    """.strip()

    # 4) Call Groq LLM directly
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a precise RAG assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        answer = completion.choices[0].message.content
        print("[ask] LLM raw answer:", answer)
    except Exception as e:
        print("[app:/ask] Groq error:", e)
        raise HTTPException(status_code=500, detail="LLM call failed")

    return {
        "answer": answer,
        "sources": sources,
    }


@app.get("/")
def root():
    return {"message": "RAG ChatApp backend running"}
