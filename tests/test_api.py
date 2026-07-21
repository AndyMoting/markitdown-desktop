"""Tests for InkDrop FastAPI endpoints."""
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from inkdrop.app import create_app
from inkdrop.jobs import JobManager


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def job_manager(tmp_dir):
    return JobManager(tmp_root=str(tmp_dir / "jobs"))


@pytest.fixture
def app(job_manager):
    return create_app(job_manager)


@pytest.fixture
def client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_index_page(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "InkDrop" in resp.text


@pytest.mark.asyncio
async def test_upload_pdf(client, sample_pdf, job_manager):
    content = sample_pdf.read_bytes()
    resp = await client.post(
        "/api/upload",
        files={"file": ("test.pdf", content, "application/pdf")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data


@pytest.mark.asyncio
async def test_get_status(client, sample_pdf, job_manager):
    # Upload first
    content = sample_pdf.read_bytes()
    upload_resp = await client.post(
        "/api/upload",
        files={"file": ("test.pdf", content, "application/pdf")},
    )
    job_id = upload_resp.json()["job_id"]

    # Check status
    resp = await client.get(f"/api/status/{job_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unsupported_format(client, tmp_dir):
    bad_file = tmp_dir / "test.ppt"
    bad_file.write_bytes(b"fake ppt content")
    content = bad_file.read_bytes()
    resp = await client.post(
        "/api/upload",
        files={"file": ("test.ppt", content, "application/vnd.ms-powerpoint")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
