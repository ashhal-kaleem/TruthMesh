"""
test_api.py — Full mocked test suite for the FactAgent FastAPI backend.

Covers:
  - Health check
  - POST /check_claim (text-only)
  - POST /check_claim (with image)
  - Structured response schema fields (verdict, confidence, reasoning, citations, flags)
  - Validation errors (missing required field)
  - CORS headers
  - 404 on invalid routes
  - All 3 verdict classes (SUPPORT, REFUTE, UNCERTAIN) via parameterised test

No real Gemini / Serper calls are made: ChatGoogleGenerativeAI._generate is patched.
"""

import os
import sys
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from src.api import app
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage

client = TestClient(app)

# ── Canned responses ──────────────────────────────────────────────────────────

PLAN_RESPONSE = json.dumps({
    "subclaims_with_queries": [
        {"subclaim": "Test Subclaim", "queries": ["Test Query"]}
    ]
})

EVIDENCE_RESPONSE = json.dumps({
    "subclaims_with_query_evidence": [
        {
            "subclaim": "Test Subclaim",
            "queries_with_evidence": [
                {
                    "query": "Test Query",
                    "evidence": [
                        {
                            "url": "https://example.com/test",
                            "title": "Test Title",
                            "excerpt": "Test excerpt about the claim.",
                            "credibility_score": "High",
                            "bias_label": "Least Biased",
                        }
                    ],
                }
            ],
        }
    ]
})

VERDICT_RESPONSES = {
    "SUPPORT": json.dumps({"result": {"label": "SUPPORT", "explanation": "Test SUPPORT explanation."}}),
    "REFUTE": json.dumps({"result": {"label": "REFUTE", "explanation": "Test REFUTE explanation."}}),
    "UNCERTAIN": json.dumps({"result": {"label": "UNCERTAIN", "explanation": "Test UNCERTAIN explanation."}}),
}

_call_index = 0
_current_verdict = "SUPPORT"


def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
    global _call_index
    responses = [PLAN_RESPONSE, EVIDENCE_RESPONSE, VERDICT_RESPONSES[_current_verdict]]
    response_text = responses[min(_call_index, len(responses) - 1)]
    _call_index += 1

    from langchain_core.outputs import ChatGeneration, ChatResult
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response_text))])


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_state():
    global _call_index, _current_verdict
    _call_index = 0
    _current_verdict = "SUPPORT"


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── Text claim — full schema validation ───────────────────────────────────────

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_text_only_schema():
    response = client.post(
        "/check_claim",
        data={"claim": "This is a test claim."},
    )
    assert response.status_code == 200
    data = response.json()

    # Top-level fields
    assert data["claim"] == "This is a test claim."
    assert data["verdict"] == "SUPPORT"
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["reasoning"], str) and data["reasoning"]
    assert isinstance(data["evidence_citations"], list)
    assert isinstance(data["image_analyzed"], bool)
    assert data["image_analyzed"] is False
    assert isinstance(data["past_context_used"], bool)

    # Citation schema
    if data["evidence_citations"]:
        cite = data["evidence_citations"][0]
        assert "url" in cite
        assert "title" in cite
        assert "excerpt" in cite
        assert "credibility_score" in cite
        assert "bias_label" in cite


# ── Image claim ───────────────────────────────────────────────────────────────

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_with_image():
    img_path = os.path.join(os.path.dirname(__file__), "fact-check.png")
    with open(img_path, "rb") as f:
        response = client.post(
            "/check_claim",
            data={"claim": "Claim with image."},
            files={"image": ("fact-check.png", f, "image/png")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["claim"] == "Claim with image."
    assert data["image_analyzed"] is True
    assert data["verdict"] in ("SUPPORT", "REFUTE", "UNCERTAIN")
    assert isinstance(data["confidence"], float)
    assert isinstance(data["reasoning"], str)
    assert isinstance(data["evidence_citations"], list)


# ── Confidence is in [0, 1] ───────────────────────────────────────────────────

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_confidence_bounds():
    response = client.post("/check_claim", data={"claim": "Confidence test."})
    assert response.status_code == 200
    conf = response.json()["confidence"]
    assert 0.0 <= conf <= 1.0


# ── Deduplication: no duplicate URLs in citations ─────────────────────────────

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_citation_deduplication():
    response = client.post("/check_claim", data={"claim": "Dedup test."})
    assert response.status_code == 200
    citations = response.json()["evidence_citations"]
    urls = [c["url"] for c in citations]
    assert len(urls) == len(set(urls)), "Duplicate URLs found in evidence_citations"


# ── All 3 verdict classes ─────────────────────────────────────────────────────

@pytest.mark.parametrize("target", ["SUPPORT", "REFUTE", "UNCERTAIN"])
@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_all_verdict_classes(target):
    global _call_index, _current_verdict
    _call_index = 0
    _current_verdict = target

    response = client.post("/check_claim", data={"claim": f"Test claim for {target}."})
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == target
    assert data["reasoning"]

    # UNCERTAIN must have confidence ≤ 0.55
    if target == "UNCERTAIN":
        assert data["confidence"] <= 0.55


# ── Validation error (missing required field) ─────────────────────────────────

def test_missing_claim_returns_422():
    response = client.post("/check_claim", data={})
    assert response.status_code == 422
    assert "detail" in response.json()


# ── CORS headers ──────────────────────────────────────────────────────────────

def test_cors_preflight():
    response = client.options(
        "/check_claim",
        headers={
            "Origin": "https://my-vercel-app.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://my-vercel-app.vercel.app"


# ── 404 on unknown route ──────────────────────────────────────────────────────

def test_unknown_route_returns_404():
    response = client.get("/not_a_real_endpoint")
    assert response.status_code == 404
