"""Shared helpers: language mapping, Gemini API call, path validation."""
import asyncio
import json
from pathlib import Path

import httpx
from fastapi import HTTPException

from config import GEMINI_API_KEY

LANGUAGE_NAMES = {
    "en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese",
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "it": "Italian", "ru": "Russian", "ar": "Arabic", "hi": "Hindi"
}


def build_translation_prompt(batch, source_lang_name, target_lang_name):
    return f"""You are a professional translator. Translate the following subtitle segments from {source_lang_name} to {target_lang_name}.

Important guidelines:
1. Maintain the natural flow and tone of the original content
2. Keep translations concise and suitable for subtitles (readable in 2-3 seconds)
3. Preserve any speaker-specific style or emotion
4. Do not add explanations or notes
5. Return ONLY a JSON array with the translated texts

Input subtitles:
{json.dumps(batch, ensure_ascii=False, indent=2)}

Return ONLY a JSON array in this exact format (no markdown, no explanation):
[{{"index": 0, "text": "translated text"}}, ...]"""


async def call_gemini_translate(client, prompt, batch_num, max_retries=5, base_delay=2, on_rate_limit=None):
    """Call Gemini translation API with exponential-backoff retry. Returns parsed response JSON."""
    response = None
    for attempt in range(max_retries):
        try:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                headers={
                    "content-type": "application/json",
                    "x-goog-api-key": GEMINI_API_KEY
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": 16384,
                        "responseMimeType": "application/json"
                    }
                }
            )

            if response.status_code == 429:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"Rate limit hit on batch {batch_num}, attempt {attempt + 1}/{max_retries}. Waiting {delay}s...")
                    if on_rate_limit:
                        on_rate_limit(delay)
                    await asyncio.sleep(delay)
                    continue
                raise HTTPException(
                    status_code=429,
                    detail=f"Gemini API rate limit error in batch {batch_num} after {max_retries} retries: {response.text}"
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Gemini API error in batch {batch_num}: {response.text}"
                )

            break

        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Timeout on batch {batch_num}, attempt {attempt + 1}/{max_retries}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                continue
            raise HTTPException(
                status_code=504,
                detail=f"Timeout error in batch {batch_num} after {max_retries} retries"
            )

    if response is None:
        raise HTTPException(
            status_code=500,
            detail=f"No response from Gemini API for batch {batch_num} after {max_retries} retries"
        )

    return response.json()


def validate_save_path(save_path: str) -> Path:
    """Reject path traversal attempts and require absolute paths."""
    path = Path(save_path)
    if any(part == ".." for part in path.parts):
        raise HTTPException(status_code=400, detail="save_path must not contain '..'")
    if not path.is_absolute():
        raise HTTPException(status_code=400, detail="save_path must be an absolute path")
    return path
