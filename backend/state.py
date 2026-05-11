"""Job state: in-memory job registry, queue, worker lifecycle, TTL cleanup."""
import asyncio
from datetime import datetime
from typing import Dict

from schemas import JobState, JobStatus

jobs: Dict[str, JobState] = {}
job_queue: asyncio.Queue = asyncio.Queue()
_worker_started = False

JOB_TTL_SECONDS = 3600  # Drop finished jobs after 1 hour


def update_job(job_id: str, **kwargs):
    if job_id in jobs:
        for key, value in kwargs.items():
            if hasattr(jobs[job_id], key):
                setattr(jobs[job_id], key, value)
        jobs[job_id].updated_at = datetime.now().timestamp()


def cleanup_expired_jobs():
    """Remove COMPLETE/ERROR jobs older than JOB_TTL_SECONDS to bound memory."""
    cutoff = datetime.now().timestamp() - JOB_TTL_SECONDS
    expired = [
        jid for jid, job in jobs.items()
        if job.status in (JobStatus.COMPLETE, JobStatus.ERROR) and job.updated_at < cutoff
    ]
    for jid in expired:
        del jobs[jid]


def start_worker_if_needed(worker_coro):
    """Spawn the job worker on first /generate call. Idempotent."""
    global _worker_started
    if not _worker_started:
        asyncio.create_task(worker_coro())
        _worker_started = True
