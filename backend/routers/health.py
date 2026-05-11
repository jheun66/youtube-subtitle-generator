"""Health check endpoint."""
from datetime import datetime

from fastapi import APIRouter

from config import DEFAULT_SAVE_DIR, ELEVENLABS_API_KEY, FFMPEG_AVAILABLE, FFPROBE_AVAILABLE, GEMINI_API_KEY

router = APIRouter()


@router.get("/health")
async def health_check():
    """Check server health and API key availability"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "ffprobe_available": FFPROBE_AVAILABLE,
        "default_save_path": str(DEFAULT_SAVE_DIR)
    }
