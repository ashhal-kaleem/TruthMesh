"""
Single real claim test for FactAgent.
Run from anywhere:  python P:\FactAgent\test_real_claim.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from src.main_agent import FactAgent

agent = FactAgent(dataset="feverous")

claim = "The Eiffel Tower is located in Paris, France."
print(f"Claim: {claim}\n")
print("Running pipeline (verbose=True)...\n")

results = agent.process_claim(claim, recursion_limit=150, verbose=True)

print("\n=== Final steps ===")
for step in results[-3:]:
    print(step)
