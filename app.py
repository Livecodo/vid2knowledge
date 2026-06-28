import os
import sys
import json
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Ensure the parent directory is on the path so we can import ingest
sys.path.append(str(Path(__file__).parent))
from ingest import run_ingest

# Simple helper to load environment variables from .env
def load_dotenv():
    dotenv_path = Path(__file__).parent / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Load environment at start
load_dotenv()

app = FastAPI(title="YouTube Transcript Scraper")

class ScrapeRequest(BaseModel):
    url: str
    lang: str = "en,es"
    whisper: bool = False

class GenerateRequest(BaseModel):
    transcript: str
    title: str
    channel: str = ""

@app.post("/api/scrape")
async def scrape_video(req: ScrapeRequest):
    # Run the ingestion logic in-process
    try:
        result = run_ingest(
            url=req.url,
            vault_root_path=Path(__file__).parent,
            lang_prefs_str=req.lang,
            whisper=req.whisper
        )
    except (RuntimeError, SystemExit, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

def call_gemini(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    # Refresh dotenv in case the user edited the key without restarting the server
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Gemini API Key not set. Please add GEMINI_API_KEY to your .env file."
        )

    # Support a comma-separated list (GEMINI_MODELS) or single model (GEMINI_MODEL)
    models_env = os.environ.get("GEMINI_MODELS") or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    models = [m.strip() for m in models_env.split(",") if m.strip()]

    last_error = "No models available."

    for model in models:
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": user_prompt}
                    ]
                }
            ]
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [
                    {"text": system_prompt}
                ]
            }

        generation_config = {}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        
        if generation_config:
            payload["generationConfig"] = generation_config

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=90
            )

            if response.status_code == 200:
                res_data = response.json()
                candidates = res_data.get("candidates", [])
                if candidates:
                    content_obj = candidates[0].get("content", {})
                    parts = content_obj.get("parts", [])
                    if parts and "text" in parts[0]:
                        print(f"[Gemini] Success with model: {model}")
                        return parts[0]["text"]
                # Empty response — try next model
                last_error = f"Model '{model}' returned an empty or unexpected response format."
                print(f"[Gemini] {last_error} Trying next model...")
                continue

            # Non-200 — extract error message then try next model
            error_msg = response.text
            try:
                error_json = response.json()
                if "error" in error_json:
                    error_msg = error_json["error"].get("message", error_msg)
            except Exception:
                pass
            last_error = f"Model '{model}' failed ({response.status_code}): {error_msg}"
            print(f"[Gemini] {last_error} Trying next model...")

        except requests.exceptions.RequestException as e:
            last_error = f"Model '{model}' request error: {str(e)}"
            print(f"[Gemini] {last_error} Trying next model...")

    # All models exhausted
    raise HTTPException(
        status_code=500,
        detail=f"All Gemini models failed. Last error: {last_error}"
    )


@app.post("/api/generate/blog")
async def generate_blog(req: GenerateRequest):
    system_prompt = (
        "You are an expert educator, researcher, and technical writer. Your task is to transform the "
        "following video transcript into a comprehensive, highly detailed, and well-structured study guide "
        "and blog post. It must explain all key concepts fully, with clear sections, examples, detailed "
        "explanations, and key takeaways so that any student or researcher can use it as high-quality study notes. "
        "Use rich markdown formatting (headers, bolding, lists, blockquotes, and code blocks). "
        "Ensure the output is long, thorough, and explains everything discussed in the transcript in depth, "
        "translating raw speech into cohesive written notes."
    )
    user_prompt = (
        f"Video Title: {req.title}\n"
        f"Channel: {req.channel}\n\n"
        f"Transcript:\n{req.transcript}"
    )
    content = call_gemini(system_prompt, user_prompt, json_mode=False)
    return {"content": content}



@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = Path(__file__).parent / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return index_file.read_text(encoding="utf-8")

if __name__ == "__main__":
    # strictly bind to localhost for security as recommended by personal-tool-builder
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)

