from utils import use_ollama, google_top_snippet, use_gpt

def self_ask(model, data):
    format_output = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "string",
                "description": "Follow-up questions separated by newline (\\n)."
            }
        },
        "required": ["questions"]
    }

    prompt = f"""
    You are a critical thinking assistant.
    
    Given a claim, your task is to generate follow-up questions that help:
    - Clarify ambiguous parts,
    - Probe for evidence or examples,
    - Test the truthfulness of the claim.
    
    Guidelines:
    - Ask 3 to 5 questions.
    - Questions should be open-ended and specific.
    - Do not answer the claim; only generate questions.
    
    Return your output in JSON format like this:
    {{
      "questions": "<Question 1>\\n<Question 2>\\n<Question 3>"
    }}
    
    Here is the claim:
    \"\"\"
    {data}
    \"\"\"
    
    Generate the follow-up questions:
    """
    if "gpt" in model:
        questions = use_gpt(model, prompt, format_output)
    else:
        questions = use_ollama(model, prompt, format_output)
    string_questions = questions['questions']
    lst_questions = string_questions.split('\n')
    lst_questions = [ques for ques in lst_questions if ques]
    evidence = []
    for ques in lst_questions: 
        d = {"question": "ques"}
        d["evidence"] = google_top_snippet(ques)
        evidence.append(d)
    prompt_predict = f"""
    You are an AI assistant responsible for determining whether a subclaim is supported by retrieved evidence.  

    ## **Provided Information**:
    This is a claim to do fact-checking:  
    \\n {data}
    Here are its subquestions, and retrieved evidence for each subquestion:  
    \\n {evidence}  

    ## **Decision-Making Process**:

    1. **Analyze the Retrieved Evidence**  
    - Review all provided evidence relevant to the subclaim.  
    - Assess the credibility, consistency, and reliability of each piece of evidence.  

    2. **Apply a Voting System for Classification**  
    - If multiple sources **strongly support** the subclaim, classify it as `"supported"`.  
    - If multiple sources **contradict** the subclaim, classify it as `"not_supported"`.  
    - If the evidence is **mixed, insufficient, or inconclusive**, classify it as `"not_supported"`.  

    3. **Provide a Justification**  
    - Clearly explain why the subclaim is classified as `"supported"` or `"not_supported"`.  
    - Reference key pieces of evidence that influenced your decision.  
    - If the evidence is inconclusive, explain the limitations or uncertainties.  
    - Remember to adjust not to include " for later parse
    ## **Response Format**:
    Your response must be a structured JSON object:  

    ```json
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

