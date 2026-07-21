"""Job lifecycle management: create → process → complete/fail."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from inkdrop.converter import ConversionResult


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    filename: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    message: str = ""
    result: Optional[ConversionResult] = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


class JobManager:
    """In-memory job store. No persistence — jobs live for the session."""

    def __init__(self, tmp_root: str = "/tmp/inkdrop"):
        self._jobs: dict[str, Job] = {}
        self._tmp_root = Path(tmp_root)
        self._tmp_root.mkdir(parents=True, exist_ok=True)

    async def create_job(self, filename: str) -> str:
        job_id = str(uuid.uuid4())[:8]
        job = Job(id=job_id, filename=filename)
        self._jobs[job_id] = job
        (self._tmp_root / job_id).mkdir(parents=True, exist_ok=True)
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "filename": job.filename,
            "status": job.status.value,
            "progress": job.progress,
            "message": job.message,
            "error": job.error,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "result": job.result,
        }

    def get_status(self, job_id: str) -> JobStatus | None:
        job = self._jobs.get(job_id)
        return job.status if job else None

    def get_result(self, job_id: str) -> ConversionResult | None:
        job = self._jobs.get(job_id)
        return job.result if job else None

    def update_progress(self, job_id: str, progress: int, message: str = ""):
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.PROCESSING
            job.progress = progress
            job.message = message

    def complete_job(self, job_id: str, result: ConversionResult):
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.message = "Complete"
            job.result = result
            job.completed_at = time.time()

    def fail_job(self, job_id: str, error: str):
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error = error
            job.completed_at = time.time()

    def get_work_dir(self, job_id: str) -> Path:
        return self._tmp_root / job_id

    def cleanup(self, job_id: str):
        """Remove job files from disk."""
        import shutil
        work_dir = self._tmp_root / job_id
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        self._jobs.pop(job_id, None)

    async def convert_job(self, job_id: str, input_path: Path):
        """Run conversion in thread pool."""
        from inkdrop.converter import convert
        loop = asyncio.get_event_loop()
        self.update_progress(job_id, 10, "Starting conversion...")
        try:
            output_dir = self.get_work_dir(job_id) / "output"
            result = await loop.run_in_executor(
                None, convert, input_path, output_dir
            )
            self.complete_job(job_id, result)
        except Exception as e:
            self.fail_job(job_id, str(e))
