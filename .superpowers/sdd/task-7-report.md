# Task 7 Report: Allure test reporting setup

## Status: DONE

## What was done

1. Created `pytest.ini` with allure config (`--alluredir=allure-results --clean-alluredir`, `asyncio_mode = auto`)
2. Created `tests/test_smoke.py` with end-to-end `test_full_flow_pdf` (upload -> poll -> preview -> download)
3. Fixed bug in `inkdrop/app.py` `/api/download` endpoint: `FileResponse` with `BytesIO` fails because Starlette expects a file path. Switched to `StreamingResponse` with `Content-Disposition` header.
4. All 18 tests pass, `allure-results/` directory generated.
5. Committed as `bff06b7`.

## Test output

```
============================= test session starts ==============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
plugins: allure-pytest-2.13.5, anyio-4.14.2, asyncio-1.4.0
collected 18 items

tests/test_api.py::test_index_page PASSED
tests/test_api.py::test_upload_pdf PASSED
tests/test_api.py::test_get_status PASSED
tests/test_api.py::test_unsupported_format PASSED
tests/test_converter.py::test_convert_returns_result PASSED
tests/test_converter.py::test_convert_creates_markdown_file PASSED
tests/test_jobs.py::test_create_job PASSED
tests/test_jobs.py::test_job_progress PASSED
tests/test_jobs.py::test_job_completion PASSED
tests/test_jobs.py::test_job_failure PASSED
tests/test_quality.py::test_check_quality_returns_report PASSED
tests/test_quality.py::test_quality_good_structure PASSED
tests/test_quality.py::test_quality_broken_heading_hierarchy PASSED
tests/test_quality.py::test_quality_detects_tables PASSED
tests/test_quality.py::test_quality_detects_garbled PASSED
tests/test_quality.py::test_quality_empty PASSED
tests/test_quality.py::test_quality_images PASSED
tests/test_smoke.py::test_full_flow_pdf PASSED

======================= 18 passed, 1 warning in 32.66s =======================
```

## Bug found and fixed

- **File**: `inkdrop/app.py` `/api/download/{job_id}`
- **Issue**: `FileResponse(buf, ...)` where `buf` is `io.BytesIO` — Starlette's `FileResponse` calls `os.stat()` on the path and raises `TypeError: stat: path should be string, bytes, os.PathLike or integer, not BytesIO`
- **Fix**: Replaced with `StreamingResponse(iter([buf.getvalue()]), ...)` + `Content-Disposition` header for download filename
