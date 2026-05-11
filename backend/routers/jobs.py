"""Job lifecycle endpoints: /generate, /jobs/{id}."""
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from config import AUDIO_DIR
from helpers import validate_video_id
from pipeline import job_worker
from schemas import GenerateRequest, GenerateResponse, JobState, JobStatus
from state import cleanup_expired_jobs, job_queue, jobs, start_worker_if_needed

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate_subtitles_job(request: GenerateRequest):
    """Start full subtitle generation pipeline"""
    validate_video_id(request.video_id)
    cleanup_expired_jobs()
    job_id = str(uuid.uuid4())
    now = datetime.now().timestamp()

    jobs[job_id] = JobState(
        job_id=job_id,
        video_id=request.video_id,
        status=JobStatus.PENDING,
        progress=0,
        message="Starting...",
        step=0,
        target_language=request.target_language,
        created_at=now,
        updated_at=now
    )

    start_worker_if_needed(job_worker)

    queue_size = job_queue.qsize()
    if queue_size > 0:
        jobs[job_id].message = f"Queued (position {queue_size + 1})"
        print(f"Job {job_id} queued at position {queue_size + 1}")

    await job_queue.put((
        job_id,
        request.video_id,
        request.source_language,
        request.target_language,
        request.force_regenerate or False,
        request.save_path
    ))

    return GenerateResponse(
        job_id=job_id,
        video_id=request.video_id,
        status=JobStatus.PENDING
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and progress"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    response = {
        "job_id": job.job_id,
        "video_id": job.video_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "step": job.step,
        "target_language": job.target_language,
        "detected_language": job.detected_language,
        "error": job.error,
        "batch_current": job.batch_current,
        "batch_total": job.batch_total
    }

    if job.status == JobStatus.COMPLETE:
        if job.subtitles is not None:
            subtitles = job.subtitles
        else:
            translation_file = AUDIO_DIR / f"{job.video_id}_translation_{job.target_language}.json"
            transcript_file = AUDIO_DIR / f"{job.video_id}_transcript.json"

            subtitles = []
            if translation_file.exists():
                with open(translation_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    subtitles = data.get("segments", [])
            elif transcript_file.exists():
                with open(transcript_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    subtitles = data.get("segments", [])

        response["subtitles"] = subtitles

    return response


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete/cancel a job"""
    if job_id in jobs:
        del jobs[job_id]
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=404, detail="Job not found")
