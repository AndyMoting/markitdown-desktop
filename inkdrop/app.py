"""FastAPI application for InkDrop."""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from starlette.responses import StreamingResponse
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
        return templates.TemplateResponse(request, "index.html")

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
            request, "preview.html", {"job": job_info}
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
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{job_id}_inkdrop.zip"'},
        )

    return app
