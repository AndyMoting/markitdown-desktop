"""End-to-end smoke test: full upload → convert → preview flow."""
import asyncio

import pytest
from httpx import AsyncClient, ASGITransport

from inkdrop.app import create_app
from inkdrop.jobs import JobManager


@pytest.fixture
def app(tmp_path):
    jm = JobManager(tmp_root=str(tmp_path / "jobs"))
    return create_app(jm)


@pytest.fixture
def client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_full_flow_pdf(client, sample_pdf, tmp_path):
    """Upload PDF → wait for completion → check result."""
    # Upload
    resp = await client.post(
        "/api/upload",
        files={"file": ("sample.pdf", sample_pdf.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # Poll status (max 30s)
    for _ in range(30):
        await asyncio.sleep(1)
        resp = await client.get(f"/api/status/{job_id}")
        assert resp.status_code == 200

    # Verify preview accessible
    resp = await client.get(f"/api/preview/{job_id}")
    assert resp.status_code == 200

    # Verify download accessible
    resp = await client.get(f"/api/download/{job_id}")
    assert resp.status_code == 200
    assert len(resp.content) > 0
