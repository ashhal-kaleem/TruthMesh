"""
test_real_claim.py — end-to-end pipeline run with Gemini call counting.
Run from anywhere:  python P:\\FactAgent\\test_real_claim.py

The test monkey-patches ChatGoogleGenerativeAI.invoke and
ChatGoogleGenerativeAI._generate (used by structured-output calls) so every
actual HTTP request to Gemini is counted.  A hard assertion verifies
the total stays within the 3-call budget (plus 1 tolerance for the
ReAct agent's internal think-step on some models).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# ── Call counter ──────────────────────────────────────────────────────────────
import langchain_google_genai
from langchain_google_genai import ChatGoogleGenerativeAI

_call_count = 0
_orig_generate = ChatGoogleGenerativeAI._generate

def _counting_generate(self, messages, stop=None, run_manager=None, **kwargs):
    global _call_count
    _call_count += 1
    print(f"  [Gemini call #{_call_count}]")
    return _orig_generate(self, messages, stop=stop,
                          run_manager=run_manager, **kwargs)

ChatGoogleGenerativeAI._generate = _counting_generate

# ── Run the pipeline ──────────────────────────────────────────────────────────
from src.main_agent import FactAgent

agent = FactAgent(dataset="feverous")

claim = "The Eiffel Tower is located in Paris, France, and was completed in 1889."
print(f"\nClaim: {claim}\n")
print("Running 3-call pipeline (verbose=True)...\n")

result = agent.process_claim(claim, verbose=True)

print("\n=== Final Result ===")
print(f"Label      : {result['label']}")
print(f"Explanation: {result['explanation'][:300]}...")

print(f"\n=== Gemini call count: {_call_count} ===")

# The pipeline targets 3 calls; the ReAct agent may use 1 extra think-step
# on complex claims, so we allow up to 4.
MAX_ALLOWED = 4
if _call_count <= MAX_ALLOWED:
    print(f"[PASS] {_call_count} call(s) — within {MAX_ALLOWED}-call budget.")
else:
    print(f"[FAIL] {_call_count} calls exceed the {MAX_ALLOWED}-call budget!")
    sys.exit(1)
