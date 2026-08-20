import base64
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from src.main_agent import FactAgent

app = FastAPI(
    title="FactAgent API",
    description="Minimal backend for FactAgent 3-call architecture pipeline.",
    version="1.0.0"
)

# Enable CORS for Vercel/frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the global agent
# Using a fixed dataset 'feverous' by default, or could be parameterized.
agent = FactAgent(dataset="feverous")

@app.get("/")
def health_check():
    return {"status": "ok", "message": "FactAgent API is running."}

@app.post("/check_claim")
async def check_claim(
    claim: str = Form(...),
    image: Optional[UploadFile] = File(None)
):
    """
    Process a text claim, optionally with an image.
    """
    image_base64 = None

    if image:
        content = await image.read()
        encoded = base64.b64encode(content).decode('utf-8')
        
        # Determine mime type from filename
        filename = image.filename.lower()
        ext = filename.split('.')[-1] if '.' in filename else "jpeg"
        mime_type = f"image/{ext}" if ext in ["png", "jpeg", "jpg", "webp"] else "image/jpeg"
        
        image_base64 = f"data:{mime_type};base64,{encoded}"

    # Run the pipeline
    result = agent.process_claim(claim=claim, image=image_base64, verbose=False)
    
    return result
