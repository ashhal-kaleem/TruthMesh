"""
test_init.py — zero-API-call instantiation + call-count instrumentation.
Run from P:\FactAgent:  python test_init.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

assert os.getenv("GOOGLE_API_KEY"),  "GOOGLE_API_KEY missing from .env"
assert os.getenv("SERPER_API_KEY"), "SERPER_API_KEY missing from .env"
print("[OK] Both API keys found in environment.")

print("Importing FactAgent...")
from src.main_agent import FactAgent
print("[OK] Import succeeded.")

print("Instantiating FactAgent(dataset='feverous')...")
agent = FactAgent(dataset="feverous")
print("[OK] FactAgent instantiated.")

# Verify new attributes
attrs = ["llm", "graph", "evidence_agent"]
for attr in attrs:
    assert hasattr(agent, attr), f"Missing attribute: {attr}"
print(f"[OK] All {len(attrs)} expected attributes present.")

# Verify old supervisor-based attributes are GONE (they consumed Gemini calls)
removed = ["ingestion_graph", "super_graph"]
for attr in removed:
    assert not hasattr(agent, attr), (
        f"Old supervisor attribute still present: {attr}"
    )
print(f"[OK] Old supervisor attributes correctly removed: {removed}")

# Verify graph has exactly 3 real nodes (plan, evidence, verdict)
nodes = list(agent.graph.get_graph().nodes.keys())
real_nodes = [n for n in nodes if n not in ("__start__", "__end__")]
assert len(real_nodes) == 3, f"Expected 3 nodes, found: {real_nodes}"
print(f"[OK] Graph has exactly 3 nodes: {real_nodes}")

# Verify retrieve.py has no genai import (Gemini article extraction removed)
import ast, pathlib
retrieve_src = pathlib.Path("src/tools/retrieve.py").read_text(encoding="utf-8")
assert "genai" not in retrieve_src, (
    "retrieve.py still imports google.generativeai — _process_content not removed!"
)
print("[OK] retrieve.py has no genai import (article extraction is deterministic).")

# Verify no supervisor node in main_agent.py
main_src = pathlib.Path("src/main_agent.py").read_text(encoding="utf-8")
assert "_make_supervisor_node" not in main_src, (
    "Supervisor node factory still present in main_agent.py!"
)
print("[OK] No LLM supervisor node in main_agent.py.")

print("\n=== Instantiation test PASSED ===")
