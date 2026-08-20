"""
input_ingestion.py
──────────────────
Defines the combined Plan schema and prompt used by plan_node.

A single Gemini call now replaces the four previously separate nodes:
  claim_decomposition → claim_classification → claim_splitter → query_generation

The Plan schema captures everything needed to drive evidence retrieval:
  - subclaims : verifiable predicate-form sub-facts extracted from the claim
  - queries   : 2-3 search questions per subclaim
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class _GetItem:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


# ── Combined output schema ─────────────────────────────────────────────────────

class SubclaimWithQueries(BaseModel):
    subclaim: str = Field(
        description=(
            "A single verifiable predicate derived from the main claim, "
            "written in the form 'Predicate(Subject, Object) ::: Verification goal'."
        )
    )
    queries: List[str] = Field(
        description=(
            "2-3 focused Google search questions that would surface evidence "
            "to confirm or refute this subclaim."
        )
    )


class Plan(_GetItem, BaseModel):
    subclaims_with_queries: List[SubclaimWithQueries] = Field(
        description=(
            "All verifiable subclaims extracted from the claim, each paired "
            "with search questions.  Non-verifiable subclaims (opinions, "
            "future events, hypotheticals) are excluded."
        )
    )


# ── Prompt ────────────────────────────────────────────────────────────────────

plan_prompt = """\
You are a fact-checking assistant.  Given an input claim, perform three steps
in a single pass and return structured JSON.

STEP 1 — DECOMPOSE
  Break the claim into atomic predicate-form subclaims.
  Use the notation:  Predicate(Subject, Object) ::: Verification goal
  Example:
    Claim: "Howard University Hospital and Providence Hospital are both in DC."
    Subclaims:
      Location(Howard_University_Hospital, Washington_DC)
        ::: Verify Howard University Hospital is in Washington DC
      Location(Providence_Hospital, Washington_DC)
        ::: Verify Providence Hospital is in Washington DC

STEP 2 — FILTER
  Discard any subclaim that is:
    • a subjective opinion or value judgment
    • about a future or hypothetical event
    • vague / unverifiable by public sources
  Keep only subclaims that assert checkable facts about the world.
  If NO subclaims survive, return a single entry:
    subclaim: "NON_VERIFIABLE" and queries: []

STEP 3 — GENERATE QUERIES
  For each surviving subclaim write 2-3 distinct Google search questions.
  Guidelines:
    • Use specific entity names and relationships from the subclaim.
    • Vary phrasing — include synonyms and alternative angles.
    • Keep each question concise and self-contained.

Return ONLY the JSON object matching the schema.  No preamble or explanation.
"""


# ── Legacy re-exports (kept so existing experiment code doesn't break) ─────────
# These schemas are no longer used by main_agent but may be referenced in
# src/experiments/*.py or evaluation scripts.

from langchain_core.prompts.few_shot import FewShotPromptTemplate  # noqa: F401
from langchain_core.prompts.prompt import PromptTemplate            # noqa: F401
from typing import Literal

class ClaimDecomposition(_GetItem, BaseModel):
    subclaims: List[str] = Field(description="Subclaims derived from the input claim.")

claim_decomposition = ClaimDecomposition

class SubclaimTypeItem(BaseModel):
    subclaim: str
    type: Literal["verifiable", "non-verifiable"]

class ClaimClassification(_GetItem, BaseModel):
    subclaim_type_dict: List[SubclaimTypeItem] = Field(
        description="Subclaims with classification types."
    )

claim_classification = ClaimClassification

class ClaimSplitting(_GetItem, BaseModel):
    subclaims: List[str] = Field(
        description="Verifiable subclaims after filtering."
    )

claim_splitting = ClaimSplitting

claim_decomposition_prompt = ""  # superseded by plan_prompt
claim_classification_prompt = ""  # superseded by plan_prompt
claim_splitter_prompt = ""         # superseded by plan_prompt
claim_decomposition_examples = []  # kept for any direct reference
