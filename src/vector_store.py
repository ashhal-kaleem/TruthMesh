"""
vector_store.py — Pluggable vector store factory for FactAgent RAG layer.

Controlled by VECTOR_BACKEND env var:
  "fake"     → InMemoryVectorStore + FakeEmbeddings  (default; dev / test)
  "chromadb" → ChromaDB + sentence-transformers       (production; no API cost)

Both backends expose the same interface:
  .add_documents(documents: List[Document]) -> None
  .similarity_search(query: str, k: int)   -> List[Document]

For production, install the extras:
  pip install chromadb sentence-transformers

CHROMA_DIR env var sets the persistence directory (default: ./chroma_db).
If ChromaDB fails to open a persistent store it falls back to an in-memory
ephemeral client so the service still starts.
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
    """

    def __init__(self) -> None:
        from langchain_core.vectorstores import InMemoryVectorStore
        from langchain_community.embeddings import FakeEmbeddings

        self._store = InMemoryVectorStore(embedding=FakeEmbeddings(size=768))

    def add_documents(self, documents: List[Document]) -> None:
        self._store.add_documents(documents)

    def similarity_search(self, query: str, k: int = 2) -> List[Document]:
        return self._store.similarity_search(query, k=k)


# ── ChromaDB backend (production) ─────────────────────────────────────────────

class _ChromaVectorStore:
    """
    ChromaDB with sentence-transformers embeddings.
    Free, runs locally, no external API required.
    Model: all-MiniLM-L6-v2 (~22 MB, downloads on first use).
    """

    def __init__(self) -> None:
        import chromadb  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore

        chroma_dir = os.getenv("CHROMA_DIR", "./chroma_db")
        try:
            self._client = chromadb.PersistentClient(path=chroma_dir)
            log.info("[vector_store] ChromaDB persistent store: %s", chroma_dir)
        except Exception as exc:
            log.warning(
                "[vector_store] PersistentClient failed (%s) — using ephemeral fallback", exc
            )
            self._client = chromadb.EphemeralClient()

        self._collection = self._client.get_or_create_collection(
            "fact_agent_rag",
            metadata={"hnsw:space": "cosine"},
        )
        self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("[vector_store] sentence-transformers model loaded")

    def add_documents(self, documents: List[Document]) -> None:
        for doc in documents:
            embedding = self._encoder.encode(doc.page_content).tolist()
            # Stable ID via hash — upsert prevents exact duplicates
            doc_id = str(abs(hash(doc.page_content)))
            self._collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[doc.page_content],
                metadatas=[doc.metadata or {}],
            )

    def similarity_search(self, query: str, k: int = 2) -> List[Document]:
        count = self._collection.count()
        if count == 0:
            return []
        embedding = self._encoder.encode(query).tolist()
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(k, count),
            include=["documents", "metadatas"],
        )
        return [
            Document(page_content=content, metadata=meta)
            for content, meta in zip(
                results["documents"][0], results["metadatas"][0]
            )
        ]


# ── Factory ───────────────────────────────────────────────────────────────────

def create_vector_store() -> VectorStore:
    """
    Return a configured vector store based on VECTOR_BACKEND env var.

    Usage:
        store = create_vector_store()
        store.add_documents([Document(page_content="...", metadata={...})])
        docs = store.similarity_search("my query", k=3)
    """
    if VECTOR_BACKEND == "chromadb":
        log.info("[vector_store] Backend → ChromaDB + sentence-transformers")
        return _ChromaVectorStore()

    log.info("[vector_store] Backend → InMemoryVectorStore + FakeEmbeddings")
    return _FakeVectorStore()
