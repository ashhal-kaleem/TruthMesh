"""
test_mock_pipeline.py — verify 2-call architecture without hitting Gemini quota.

evidence_node is now a deterministic Python loop (zero Gemini calls), so only
plan_node and verdict_node invoke the LLM — exactly 2 calls total.

Patches ChatGoogleGenerativeAI._generate to return canned responses and also
patches search_retrieve_news.invoke so evidence retrieval never hits Serper.
The test:
  1. Counts every _generate call — asserts exactly 2.
  2. Verifies each node received and returned well-formed data.
  3. Confirms no supervisor / routing calls occur.

Run:  python P:\\FactAgent\\tests\\test_mock_pipeline.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# ── Canned model responses ────────────────────────────────────────────────────

PLAN_RESPONSE = json.dumps({
    "subclaims_with_queries": [
        {
            "subclaim": "Location(Eiffel_Tower, Paris_France) ::: Verify Eiffel Tower is in Paris",
            "queries": ["Where is the Eiffel Tower located?", "Eiffel Tower Paris location"]
        },
        {
            "subclaim": "Completed(Eiffel_Tower, 1889) ::: Verify construction completed 1889",
            "queries": ["When was the Eiffel Tower built?", "Eiffel Tower construction year"]
        }
    ]
})

# The evidence agent emits JSON in its final message
EVIDENCE_RESPONSE = json.dumps({
    "subclaims_with_query_evidence": [
        {
            "subclaim": "Location(Eiffel_Tower, Paris_France) ::: Verify Eiffel Tower is in Paris",
            "queries_with_evidence": [
                {
                    "query": "Where is the Eiffel Tower located?",
                    "evidence": [
                        {
                            "url": "https://example.com/eiffel-tower",
                            "title": "Eiffel Tower History",
                            "excerpt": "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France.",
                            "credibility_score": "High",
                            "bias_label": "Least Biased"
                        }
                    ]
                }
            ]
        },
        {
            "subclaim": "Completed(Eiffel_Tower, 1889) ::: Verify construction completed 1889",
            "queries_with_evidence": [
                {
                    "query": "When was the Eiffel Tower built?",
                    "evidence": [
                        {
                            "url": "https://example.com/eiffel-tower-history",
                            "title": "Eiffel Tower Construction",
                            "excerpt": "The Eiffel Tower was constructed from 1887 to 1889 as the centerpiece of the 1889 World's Fair.",
                            "credibility_score": "High",
                            "bias_label": "Least Biased"
                        }
                    ]
                }
            ]
        }
    ]
})

VERDICT_RESPONSES = {
    "SUPPORT": json.dumps({"result": {"label": "SUPPORT", "explanation": "Multiple sources confirm the Eiffel Tower stands in Paris, France."}}),
    "REFUTE": json.dumps({"result": {"label": "REFUTE", "explanation": "Sources contradict the claim."}}),
    "UNCERTAIN": json.dumps({"result": {"label": "UNCERTAIN", "explanation": "Evidence is mixed."}})
}

# ── Response sequencer ────────────────────────────────────────────────────────

_responses = []
_call_index = 0
_call_count = 0
_call_log   = []
_current_target = "SUPPORT"

def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
    global _call_index, _call_count
    _call_count += 1

    # evidence_node makes ZERO Gemini calls — only plan and verdict reach here
    responses = [PLAN_RESPONSE, VERDICT_RESPONSES[_current_target]]
    response_text = responses[min(_call_index, len(responses) - 1)]
    _call_index += 1

    node_hints = {0: "plan_node", 1: "verdict_node"}
    label = node_hints.get(_call_count - 1, f"call #{_call_count}")
    _call_log.append(label)
    print(f"  [Mock Gemini call #{_call_count} -> {label}]")

    from langchain_core.outputs import ChatGeneration, ChatResult
    msg = AIMessage(content=response_text)
    return ChatResult(generations=[ChatGeneration(message=msg)])

# ── Fake Serper/retrieval response (evidence_node calls this) ─────────────────

FAKE_EVIDENCE_ITEM = json.dumps({
    "url": "https://example.com/eiffel-tower",
    "title": "Eiffel Tower History",
    "excerpt": "The Eiffel Tower stands in Paris, France.",
    "credibility_score": "High",
    "bias_label": "Least Biased",
})

def fake_search_invoke(args):
    """Return a canned JSON evidence item so no Serper API calls are made."""
    return FAKE_EVIDENCE_ITEM

# ── Run test ──────────────────────────────────────────────────────────────────
print("Patching ChatGoogleGenerativeAI._generate and search_retrieve_news with mocks...")
with (
    patch.object(ChatGoogleGenerativeAI, "_generate", fake_generate),
    patch("src.main_agent.search_retrieve_news") as mock_tool,
):
    mock_tool.invoke = fake_search_invoke
    from src.main_agent import TruthMesh
    agent = TruthMesh(dataset="feverous")

    claim = "The Eiffel Tower is located in Paris, France, and was completed in 1889."
    print(f"\nClaim: {claim}\n")
    
    for target_label in ["SUPPORT", "REFUTE", "UNCERTAIN"]:
        _current_target = target_label
        _call_index = 0
        _call_count = 0
        _call_log = []
        
        print(f"Running mocked 2-call pipeline for target label: {target_label} (Text only)...\n")
        result = agent.process_claim(claim, verbose=False)

        print("\n=== Result ===")
        print(f"Expected   : {target_label}")
        print(f"Label      : {result['label']}")
        print(f"Explanation: {result['explanation'][:200]}")

        print(f"\n=== Call count: {_call_count} ===")
        for i, name in enumerate(_call_log, 1):
            print(f"  Call {i}: {name}")

        # ── Assertions ────────────────────────────────────────────────────────────────
        errors = []
        if _call_count != 2:
            errors.append(f"Expected 2 Gemini calls (plan + verdict), got {_call_count}")
        if result.get("label") != target_label:
            errors.append(f"Expected label='{target_label}', got '{result.get('label')}'")
        if not result.get("explanation"):
            errors.append("Missing explanation in result")

        if errors:
            print(f"\n[FAIL] for label {target_label} (Text only)")
            for e in errors:
                print(f"  ✗ {e}")
            sys.exit(1)
        else:
            print(f"\n[PASS] Exactly 2 Gemini calls, correct label, explanation present for {target_label} (Text only).")
            print("-" * 40)

        # ── Test with Image ───────────────────────────────────────────────────────────
        _call_index = 0
        _call_count = 0
        _call_log = []
        image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fact-check.png")
        
        print(f"Running mocked 2-call pipeline for target label: {target_label} (With Image)...\n")
        result_with_img = agent.process_claim(claim, image=image_path, verbose=False)

        errors_img = []
        if _call_count != 2:
            errors_img.append(f"Expected 2 Gemini calls (plan + verdict), got {_call_count}")
        if result_with_img.get("label") != target_label:
            errors_img.append(f"Expected label='{target_label}', got '{result_with_img.get('label')}'")
        if not result_with_img.get("explanation"):
            errors_img.append("Missing explanation in result")

        if errors_img:
            print(f"\n[FAIL] for label {target_label} (With Image)")
            for e in errors_img:
                print(f"  ✗ {e}")
            sys.exit(1)
        else:
            print(f"\n[PASS] Exactly 2 Gemini calls, correct label, explanation present for {target_label} (With Image).")
            print("-" * 40)

print("\n=== All Mock pipeline tests PASSED ===")

