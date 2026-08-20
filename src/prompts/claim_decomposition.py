# Re-export from input_ingestion to satisfy main_agent.py import
from src.prompts.input_ingestion import (
    claim_decomposition,
    claim_decomposition_prompt,
    claim_decomposition_examples,
    claim_classification,
    claim_classification_prompt,
    claim_splitting,
    claim_splitter_prompt,
)
