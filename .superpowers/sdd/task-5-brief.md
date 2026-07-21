# Task 5: FastAPI app + API routes

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\inkdrop\app.py`
- `D:\Projects\MD\markitdown-desktop\inkdrop\templates\index.html`
- `D:\Projects\MD\markitdown-desktop\inkdrop\templates\preview.html`
- `D:\Projects\MD\markitdown-desktop\inkdrop\static\style.css`
- `D:\Projects\MD\markitdown-desktop\tests\test_api.py`

## Pre-step: Write the failing API test FIRST (TDD)

Create `tests/test_api.py`:
```python
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
```

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_api.py -v`
Expected: FAIL — `create_app` not found

## Step: Create templates

Create directory `inkdrop/templates/` and `inkdrop/static/`.

Create `inkdrop/templates/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkDrop · 喂给 AI 的文档预处理器</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
    <script src="https://unpkg.com/htmx.org@2.0.2"></script>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <main class="container">
        <h1>InkDrop <small>喂给 AI 的文档预处理器</small></h1>
        <div id="upload-zone"
             class="drop-zone"
             hx-post="/api/upload"
             hx-encoding="multipart/form-data"
             hx-target="#result"
             hx-swap="innerHTML"
             hx-on::after-request="this.value=''">
            <input type="file" name="file" id="file-input"
                   accept=".pdf,.doc,.docx,.pptx,.xlsx,.xls,.html,.csv,.json,.xml,.txt,.epub,.zip,.png,.jpg,.jpeg,.gif,.bmp,.eml,.msg">
            <p>拖拽文件到这里，或点击选择</p>
            <small>支持 PDF / DOC / DOCX / PPTX / XLSX / 图片 / 邮件 等</small>
        </div>
        <div id="result"></div>
    </main>
</body>
</html>
```

Create `inkdrop/templates/preview.html`:
```html
<div class="preview-container" id="preview-{{ job.id }}">
    {% if job.result and job.result.quality %}
    <div class="quality-badge quality-{{ 'good' if job.result.quality.score >= 70 else 'medium' if job.result.quality.score >= 40 else 'bad' }}">
        质量评分: {{ job.result.quality.score }}/100
    </div>
    {% endif %}

    {% if job.status == 'processing' or job.status == 'pending' %}
    <div class="progress-bar" hx-get="/api/status/{{ job.id }}"
         hx-trigger="every 1s" hx-swap="none"
         hx-on::after-request="if(event.detail.successful) { document.getElementById('preview-{{ job.id }}').outerHTML = event.detail.xhr.responseText; }">
        <div class="progress-fill" style="width: {{ job.progress }}%"></div>
        <span>{{ job.message or '处理中...' }}</span>
    </div>
    {% endif %}

    {% if job.status == 'completed' and job.result %}
    <div class="result-grid">
        <section class="preview-md">
            <h3>Markdown 预览</h3>
            <article class="markdown-body">
                {{ job.result.markdown | truncate(500) }}
            </article>
        </section>

        {% if job.result.images %}
        <section class="image-gallery">
            <h3>提取的图片 ({{ job.result.images | length }})</h3>
            <div class="gallery-grid">
                {% for img in job.result.images[:20] %}
                <figure>
                    <img src="/api/images/{{ job.id }}/{{ img.name }}"
                         alt="{{ img.name }}"
                         onclick="document.getElementById('dlg-{{ job.id }}-{{ loop.index }}').showModal()">
                    <figcaption>{{ img.name }}</figcaption>
                    <dialog id="dlg-{{ job.id }}-{{ loop.index }}">
                        <img src="/api/images/{{ job.id }}/{{ img.name }}" style="max-width:90vw;max-height:90vh">
                        <form method="dialog"><button>关闭</button></form>
                    </dialog>
                </figure>
                {% endfor %}
            </div>
        </section>
        {% endif %}

        {% if job.result.quality %}
        <section class="quality-report">
            <h3>质量报告</h3>
            <ul>
                <li>标题结构: {{ '✅ 正常' if job.result.quality.heading_structure_ok else '⚠️ 层级断裂' }}</li>
                <li>表格数量: {{ job.result.quality.table_count }}</li>
                <li>提取图片: {{ job.result.quality.image_count }}</li>
                <li>乱码检测: {{ '⚠️ 疑似乱码' if job.result.quality.garbled_detected else '✅ 正常' }}</li>
            </ul>
        </section>
        {% endif %}

        {% if job.result.warning %}
        <div class="warning">⚠️ {{ job.result.warning }}</div>
        {% endif %}
    </div>

    <div class="actions">
        <button onclick="navigator.clipboard.writeText(`{{ job.result.markdown | replace('`', '\\`') | truncate(10000) }})`)">复制 Markdown</button>
        <a href="/api/download/{{ job.id }}" role="button">下载 ZIP</a>
    </div>
    {% endif %}

    {% if job.status == 'failed' %}
    <div class="error">
        <h3>❌ 转换失败</h3>
        <p>{{ job.error }}</p>
    </div>
    {% endif %}
</div>
```

