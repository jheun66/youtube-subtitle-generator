"""Audio transcription via ElevenLabs Scribe."""
import json
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from config import AUDIO_DIR, ELEVENLABS_API_KEY
from schemas import SubtitleSegment, TranscribeRequest, TranscribeResponse

router = APIRouter()


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(request: TranscribeRequest):
    """Transcribe audio using ElevenLabs Speech-to-Text API"""

    if not ELEVENLABS_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ElevenLabs API key not configured. Set ELEVENLABS_API_KEY environment variable."
        )

    audio_path = Path(request.audio_path).resolve()

    if not audio_path.is_relative_to(AUDIO_DIR.resolve()):
        raise HTTPException(
            status_code=400,
            detail="audio_path must be within the server audio directory"
        )

    if not audio_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Audio file not found: {audio_path}"
        )

    video_id = audio_path.stem
    transcript_file = AUDIO_DIR / f"{video_id}_transcript.json"

    if transcript_file.exists() and not request.force_regenerate:
        print(f"\n=== Using Cached Transcription ===")
        print(f"Found existing transcript: {transcript_file}")

        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)

            detected_language = cached_data.get("detected_language", "en")
            segments = cached_data.get("segments", [])

            subtitles = [
                SubtitleSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"]
                )
                for seg in segments
            ]

            print(f"Loaded {len(subtitles)} segments from cache")
            print(f"Detected language: {detected_language}")

            return TranscribeResponse(
                success=True,
                detected_language=detected_language,
                subtitles=subtitles,
                cached=True
            )
        except Exception as e:
            print(f"Failed to load cached transcript: {str(e)}")
            print("Proceeding with fresh transcription...")

    print(f"\n=== Transcription Request ===")
    print(f"Audio file: {audio_path.name}")
    print(f"File size: {audio_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"Language: {request.language or 'auto-detect'}")
    print(f"Force regenerate: {request.force_regenerate}")

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            ext = audio_path.suffix.lower()
            mime_types = {
                '.mp3': 'audio/mpeg',
                '.m4a': 'audio/mp4',
                '.webm': 'audio/webm',
                '.opus': 'audio/opus',
                '.ogg': 'audio/ogg',
                '.wav': 'audio/wav'
            }
            mime_type = mime_types.get(ext, 'audio/mpeg')

            with open(audio_path, "rb") as audio_file:
                files = {
                    "file": (audio_path.name, audio_file, mime_type)
                }

                data = {
                    "model_id": "scribe_v1",
                    "timestamps_granularity": "word",
                    "diarize": "false",
                    "tag_audio_events": "false"
                }

                if request.language:
                    data["language_code"] = request.language

                response = await client.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    headers={
                        "xi-api-key": ELEVENLABS_API_KEY
                    },
                    files=files,
                    data=data
                )

            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"ElevenLabs API error: {error_detail}"
                )

            result = response.json()

            subtitles = []
            words = result.get("words", [])

            if words:
                # Group words into sentences/segments (roughly 5-10 seconds each)
                current_segment = {
                    "start": words[0]["start"],
                    "text": "",
                    "words": []
                }

                for word in words:
                    if word.get("type") != "word":
                        continue

                    current_segment["words"].append(word)
                    current_segment["text"] += word.get("text", "") + " "

                    segment_duration = word["end"] - current_segment["start"]
                    text_so_far = current_segment["text"].strip()

                    should_end = (
                        segment_duration >= 5.0 and any(text_so_far.endswith(p) for p in ".!?。！？") or
                        segment_duration >= 8.0 or
                        len(text_so_far.split()) >= 15
                    )

                    if should_end and current_segment["words"]:
                        subtitles.append(SubtitleSegment(
                            start=current_segment["start"],
                            end=word["end"],
                            text=current_segment["text"].strip()
                        ))

                        current_segment = {
                            "start": word["end"],
                            "text": "",
                            "words": []
                        }

                if current_segment["text"].strip():
                    last_word = current_segment["words"][-1] if current_segment["words"] else words[-1]
                    subtitles.append(SubtitleSegment(
                        start=current_segment["start"],
                        end=last_word["end"],
                        text=current_segment["text"].strip()
                    ))
            else:
                full_text = result.get("text", "")
                if full_text:
                    subtitles.append(SubtitleSegment(
                        start=0.0,
                        end=60.0,
                        text=full_text
                    ))

            detected_language = result.get("language_code", "en")

            print(f"\n=== Transcription Complete ===")
            print(f"Detected language: {detected_language}")
            print(f"Number of subtitle segments: {len(subtitles)}")
            if subtitles:
                print(f"First segment: {subtitles[0].text[:100]}...")
                print(f"Last segment: {subtitles[-1].text[:100]}...")

            with open(transcript_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "detected_language": detected_language,
                    "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in subtitles]
                }, f, ensure_ascii=False, indent=2)
            print(f"Transcription saved to: {transcript_file}")

            return TranscribeResponse(
                success=True,
                detected_language=detected_language,
                subtitles=subtitles,
                cached=False
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error transcribing audio: {str(e)}"
        )
