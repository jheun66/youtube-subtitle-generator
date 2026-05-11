"""Sequential job worker and the end-to-end subtitle generation pipeline."""
import asyncio
import json
import shutil
from typing import List

import httpx
from fastapi import HTTPException
from json_repair import loads as json_repair_loads

from config import AUDIO_DIR, DEFAULT_SAVE_DIR, GEMINI_API_KEY
from helpers import LANGUAGE_NAMES, build_translation_prompt, call_gemini_translate, validate_save_path
from routers.extract import extract_audio
from routers.transcribe import transcribe_audio
from schemas import ExtractRequest, JobStatus, SubtitleSegment, TranscribeRequest
from state import job_queue, update_job


async def job_worker():
    """Process jobs sequentially from the queue."""
    while True:
        job_id, video_id, source_lang, target_lang, force_regenerate, save_path = await job_queue.get()
        try:
            await run_pipeline(job_id, video_id, source_lang, target_lang, force_regenerate, save_path)
        except Exception as e:
            print(f"Job worker error for {job_id}: {e}")
        finally:
            job_queue.task_done()


async def run_pipeline(job_id: str, video_id: str, source_lang: str,
                       target_lang: str, force_regenerate: bool, save_path: str = None):
    """Execute full subtitle generation pipeline with progress updates"""

    try:
        print(f"\n{'='*60}")
        print(f"Starting pipeline for job {job_id} (video: {video_id})")
        print(f"Queue remaining: {job_queue.qsize()}")
        print(f"{'='*60}")

        # Step 1: Extract audio
        update_job(job_id, status=JobStatus.EXTRACTING, step=1, progress=10,
                   message="Extracting audio...")

        extract_result = await extract_audio(ExtractRequest(video_id=video_id))

        update_job(job_id, progress=25, message="Audio extracted")

        # Step 2: Transcribe
        update_job(job_id, status=JobStatus.TRANSCRIBING, step=2, progress=30,
                   message="Transcribing audio...")

        transcribe_result = await transcribe_audio(TranscribeRequest(
            audio_path=extract_result.audio_path,
            language=source_lang if source_lang != "auto" else None,
            force_regenerate=force_regenerate
        ))

        detected_language = transcribe_result.detected_language
        num_segments = len(transcribe_result.subtitles)

        update_job(job_id, detected_language=detected_language, progress=60,
                   message=f"Transcribed ({num_segments} segments)")

        # Step 3: Translate (if needed)
        if detected_language != target_lang:
            update_job(job_id, status=JobStatus.TRANSLATING, step=3, progress=65,
                       message="Starting translation...")

            await translate_subtitles_with_job(
                job_id,
                transcribe_result.subtitles,
                detected_language,
                target_lang,
                video_id,
                force_regenerate
            )
        else:
            update_job(job_id, progress=90, message="No translation needed (same language)")

        # Step 4: Save result (user-provided path or default)
        update_job(job_id, step=4, progress=95, message="Saving result...")

        save_dir = validate_save_path(save_path) if save_path else DEFAULT_SAVE_DIR
        save_dir.mkdir(parents=True, exist_ok=True)

        translation_file = AUDIO_DIR / f"{video_id}_translation_{target_lang}.json"
        transcript_file = AUDIO_DIR / f"{video_id}_transcript.json"

        src_file = translation_file if translation_file.exists() else transcript_file
        if src_file.exists():
            dst_file = save_dir / src_file.name
            shutil.copy2(src_file, dst_file)
            print(f"Result saved to: {dst_file}")

            with open(src_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                update_job(job_id, subtitles=data.get("segments", []))

        for f in AUDIO_DIR.glob(f"{video_id}*"):
            try:
                f.unlink()
                print(f"Cleaned up: {f.name}")
            except Exception as e:
                print(f"Failed to clean up {f.name}: {e}")

        update_job(job_id, status=JobStatus.COMPLETE, step=4, progress=100,
                   message="Complete!")

    except Exception as e:
        print(f"Pipeline error for job {job_id}: {str(e)}")
        update_job(job_id, status=JobStatus.ERROR, error=str(e),
                   message=f"Error: {str(e)}")


async def translate_subtitles_with_job(
    job_id: str,
    subtitles: List[SubtitleSegment],
    source_language: str,
    target_language: str,
    video_id: str,
    force_regenerate: bool
):
    """Translate subtitles with job progress updates and partial-resume support."""

    if not GEMINI_API_KEY:
        raise Exception("Gemini API key not configured")

    translation_file = AUDIO_DIR / f"{video_id}_translation_{target_language}.json"

    if translation_file.exists() and not force_regenerate:
        print(f"\n=== Using Cached Translation ===")
        update_job(job_id, progress=90, message="Using cached translation")
        return

    source_lang_name = LANGUAGE_NAMES.get(source_language, source_language)
    target_lang_name = LANGUAGE_NAMES.get(target_language, target_language)

    subtitle_texts = [{"index": i, "text": sub.text} for i, sub in enumerate(subtitles)]

    BATCH_SIZE = 50
    batches = [subtitle_texts[i:i + BATCH_SIZE] for i in range(0, len(subtitle_texts), BATCH_SIZE)]
    num_batches = len(batches)

    print(f"\n=== Translation with Job Tracking ===")
    print(f"Job ID: {job_id}")
    print(f"Source: {source_lang_name}, Target: {target_lang_name}")
    print(f"Total batches: {num_batches}")

    update_job(job_id, batch_total=num_batches)

    partial_file = AUDIO_DIR / f"{video_id}_translation_{target_language}_partial.json"
    all_translated = []
    start_batch = 1

    if partial_file.exists():
        try:
            with open(partial_file, 'r', encoding='utf-8') as f:
                partial_data = json.load(f)
            all_translated = partial_data.get("translated", [])
            completed_batches = partial_data.get("completed_batches", 0)
            start_batch = completed_batches + 1
            print(f"\n=== Resuming from batch {start_batch}/{num_batches} ({len(all_translated)} segments already translated) ===")
        except Exception as e:
            print(f"Failed to load partial progress: {e}, starting fresh")
            all_translated = []
            start_batch = 1

    async with httpx.AsyncClient(timeout=120.0) as client:
        for batch_num, batch in enumerate(batches, 1):
            if batch_num < start_batch:
                continue

            batch_progress = 65 + int((batch_num - 1) / num_batches * 25)
            update_job(
                job_id,
                progress=batch_progress,
                message=f"Translating batch {batch_num}/{num_batches}...",
                batch_current=batch_num
            )

            print(f"\n=== Processing batch {batch_num}/{num_batches} ===")

            prompt = build_translation_prompt(batch, source_lang_name, target_lang_name)
            result = await call_gemini_translate(
                client, prompt, batch_num,
                on_rate_limit=lambda delay: update_job(job_id, message=f"Rate limited, retrying in {delay}s...")
            )
            candidates = result.get("candidates", [])

            if not candidates:
                print(f"WARNING: No candidates in response for batch {batch_num}")
                print(f"Response keys: {list(result.keys())}")
                print(f"Response preview: {json.dumps(result, ensure_ascii=False)[:500]}")
                raise Exception(f"No candidates in Gemini response for batch {batch_num}")

            finish_reason = candidates[0].get("finishReason", "unknown")
            print(f"Batch {batch_num} finishReason: {finish_reason}")

            content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            print(f"Batch {batch_num} content length: {len(content)}")

            if not content:
                print(f"WARNING: Empty content for batch {batch_num}")
                print(f"Candidate: {json.dumps(candidates[0], ensure_ascii=False)[:500]}")
                raise Exception(f"Empty response content for batch {batch_num}")

            translated = None
            try:
                translated = json_repair_loads(content)
            except Exception:
                pass

            if translated is None:
                print(f"Failed to parse batch {batch_num}. Content preview: {content[:500]}")
                raise Exception(f"Failed to parse translation response for batch {batch_num}")

            all_translated.extend(translated)
            print(f"Batch {batch_num} complete: {len(translated)} segments")

            with open(partial_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "completed_batches": batch_num,
                    "total_batches": num_batches,
                    "translated": all_translated
                }, f, ensure_ascii=False)
            print(f"Partial progress saved: {batch_num}/{num_batches} batches")

            if batch_num < num_batches:
                update_job(job_id, message=f"Batch {batch_num}/{num_batches} done. Waiting...")
                await asyncio.sleep(5)

    translated_subtitles = []
    translation_map = {item["index"]: item["text"] for item in all_translated}

    for i, original_sub in enumerate(subtitles):
        translated_text = translation_map.get(i, original_sub.text)
        translated_subtitles.append({
            "start": original_sub.start,
            "end": original_sub.end,
            "text": translated_text,
            "original_text": original_sub.text
        })

    with open(translation_file, 'w', encoding='utf-8') as f:
        json.dump({
            "source_language": source_language,
            "target_language": target_language,
            "segments": translated_subtitles
        }, f, ensure_ascii=False, indent=2)

    if partial_file.exists():
        partial_file.unlink()

    print(f"Translation saved to: {translation_file}")
    update_job(job_id, progress=90, message=f"Translation complete ({len(translated_subtitles)} segments)")
