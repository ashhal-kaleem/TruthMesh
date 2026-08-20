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

evidence_seeking = EvidenceSeeking

evidence_seeking_prompt = """
You are a helpful assistant who extracts information from text.
Given the following query and text content, extract only the sentences or phrases that directly
relate to the query. Do not include any information that is not relevant.
If the content contains no relevant information, return None.
"""
