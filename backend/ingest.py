"""Build a fresh Chroma index from every PDF in ``data/pdfs``."""

import os
import shutil
import tempfile
import base64
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from google import genai
from google.genai import types
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma

from config import CHROMA_DIR, OCR_MAX_PAGES, OCR_MODEL, PDF_DIR
from rag_pipeline import create_embeddings


def _ocr_scanned_pdf(pdf_path: Path) -> list[Document]:
    """Extract text from image-only PDFs with the configured vision model."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            f"{pdf_path.name} is image-only and OCR requires GEMINI_API_KEY to be configured"
        )

    pdf = pdfium.PdfDocument(str(pdf_path))
    if len(pdf) > OCR_MAX_PAGES:
        raise ValueError(
            f"{pdf_path.name} is image-only and exceeds the OCR page limit ({OCR_MAX_PAGES})"
        )

    client = genai.Client(api_key=api_key)
    documents: list[Document] = []
    for page_number in range(len(pdf)):
        image = pdf[page_number].render(scale=1.8).to_pil().convert("RGB")
        image.thumbnail((1800, 1800))
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=85, optimize=True)
        image_data = base64.b64encode(encoded.getvalue()).decode("ascii")
        completion = client.models.generate_content(
            model=OCR_MODEL,
            contents=[
                "Transcribe all readable text from this document page exactly. Preserve headings, names, dates, and bullet points. Return only the transcription.",
                types.Part.from_bytes(
                    data=base64.b64decode(image_data),
                    mime_type="image/jpeg",
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=4000,
            ),
        )
        text = (completion.text or "").strip()
        if text:
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": str(pdf_path),
                        "source_name": pdf_path.name,
                        "page": page_number,
                        "extraction_method": "vision_ocr",
                    },
                )
            )
    if not documents:
        raise ValueError(f"OCR could not read text from {pdf_path.name}")
    return documents


def ingest_documents() -> int:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths = sorted(
        path for path in PDF_DIR.iterdir() if path.suffix.lower() == ".pdf"
    )
    if not pdf_paths:
        raise ValueError("No PDF files are available to index")

    documents = []
    for pdf_path in pdf_paths:
        loaded = PyPDFLoader(str(pdf_path)).load()
        if not any(document.page_content.strip() for document in loaded):
            loaded = _ocr_scanned_pdf(pdf_path)
        for document in loaded:
            # Keep the original source path for traceability, but store a stable
            # filename for the UI's per-chat document filter.
            document.metadata["source_name"] = pdf_path.name
        documents.extend(loaded)

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        separators=["\n\n", "\n", ".", " ", ""],
    ).split_documents(documents)
    if not chunks:
        raise ValueError("No text could be extracted from the available PDFs")

    # Build outside the live directory, then replace it only after embeddings and
    # writes succeed. This prevents duplicate chunks and avoids a half-built index.
    temporary_dir = Path(
        tempfile.mkdtemp(prefix="chroma-build-", dir=CHROMA_DIR.parent)
    )
    backup_dir = CHROMA_DIR.with_name(f"{CHROMA_DIR.name}.previous")
    try:
        Chroma.from_documents(
            chunks,
            embedding=create_embeddings(),
            persist_directory=str(temporary_dir),
        )
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if CHROMA_DIR.exists():
            os.replace(CHROMA_DIR, backup_dir)
        os.replace(temporary_dir, CHROMA_DIR)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
    except Exception:
        if not CHROMA_DIR.exists() and backup_dir.exists():
            os.replace(backup_dir, CHROMA_DIR)
        raise
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir, ignore_errors=True)
    return len(chunks)


if __name__ == "__main__":
    print(f"Indexed {ingest_documents()} chunks.")
