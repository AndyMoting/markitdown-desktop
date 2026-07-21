# InkDrop 2.0 — Fix Report

**Date:** 2026-07-21
**Issues fixed:** C1, C2, C3, I2, I3

## Summary

| ID | Issue | File | Status |
|---|---|---|---|
| C1 | Path traversal in upload filename | `inkdrop/app.py:62` | Fixed |
| C2 | XSS fragility in markdown preview | `inkdrop/templates/preview.html:22` | Fixed |
| C3 | Missing 60s conversion timeout | `inkdrop/jobs.py:convert_job` | Fixed |
| I2 | HTMX polling race condition | `inkdrop/templates/preview.html:9-14` | Comment added |
| I3 | Windows-incompatible default tmp_root | `inkdrop/jobs.py:38` | Fixed |

## Changes

### C1 — Path traversal (`inkdrop/app.py`)
- Added `Path(file.filename).name` to strip path components
- Fallback to `"upload.bin"` if sanitized name is empty

### C2 — XSS hardening (`inkdrop/templates/preview.html`)
- Added `|e` (escape) filter to `{{ job.result.markdown | truncate(500) | e }}`
- Explicit escaping future-proofs against changes to Jinja2 auto-escape behavior

### C3 — Conversion timeout (`inkdrop/jobs.py`)
- Wrapped `loop.run_in_executor` with `asyncio.wait_for(..., timeout=60.0)`
- Added `asyncio.TimeoutError` handler calling `fail_job` with descriptive message

### I2 — HTMX polling race (`inkdrop/templates/preview.html`)
- Added comment explaining the intentional design: polling stops naturally when the progress bar div is replaced by the full result HTML

### I3 — Default tmp_root (`inkdrop/jobs.py`)
- Changed default from `"/tmp/inkdrop"` to `None`
- Uses `tempfile.mkdtemp(prefix="inkdrop_")` when no path is provided
- Compatible with all platforms (Windows, Linux, macOS)

## Test Results

```
19 passed, 11 warnings in 32.68s
```

All 19 existing tests continue to pass. No regressions introduced.
