"""Pydantic request/response models."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ExtractRequest(BaseModel):
    video_id: str


class ExtractResponse(BaseModel):
    success: bool
    video_id: str
    audio_path: str
    duration: Optional[float] = None


class TranscribeRequest(BaseModel):
    audio_path: str
    language: Optional[str] = None
    force_regenerate: Optional[bool] = False


class SubtitleSegment(BaseModel):
    start: float
    end: float
    text: str
    original_text: Optional[str] = None
    speaker_id: Optional[str] = None


class TranscribeResponse(BaseModel):
    success: bool
    detected_language: str
    subtitles: List[SubtitleSegment]
    cached: Optional[bool] = False


class TranslateRequest(BaseModel):
    subtitles: List[SubtitleSegment]
    source_language: str
    target_language: str
    video_id: Optional[str] = None
    force_regenerate: Optional[bool] = False


class TranslateResponse(BaseModel):
    success: bool
    source_language: str
    target_language: str
    subtitles: List[SubtitleSegment]


class JobStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    COMPLETE = "complete"
    ERROR = "error"


class JobState(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    progress: int
    message: str
    step: int
    target_language: str
    detected_language: Optional[str] = None
    error: Optional[str] = None
    created_at: float
    updated_at: float
    batch_current: Optional[int] = None
    batch_total: Optional[int] = None
    subtitles: Optional[List] = None


class GenerateRequest(BaseModel):
    video_id: str
    source_language: Optional[str] = "auto"
    target_language: str
    force_regenerate: Optional[bool] = False
    save_path: Optional[str] = None


class GenerateResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
