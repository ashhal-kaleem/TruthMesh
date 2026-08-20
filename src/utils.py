import json
import requests
from dotenv import load_dotenv
import os
import ollama
from openai import OpenAI
from typing import Dict
load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def google_top_snippet(question: str) -> str:
    url = "https://google.serper.dev/search"  # Adjust if necessary
    try:
        payload = json.dumps({
            "q": question,
            "num": 1,
            "tbs": "cdr:1,cd_min:,cd_max:12/13/2023",  # Optional: time restriction
        })
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, headers=headers, data=payload)
        result = response.json()
        
        if "organic" in result and result["organic"]:
            snippet = result["organic"][0].get("snippet")
            if snippet:
                return snippet
    except requests.RequestException:
        raise Exception("SERPER_API_KEY exhausted. No results retrieved.")
        
def use_ollama(model: str, prompt: str, format_output: Dict) -> Dict:
    try:
        ollama.chat(model)
    except ollama.ResponseError as e:
        if e.status_code == 404:
            ollama.pull(model)
#  - Avoid slashes '/' and newline characters ('\n') in the output.- YOU MUST maintain \\n while translating.
    # text = text.replace("\r", "\n")
    response = ollama.chat(model=model, messages=[
        {
            'role': 'user',
            'content': prompt,
        }],
        stream=False,
        format= format_output,
        options={"temperature": 0.0}
    )
   
    result = response['message']['content']
    result = json.loads(result)  # Convert JSON-like response
    return result

def use_gpt(model: str, prompt: str, format_output: Dict) -> Dict:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Create the completion request
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"} if format_output else None,
            temperature=0.0
        )
        
        result = response.choices[0].message.content
        result = json.loads(result)  # Convert JSON-like response
        return result
        
    except Exception as e:
        raise Exception(f"OpenAI API error: {str(e)}")
