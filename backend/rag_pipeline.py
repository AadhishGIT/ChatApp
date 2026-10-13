"""Production RAG Pipeline using Supabase (pgvector) and Google Gemini Embeddings."""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import httpx
from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    RETRIEVAL_K,
    SUPABASE_KEY,
    SUPABASE_URL,
)

logger = logging.getLogger(__name__)


@dataclass
class Document:
    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def get_gemini_client() -> genai.Client | None:
    if not GEMINI_API_KEY:
        return None
    return genai.Client(api_key=GEMINI_API_KEY)


def embed_texts(texts: list[str], client: genai.Client | None = None) -> list[list[float]]:
    """Embed multiple texts in batches using Google Gemini embeddings with automatic rate-limit backoff."""
    if not texts:
        return []
    client = client or get_gemini_client()
    if not client:
        raise ValueError("GEMINI_API_KEY is not configured for embeddings.")

    all_embeddings: list[list[float]] = []
    # Use larger batch size (up to 60 chunks per call) to drastically reduce total HTTP requests
    batch_size = 60
    max_retries = 4

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = None

        for attempt in range(max_retries):
            try:
                response = client.models.embed_content(
                    model=GEMINI_EMBEDDING_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(output_dimensionality=768),
                )
                break
            except Exception as e:
                err_str = str(e)
                if (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "quota" in err_str.lower()
                ) and attempt < max_retries - 1:
                    sleep_time = (attempt + 1) * 4.0
                    logger.warning(
                        "Gemini rate limit encountered. Pausing for %.1fs before retrying (attempt %d/%d)...",
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(sleep_time)
                else:
                    raise

        if response is None:
            raise RuntimeError("Failed to generate embeddings after retries.")

        if hasattr(response, "embeddings") and response.embeddings:
            for emb in response.embeddings:
                all_embeddings.append(list(emb.values))
        elif hasattr(response, "embedding") and response.embedding:
            all_embeddings.append(list(response.embedding.values))
        else:
            raise ValueError(f"Unexpected response format from embedding API: {response}")

        # Small pause between batches to respect Google AI Studio Free Tier rate limits
        if i + batch_size < len(texts):
            time.sleep(1.0)

    return all_embeddings


def embed_query(query: str, client: genai.Client | None = None) -> list[float]:
    """Embed a single query string."""
    results = embed_texts([query], client)
    if not results:
        raise ValueError("Failed to generate embedding for query.")
    return results[0]


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SupabaseDocumentStore:
    """Production vector store using Supabase pgvector with REST/RPC."""

    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_KEY):
        self.url = url.rstrip("/")
        self.key = key
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def is_configured(self) -> bool:
        return bool(self.url and self.key)

    def insert_document_sections(
        self,
        document_name: str,
        chunks: list[dict[str, Any]],
        session_id: str = "default",
        size_bytes: int = 0,
    ) -> int:
        """Insert chunked sections with embeddings into Supabase."""
        if not self.is_configured():
            raise RuntimeError("Supabase credentials are not configured.")

        # 1. First delete existing entries for this document in this session to allow overwrites
        self.delete_document(document_name, session_id=session_id)

        # 2. Extract contents and embed with Gemini
        contents = [chunk["content"] for chunk in chunks]
        embeddings = embed_texts(contents)

        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            rows.append(
                {
                    "document_name": document_name,
                    "session_id": session_id,
                    "page_number": chunk.get("page", 1),
                    "content": chunk["content"],
                    "embedding": embedding,
                    "metadata": chunk.get("metadata", {}),
                }
            )

        # 3. Batch insert rows via PostgREST
        with httpx.Client(timeout=60.0) as http_client:
            # Insert document record
            doc_row = {
                "name": document_name,
                "session_id": session_id,
                "size_bytes": size_bytes,
                "chunk_count": len(rows),
            }
            http_client.post(
                f"{self.url}/rest/v1/documents",
                headers=self.headers,
                json=doc_row,
            )

            # Insert sections in batches of 50
            batch_size = 50
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                res = http_client.post(
                    f"{self.url}/rest/v1/document_sections",
                    headers=self.headers,
                    json=batch,
                )
                res.raise_for_status()

        return len(rows)

    def search(
        self,
        question: str,
        sources: Sequence[str] | None = None,
        session_id: str = "default",
        k: int = RETRIEVAL_K,
    ) -> list[Document]:
        """Perform semantic search using the match_documents RPC."""
        if not self.is_configured():
            logger.warning("Supabase is not configured; search returned empty.")
            return []

        query_embedding = embed_query(question)
        rpc_payload: dict[str, Any] = {
            "query_embedding": query_embedding,
            "match_count": k,
            "filter_sources": list(sources) if sources else None,
            "filter_session": session_id,
        }

        with httpx.Client(timeout=30.0) as http_client:
            res = http_client.post(
                f"{self.url}/rest/v1/rpc/match_documents",
                headers=self.headers,
                json=rpc_payload,
            )
            if res.status_code != 200:
                logger.error("Supabase match_documents error %d: %s", res.status_code, res.text)
                return []
            records = res.json()

        documents = []
        for r in records:
            meta = r.get("metadata") or {}
            meta.update(
                {
                    "source": r.get("document_name"),
                    "source_name": r.get("document_name"),
                    "page": r.get("page_number", 1),
                    "similarity": r.get("similarity", 0.0),
                }
            )
            documents.append(
                Document(
                    page_content=r.get("content", ""),
                    metadata=meta,
                )
            )
        return documents

    def list_documents(self, session_id: str = "default") -> list[dict[str, Any]]:
        """List all indexed documents for a session."""
        if not self.is_configured():
            return []
        with httpx.Client(timeout=15.0) as http_client:
            res = http_client.get(
                f"{self.url}/rest/v1/documents?session_id=eq.{session_id}&order=created_at.desc",
                headers=self.headers,
            )
            if res.status_code == 200:
                return res.json()
        return []

    def delete_document(self, document_name: str, session_id: str = "default") -> None:
        """Delete a document and its section vectors."""
        if not self.is_configured():
            return
        with httpx.Client(timeout=15.0) as http_client:
            http_client.delete(
                f"{self.url}/rest/v1/document_sections?session_id=eq.{session_id}&document_name=eq.{document_name}",
                headers=self.headers,
            )
            http_client.delete(
                f"{self.url}/rest/v1/documents?session_id=eq.{session_id}&name=eq.{document_name}",
                headers=self.headers,
            )

    def reset(self, session_id: str = "default") -> None:
        """Clear all documents and embeddings for a session."""
        if not self.is_configured():
            return
        with httpx.Client(timeout=15.0) as http_client:
            http_client.delete(
                f"{self.url}/rest/v1/document_sections?session_id=eq.{session_id}",
                headers=self.headers,
            )
            http_client.delete(
                f"{self.url}/rest/v1/documents?session_id=eq.{session_id}",
                headers=self.headers,
            )


