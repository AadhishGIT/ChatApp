"""PDF Ingestion and indexing pipeline using Gemini embeddings and Supabase pgvector."""

import base64
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import pypdf
import pypdfium2 as pdfium
from google import genai
from google.genai import types
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import OCR_MAX_PAGES, OCR_MODEL, PDF_DIR
from rag_pipeline import get_gemini_client, get_store

logger = logging.getLogger(__name__)


def ocr_scanned_page(client: genai.Client, image_bytes: bytes) -> str:
    """Extract text from an image-based PDF page using Gemini vision."""
    completion = client.models.generate_content(
        model=OCR_MODEL,
        contents=[
            "Transcribe all readable text from this document page exactly. "
            "Preserve headings, tables, names, dates, and bullet points. Return only the text.",
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=3000,
        ),
    )
    return (completion.text or "").strip()


def extract_chunks_from_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    gemini_client: genai.Client | None = None,
) -> list[dict[str, Any]]:
    """Extract text from PDF bytes (with automatic OCR fallback) and split into chunks."""
    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    raw_pages: list[tuple[int, str]] = []

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        text = (page.extract_text() or "").strip()
        raw_pages.append((page_num, text))

    # Check if this PDF is an image-only/scanned document
    total_text = "".join(text for _, text in raw_pages)
    if not total_text.strip():
        logger.info("PDF %s appears to be scanned; running vision OCR...", filename)
        client = gemini_client or get_gemini_client()
        if not client:
            raise ValueError(
                f"{filename} is image-only and OCR requires GEMINI_API_KEY to be configured"
            )

        pdf = pdfium.PdfDocument(pdf_bytes)
        num_pages = len(pdf)
        if num_pages > OCR_MAX_PAGES:
            raise ValueError(
                f"{filename} is image-only and exceeds the OCR page limit ({OCR_MAX_PAGES})"
            )

        raw_pages = []
        for page_idx in range(num_pages):
            page_num = page_idx + 1
            image = pdf[page_idx].render(scale=1.8).to_pil().convert("RGB")
            image.thumbnail((1800, 1800))
            buf = BytesIO()
            image.save(buf, format="JPEG", quality=85, optimize=True)
            ocr_text = ocr_scanned_page(client, buf.getvalue())
            raw_pages.append((page_num, ocr_text))

    # Split page contents into semantic chunks (optimized for 8k Gemini embedding context)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1800,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[dict[str, Any]] = []
    for page_num, text in raw_pages:
        if not text.strip():
            continue
        page_chunks = splitter.split_text(text)
        for chunk_text in page_chunks:
            if chunk_text.strip():
                chunks.append(
                    {
                        "content": chunk_text,
                        "page": page_num,
                        "metadata": {
                            "source_name": filename,
                            "page": page_num,
                        },
                    }
                )

    return chunks


def ingest_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    session_id: str = "default",
    gemini_client: genai.Client | None = None,
) -> int:
    """Process PDF bytes and store chunks + embeddings into the vector store."""
    chunks = extract_chunks_from_pdf_bytes(pdf_bytes, filename, gemini_client)
    if not chunks:
        raise ValueError(f"No extractable text found in {filename}")

    store = get_store()
    count = store.insert_document_sections(
        document_name=filename,
        chunks=chunks,
        session_id=session_id,
        size_bytes=len(pdf_bytes),
    )
    return count


def ingest_directory(session_id: str = "default") -> int:
    """Ingest all PDFs present in the data/pdfs directory."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths = sorted(path for path in PDF_DIR.iterdir() if path.suffix.lower() == ".pdf")
    if not pdf_paths:
        logger.info("No PDF files found in %s", PDF_DIR)
        return 0

    total_chunks = 0
    client = get_gemini_client()
    for path in pdf_paths:
        logger.info("Ingesting %s...", path.name)
        with path.open("rb") as f:
            pdf_bytes = f.read()
        chunks_count = ingest_pdf_bytes(
            pdf_bytes=pdf_bytes,
            filename=path.name,
            session_id=session_id,
            gemini_client=client,
        )
        total_chunks += chunks_count
        logger.info("Indexed %s with %d chunks", path.name, chunks_count)

    return total_chunks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Ingesting PDFs from data/pdfs...")
    indexed = ingest_directory()
    print(f"Ingestion complete. Total chunks indexed: {indexed}")
