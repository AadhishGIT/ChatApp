import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")
CHROMA_DIR = os.path.join(BASE_DIR, "data", "chroma")


def ingest_docs():
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(CHROMA_DIR, exist_ok=True)

    documents = []

    # 1) Load all PDFs
    for fname in os.listdir(PDF_DIR):
        if not fname.lower().endswith(".pdf"):
            continue
        pdf_path = os.path.join(PDF_DIR, fname)
        print(f"[ingest] Loading {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        documents.extend(docs)

    if not documents:
        print("[ingest] No documents found in data/pdfs")
        return

    # 2) Chunk documents
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"[ingest] Total chunks: {len(chunks)}")

    if not chunks:
        print("[ingest] No chunks created, aborting.")
        return

    # 3) Embeddings
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # 4) Store in Chroma
    _ = Chroma.from_documents(
        chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
    )

    print("[ingest] Ingestion complete.")


if __name__ == "__main__":
    ingest_docs()
