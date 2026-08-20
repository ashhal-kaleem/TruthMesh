"""
vector_store.py — Pluggable vector store factory for FactAgent RAG layer.

Controlled by VECTOR_BACKEND env var:
  "fake"     → InMemoryVectorStore + FakeEmbeddings  (default; dev / test)
  "pgvector" → PostgreSQL pgvector + Google text-embedding-004 API (production)

Production design principles:
  - No local model files — embeddings are generated via the Google Gemini API
    (model: text-embedding-004, 768 dimensions, free quota available)
  - No local vector-file storage — vectors are stored in a PostgreSQL table
    with the pgvector extension enabled (Supabase free tier recommended)
  - The same DATABASE_URL used for auth/history also stores RAG vectors

Both backends expose an identical interface:
  .add_documents(documents: List[Document]) -> None
  .similarity_search(query: str, k: int)   -> List[Document]

Production requirements (no extra pip packages beyond psycopg2-binary):
  - DATABASE_URL → PostgreSQL instance with pgvector extension enabled
  - GOOGLE_API_KEY → for Google text-embedding-004

Test requirements (VECTOR_BACKEND=fake — default):
  - No external services required
"""

import logging
import os
from typing import List, Protocol, runtime_checkable

from langchain_core.documents import Document

VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "fake")

log = logging.getLogger(__name__)


# ── Interface ─────────────────────────────────────────────────────────────────

@runtime_checkable
class VectorStore(Protocol):
    def add_documents(self, documents: List[Document]) -> None: ...
    def similarity_search(self, query: str, k: int = 2) -> List[Document]: ...


# ── Fake backend (dev / test) ─────────────────────────────────────────────────

class _FakeVectorStore:
    """
    Wraps LangChain InMemoryVectorStore with FakeEmbeddings.
    Zero external dependencies — safe for CI and local dev.
    Set VECTOR_BACKEND=fake (or leave unset) to use this backend.
    """

    def __init__(self) -> None:
        from langchain_core.vectorstores import InMemoryVectorStore
        from langchain_community.embeddings import FakeEmbeddings

        self._store = InMemoryVectorStore(embedding=FakeEmbeddings(size=768))

    def add_documents(self, documents: List[Document]) -> None:
        self._store.add_documents(documents)

    def similarity_search(self, query: str, k: int = 2) -> List[Document]:
        return self._store.similarity_search(query, k=k)


# ── pgvector backend (production) ─────────────────────────────────────────────

class _PgVectorStore:
    """
    Cloud-native vector store backed by PostgreSQL + pgvector extension.

    Storage:    rag_documents table in the same PostgreSQL instance used for
                auth / claim history (DATABASE_URL). Supabase free tier has
                pgvector pre-installed. No local file or index storage.

    Embeddings: Google text-embedding-004 API via google-generativeai.
                768 dimensions. Free quota; separate from chat LLM quota.

    Deduplication: content-level — exact duplicate claims are not re-embedded.

    Set VECTOR_BACKEND=pgvector to activate this backend.
    """

    # DDL run once at startup
    _INIT_SQL = """
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS rag_documents (
            id        SERIAL PRIMARY KEY,
            content   TEXT        NOT NULL,
            embedding vector(768) NOT NULL,
            metadata  JSONB       NOT NULL DEFAULT '{}'
        );
    """

    def __init__(self) -> None:
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url or "sqlite" in db_url:
            raise RuntimeError(
                "VECTOR_BACKEND=pgvector requires a PostgreSQL DATABASE_URL. "
                "Supabase free tier (https://supabase.com) is recommended."
            )
        self._db_url = db_url
        self._init_table()
        log.info("[vector_store] pgvector backend ready (Google text-embedding-004)")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _connect(self):
        """Open and return a new psycopg2 connection."""
        import psycopg2
        return psycopg2.connect(self._db_url)

    def _embed(self, text: str) -> List[float]:
        """
        Embed *text* using Google text-embedding-004.
        Returns a list of 768 floats. No local model download.
        """
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is required for VECTOR_BACKEND=pgvector embeddings"
            )
        genai.configure(api_key=api_key)
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
        )
        return result["embedding"]   # list[float], len == 768

    @staticmethod
    def _vec_literal(embedding: List[float]) -> str:
        """Serialise a float list to the pgvector literal format '[0.1,0.2,...]'."""
        return "[" + ",".join(f"{v:.9f}" for v in embedding) + "]"

    def _init_table(self) -> None:
        """Create the pgvector extension and rag_documents table if absent."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(self._INIT_SQL)
            conn.commit()
        finally:
            conn.close()

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_documents(self, documents: List[Document]) -> None:
        """
        Embed each document and store it in rag_documents.
        Exact duplicate content (by text equality) is skipped.
        Makes one Google embedding API call per unique document.
        """
        import psycopg2.extras

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for doc in documents:
                    embedding = self._embed(doc.page_content)
                    vec_lit = self._vec_literal(embedding)
                    meta = psycopg2.extras.Json(doc.metadata or {})
                    # Skip if identical content already stored
                    cur.execute(
                        """
                        INSERT INTO rag_documents (content, embedding, metadata)
                        SELECT %s, %s::vector, %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM rag_documents WHERE content = %s
                        )
                        """,
                        (doc.page_content, vec_lit, meta, doc.page_content),
                    )
            conn.commit()
        finally:
            conn.close()

    def similarity_search(self, query: str, k: int = 2) -> List[Document]:
        """
        Embed *query* and return the *k* most similar stored documents
        using pgvector cosine distance (<=>).
        Makes one Google embedding API call.
        """
        embedding = self._embed(query)
        vec_lit = self._vec_literal(embedding)

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, metadata
                    FROM   rag_documents
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  %s
                    """,
                    (vec_lit, k),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [
            Document(page_content=row[0], metadata=row[1] or {})
            for row in rows
        ]


# ── Factory ───────────────────────────────────────────────────────────────────

def create_vector_store() -> VectorStore:
    """
    Return a configured vector store based on VECTOR_BACKEND env var.

    "fake"     → _FakeVectorStore  (InMemoryVectorStore + FakeEmbeddings)
    "pgvector" → _PgVectorStore    (PostgreSQL + pgvector + Google Embeddings API)

    Usage:
        store = create_vector_store()
        store.add_documents([Document(page_content="...", metadata={...})])
        docs = store.similarity_search("my query", k=3)
    """
    if VECTOR_BACKEND == "pgvector":
        log.info("[vector_store] Backend → pgvector (Google text-embedding-004)")
        return _PgVectorStore()

    log.info("[vector_store] Backend → InMemoryVectorStore + FakeEmbeddings")
    return _FakeVectorStore()
