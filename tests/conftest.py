"""
conftest.py — pytest configuration for TruthMesh test suite.

This file is loaded by pytest BEFORE test collection begins, ensuring that
all environment variables are set prior to any src.* module import.
This is required because database.py, vector_store.py and auth.py read
their configuration from os.environ at module-import time.
"""
import os

# ── Test-safe overrides ───────────────────────────────────────────────────────
# SQLite file DB (avoids requiring a live PostgreSQL server in CI/dev)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_truthmesh.db")

# Use FakeEmbeddings + InMemoryVectorStore (no chromadb / sentence-transformers needed)
os.environ.setdefault("VECTOR_BACKEND", "fake")

# Deterministic JWT secret for tests
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_for_testing_only_32ch")

# Ensure tests never accidentally hit real APIs
os.environ.setdefault("ENVIRONMENT", "test")
