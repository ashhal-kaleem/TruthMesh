"""
No-API-call instantiation test for FactAgent.
Run from P:\FactAgent:  python test_init.py
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

# ── 1. Load real .env so GOOGLE_API_KEY / SERPER_API_KEY are present ──────────
from dotenv import load_dotenv
load_dotenv()

# Sanity-check keys are present without printing their values
assert os.getenv("GOOGLE_API_KEY"), "GOOGLE_API_KEY missing from .env"
assert os.getenv("SERPER_API_KEY"), "SERPER_API_KEY missing from .env"
print("[OK] Both API keys found in environment.")

# ── 2. Import FactAgent (exercises all module-level code in src/) ──────────────
print("Importing FactAgent...")
from src.main_agent import FactAgent
print("[OK] Import succeeded.")

# ── 3. Instantiate (no graph.invoke / stream called, so zero API calls) ────────
print("Instantiating FactAgent(dataset='feverous')...")
agent = FactAgent(dataset="feverous")
print("[OK] FactAgent instantiated.")

# ── 4. Verify expected attributes exist ───────────────────────────────────────
attrs = [
    "llm", "ingestion_graph", "super_graph",
    "evidence_seeking_agent",   # only ReAct agent remaining
]
for attr in attrs:
    assert hasattr(agent, attr), f"Missing attribute: {attr}"
print(f"[OK] All {len(attrs)} expected attributes present.")

print("\n=== Instantiation test PASSED ===")
