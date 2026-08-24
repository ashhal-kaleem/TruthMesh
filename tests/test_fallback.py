"""
test_fallback.py — Groq fallback unit tests for TruthMesh.

Verifies the fallback contract:
  1. _invoke_with_fallback: Gemini success → Groq never called.
  2. _invoke_with_fallback: Gemini quota error (text) → exactly 1 Groq call.
  3. _invoke_with_fallback: Gemini quota error (image) → re-raise, Groq never called.
  4. _invoke_with_fallback: Gemini quota error + no GROQ_API_KEY → re-raise.
  5. _invoke_with_fallback: Gemini non-quota error → re-raise immediately, Groq never called.
  6. plan_node Gemini fails → Groq handles it → total successful LLM calls = 2 (1 Groq + 1 Gemini).
  7. verdict_node Gemini fails → Groq handles it → total successful LLM calls = 2 (1 Gemini + 1 Groq).
  8. Full pipeline text claim: Gemini fails on plan → Groq plan + Gemini verdict = 2 total calls.
  9. Full pipeline text claim: Gemini fails on verdict → Gemini plan + Groq verdict = 2 total calls.

All tests are fully mocked — no real Gemini or Groq API calls are made.
"""

import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch, call

# ── ensure project root is on path ───────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── env vars must be set before any src.* import ─────────────────────────────
os.environ.setdefault("DATABASE_URL",   "sqlite:///./test_truthmesh.db")
os.environ.setdefault("VECTOR_BACKEND", "fake")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_for_testing_only_32ch")
os.environ.setdefault("GOOGLE_API_KEY", "fake-google-key-for-tests")
os.environ.setdefault("GROQ_API_KEY",   "fake-groq-key-for-tests")

from src.main_agent import _invoke_with_fallback, _is_quota_error, TruthMesh
from src.prompts.verdict_prediction import VerdictPrediction, VerdictResult
from src.prompts.input_ingestion import Plan, SubclaimWithQueries
from langchain_core.messages import HumanMessage, SystemMessage

# ── Shared fixtures / helpers ─────────────────────────────────────────────────

PLAN_PYDANTIC = Plan(subclaims_with_queries=[
    SubclaimWithQueries(subclaim="Test subclaim", queries=["test query"])
])

VERDICT_PYDANTIC = VerdictPrediction(
    result=VerdictResult(label="SUPPORT", explanation="Evidence supports the claim.")
)

QUOTA_ERROR   = Exception("quota exceeded — 429 resource exhausted")
NON_QUOTA_ERR = Exception("Invalid API key provided")

MESSAGES = [
    SystemMessage(content="system prompt"),
    HumanMessage(content="user message"),
]


def _make_gemini_llm(side_effect=None, return_value=None):
    """Return a mock that looks like a Gemini LLM."""
    chain = MagicMock()
    if side_effect is not None:
        chain.invoke.side_effect = side_effect
    else:
        chain.invoke.return_value = return_value
    llm = MagicMock()
    llm.with_structured_output.return_value = chain
    return llm, chain


def _make_groq_llm(return_value=None, side_effect=None):
    """Return a mock that looks like a Groq LLM."""
    chain = MagicMock()
    if side_effect is not None:
        chain.invoke.side_effect = side_effect
    else:
        chain.invoke.return_value = return_value
    llm = MagicMock()
    llm.with_structured_output.return_value = chain
    return llm, chain


# ══════════════════════════════════════════════════════════════════════════════
# 1. _is_quota_error detection
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("msg,expected", [
    ("quota exceeded",                  True),
    ("rate limit hit",                  True),
    ("rate_limit exceeded",             True),
    ("resource exhausted",              True),
    ("resourceexhausted",               True),
    ("too many requests",               True),
    ("service unavailable",             True),
    ("serviceunavailable",              True),
    ("overloaded",                      True),
    ("429",                             True),
    ("503",                             True),
    ("invalid api key",                 False),
    ("connection timeout",              False),
    ("json decode error",               False),
    ("validation error",                False),
])
def test_is_quota_error_classification(msg, expected):
    assert _is_quota_error(Exception(msg)) == expected


# ══════════════════════════════════════════════════════════════════════════════
# 2. _invoke_with_fallback: Gemini succeeds → Groq never called
# ══════════════════════════════════════════════════════════════════════════════

def test_fallback_not_triggered_on_gemini_success():
    gemini_llm, gemini_chain = _make_gemini_llm(return_value=PLAN_PYDANTIC)
    groq_llm,   groq_chain   = _make_groq_llm(return_value=PLAN_PYDANTIC)

    with patch("src.main_agent._get_groq_llm", return_value=groq_llm):
        result = _invoke_with_fallback(
            gemini_llm, Plan, MESSAGES, has_image=False
        )

    assert result == PLAN_PYDANTIC
    gemini_chain.invoke.assert_called_once()
    groq_chain.invoke.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 3. _invoke_with_fallback: Gemini quota error (text) → exactly 1 Groq call
