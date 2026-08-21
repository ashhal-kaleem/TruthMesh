"""
api.py — TruthMesh FastAPI Backend (v3 — production-ready)
──────────────────────────────────────────────────────────

Architecture:
  POST /auth/register   — create account, return JWT
  POST /auth/login      — verify credentials, return JWT
  GET  /me/history      — authenticated user's past claims (paginated)
  GET  /                — health check
  POST /check_claim     — text + optional image → FactCheckResponse (auth optional)

Every successfully fact-checked claim is persisted to PostgreSQL.
Anonymous requests are stored without a user_id.
The RAG vector store is initialised once at startup via `create_vector_store()`.
"""

import base64
import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Query, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from src.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_current_user,
    verify_password,
)
from src.database import (
    ClaimRecord,
    EvidenceCitationRecord,
    User,
    drop_db,
    get_db,
    init_db,
)
from src.main_agent import TruthMesh

# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — create DB tables and warm up agent
    init_db()
    yield
    # Shutdown — nothing required

app = FastAPI(
    title="TruthMesh API",
    description="Fact-checking pipeline — 3-call architecture, multimodal, RAG, auth.",
    version="3.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global agent (initialised once at startup) ────────────────────────────────
agent = TruthMesh(dataset="feverous")


# ── Request / Response schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EvidenceCitation(BaseModel):
    url: str
    title: str
    excerpt: str
    credibility_score: str
    bias_label: str


class FactCheckResponse(BaseModel):
    claim: str
    verdict: str = Field(description="SUPPORT | REFUTE | UNCERTAIN")
    confidence: float = Field(description="0.0 – 1.0, derived from evidence credibility")
    reasoning: str
    evidence_citations: List[EvidenceCitation] = Field(default_factory=list)
    image_analyzed: bool
    past_context_used: bool


class ClaimHistoryItem(BaseModel):
    id: int
    claim_text: str
    verdict: str
    confidence: float
    reasoning: str
    image_analyzed: bool
    past_context_used: bool
    created_at: str
    citations: List[EvidenceCitation] = Field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CREDIBILITY_SCORE_MAP = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.2,
    "unknown": 0.4,
}


def _compute_confidence(verdict: str, evidence: dict) -> float:
    scores: List[float] = []
    for subclaim in evidence.get("subclaims_with_query_evidence", []):
        for qe in subclaim.get("queries_with_evidence", []):
            for item in qe.get("evidence", []):
                raw = item.get("credibility_score", "Unknown").lower()
                scores.append(_CREDIBILITY_SCORE_MAP.get(raw, 0.4))
    base = sum(scores) / len(scores) if scores else 0.5
    if verdict == "UNCERTAIN":
        return round(min(base, 0.55), 3)
    return round(base, 3)


def _extract_citations(evidence: dict) -> List[EvidenceCitation]:
    seen: set = set()
    citations: List[EvidenceCitation] = []
    for subclaim in evidence.get("subclaims_with_query_evidence", []):
        for qe in subclaim.get("queries_with_evidence", []):
            for item in qe.get("evidence", []):
                url = item.get("url", "")
                if url in seen:
                    continue
                seen.add(url)
                citations.append(EvidenceCitation(
                    url=url,
                    title=item.get("title", ""),
                    excerpt=item.get("excerpt", ""),
                    credibility_score=item.get("credibility_score", "Unknown"),
                    bias_label=item.get("bias_label", "Unknown"),
                ))
    return citations


def _save_claim_to_db(
    db: Session,
    *,
    user_id: Optional[int],
    claim: str,
    verdict: str,
    confidence: float,
    reasoning: str,
    image_analyzed: bool,
    past_context_used: bool,
    citations: List[EvidenceCitation],
) -> ClaimRecord:
    record = ClaimRecord(
        user_id=user_id,
        claim_text=claim,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        image_analyzed=image_analyzed,
        past_context_used=past_context_used,
    )
    db.add(record)
    db.flush()   # get record.id without committing

    for cite in citations:
        db.add(EvidenceCitationRecord(
            claim_id=record.id,
            url=cite.url,
            title=cite.title,
            excerpt=cite.excerpt,
            credibility_score=cite.credibility_score,
            bias_label=cite.bias_label,
        ))

    db.commit()
    db.refresh(record)
    return record


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account and return a JWT."""
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{req.username}' is already taken",
        )
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return a JWT."""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token)


# ── History endpoint ──────────────────────────────────────────────────────────

@app.get("/me/history", response_model=List[ClaimHistoryItem])
def my_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_current_user),
):
    """Return the authenticated user's claim history, newest first (paginated)."""
    user_id = int(current_user["sub"])
    offset = (page - 1) * page_size
    records = (
        db.query(ClaimRecord)
        .filter(ClaimRecord.user_id == user_id)
        .order_by(ClaimRecord.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return [
        ClaimHistoryItem(
            id=r.id,
            claim_text=r.claim_text,
            verdict=r.verdict,
            confidence=r.confidence,
            reasoning=r.reasoning,
            image_analyzed=r.image_analyzed,
            past_context_used=r.past_context_used,
            created_at=r.created_at.isoformat(),
            citations=[
                EvidenceCitation(
                    url=c.url,
                    title=c.title,
                    excerpt=c.excerpt,
                    credibility_score=c.credibility_score,
                    bias_label=c.bias_label,
                )
                for c in r.citations
            ],
        )
        for r in records
    ]


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "TruthMesh API is running.",
        "version": "3.0.0",
    }


# ── Fact-check endpoint ───────────────────────────────────────────────────────

@app.post("/check_claim", response_model=FactCheckResponse)
def check_claim(
    claim: str = Form(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    Fact-check a text claim, optionally accompanied by an image.

    Authentication is **optional** — anonymous requests are stored without
    a user_id and are not accessible via /me/history.
    """
    # ── Handle optional image ─────────────────────────────────────────────────
    image_base64: Optional[str] = None
    if image:
        content = image.file.read()
        encoded = base64.b64encode(content).decode("utf-8")
        filename = image.filename.lower()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpeg"
        mime_type = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "webp") else "image/jpeg"
        image_base64 = f"data:{mime_type};base64,{encoded}"

    # ── Run the 3-call pipeline ───────────────────────────────────────────────
    raw: dict = agent.process_claim(claim=claim, image=image_base64, verbose=False)

    verdict: str = raw.get("label", "UNCERTAIN")
    reasoning: str = raw.get("explanation", "")
    evidence_dict: dict = raw.get("evidence") or {}
    past_claims: list = raw.get("past_claims", [])

    citations = _extract_citations(evidence_dict)
    confidence = _compute_confidence(verdict, evidence_dict)

    # ── Persist to DB ─────────────────────────────────────────────────────────
    user_id = int(current_user["sub"]) if current_user else None
    _save_claim_to_db(
        db,
        user_id=user_id,
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        image_analyzed=image_base64 is not None,
        past_context_used=bool(past_claims),
        citations=citations,
    )

    return FactCheckResponse(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        evidence_citations=citations,
        image_analyzed=image_base64 is not None,
        past_context_used=bool(past_claims),
    )
