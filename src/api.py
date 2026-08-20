"""
api.py — FactAgent FastAPI Backend
────────────────────────────────────────────────
Exposes the 3-call FactAgent pipeline over HTTP.
Returns a consistent, frontend-ready JSON schema.

Endpoints:
  GET  /                — health check
  POST /check_claim     — text claim + optional image upload → FactCheckResponse
"""

import base64
from typing import Optional, List

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.main_agent import FactAgent

app = FastAPI(
    title="FactAgent API",
    description="Fact-checking pipeline — 3-call architecture, multimodal, RAG-backed.",
    version="2.0.0",
)

# ── CORS — allow any Vercel/frontend origin ───────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Tighten to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Response schema ───────────────────────────────────────────────────────────

class EvidenceCitation(BaseModel):
    """A single piece of retrieved evidence with source metadata."""
    url: str = Field(description="Source URL")
    title: str = Field(description="Article or page title")
    excerpt: str = Field(description="Relevant snippet from the source")
    credibility_score: str = Field(description="Credibility rating (High / Medium / Low / Unknown)")
    bias_label: str = Field(description="Media-bias classification of the source")


class FactCheckResponse(BaseModel):
    """Canonical frontend-ready response for a fact-check request."""
    claim: str = Field(description="The original claim that was fact-checked")
    verdict: str = Field(description="SUPPORT | REFUTE | UNCERTAIN")
    confidence: float = Field(
        description="Confidence score 0.0–1.0, derived from evidence credibility"
    )
    reasoning: str = Field(
        description="Natural-language explanation justifying the verdict"
    )
    evidence_citations: List[EvidenceCitation] = Field(
        default_factory=list,
        description="All evidence items collected during retrieval"
    )
    image_analyzed: bool = Field(
        description="Whether an image was provided and forwarded to the vision model"
    )
    past_context_used: bool = Field(
        description="Whether the RAG layer surfaced prior matching claims"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_CREDIBILITY_SCORE_MAP = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.2,
    "unknown": 0.4,
}

def _compute_confidence(verdict: str, evidence: dict) -> float:
    """
    Derive a deterministic confidence score without an extra LLM call.
    Logic:
      1. Collect credibility scores from all evidence items (default 0.4).
      2. Average them to get base_confidence.
      3. UNCERTAIN verdict → cap at 0.55; REFUTE → invert slightly (1 - avg * 0.9).
    """
    scores: List[float] = []
    for subclaim in evidence.get("subclaims_with_query_evidence", []):
        for qe in subclaim.get("queries_with_evidence", []):
            for item in qe.get("evidence", []):
                raw = item.get("credibility_score", "Unknown").lower()
                scores.append(_CREDIBILITY_SCORE_MAP.get(raw, 0.4))

    base = sum(scores) / len(scores) if scores else 0.5

    if verdict == "UNCERTAIN":
        return round(min(base, 0.55), 3)
    if verdict == "REFUTE":
        # High-credibility REFUTE is still high-confidence
        return round(base, 3)
    # SUPPORT
    return round(base, 3)


def _extract_citations(evidence: dict) -> List[EvidenceCitation]:
    """Flatten nested evidence structure into a deduplicated citation list."""
    seen_urls: set = set()
    citations: List[EvidenceCitation] = []
    for subclaim in evidence.get("subclaims_with_query_evidence", []):
        for qe in subclaim.get("queries_with_evidence", []):
            for item in qe.get("evidence", []):
                url = item.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                citations.append(
                    EvidenceCitation(
                        url=url,
                        title=item.get("title", ""),
                        excerpt=item.get("excerpt", ""),
                        credibility_score=item.get("credibility_score", "Unknown"),
                        bias_label=item.get("bias_label", "Unknown"),
                    )
                )
    return citations


# ── Global agent ─────────────────────────────────────────────────────────────
# Initialised once at startup; all requests share this instance.
agent = FactAgent(dataset="feverous")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    return {"status": "ok", "message": "FactAgent API is running.", "version": "2.0.0"}


@app.post("/check_claim", response_model=FactCheckResponse)
async def check_claim(
    claim: str = Form(...),
    image: Optional[UploadFile] = File(None),
):
    """
    Fact-check a text claim, optionally accompanied by an image.

    - **claim**: The statement to verify.
    - **image**: Optional image upload (PNG / JPEG / WEBP).

    Returns a `FactCheckResponse` with verdict, confidence, reasoning,
    deduplicated evidence citations, and provenance flags.
    """
    # ── Handle optional image ──────────────────────────────────────────────────
    image_base64: Optional[str] = None
    if image:
        content = await image.read()
        encoded = base64.b64encode(content).decode("utf-8")
        filename = image.filename.lower()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpeg"
        mime_type = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "webp") else "image/jpeg"
        image_base64 = f"data:{mime_type};base64,{encoded}"

    # ── Run the 3-call pipeline ────────────────────────────────────────────────
    raw: dict = agent.process_claim(claim=claim, image=image_base64, verbose=False)

    verdict = raw.get("label", "UNCERTAIN")
    reasoning = raw.get("explanation", "")
    evidence_dict: dict = raw.get("evidence") or {}
    past_claims = raw.get("past_claims", [])

    # ── Build structured response ──────────────────────────────────────────────
    citations = _extract_citations(evidence_dict)
    confidence = _compute_confidence(verdict, evidence_dict)

    return FactCheckResponse(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        evidence_citations=citations,
        image_analyzed=image_base64 is not None,
        past_context_used=bool(past_claims),
    )
