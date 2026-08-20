from typing import Literal, Any
from pydantic import BaseModel, Field

class _GetItem:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

class VerdictResult(BaseModel):
    label: Literal["SUPPORT", "REFUTE", "UNCERTAIN"] = Field(
        description="The verdict on whether the claim is supported by the evidence."
    )
    explanation: str = Field(
        description="A textual explanation justifying the verdict based on the evidence."
    )

class VerdictPrediction(_GetItem, BaseModel):
    result: VerdictResult = Field(
        description="The final verdict and explanation."
    )

verdict_prediction = VerdictPrediction

verdict_prediction_prompt = """
You are an AI assistant responsible for determining whether a subclaim is supported by retrieved evidence.  
 
## Provided Information:
This is a claim to do fact-checking:  
\\n {claim}
Here is the given subclaims, its subquestions, and retrieved evidence for each subquestion:  
\\n {cell}  

## Decision-Making Process:

1. Analyze the Retrieved Evidence  
- Review all provided evidence relevant to the subclaim.  
- Assess the credibility, consistency, and reliability of each piece of evidence.  

2. Apply a Voting System for Classification  
- If multiple sources strongly support the subclaim, classify it as "SUPPORT".  
- If multiple sources contradict the subclaim, classify it as "REFUTE".  
- If the evidence is mixed, insufficient, or inconclusive, classify it as "UNCERTAIN".  

3. Provide a Justification  
- Clearly explain why the subclaim is classified as "SUPPORT", "REFUTE", or "UNCERTAIN".  
- Reference key pieces of evidence that influenced your decision.  
- If the evidence is inconclusive, explain the limitations or uncertainties.  
- Remember to adjust not to include " for later parse
"""
