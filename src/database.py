"""
database.py — SQLAlchemy ORM setup for TruthMesh.

Tables:
  users              — auth accounts
  claim_records      — per-claim results with verdict and metadata
  evidence_citations — flattened per-claim source citations

DATABASE_URL env var selects the engine:
  PostgreSQL (prod): postgresql://user:pass@host:5432/truthmesh
  SQLite    (dev):   sqlite:///./truthmesh.db   (default fallback)
  SQLite   (test):   sqlite:///./test_truthmesh.db  (set via conftest.py)

Railway/Render may emit postgres:// URLs — these are normalised to postgresql://.
"""

import os
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session

# ── Engine configuration ──────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./truthmesh.db")

# Normalise legacy Heroku / Railway postgres:// scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Supabase direct connections (port 5432) resolve to IPv6 on Render,
# causing "Network is unreachable".  The transaction pooler (port 6543)
# is IPv4-only and is the correct endpoint for PaaS deployments.
if "supabase.co" in DATABASE_URL and ":5432" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(":5432", ":6543")

# ── TEMPORARY DIAGNOSTIC (remove after Render verification) ──────────────────
try:
    from urllib.parse import urlparse as _urlparse
    _p = _urlparse(DATABASE_URL)
    print(
        f"[DB DIAG] scheme={_p.scheme!r} host={_p.hostname!r} "
        f"port={_p.port!r} user={_p.username!r} db={_p.path.lstrip('/')!r}",
        flush=True,
    )
except Exception as _e:
    print(f"[DB DIAG] parse error: {_e}", flush=True)
# ── END TEMPORARY DIAGNOSTIC ──────────────────────────────────────────────────

_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Base ──────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    claims = relationship("ClaimRecord", back_populates="user", cascade="all, delete-orphan")


class ClaimRecord(Base):
    __tablename__ = "claim_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # None = anonymous
    claim_text = Column(Text, nullable=False)
    verdict = Column(String(16), nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=False)
    image_analyzed = Column(Boolean, default=False)
    past_context_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="claims")
    citations = relationship(
        "EvidenceCitationRecord", back_populates="claim", cascade="all, delete-orphan"
    )


class EvidenceCitationRecord(Base):
    __tablename__ = "evidence_citations"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claim_records.id"), nullable=False)
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    excerpt = Column(Text, nullable=False)
    credibility_score = Column(String(32), nullable=False)
    bias_label = Column(String(64), nullable=False)

    claim = relationship("ClaimRecord", back_populates="citations")


# ── Session dependency (for FastAPI Depends) ──────────────────────────────────

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Startup ───────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they do not already exist. Called at app startup."""
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all tables. Used in tests to start with a clean slate."""
    Base.metadata.drop_all(bind=engine)
