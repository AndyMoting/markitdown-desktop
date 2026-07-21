# Task 1 Report

**Status:** DONE

## What I did

1. Appended web framework and testing dependencies to `requirements.txt`
2. Created `inkdrop/__init__.py` with version `2.0.0`
3. Created `inkdrop/engines/__init__.py` with docstring
4. Created `tests/__init__.py` (empty)
5. Created `tests/conftest.py` with `tmp_dir` and `sample_pdf` fixtures
6. Installed all dependencies via pip
7. Committed all changes

## Commands run

### pip install
```
D:\Projects\.venv\Scripts\pip.exe install -r D:\Projects\MD\markitdown-desktop\requirements.txt
```
Result: All packages installed successfully. New installs: fastapi-0.115.0, uvicorn-0.30.6, jinja2-3.1.4, python-multipart-0.0.9, httpx-0.27.2, pytest-8.3.3, allure-pytest-2.13.5, plus transitive dependencies (starlette, h11, httpcore, anyio, sniffio, attrs, pluggy, iniconfig, MarkupSafe, etc.).

### git commit
```
git add -A
git commit -m "chore: add web dependencies and project structure"
```
Result: `2921507` — 9 files changed, 1796 insertions.

## Issues

None.
