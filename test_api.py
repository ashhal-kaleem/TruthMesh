"""
test_api.py — Full mocked test suite for the FactAgent FastAPI backend.

Environment vars are set in conftest.py BEFORE any src.* import:
  DATABASE_URL=sqlite:///./test_factagent.db
  VECTOR_BACKEND=fake
  JWT_SECRET_KEY=test_jwt_secret_key_for_testing_only_32ch

Covers:
  ── Core ──────────────────────────────────────────────────────────────
  - GET  /              health check + version
  - POST /check_claim   text-only, with image, anonymous, authenticated
  ── Schema validation ─────────────────────────────────────────────────
  - All FactCheckResponse fields present and correctly typed
  - confidence bounded [0, 1]; UNCERTAIN capped ≤ 0.55
  - No duplicate URLs in evidence_citations
  - All 3 verdict classes (SUPPORT, REFUTE, UNCERTAIN) — parametrised
  ── Auth ──────────────────────────────────────────────────────────────
  - POST /auth/register (success, duplicate username, duplicate email)
  - POST /auth/login    (success, wrong password)
  - GET  /me/history    (requires auth, paginated, returns DB records)
  ── Infrastructure ────────────────────────────────────────────────────
  - 422 on missing required form field
  - CORS preflight headers present
  - 404 on unknown route

No real Gemini / Serper calls are made (ChatGoogleGenerativeAI._generate patched).
"""

import json
import os
import sys
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

# ── conftest.py has already set env vars before this import ──────────────────
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from src.api import app
from src.database import drop_db, init_db
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage

# ── DB lifecycle ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create tables once per session; drop them afterwards."""
    drop_db()   # start completely clean
    init_db()
    yield
    drop_db()
    # Remove SQLite file (best-effort; ignore if locked)
    db_path = os.path.join(os.path.dirname(__file__), "test_factagent.db")
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass  # Windows may keep the file locked; pytest will clean it on next run


@pytest.fixture(scope="session")
def client(setup_test_db) -> Generator:
    """Session-scoped TestClient that triggers FastAPI lifespan events."""
    with TestClient(app) as c:
        yield c


# ── Canned LLM responses ──────────────────────────────────────────────────────

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
    "SUPPORT":   json.dumps({"result": {"label": "SUPPORT",   "explanation": "Test SUPPORT explanation."}}),
    "REFUTE":    json.dumps({"result": {"label": "REFUTE",    "explanation": "Test REFUTE explanation."}}),
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


@pytest.fixture(autouse=True)
def reset_llm_state():
    global _call_index, _current_verdict
    _call_index = 0
    _current_verdict = "SUPPORT"


# ── Helper to get a fresh auth token ─────────────────────────────────────────

def _register_and_login(client: TestClient, suffix: str = "") -> str:
    """Register a unique user and return a JWT token."""
    uid = uuid.uuid4().hex[:8] + suffix
    reg = client.post(
        "/auth/register",
        json={"username": f"u_{uid}", "email": f"{uid}@test.com", "password": "TestPass123!"},
    )
    assert reg.status_code == 201, reg.text
    return reg.json()["access_token"]


# ══════════════════════════════════════════════════════════════════════════════
# Health check
# ══════════════════════════════════════════════════════════════════════════════

def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ══════════════════════════════════════════════════════════════════════════════
# POST /check_claim — anonymous text-only
# ══════════════════════════════════════════════════════════════════════════════

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_text_only_schema(client):
    resp = client.post("/check_claim", data={"claim": "This is a test claim."})
    assert resp.status_code == 200
    data = resp.json()

    assert data["claim"] == "This is a test claim."
    assert data["verdict"] == "SUPPORT"
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["reasoning"], str) and data["reasoning"]
    assert isinstance(data["evidence_citations"], list)
    assert data["image_analyzed"] is False
    assert isinstance(data["past_context_used"], bool)

    if data["evidence_citations"]:
        cite = data["evidence_citations"][0]
        for key in ("url", "title", "excerpt", "credibility_score", "bias_label"):
            assert key in cite


