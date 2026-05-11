"""YouTube audio extraction via yt-dlp."""
import asyncio

from fastapi import APIRouter, HTTPException

from config import AUDIO_DIR, FFMPEG_AVAILABLE
from helpers import validate_video_id
from schemas import ExtractRequest, ExtractResponse

router = APIRouter()

AUDIO_EXTENSIONS = ('mp3', 'm4a', 'webm', 'opus', 'ogg')


@router.post("/extract", response_model=ExtractResponse)
async def extract_audio(request: ExtractRequest):
    """Extract audio from YouTube video using yt-dlp"""
    video_id = validate_video_id(request.video_id)
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    if FFMPEG_AVAILABLE:
        audio_format = "mp3"
    else:
        audio_format = "m4a"

    for ext in AUDIO_EXTENSIONS:
        existing_path = AUDIO_DIR / f"{video_id}.{ext}"
        if existing_path.exists():
            return ExtractResponse(
                success=True,
                video_id=video_id,
                audio_path=str(existing_path)
            )

    try:
        if FFMPEG_AVAILABLE:
            cmd = [
                "yt-dlp",
                "-f", "bestaudio",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "-o", str(AUDIO_DIR / f"{video_id}.%(ext)s"),
                "--no-playlist",
                "--no-warnings",
                "--cookies-from-browser", "chrome",
                "--remote-components", "ejs:github",
                "--js-runtimes", "node",
                video_url
            ]
        else:
            cmd = [
                "yt-dlp",
                "-f", "bestaudio",
                "-o", str(AUDIO_DIR / f"{video_id}.%(ext)s"),
                "--no-playlist",
                "--no-warnings",
                "--cookies-from-browser", "chrome",
                "--remote-components", "ejs:github",
                "--js-runtimes", "node",
                video_url
            ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise HTTPException(
                status_code=504,
                detail="Audio extraction timed out after 5 minutes"
            )

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"

            if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
                raise HTTPException(
                    status_code=500,
                    detail="ffmpeg/ffprobe not found. Please install ffmpeg:\n"
                           "- macOS: brew install ffmpeg\n"
                           "- Ubuntu/Debian: sudo apt install ffmpeg\n"
                           "- Windows: Download from https://ffmpeg.org/download.html"
                )

            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract audio: {error_msg}"
            )

        actual_path = None
        for ext in AUDIO_EXTENSIONS:
            check_path = AUDIO_DIR / f"{video_id}.{ext}"
            if check_path.exists():
                actual_path = check_path
                break

        if not actual_path:
            for f in AUDIO_DIR.glob(f"{video_id}*"):
                if f.is_file() and f.suffix.lstrip('.') in AUDIO_EXTENSIONS:
                    actual_path = f
                    break

        if not actual_path:
            raise HTTPException(
                status_code=500,
                detail="Audio file was not created. Check if yt-dlp is installed correctly."
            )

        return ExtractResponse(
            success=True,
            video_id=video_id,
            audio_path=str(actual_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error extracting audio: {str(e)}"
        )
