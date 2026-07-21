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
