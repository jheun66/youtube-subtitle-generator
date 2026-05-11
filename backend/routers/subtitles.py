"""Retrieve saved subtitles and clean up temp files."""
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from config import AUDIO_DIR
from helpers import validate_save_path, validate_video_id
from schemas import SubtitleSegment

router = APIRouter()


@router.get("/subtitles/{video_id}")
async def get_subtitles(video_id: str, language: Optional[str] = None, save_path: Optional[str] = None):
    """Get the latest subtitles for a video (translation or transcript)"""
    validate_video_id(video_id)

    print(f"\n=== Get Subtitles Request ===")
    print(f"Video ID: {video_id}")
    print(f"Preferred language: {language or 'any'}")
    print(f"Save path: {save_path or 'none'}")

    search_dirs = []
    if save_path:
        search_dirs.append(validate_save_path(save_path))
    search_dirs.append(AUDIO_DIR)

    if language:
        translation_file = None
        for d in search_dirs:
            candidate = d / f"{video_id}_translation_{language}.json"
            if candidate.exists():
                translation_file = candidate
                break

        if translation_file and translation_file.exists():
            print(f"Found translation file: {translation_file}")
            try:
                with open(translation_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                subtitles = [
                    SubtitleSegment(
                        start=seg["start"],
                        end=seg["end"],
                        text=seg["text"],
                        original_text=seg.get("original_text")
                    )
                    for seg in data.get("segments", [])
                ]

                return {
                    "success": True,
                    "video_id": video_id,
                    "language": data.get("target_language", language),
                    "source": "translation",
                    "subtitles": subtitles
                }
            except Exception as e:
                print(f"Failed to load translation file: {str(e)}")

    transcript_file = None
    for d in search_dirs:
        candidate = d / f"{video_id}_transcript.json"
        if candidate.exists():
            transcript_file = candidate
            break

    if transcript_file and transcript_file.exists():
        print(f"Found transcript file: {transcript_file}")
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            subtitles = [
                SubtitleSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"]
                )
                for seg in data.get("segments", [])
            ]

            return {
                "success": True,
                "video_id": video_id,
                "language": data.get("detected_language", "unknown"),
                "source": "transcript",
                "subtitles": subtitles
            }
        except Exception as e:
            print(f"Failed to load transcript file: {str(e)}")

    raise HTTPException(
        status_code=404,
        detail=f"No subtitles found for video ID: {video_id}"
    )


@router.delete("/cleanup/{video_id}")
async def cleanup_files(video_id: str, background_tasks: BackgroundTasks):
    """Clean up temporary files for a video"""
    validate_video_id(video_id)

    def delete_files():
        for pattern in [f"{video_id}*"]:
            for f in AUDIO_DIR.glob(pattern):
                try:
                    f.unlink()
                    print(f"Deleted: {f}")
                except Exception as e:
                    print(f"Failed to delete {f}: {e}")

    background_tasks.add_task(delete_files)

    return {"status": "cleanup scheduled", "video_id": video_id}
