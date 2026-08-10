"""Vector-store access used by the API."""

from pathlib import Path
from typing import Sequence

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from config import CHROMA_DIR, RETRIEVAL_K

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def create_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=MODEL_NAME)


class DocumentStore:
    def __init__(self, persist_directory: Path = CHROMA_DIR):
        self._db = Chroma(
            persist_directory=str(persist_directory),
            embedding_function=create_embeddings(),
        )

    def search(self, question: str, sources: Sequence[str] | None = None):
        # Filter at vector-search time. Filtering after a global top-k search can
        # incorrectly produce no result for a selected document.
        where = {"source_name": {"$in": list(sources)}} if sources else None
        results = self._db.similarity_search(question, k=RETRIEVAL_K, filter=where)
        if results or not sources:
            return results

        # Compatibility with indexes created before source_name was introduced.
        # The next upload rebuilds the index with the efficient metadata field.
        allowed = set(sources)
        legacy_results = self._db.similarity_search(question, k=RETRIEVAL_K * 4)
        return [
            document
            for document in legacy_results
            if Path(str(document.metadata.get("source", ""))).name in allowed
        ][:RETRIEVAL_K]


def get_store() -> DocumentStore:
    return DocumentStore()
