from typing import List, Any
from pydantic import BaseModel, Field

class _GetItem:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

class SubclaimWithQuestions(BaseModel):
    subclaim: str = Field(description="A subclaim derived from the main claim.")
    questions: List[str] = Field(description="A list of questions generated based on the subclaim.")

class QueryGeneration(_GetItem, BaseModel):
    subclaim_with_questions: List[SubclaimWithQuestions] = Field(
        description="A list of subclaims, each with a corresponding set of generated questions."
    )

query_generation = QueryGeneration

query_generation_prompt = """
For each input subclaim, generate k Google search question(s) that could be used to find evidence to verify the subclaim.
The questions should be diverse, exploring different aspects or perspectives related to the subclaim, while remaining clear and concise. Follow these guidelines:
1. Use Specific Keywords: Include precise terms related to entities and relationships in the claim.
2. Incorporate Synonyms and Related Terms: Use alternative phrasings to overcome vocabulary mismatches.
3. Vary Specificity: Generate both specific queries targeting exact details and broader queries that may capture contextual information.
4. Consider Different Angles: Approach the claim from multiple perspectives to ensure comprehensive evidence gathering.
5. Maintain Simplicity: Keep questions straightforward and directly relevant to the claim.

Return the output in JSON format like this: 
[{ 
    "claim": "Location(Howard Hospital, Washington D.C.) ::: Verify Howard University Hospital is located in Washington, D.C.", 
    "questions": ["Where is Howard Hospital located?"] 
}]
"""
