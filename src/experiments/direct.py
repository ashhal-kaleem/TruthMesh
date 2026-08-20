from src.utils import use_ollama, use_gpt

def direct(model, data):
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
    prompt = f"""
    You are a truth detecting machine, your task is given a claim, tell that is it Supported or Non-supported. Supported means truthfull and non-supported is non-truthful.
    Return your answer in JSON format as:
    {{
      "label": "<supported|not_supported>",
      "explanation": "<step-by-step explanation including subclaims and their evaluation>"
    }}
    
    This is the claim:
    \"\"\"
    {data}
    \"\"\"
    """
    if "gpt" in model:
        result = use_gpt(model, prompt, format_output)
    else:
        result = use_ollama(model, prompt, format_output)
    return result