class LocalMemoryStore:
    """Fallback in-memory vector store for offline/local development without Supabase."""

    def __init__(self):
        self._sections: list[dict[str, Any]] = []
        self._documents: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return True

    def insert_document_sections(
        self,
        document_name: str,
        chunks: list[dict[str, Any]],
        session_id: str = "default",
        size_bytes: int = 0,
    ) -> int:
        self.delete_document(document_name, session_id)
        contents = [chunk["content"] for chunk in chunks]
        embeddings = embed_texts(contents)
        for chunk, emb in zip(chunks, embeddings):
            self._sections.append(
                {
                    "document_name": document_name,
                    "session_id": session_id,
                    "page_number": chunk.get("page", 1),
                    "content": chunk["content"],
                    "embedding": emb,
                    "metadata": chunk.get("metadata", {}),
                }
            )
        self._documents.append(
            {
                "name": document_name,
                "session_id": session_id,
                "size_bytes": size_bytes,
                "chunk_count": len(chunks),
            }
        )
        return len(chunks)

    def search(
        self,
        question: str,
        sources: Sequence[str] | None = None,
        session_id: str = "default",
        k: int = RETRIEVAL_K,
    ) -> list[Document]:
        query_emb = embed_query(question)
        candidates = [
            s
            for s in self._sections
            if s["session_id"] == session_id
            and (not sources or s["document_name"] in sources)
        ]
        scored = []
        for item in candidates:
            sim = _cosine_similarity(query_emb, item["embedding"])
            scored.append((sim, item))
        scored.sort(key=lambda x: x[0], reverse=True)

        docs = []
        for sim, r in scored[:k]:
            meta = dict(r.get("metadata", {}))
            meta.update(
                {
                    "source": r["document_name"],
                    "source_name": r["document_name"],
                    "page": r.get("page_number", 1),
                    "similarity": sim,
                }
            )
            docs.append(Document(page_content=r["content"], metadata=meta))
        return docs

    def list_documents(self, session_id: str = "default") -> list[dict[str, Any]]:
        return [d for d in self._documents if d["session_id"] == session_id]

    def delete_document(self, document_name: str, session_id: str = "default") -> None:
        self._sections = [
            s
            for s in self._sections
            if not (s["session_id"] == session_id and s["document_name"] == document_name)
        ]
        self._documents = [
            d
            for d in self._documents
            if not (d["session_id"] == session_id and d["name"] == document_name)
        ]

    def reset(self, session_id: str = "default") -> None:
        self._sections = [s for s in self._sections if s["session_id"] != session_id]
        self._documents = [d for d in self._documents if d["session_id"] != session_id]


_store_instance: SupabaseDocumentStore | LocalMemoryStore | None = None


def get_store() -> SupabaseDocumentStore | LocalMemoryStore:
    global _store_instance
    if _store_instance is None:
        if SUPABASE_URL and SUPABASE_KEY:
            logger.info("Initializing Supabase pgvector store")
            _store_instance = SupabaseDocumentStore()
        else:
            logger.warning(
                "SUPABASE_URL and SUPABASE_KEY not found; using in-memory vector store fallback"
            )
            _store_instance = LocalMemoryStore()
    return _store_instance
