# Task 8: Temp file cleanup service

**Files to modify:**
- `D:\Projects\MD\markitdown-desktop\inkdrop\app.py`

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\tests\test_cleanup.py`

## Pre-step: Write the test

Create `tests/test_cleanup.py`:
```python
"""Tests for temp file cleanup."""
import asyncio
import time
from pathlib import Path

import pytest
from inkdrop.jobs import JobManager, JobStatus
from inkdrop.converter import ConversionResult


@pytest.fixture
def job_manager(tmp_dir):
    return JobManager(tmp_root=str(tmp_dir / "jobs"))


@pytest.mark.asyncio
async def test_cleanup_removes_files(job_manager, sample_pdf, tmp_dir):
    job_id = await job_manager.create_job("test.pdf")
    work_dir = job_manager.get_work_dir(job_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "test.txt").write_text("temp")

    assert work_dir.exists()
    job_manager.cleanup(job_id)
    assert not work_dir.exists()
```

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_cleanup.py -v`
Expected: PASS (cleanup method already exists in JobManager from Task 4)

## Step: Add cleanup scheduler to app.py

Modify `inkdrop/app.py` — add a startup event handler that runs a background cleanup loop. Add this inside `create_app()`, after the `app = FastAPI(...)` line:

```python
    @app.on_event("startup")
    async def start_cleanup_task():
        async def cleanup_loop():
            import shutil
            while True:
                await asyncio.sleep(300)  # every 5 minutes
                now = time.time()
                for job_id, job in list(job_manager._jobs.items()):
                    if (job.completed_at
                            and now - job.completed_at > 300):  # 5 min old
                        job_manager.cleanup(job_id)
                        _log.info("Cleaned up job %s", job_id)
        asyncio.create_task(cleanup_loop())
```

Also add `import time` at the top of app.py.

## After: Run all tests and commit

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests/ -v`
Expected: PASS

Commit:
```powershell
git add -A
git commit -m "feat: add automatic temp file cleanup every 5 minutes"
```

## Global Constraints
- Cleanup runs every 5 minutes, removes jobs completed >5 min ago
- Do NOT modify JobManager.cleanup() — it already works
