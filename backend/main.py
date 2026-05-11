"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import AUDIO_DIR, ELEVENLABS_API_KEY, FFMPEG_AVAILABLE, FFPROBE_AVAILABLE, GEMINI_API_KEY
from routers import extract, health, jobs, subtitles, transcribe, translate

app = FastAPI(
    title="YouTube Subtitle Generator API",
    description="Backend API for YouTube subtitle generation using ElevenLabs STT and Gemini translation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(extract.router)
app.include_router(transcribe.router)
app.include_router(translate.router)
app.include_router(jobs.router)
app.include_router(subtitles.router)


if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("YouTube Subtitle Generator Backend Server")
    print("=" * 60)
    print(f"\n📁 Audio cache directory: {AUDIO_DIR}")
    print(f"🔑 ElevenLabs API: {'✅ Configured' if ELEVENLABS_API_KEY else '❌ Not configured'}")
    print(f"🔑 Gemini API: {'✅ Configured' if GEMINI_API_KEY else '❌ Not configured'}")
    print(f"🎬 ffmpeg: {'✅ Available' if FFMPEG_AVAILABLE else '⚠️  Not found (will use m4a format)'}")
    print(f"🔍 ffprobe: {'✅ Available' if FFPROBE_AVAILABLE else '⚠️  Not found'}")

    if not FFMPEG_AVAILABLE:
        print("\n💡 Install ffmpeg for best audio quality:")
        print("   - macOS: brew install ffmpeg")
        print("   - Ubuntu/Debian: sudo apt install ffmpeg")
        print("   - Windows: Download from https://ffmpeg.org/download.html")

    print("\n ⚠️  Make sure to set environment variables:")
    print("   - ELEVENLABS_API_KEY")
    print("   - GEMINI_API_KEY")
    print("\n🚀 Starting server on http://localhost:8000")
    print("=" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
