import os
import sys
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

# Adjust sys.path to find src
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Import after dotenv so FactAgent gets GOOGLE_API_KEY
from src.api import app
from src.main_agent import FactAgent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage

client = TestClient(app)

# ── Canned model responses for Mock ────────────────────────────────────────────
PLAN_RESPONSE = json.dumps({
    "subclaims_with_queries": [
        {
            "subclaim": "Test Subclaim",
            "queries": ["Test Query"]
        }
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
                            "excerpt": "Test excerpt",
                            "credibility_score": "High",
                            "bias_label": "Least Biased"
                        }
                    ]
                }
            ]
        }
    ]
})

VERDICT_RESPONSE = json.dumps({
    "result": {
        "label": "SUPPORT", 
        "explanation": "Test explanation."
    }
})

_call_index = 0

def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
    global _call_index
    responses = [PLAN_RESPONSE, EVIDENCE_RESPONSE, VERDICT_RESPONSE]
    response_text = responses[min(_call_index, len(responses) - 1)]
    _call_index += 1

    from langchain_core.outputs import ChatGeneration, ChatResult
    msg = AIMessage(content=response_text)
    return ChatResult(generations=[ChatGeneration(message=msg)])

# ── Tests ───────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_call_index():
    global _call_index
    _call_index = 0

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_text_only():
    response = client.post(
        "/check_claim",
        data={"claim": "This is a test claim."}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "SUPPORT"
    assert data["claim"] == "This is a test claim."
    assert "explanation" in data
    assert "plan" in data
    assert "evidence" in data

@patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate)
def test_check_claim_with_image():
    # Provide a real dummy file path for the upload test
    img_path = os.path.join(os.path.dirname(__file__), "fact-check.png")
    
    with open(img_path, "rb") as f:
        response = client.post(
            "/check_claim",
            data={"claim": "Claim with image."},
            files={"image": ("fact-check.png", f, "image/png")}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "SUPPORT"
    assert data["claim"] == "Claim with image."
    assert "explanation" in data
    assert "plan" in data
    assert "evidence" in data

def test_missing_claim_validation_error():
    # Should fail if 'claim' form data is missing
    response = client.post("/check_claim", data={})
    assert response.status_code == 422
    assert "detail" in response.json()

def test_cors_headers():
    # Test that CORS headers are set (since we allow all origins in api.py)
    response = client.options(
        "/check_claim",
        headers={
            "Origin": "https://vercel.app",
            "Access-Control-Request-Method": "POST",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://vercel.app"

def test_invalid_route():
    response = client.get("/invalid_route_that_does_not_exist")
    assert response.status_code == 404