# ══════════════════════════════════════════════════════════════════════════════

def test_fallback_triggered_on_gemini_quota_text():
    gemini_llm, gemini_chain = _make_gemini_llm(side_effect=QUOTA_ERROR)
    groq_llm,   groq_chain   = _make_groq_llm(return_value=PLAN_PYDANTIC)

    with patch("src.main_agent._get_groq_llm", return_value=groq_llm):
        result = _invoke_with_fallback(
            gemini_llm, Plan, MESSAGES, has_image=False
        )

    assert result == PLAN_PYDANTIC
    gemini_chain.invoke.assert_called_once()
    groq_chain.invoke.assert_called_once()   # exactly 1 Groq call


# ══════════════════════════════════════════════════════════════════════════════
# 4. _invoke_with_fallback: Gemini quota error on IMAGE call → re-raise, no Groq
# ══════════════════════════════════════════════════════════════════════════════

def test_fallback_suppressed_for_image_calls():
    gemini_llm, gemini_chain = _make_gemini_llm(side_effect=QUOTA_ERROR)
    groq_llm,   groq_chain   = _make_groq_llm(return_value=PLAN_PYDANTIC)

    with patch("src.main_agent._get_groq_llm", return_value=groq_llm):
        with pytest.raises(Exception, match="quota"):
            _invoke_with_fallback(
                gemini_llm, Plan, MESSAGES, has_image=True
            )

    gemini_chain.invoke.assert_called_once()
    groq_chain.invoke.assert_not_called()   # Groq must not be reached


# ══════════════════════════════════════════════════════════════════════════════
# 5. _invoke_with_fallback: Gemini quota error + GROQ_API_KEY absent → re-raise
# ══════════════════════════════════════════════════════════════════════════════

def test_fallback_suppressed_when_no_groq_key():
    gemini_llm, gemini_chain = _make_gemini_llm(side_effect=QUOTA_ERROR)

    with patch("src.main_agent._get_groq_llm", return_value=None):
        with pytest.raises(Exception, match="quota"):
            _invoke_with_fallback(
                gemini_llm, Plan, MESSAGES, has_image=False
            )

    gemini_chain.invoke.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# 6. _invoke_with_fallback: non-quota Gemini error → re-raise immediately
# ══════════════════════════════════════════════════════════════════════════════

def test_non_quota_error_propagates_immediately():
    gemini_llm, gemini_chain = _make_gemini_llm(side_effect=NON_QUOTA_ERR)
    groq_llm,   groq_chain   = _make_groq_llm(return_value=PLAN_PYDANTIC)

    with patch("src.main_agent._get_groq_llm", return_value=groq_llm):
        with pytest.raises(Exception, match="Invalid API key"):
            _invoke_with_fallback(
                gemini_llm, Plan, MESSAGES, has_image=False
            )

    gemini_chain.invoke.assert_called_once()
    groq_chain.invoke.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 7 & 8. Full pipeline: plan_node Gemini fails → Groq plan + Gemini verdict
#         Total successful LLM calls = 2
# ══════════════════════════════════════════════════════════════════════════════

PLAN_JSON    = json.dumps({"subclaims_with_queries": [
    {"subclaim": "Test subclaim", "queries": ["test query"]}
]})
VERDICT_JSON = json.dumps({"result": {"label": "SUPPORT", "explanation": "Supported."}})

FAKE_EVIDENCE = json.dumps({
    "url": "https://example.com",
    "title": "Test",
    "excerpt": "Test excerpt.",
    "credibility_score": "High",
    "bias_label": "Least Biased",
})


def _build_pipeline_agent():
    """Build a TruthMesh with mocked vector store (no DB/Gemini needed at init)."""
    with patch("src.main_agent.create_vector_store") as mock_vs:
        mock_vs.return_value = MagicMock()
        mock_vs.return_value.similarity_search.return_value = []
        mock_vs.return_value.add_documents.return_value = None
        agent = TruthMesh.__new__(TruthMesh)
        agent.dataset     = "feverous"
        agent.temperature = 0.2
        agent.llm         = MagicMock()   # replaced per test
        agent.vector_store = mock_vs.return_value
        agent._build_graph()
    return agent


def _make_structured_chain(response_json: str, schema):
    """
    Return a mock chain whose .invoke() returns the Pydantic model parsed from
    response_json — same as what with_structured_output would produce.
    """
    chain = MagicMock()
    chain.invoke.return_value = schema.model_validate_json(response_json)
    return chain


def _make_structured_chain_raising(exc):
    chain = MagicMock()
    chain.invoke.side_effect = exc
    return chain


@pytest.fixture
def agent():
    return _build_pipeline_agent()


