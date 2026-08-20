from src.utils import use_ollama, use_gpt, google_top_snippet
import json

def create_fol_subclaim(mode, claim):
    format_output = {
        "type": "object",
        "properties": {
            "response": {"type": "string"}
        },
        "required": ["response"]
    }
    prompt = f"""
    You are given a problem description and a claim. The task is to define all the predicates in the claim and return in JSON format like in example. Below is the claim:
    {claim}
   
    Below is example
    Claim: Howard University Hospital and Providence Hospital are both located in Washington, D.C.
    >>>>>>
    {{
        "response": "Predicates:\n1. Location(Howard_University_Hospital, Washington_D.C.) ::: Verify Howard University Hospital is located in Washington, D.C.\n2. Location(Providence_Hospital, Washington_D.C.) ::: Verify Providence Hospital is located in Washington, D.C.\n\nFollowup Question: Where is Howard University Hospital located?\nFollowup Question: Where is Providence Hospital located?"
    }}
    ------
    Claim: In 1959, former Chilean boxer Alfredo Cornejo Cuevas (born June 6, 1933) won the gold medal in the welterweight division at the Pan American Games (held in Chicago, United States, from August 27 to September 7) in Chicago, United States, and the world amateur welterweight title in Mexico City.
    >>>>>>
    {{
        "response": "Predicates:\n1. Born(Alfredo Cornejo Cuevas, June 6 1933) ::: Verify that Alfredo Cornejo Cuevas was born June 6, 1933.\n2. Won(Alfredo Cornejo Cuevas, the gold medal in the welterweight division at the Pan American Games in 1959) ::: Verify that Alfredo Cornejo Cuevas won the gold medal in the welterweight division at the Pan American Games in 1959.\n3. Held(The Pan American Games in 1959, Chicago United States) ::: Verify that The Pan American Games in 1959 was held in Chicago, United States.\n4. Won(Alfredo Cornejo Cuevas, the world amateur welterweight title in Mexico City).\n\nFollowup Question: When was Alfredo Cornejo Cuevas born?\nFollowup Question: Where were the 1959 Pan American Games held?\nFollowup Question: What title did Alfredo Cornejo Cuevas win in Mexico City?"
    }}
    """
    if "gpt" in model:
        result = use_gpt(model, prompt, format_output)
    else:
        result = use_ollama(model, prompt, format_output)
    return result

def create_a_question(claim, k):
    format_output = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "questions": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["claim", "questions"]
        }
    }
    prompt = f"""
    For each input subclaim,  generate {k} google search question(s) that could be used to find evidence to verify subclaim.
    The questions should be diverse, exploring different aspects or perspectives related to the subclaim, but still ensure simple and straightforward. There are some tips
    1. Use Specific Keywords – Instead of broad terms like "best laptops," specify details like "top-rated Dell XPS 15 laptops."
    2. Include Synonyms and Related Terms – Improve query accuracy by adding variations, e.g., "affordable hotels" OR "cheap accommodations."
    3. Balance Broad and Long-Tail Keywords – Combine general and specific terms to target a wider yet precise audience.
   
    Return the output in JSON format like this [{{"claim": "Location(Howard Hospital, Washington D.C.) ::: Verify Howard University Hospital is located in Washington, D.C.", "questions": ["Where is Howard Hospital located?"]}}]
    [{{
        "claims": ,
        "questions": ["question_1", ...],
    }}]
 
    Below are given claims
    {claim}
    """
    if "gpt" in model:
        result = use_gpt(model, prompt, format_output)
    else:
        result = use_ollama(model, prompt, format_output)
    return result
 

def folk(model, data):
    # Step 1: Create subclaims with FOL representation
    fol_response = create_fol_subclaim(model, data)
    fol_output = fol_response["response"]

    # Extract follow-up questions from the FOL response
    followup_questions = []
    for line in fol_output.split('\n'):
        if line.startswith("Followup Question:"):
            question = line.replace("Followup Question:", "").strip()
            followup_questions.append(question)

    # Step 2: Get evidence from Google for each follow-up question
    evidence = []
    for ques in followup_questions:
        try:
            snippet = google_top_snippet(ques)
        except Exception as e:
            snippet = f"Error fetching evidence: {str(e)}"
        evidence.append({
            "question": ques,
            "evidence": snippet
        })

    # Step 3: Generate decision prompt and get verdict
    prompt_predict = f"""
    You are an AI assistant responsible for determining whether a subclaim is supported by retrieved evidence.  

    ## **Provided Information**:
    This is a claim to do fact-checking:  
    {data}
    Here are its subquestions, and retrieved evidence for each subquestion:  
    {json.dumps(evidence, indent=2)}  

    ## **Decision-Making Process**:
    1. **Analyze the Retrieved Evidence**  
    2. **Apply a Voting System for Classification**  
    3. **Provide a Justification**  

    ## **Response Format**:
    Your response must be a structured JSON object:  
    {{
        "label": "supported" or "not_supported",
        "explanation": "A concise, evidence-based summary supporting your decision."
    }}
    """

    format_output = {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": ["supported", "not_supported"]
            },
            "explanation": {"type": "string"}
        },
        "required": ["label", "explanation"]
    }

    if "gpt" in model:
        results_predict = use_gpt(model, prompt_predict, format_output)
    else:
        results_predict = use_ollama(model, prompt_predict, format_output)
    return results_predict


