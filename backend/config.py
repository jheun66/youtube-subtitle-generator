"""Configuration: environment variables, paths, dependency checks."""
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

AUDIO_DIR = Path(tempfile.gettempdir()) / "subtitle_generator"
AUDIO_DIR.mkdir(exist_ok=True)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None
