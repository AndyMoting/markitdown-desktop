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