Create `inkdrop/static/style.css`:
```css
.drop-zone {
    border: 2px dashed var(--pico-muted-border-color);
    border-radius: 1rem;
    padding: 3rem 2rem;
    text-align: center;
    margin: 2rem 0;
    transition: all 0.2s;
    cursor: pointer;
    position: relative;
}
.drop-zone:hover, .drop-zone.drag-over {
    border-color: var(--pico-primary);
    background: var(--pico-primary-background);
}
.drop-zone input[type="file"] {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
}
.progress-bar {
    background: var(--pico-muted-border-color);
    border-radius: 0.5rem;
    height: 2rem;
    margin: 1rem 0;
    position: relative;
    overflow: hidden;
}
.progress-fill {
    background: var(--pico-primary);
    height: 100%;
    transition: width 0.3s;
}
.progress-bar span {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
}
.result-grid {
    display: grid;
    gap: 1.5rem;
    margin: 1.5rem 0;
}
.quality-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-weight: bold;
    margin-bottom: 1rem;
}
.quality-good { background: #d4edda; color: #155724; }
.quality-medium { background: #fff3cd; color: #856404; }
.quality-bad { background: #f8d7da; color: #721c24; }
.gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 0.75rem;
}
.gallery-grid figure { margin: 0; text-align: center; }
.gallery-grid img {
    width: 100%;
    height: 100px;
    object-fit: cover;
    border-radius: 0.5rem;
    cursor: zoom-in;
}
.warning {
    background: #fff3cd;
    border: 1px solid #ffc107;
    padding: 0.75rem;
    border-radius: 0.5rem;
    margin: 1rem 0;
}
.error {
    background: #f8d7da;
    border: 1px solid #f5c6cb;
    padding: 1rem;
    border-radius: 0.5rem;
    color: #721c24;
}
.markdown-body {
    padding: 1rem;
    background: var(--pico-code-background-color);
    border-radius: 0.5rem;
    max-height: 400px;
    overflow-y: auto;
}
.actions { display: flex; gap: 1rem; margin-top: 1rem; }
.quality-report ul { list-style: none; padding: 0; }
.quality-report li { padding: 0.25rem 0; }
```

## Step: Implement FastAPI app

Create `inkdrop/app.py`:
```python
"""FastAPI application for InkDrop."""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from inkdrop.jobs import JobManager


_log = logging.getLogger("inkdrop")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def create_app(job_manager: JobManager | None = None) -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(title="InkDrop", version="2.0.0")

    if job_manager is None:
        import tempfile
        job_manager = JobManager(tmp_root=str(Path(tempfile.mkdtemp(prefix="inkdrop_"))))

    base_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(413, "文件过大，最大支持 50MB")

        job_id = await job_manager.create_job(file.filename)

        work_dir = job_manager.get_work_dir(job_id) / "input"
        work_dir.mkdir(parents=True, exist_ok=True)
        input_path = work_dir / file.filename
        input_path.write_bytes(content)

        asyncio.create_task(job_manager.convert_job(job_id, input_path))

        return JSONResponse({"job_id": job_id, "filename": file.filename})

    @app.get("/api/status/{job_id}")
    async def status(job_id: str, request: Request):
        job_info = job_manager.get_job(job_id)
        if job_info is None:
            raise HTTPException(404, "Job not found")
        return templates.TemplateResponse(
            "preview.html",
            {"request": request, "job": job_info}
        )

    @app.get("/api/preview/{job_id}")
    async def preview(job_id: str):
        result = job_manager.get_result(job_id)
        if result is None:
            raise HTTPException(404, "Result not found")
        return JSONResponse({"markdown": result.markdown})

    @app.get("/api/images/{job_id}/{image_name}")
    async def get_image(job_id: str, image_name: str):
        images_dir = job_manager.get_work_dir(job_id) / "output" / "images"
        image_path = images_dir / image_name
        if not image_path.exists():
            for p in job_manager.get_work_dir(job_id).rglob(image_name):
                image_path = p
                break
        if not image_path.exists():
            raise HTTPException(404, "Image not found")
        return FileResponse(image_path)

    @app.get("/api/download/{job_id}")
    async def download(job_id: str):
        import zipfile
        import io

        result = job_manager.get_result(job_id)
        if result is None or result.output_dir is None:
            raise HTTPException(404, "Result not found")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for md_file in result.output_dir.glob("*.md"):
                zf.write(md_file, md_file.name)
            images_dir = result.output_dir / "images"
            if images_dir.exists():
                for img in images_dir.glob("*.*"):
                    zf.write(img, f"images/{img.name}")

        buf.seek(0)
        return FileResponse(
            buf,
            media_type="application/zip",
            filename=f"{job_id}_inkdrop.zip"
        )

    return app
```

## After: Run tests and commit

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_api.py -v`
Expected: PASS

Commit:
```powershell
git add -A
git commit -m "feat: add FastAPI app with upload, status, preview, download routes"
```

## Interfaces
- **Consumes:** `JobManager` from `inkdrop.jobs` (Task 4)
- **Consumes:** `convert` from `inkdrop.converter` (Task 2)
- **Produces:** `create_app(job_manager?) -> FastAPI` factory function
- **Produces:** HTML templates for frontend

## Global Constraints
- `create_app()` must accept an optional `JobManager` for testing
- 50MB file size limit
- Do NOT modify existing files
