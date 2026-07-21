# Task 5 Report: FastAPI app + API routes

**Status:** DONE

## What I did

1. Wrote failing API test first (TDD) — `tests/test_api.py` with 4 test cases
2. Confirmed test fails with `ModuleNotFoundError: No module named 'inkdrop.app'`
3. Created `inkdrop/templates/` directory with `index.html` and `preview.html`
4. Created `inkdrop/static/` directory with `style.css`
5. Implemented `inkdrop/app.py` with `create_app()` factory function
6. All 4 tests pass
7. Committed as `1eaa755`

## Files created

- `inkdrop/app.py` — FastAPI app with routes: `/`, `/api/upload`, `/api/status/{job_id}`, `/api/preview/{job_id}`, `/api/images/{job_id}/{image_name}`, `/api/download/{job_id}`
- `inkdrop/templates/index.html` — Upload page with htmx drag-and-drop
- `inkdrop/templates/preview.html` — Job result preview with quality badge, progress bar, markdown preview, image gallery
- `inkdrop/static/style.css` — PicoCSS-compatible styles
- `tests/test_api.py` — 4 async API tests

## Test results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 4 items

markitdown-desktop/tests/test_api.py::test_index_page PASSED             [ 25%]
markitdown-desktop/tests/test_api.py::test_upload_pdf PASSED             [ 50%]
markitdown-desktop/tests/test_api.py::test_get_status PASSED             [ 75%]
markitdown-desktop/tests/test_api.py::test_unsupported_format PASSED     [100%]

======================== 4 passed, 3 warnings in 3.38s ========================
```

Warnings (non-blocking):
- Starlette `TemplateResponse` parameter order deprecation (code still works)
- pydub ffmpeg not found (unrelated to this task)

## Issues

None. All requirements met.
