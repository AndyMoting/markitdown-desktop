# InkDrop 2.0 — Final Whole-Branch Review

**Reviewer:** opencode (automated)
**Date:** 2026-07-21
**Range:** `5bb8227..a4138fe` (9 commits, 16 new files, 1 modified)
**Tests:** 19/19 passing

---

## Overall Verdict: NEEDS_FIXES

Implementation is ~85% spec-complete with good architecture, but has **2 critical security issues** and **1 important missing spec requirement** that must be addressed before use.

---

## Critical (must fix before use)

### C1. Path traversal in upload filename — `inkdrop/app.py:62`

```python
input_path = work_dir / file.filename
input_path.write_bytes(content)
```

`file.filename` is attacker-controlled. A malicious client can send `filename=../../evil.exe` and write outside the intended work directory. This is a local-RCE-adjacent vulnerability on a local server.

**Recommendation:** Sanitize with `Path(file.filename).name` or generate a safe stem + preserve extension.

### C2. XSS via markdown rendering in `preview.html:22`

```html
{{ job.result.markdown | truncate(500) }}
```

Jinja2 auto-escapes `{{ }}` so this is *currently safe* for the plain-text preview, but the `hx-swap="none"` + outerHTML pattern at line 11 means the **already-rendered HTML from the server is trusted and inserted into the DOM**. If `markdown` ever gets pre-rendered to HTML (as spec says `/api/preview` should return "rendered HTML"), XSS becomes exploitable. The current design returns raw markdown in the preview template — this is inconsistent with the spec and fragile.

**Recommendation:** Clarify the data contract. If preview renders markdown→HTML server-side, it MUST be sanitized (e.g., bleach). If it stays raw markdown in template, ensure Jinja2 auto-escaping is retained (do not use `|safe`).

### C3. Missing conversion timeout — spec violation

Design doc requires "转换超时 60s". No timeout exists in `jobs.py:convert_job`. A malformed input can hang the thread pool indefinitely.

**Recommendation:** Wrap with `asyncio.wait_for` + 60s timeout, call `fail_job` on timeout.

---

## Important (should fix)

### I1. Memory leak in JobManager — `inkdrop/jobs.py:35`

`cleanup()` removes files from disk but only runs on completed jobs older than 5 min — and only removes the directory, **not the Job object from `_jobs`**. Over many sessions, the in-memory dict grows unbounded.

**Recommendation:** Also pop job from `_jobs` in cleanup (already done in line 106, but the cleanup loop at `app.py:41` is correct — verify this actually works under test. It does per `test_cleanup_removes_files`. **No issue.** Removing from list.)

### I2. HTMX progress polling race condition — `app.py:74` / `preview.html:9-14`

The `hx-on::after-request` handler swaps `outerHTML` of the progress bar. If status transitions from `processing` → `completed` between two polls, the returned HTML replaces the progress div with the full result, but the polling attribute (`hx-trigger="every 1s"`) is on the **replaced** element, so polling stops. This works by accident (completed template has no polling attribute), but if a future status re-introduces polling it will break.

**Recommendation:** Move the polling trigger to a parent wrapper that is never swapped, or use `hx-swap="delete"` on the progress bar when done.

### I3. `JobManager.__init__` default `tmp_root="/tmp/inkdrop"` — `jobs.py:38`

Breaks on Windows. The app overrides this via `tempfile.mkdtemp`, so it works today, but any other consumer (tests, `__main__`) will fail on Windows.

**Recommendation:** Default to `tempfile.mkdtemp(prefix="inkdrop_")` instead of hardcoded POSIX path.

### I4. Quality scoring threshold quirk — `quality.py:64-68`

Empty/very short markdown (< 20 chars) gets -20 penalty, but the garbled penalty (-30) is harsher than the "low content" penalty. A document with 19 chars of real text scores 30/100, while a 20-char garbled document scores 20/100. This inverts user expectations.

**Recommendation:** Reconsider relative weights. Short-but-valid content should not score lower than garbled content.

---

## Minor (nice-to-have)

### M1. `/api/source/{job_id}` route defined in spec but not implemented

Design doc table lists this route; implementation omits it. The preview endpoint returns markdown, so this may be redundant. Either implement or remove from spec.

### M2. PyMuPDF import not lazy in `pdf_engine.py`

Spec requires "保持 lazy-import 隔离". Existing `pdf_engine.py` was not modified (verified), so this is a pre-existing condition, not a regression. Noted for completeness.

### M3. No test for download endpoint content validity

`test_smoke.py` verifies `/api/download/{job_id}` returns 200 and non-empty, but doesn't validate the zip structure.

### M4. No test for 413 file-too-large path

50MB limit is enforced in `app.py:55` but not covered by tests.

### M5. `/api/preview/{job_id}` returns raw markdown, not rendered HTML

Spec table says "/api/preview → Markdown → HTML". Current implementation returns `{"markdown": "..."}` as JSON. Frontend doesn't use this endpoint (preview is rendered directly in `preview.html` via Jinja2). Dead code path.

### M6. Unused `import shutil` inside function scope — `jobs.py:102`

Move to module top-level for consistency with other imports.

---

## Spec Compliance Summary

| Requirement | Status |
|---|---|
| FastAPI backend with 6 routes | ✅ All present (`/`, `/api/upload`, `/api/status/{id}`, `/api/preview/{id}`, `/api/images/{id}/{name}`, `/api/download/{id}`) |
| Quality report (score, headings, tables, images, garbled) | ✅ |
| Background conversion with progress polling | ✅ |
| Image gallery with click-to-enlarge | ✅ |
| 50MB file size limit | ✅ Enforced |
| Temp file cleanup every 5 min | ✅ |
| PyMuPDF AGPL isolation | ✅ Unchanged (lazy import in pdf_engine.py) |
| HTMX frontend (no React/Vue) | ✅ |
| Existing files untouched | ✅ `git diff` empty |
| 60s conversion timeout | ❌ **Missing (C3)** |
| `/api/source/{job_id}` route | ❌ Missing (M1, minor) |
| `/api/preview` returns rendered HTML | ❌ Returns JSON instead (M5, minor) |

---

## Code Quality Notes

- **Architecture is clean**: separation into `converter.py`, `quality.py`, `jobs.py`, `app.py` is well done.
- **Factory pattern** in `create_app(job_manager=...)` enables testability — good design choice.
- **Type hints** present throughout, `dataclasses` for structured results.
- **Test coverage** is broad for unit level (converter, quality, jobs) but thin on endpoints (only 3 API tests, 1 cleanup test, 1 smoke test).
- **Test for `unsupported_format`** (test_api.py:66-76) is weak: only checks `job_id` returned, doesn't verify the job eventually fails.

---

## Recommendations (priority order)

1. **Fix path traversal (C1)** — sanitize `file.filename`
2. **Add 60s timeout (C3)** — `asyncio.wait_for` in `convert_job`
3. **Decide on preview HTML sanitization (C2)** — future-proof against XSS
4. **Fix default `tmp_root` (I3)** — use `tempfile.mkdtemp`
5. **Add 413 + download zip structure tests** (M3, M4)

After C1 and C3 are fixed, the implementation will be spec-sufficient and safe for local use.
