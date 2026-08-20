# Re-export shim — main_agent.py no longer imports from here,
# but experiment scripts may still reference these names.
from src.prompts.input_ingestion import (
    Plan,
    plan_prompt,
    SubclaimWithQueries,
    ClaimDecomposition,
    claim_decomposition,
    claim_decomposition_prompt,
    claim_decomposition_examples,
    ClaimClassification,
    claim_classification,
    claim_classification_prompt,
    ClaimSplitting,
    claim_splitting,
    claim_splitter_prompt,
)
