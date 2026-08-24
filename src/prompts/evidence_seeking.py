"""
evidence_seeking.py — Evidence schema types for TruthMesh.

These Pydantic classes define the structure of the evidence dict produced by
evidence_node and consumed by verdict_node.  No LLM prompt lives here:
evidence_node is now a deterministic Python loop over (subclaim, query) pairs
that calls search_retrieve_news() directly — zero Gemini calls.
"""

from typing import List, Any
from pydantic import BaseModel, Field


class _GetItem:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class EvidenceItem(BaseModel):
    url: str = Field(description="The URL of the evidence source.")
    title: str = Field(description="The title of the article or page.")
    excerpt: str = Field(description="The relevant content extracted from the source.")
    credibility_score: str = Field(description="The credibility score of the source domain.")
    bias_label: str = Field(description="The political or ideological bias of the source domain.")


class QueryWithEvidence(BaseModel):
    query: str = Field(description="A query generated to seek evidence for the subclaim.")
    evidence: List[EvidenceItem] = Field(description="All evidences retrieved for the query.")


class SubclaimWithQueryEvidence(BaseModel):
    subclaim: str = Field(description="A subclaim derived from the main claim.")
    queries_with_evidence: List[QueryWithEvidence] = Field(
        description="A list of queries and their corresponding evidence for the subclaim."
    )


class EvidenceSeeking(_GetItem, BaseModel):
    subclaims_with_query_evidence: List[SubclaimWithQueryEvidence] = Field(
        description="A list of subclaims, each containing multiple queries with their corresponding evidence."
    )


# Kept for any external reference (experiment scripts, etc.)
evidence_seeking = EvidenceSeeking

# evidence_seeking_prompt has been removed: evidence_node no longer uses an LLM.
# Sentence-level relevance extraction is handled deterministically by
# SearchEngineRetriever._extract_relevant_sentences() in tools/retrieve.py.
