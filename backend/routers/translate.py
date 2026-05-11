"""Standalone subtitle translation via Gemini."""
import asyncio
import json
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException
from json_repair import loads as json_repair_loads

from config import AUDIO_DIR, GEMINI_API_KEY
from helpers import LANGUAGE_NAMES, build_translation_prompt, call_gemini_translate
from schemas import SubtitleSegment, TranslateRequest, TranslateResponse

router = APIRouter()


@router.post("/translate", response_model=TranslateResponse)
async def translate_subtitles(request: TranslateRequest):
    """Translate subtitles using Gemini API"""

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Gemini API key not configured. Set GEMINI_API_KEY environment variable."
        )

    if not request.subtitles:
        raise HTTPException(
            status_code=400,
            detail="No subtitles provided for translation"
        )

    if request.video_id and not request.force_regenerate:
        translation_file = AUDIO_DIR / f"{request.video_id}_translation_{request.target_language}.json"

        if translation_file.exists():
            print(f"\n=== Using Cached Translation ===")
            print(f"Found existing translation: {translation_file}")

            try:
                with open(translation_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                cached_subtitles = [
                    SubtitleSegment(
                        start=seg["start"],
                        end=seg["end"],
                        text=seg["text"],
                        original_text=seg.get("original_text")
                    )
                    for seg in cached_data.get("segments", [])
                ]

                print(f"Loaded {len(cached_subtitles)} translated segments from cache")
                print(f"Source: {cached_data.get('source_language')}, Target: {cached_data.get('target_language')}")

                return TranslateResponse(
                    success=True,
                    source_language=cached_data.get("source_language", request.source_language),
                    target_language=cached_data.get("target_language", request.target_language),
                    subtitles=cached_subtitles
                )
            except Exception as e:
                print(f"Failed to load cached translation: {str(e)}")
                print("Proceeding with fresh translation...")

    source_lang_name = LANGUAGE_NAMES.get(request.source_language, request.source_language)
    target_lang_name = LANGUAGE_NAMES.get(request.target_language, request.target_language)

    subtitle_texts = [{"index": i, "text": sub.text} for i, sub in enumerate(request.subtitles)]

    print(f"\n=== Translation Request ===")
    print(f"Source: {source_lang_name}, Target: {target_lang_name}")
    print(f"Number of subtitle segments: {len(subtitle_texts)}")
    print(f"Video ID: {request.video_id or 'None'}")
    print(f"Force regenerate: {request.force_regenerate}")
    print(f"First few subtitles: {subtitle_texts[:3]}")

    BATCH_SIZE = 50
    batches = [subtitle_texts[i:i + BATCH_SIZE] for i in range(0, len(subtitle_texts), BATCH_SIZE)]
    print(f"Splitting into {len(batches)} batches of up to {BATCH_SIZE} segments each")

    all_translated = []

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            for batch_num, batch in enumerate(batches, 1):
                print(f"\n=== Processing batch {batch_num}/{len(batches)} ===")
                print(f"Segments {batch[0]['index']} to {batch[-1]['index']}")

                prompt = build_translation_prompt(batch, source_lang_name, target_lang_name)
                result = await call_gemini_translate(client, prompt, batch_num)
                content = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

                print(f"Response length: {len(content)} characters")
                print(f"First 200 chars: {content[:200]}")
                print(f"Last 200 chars: {content[-200:]}")

                try:
                    content = content.strip()

                    translated = None
                    parse_error = None

                    try:
                        translated = json_repair_loads(content)
                    except Exception as e:
                        parse_error = str(e)

                    if translated is None:
                        print(f"Failed to parse Gemini response for batch {batch_num}. Content preview: {content[:500]}...")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to parse translation response for batch {batch_num}: {parse_error}. Check server logs for details."
                        )

                    if not isinstance(translated, list):
                        raise HTTPException(
                            status_code=500,
                            detail=f"Translation response for batch {batch_num} is not a JSON array"
                        )

                    all_translated.extend(translated)
                    print(f"Batch {batch_num} complete: {len(translated)} segments translated")

                    if batch_num < len(batches):
                        delay_between_batches = 5
                        print(f"Waiting {delay_between_batches}s before next batch to respect rate limits...")
                        await asyncio.sleep(delay_between_batches)

                except json.JSONDecodeError as e:
                    print(f"JSON decode error in batch {batch_num}: {str(e)}")
                    print(f"Content: {content[:1000]}...")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to parse translation response for batch {batch_num}: {str(e)}"
                    )

            print(f"\n=== All batches complete ===")
            print(f"Total translated segments: {len(all_translated)}")

            translated_subtitles = []
            translation_map = {item["index"]: item["text"] for item in all_translated}

            for i, original_sub in enumerate(request.subtitles):
                translated_text = translation_map.get(i, original_sub.text)
                translated_subtitles.append(SubtitleSegment(
                    start=original_sub.start,
                    end=original_sub.end,
                    text=translated_text,
                    original_text=original_sub.text,
                    speaker_id=original_sub.speaker_id
                ))

            if request.video_id:
                translation_file = AUDIO_DIR / f"{request.video_id}_translation_{request.target_language}.json"
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                translation_file = AUDIO_DIR / f"translation_{request.source_language}_to_{request.target_language}_{timestamp}.json"

            with open(translation_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "source_language": request.source_language,
                    "target_language": request.target_language,
                    "segments": [{"start": s.start, "end": s.end, "text": s.text, "original_text": s.original_text} for s in translated_subtitles]
                }, f, ensure_ascii=False, indent=2)
            print(f"Translation saved to: {translation_file}")

            return TranslateResponse(
                success=True,
                source_language=request.source_language,
                target_language=request.target_language,
                subtitles=translated_subtitles
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error translating subtitles: {str(e)}"
        )