def test_plan_gemini_fails_groq_takes_over_total_calls_2(agent):
    """
    plan_node: Gemini raises quota → Groq returns plan (1 Groq call).
    verdict_node: Gemini succeeds (1 Gemini call).
    Total successful calls = 2.
    """
    gemini_plan_chain   = _make_structured_chain_raising(QUOTA_ERROR)
    groq_plan_chain     = _make_structured_chain(PLAN_JSON, Plan)
    gemini_verdict_chain = _make_structured_chain(VERDICT_JSON, VerdictPrediction)

    # Gemini llm: plan call raises, verdict call succeeds
    def gemini_with_structured_output(schema):
        if schema is Plan:
            return gemini_plan_chain
        return gemini_verdict_chain

    agent.llm.with_structured_output.side_effect = gemini_with_structured_output

    # Groq llm: plan succeeds
    groq_llm = MagicMock()
    groq_llm.with_structured_output.return_value = groq_plan_chain

    with (
        patch("src.main_agent._get_groq_llm", return_value=groq_llm),
        patch("src.main_agent.search_retrieve_news") as mock_search,
    ):
        mock_search.invoke.return_value = FAKE_EVIDENCE
        result = agent.process_claim("The Eiffel Tower is in Paris.")

    assert result["label"] == "SUPPORT"

    # Gemini attempted plan once (failed), succeeded on verdict once
    assert gemini_plan_chain.invoke.call_count   == 1   # Gemini plan attempt
    assert gemini_verdict_chain.invoke.call_count == 1   # Gemini verdict success
    # Groq filled in for plan exactly once
    assert groq_plan_chain.invoke.call_count     == 1


def test_verdict_gemini_fails_groq_takes_over_total_calls_2(agent):
    """
    plan_node:    Gemini succeeds (1 Gemini call).
    verdict_node: Gemini raises quota → Groq returns verdict (1 Groq call).
    Total successful calls = 2.
    """
    gemini_plan_chain    = _make_structured_chain(PLAN_JSON, Plan)
    gemini_verdict_chain = _make_structured_chain_raising(QUOTA_ERROR)
    groq_verdict_chain   = _make_structured_chain(VERDICT_JSON, VerdictPrediction)

    def gemini_with_structured_output(schema):
        if schema is Plan:
            return gemini_plan_chain
        return gemini_verdict_chain

    agent.llm.with_structured_output.side_effect = gemini_with_structured_output

    groq_llm = MagicMock()
    groq_llm.with_structured_output.return_value = groq_verdict_chain

    with (
        patch("src.main_agent._get_groq_llm", return_value=groq_llm),
        patch("src.main_agent.search_retrieve_news") as mock_search,
    ):
        mock_search.invoke.return_value = FAKE_EVIDENCE
        result = agent.process_claim("The Eiffel Tower is in Paris.")

    assert result["label"] == "SUPPORT"

    # Gemini plan succeeded, verdict failed
    assert gemini_plan_chain.invoke.call_count    == 1
    assert gemini_verdict_chain.invoke.call_count == 1   # Gemini verdict attempt
    # Groq filled in for verdict exactly once
    assert groq_verdict_chain.invoke.call_count   == 1


# ══════════════════════════════════════════════════════════════════════════════
# 9. Image plan: Gemini quota error → re-raise (Groq never touched)
# ══════════════════════════════════════════════════════════════════════════════

def test_image_plan_gemini_quota_raises_no_groq(agent):
    """
    plan_node with image: Gemini raises quota → pipeline raises, Groq untouched.
    """
    gemini_plan_chain = _make_structured_chain_raising(QUOTA_ERROR)
    agent.llm.with_structured_output.return_value = gemini_plan_chain

    groq_llm = MagicMock()

    with (
        patch("src.main_agent._get_groq_llm", return_value=groq_llm),
        patch("src.main_agent.search_retrieve_news"),
        # Provide a tiny valid PNG as a data URI so has_image=True
        patch("os.path.exists", return_value=False),
    ):
        with pytest.raises(Exception, match="quota"):
            agent.process_claim(
                "Claim with image.",
                image="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            )

    groq_llm.with_structured_output.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 10. Both nodes use Gemini → Groq is never instantiated
# ══════════════════════════════════════════════════════════════════════════════

def test_happy_path_groq_never_instantiated(agent):
    """
    When both Gemini calls succeed, _get_groq_llm is never called at all.
    """
    gemini_plan_chain    = _make_structured_chain(PLAN_JSON, Plan)
    gemini_verdict_chain = _make_structured_chain(VERDICT_JSON, VerdictPrediction)

    def gemini_with_structured_output(schema):
        if schema is Plan:
            return gemini_plan_chain
        return gemini_verdict_chain

    agent.llm.with_structured_output.side_effect = gemini_with_structured_output

    with (
        patch("src.main_agent._get_groq_llm") as mock_get_groq,
        patch("src.main_agent.search_retrieve_news") as mock_search,
    ):
        mock_search.invoke.return_value = FAKE_EVIDENCE
        result = agent.process_claim("The Eiffel Tower is in Paris.")

    assert result["label"] == "SUPPORT"
    mock_get_groq.assert_not_called()
    assert gemini_plan_chain.invoke.call_count    == 1
    assert gemini_verdict_chain.invoke.call_count == 1
