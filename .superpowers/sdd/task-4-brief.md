# Task 4: Job manager (background tasks + temp file management)

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\inkdrop\jobs.py`
- `D:\Projects\MD\markitdown-desktop\tests\test_jobs.py`

## Pre-step: Write the failing test FIRST (TDD)

Create `tests/test_jobs.py`:
```python
"""Tests for inkdrop.jobs module."""
import asyncio
import time
from pathlib import Path

import pytest
from inkdrop.jobs import JobManager, JobStatus


@pytest.fixture
def job_manager(tmp_dir):
    return JobManager(tmp_root=str(tmp_dir))


@pytest.mark.asyncio
async def test_create_job(job_manager):
    job_id = await job_manager.create_job("test.pdf")
    assert job_id
    status = job_manager.get_status(job_id)
    assert status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_job_progress(job_manager):
    job_id = await job_manager.create_job("doc.pdf")
    job_manager.update_progress(job_id, 50, "Half done")
    info = job_manager.get_job(job_id)
    assert info["progress"] == 50
    assert info["message"] == "Half done"


@pytest.mark.asyncio
async def test_job_completion(job_manager, sample_pdf, tmp_dir):
    job_id = await job_manager.create_job("sample.pdf")
    from inkdrop.converter import convert
    result = convert(sample_pdf, tmp_dir / "out")
    job_manager.complete_job(job_id, result)
    info = job_manager.get_job(job_id)
    assert info["status"] == JobStatus.COMPLETED
    assert info["result"] is not None


@pytest.mark.asyncio
async def test_job_failure(job_manager):
    job_id = await job_manager.create_job("bad.pdf")
    job_manager.fail_job(job_id, "Conversion failed")
    info = job_manager.get_job(job_id)
    assert info["status"] == JobStatus.FAILED
    assert info["error"] == "Conversion failed"
```

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_jobs.py -v`
Expected: FAIL — ModuleNotFoundError

## Step: Implement job manager

Create `inkdrop/jobs.py`:
```python
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
        # Create job working directory
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
```

## After: Run tests and commit

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_jobs.py -v`
Expected: PASS

Commit:
```powershell
git add -A
git commit -m "feat: add job manager for background conversion tracking"
```

## Interfaces
- **Produces:** `JobManager` class with `create_job()`, `get_job()`, `get_result()`, `cleanup()`, `convert_job()`
- **Produces:** `JobStatus` enum: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`
- **Consumed by:** `inkdrop/app.py` (Task 5)

## Global Constraints
- In-memory only, no persistence
- Thread-safe enough for asyncio (single-threaded event loop)
- Do NOT modify existing files
