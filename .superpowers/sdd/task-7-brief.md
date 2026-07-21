# Task 7: Allure test reporting setup

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\tests\test_smoke.py`
- `D:\Projects\MD\markitdown-desktop\pytest.ini`

## Step 1: Create pytest.ini

Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = --alluredir=allure-results --clean-alluredir
```

Note: `asyncio_mode = auto` requires `pytest-asyncio`. Check if it's installed. If not, add it to requirements.txt and install. From Task 4 we know `pytest-asyncio` was installed.

## Step 2: Write end-to-end smoke test

Create `tests/test_smoke.py`:
```python
"""End-to-end smoke test: full upload → convert → preview flow."""
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
    import asyncio
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
```

## Step 3: Run full test suite with Allure output

Run:
```powershell
cd D:\Projects\MD\markitdown-desktop
D:\Projects\.venv\Scripts\pytest.exe tests/ -v
```
Expected: All tests pass. `allure-results/` directory created with test artifacts.

## Step 4: Commit

```powershell
git add -A
git commit -m "test: add allure reporting and end-to-end smoke test"
```

## Global Constraints
- Do NOT modify existing test files or source code
- The smoke test will take ~30s due to polling. That's OK.
