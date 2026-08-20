from typing import List, Literal, Any
from pydantic import BaseModel, Field
from langchain_core.prompts.few_shot import FewShotPromptTemplate
from langchain_core.prompts.prompt import PromptTemplate

# ── Base mixin so dict-style access still works in main_agent.py ──────────────
class _GetItem:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

# ── Pydantic schemas (replace old OpenAI-style dicts) ────────────────────────

class ClaimDecomposition(_GetItem, BaseModel):
    subclaims: List[str] = Field(description="The subclaims derived from the input claim.")

claim_decomposition = ClaimDecomposition


class SubclaimTypeItem(BaseModel):
    subclaim: str
    type: Literal["verifiable", "non-verifiable"]

class ClaimClassification(_GetItem, BaseModel):
    subclaim_type_dict: List[SubclaimTypeItem] = Field(
        description="A list of subclaims with their classification types."
    )

claim_classification = ClaimClassification


class ClaimSplitting(_GetItem, BaseModel):
    subclaims: List[str] = Field(
        description="The verifiable subclaims after filtering out non-verifiable subclaims."
    )

claim_splitting = ClaimSplitting


# ── Prompts and examples (unchanged) ─────────────────────────────────────────

claim_decomposition_examples = [
    {
        "input_claim": "Howard University Hospital and Providence Hospital are both located in Washington, D.C.",
        "subclaims": [
            "Location(Howard_University_Hospital, Washington_D.C.) ::: Verify Howard University Hospital is located in Washington, D.C",
            "Location(Providence_Hospital, Washington_D.C.) ::: Verify Providence Hospital is located in Washington, D.C",
        ],
    },
    {
        "input_claim": "In 1959, former Chilean boxer Alfredo Cornejo Cuevas (born June 6, 1933) won the gold medal in the welterweight division at the Pan American Games (held in Chicago, United States, from August 27 to September 7) in Chicago, United States, and the world amateur welterweight title in Mexico City.",
        "subclaims": [
            "Born(Alfredo_Cornejo_Cuevas, June 6 1933) ::: Verify that Alfredo Cornejo Cuevas was born June 6, 1933.",
            "Won(Alfredo_Cornejo_Cuevas, the gold medal in the welterweight division at the Pan American Games in 1959) ::: Verify that Alfredo Cornejo Cuevas won the gold medal in the welterweight division at the Pan American Games in 1959.",
            "Held(The Pan American Games in 1959, Chicago United States) ::: Verify that the Pan American Games in 1959 were held in Chicago, United States.",
            "Won(Alfredo_Cornejo_Cuevas, the world amateur welterweight title in Mexico City) ::: Verify that Alfredo Cornejo Cuevas won the world amateur welterweight title in Mexico City."
        ],
    },
]

claim_decomposition_prompt = f"""
You are given a problem description and a claim. The task is to define all the predicates in the claim and return them in JSON format, as shown in the example below.
Here are examples:
{claim_decomposition_examples}
"""

claim_classification_prompt = """
You are an expert in claim verification. Your task is to determine whether a given claim is verifiable or non-verifiable.
A verifiable claim is a factual statement that can be checked against objective evidence from reliable sources. It makes specific assertions about the world that can be proven true or false through investigation.

A non-verifiable claim is one that cannot be objectively verified because it:
- Expresses a subjective opinion, preference, or personal experience  
- Makes vague or ambiguous statements without specific details  
- Refers to future events that haven't occurred yet  
- Makes normative or ethical judgments about what "should" be  
- Contains hypothetical scenarios or counterfactuals  

### Examples:
Verifiable: "The average global temperature increased by 0.8$^\\circ$C between 1880 and 2012." 
Non-verifiable: "Climate change is the most important issue facing humanity today."  
Verifiable: "The film 'Parasite' won the Academy Award for Best Picture in 2020."  
Non-verifiable: "Parasite deserved to win the Academy Award for Best Picture."

Please analyze the following claim and classify it as either VERIFIABLE or NON-VERIFIABLE. Provide a brief explanation for your classification.
"""

claim_splitter_prompt = "Filter out the non-verifiable claims. If there is no verifiable fact, return NON-SUPPORTED."