# ══════════════════════════════════════════════════════════════════════════════
# POST /check_claim — with image
# ══════════════════════════════════════════════════════════════════════════════

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_with_image(client):
    img_path = os.path.join(os.path.dirname(__file__), "fact-check.png")
    with open(img_path, "rb") as f:
        resp = client.post(
            "/check_claim",
            data={"claim": "Claim with image."},
            files={"image": ("fact-check.png", f, "image/png")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_analyzed"] is True
    assert data["verdict"] in ("SUPPORT", "REFUTE", "UNCERTAIN")
    assert isinstance(data["confidence"], float)


# ══════════════════════════════════════════════════════════════════════════════
# Authenticated check_claim — result linked to user
# ══════════════════════════════════════════════════════════════════════════════

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_authenticated_appears_in_history(client):
    token = _register_and_login(client, "_hist")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/check_claim",
        data={"claim": "Authenticated claim for history test."},
        headers=headers,
    )
    assert resp.status_code == 200

    hist = client.get("/me/history", headers=headers)
    assert hist.status_code == 200
    items = hist.json()
    assert len(items) >= 1
    assert items[0]["claim_text"] == "Authenticated claim for history test."


# ══════════════════════════════════════════════════════════════════════════════
# Confidence
# ══════════════════════════════════════════════════════════════════════════════

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_confidence_bounds(client):
    resp = client.post("/check_claim", data={"claim": "Confidence bounds test."})
    assert resp.status_code == 200
    conf = resp.json()["confidence"]
    assert 0.0 <= conf <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Citation deduplication
# ══════════════════════════════════════════════════════════════════════════════

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_citation_deduplication(client):
    resp = client.post("/check_claim", data={"claim": "Dedup test claim."})
    assert resp.status_code == 200
    citations = resp.json()["evidence_citations"]
    urls = [c["url"] for c in citations]
    assert len(urls) == len(set(urls)), "Duplicate URLs found in evidence_citations"


# ══════════════════════════════════════════════════════════════════════════════
# All 3 verdict classes
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("target", ["SUPPORT", "REFUTE", "UNCERTAIN"])
@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_all_verdict_classes(target, client):
    global _call_index, _current_verdict
    _call_index = 0
    _current_verdict = target

    resp = client.post("/check_claim", data={"claim": f"Verdict test for {target}."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == target
    assert data["reasoning"]
    if target == "UNCERTAIN":
        assert data["confidence"] <= 0.55


# ══════════════════════════════════════════════════════════════════════════════
# Auth: Register
# ══════════════════════════════════════════════════════════════════════════════

def test_register_success(client):
    uid = uuid.uuid4().hex[:8]
    resp = client.post(
        "/auth/register",
        json={"username": f"new_{uid}", "email": f"{uid}@ex.com", "password": "StrongPass1!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_username(client):
    uid = uuid.uuid4().hex[:8]
    payload = {"username": f"dup_{uid}", "email": f"first_{uid}@ex.com", "password": "Pass1234!"}
    client.post("/auth/register", json=payload)

    # Second registration with same username, different email
    payload2 = {"username": f"dup_{uid}", "email": f"second_{uid}@ex.com", "password": "Pass1234!"}
    resp = client.post("/auth/register", json=payload2)
    assert resp.status_code == 409


def test_register_duplicate_email(client):
    uid = uuid.uuid4().hex[:8]
    email = f"shared_{uid}@ex.com"
    client.post("/auth/register", json={"username": f"u1_{uid}", "email": email, "password": "Pass1234!"})

    resp = client.post("/auth/register", json={"username": f"u2_{uid}", "email": email, "password": "Pass1234!"})
    assert resp.status_code == 409


def test_register_password_too_short(client):
    resp = client.post(
        "/auth/register",
        json={"username": "shortpw", "email": "shortpw@ex.com", "password": "abc"},
    )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# Auth: Login
# ══════════════════════════════════════════════════════════════════════════════

def test_login_success(client):
    uid = uuid.uuid4().hex[:8]
    client.post(
        "/auth/register",
        json={"username": f"login_{uid}", "email": f"login_{uid}@ex.com", "password": "LoginPass1!"},
    )
    resp = client.post("/auth/login", json={"username": f"login_{uid}", "password": "LoginPass1!"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    uid = uuid.uuid4().hex[:8]
    client.post(
        "/auth/register",
        json={"username": f"wp_{uid}", "email": f"wp_{uid}@ex.com", "password": "CorrectPass1!"},
    )
    resp = client.post("/auth/login", json={"username": f"wp_{uid}", "password": "WrongPassword!"})
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    resp = client.post("/auth/login", json={"username": "doesnotexist", "password": "Anything1!"})
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Auth: /me/history
# ══════════════════════════════════════════════════════════════════════════════

def test_history_requires_auth(client):
    resp = client.get("/me/history")
    assert resp.status_code == 401


def test_history_invalid_token(client):
    resp = client.get("/me/history", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_history_pagination(client):
    token = _register_and_login(client, "_pg")
    headers = {"Authorization": f"Bearer {token}"}

    # Submit 3 claims, resetting call_index each time
    for i in range(3):
        global _call_index
        _call_index = 0
        client.post("/check_claim", data={"claim": f"Pagination claim {i}."}, headers=headers)

    hist_page1 = client.get("/me/history?page=1&page_size=2", headers=headers)
    assert hist_page1.status_code == 200
    page1 = hist_page1.json()
    assert len(page1) == 2

    hist_page2 = client.get("/me/history?page=2&page_size=2", headers=headers)
    assert hist_page2.status_code == 200
    page2 = hist_page2.json()
    assert len(page2) >= 1   # at least 1 remaining


# ══════════════════════════════════════════════════════════════════════════════
# Validation errors
# ══════════════════════════════════════════════════════════════════════════════

def test_missing_claim_returns_422(client):
    resp = client.post("/check_claim", data={})
    assert resp.status_code == 422
    assert "detail" in resp.json()


# ══════════════════════════════════════════════════════════════════════════════
# CORS
# ══════════════════════════════════════════════════════════════════════════════

def test_cors_preflight(client):
    resp = client.options(
        "/check_claim",
        headers={
            "Origin": "https://my-vercel-app.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://my-vercel-app.vercel.app"


# ══════════════════════════════════════════════════════════════════════════════
# 404
# ══════════════════════════════════════════════════════════════════════════════

def test_unknown_route_returns_404(client):
    resp = client.get("/not_a_real_endpoint")
    assert resp.status_code == 404
