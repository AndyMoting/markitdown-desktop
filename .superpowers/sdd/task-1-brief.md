# Task 1: Project structure + dependencies

**Files to modify:**
- `D:\Projects\MD\markitdown-desktop\requirements.txt`

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\inkdrop\__init__.py`
- `D:\Projects\MD\markitdown-desktop\inkdrop\engines\__init__.py`
- `D:\Projects\MD\markitdown-desktop\tests\__init__.py`
- `D:\Projects\MD\markitdown-desktop\tests\conftest.py`

## Steps

### Step 1: Add new dependencies to requirements.txt

Append the following to the end of requirements.txt:

```
# Web framework
fastapi==0.115.0
uvicorn==0.30.6
jinja2==3.1.4
python-multipart==0.0.9
httpx==0.27.2

# Testing
pytest==8.3.3
allure-pytest==2.13.5
```

### Step 2: Create package directories and files

Create `inkdrop/__init__.py`:
```python
"""InkDrop 2.0 — Feed documents to AI."""
__version__ = "2.0.0"
```

Create `inkdrop/engines/__init__.py`:
```python
"""Document conversion engines."""
```

Create `tests/__init__.py`: empty file

Create `tests/conftest.py`:
```python
"""Shared pytest fixtures."""
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="inkdrop_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_pdf(tmp_dir):
    """Create a minimal valid PDF file for testing."""
    pdf_path = tmp_dir / "sample.pdf"
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n453\n%%EOF"
    )
    pdf_path.write_bytes(pdf_content)
    return pdf_path
```

### Step 3: Install dependencies

Run in PowerShell:
```powershell
D:\Projects\.venv\Scripts\pip.exe install -r D:\Projects\MD\markitdown-desktop\requirements.txt
```
Expected: All packages installed successfully

### Step 4: Commit

```powershell
cd D:\Projects\MD\markitdown-desktop
git add -A
git commit -m "chore: add web dependencies and project structure"
```

## Global Constraints
- Python 3.12+ at `D:\Projects\.venv\Scripts\python.exe`
- Existing `doc2md.py`, `pdf_engine.py`, `doc_engine.py`, `sniffer.py` must be preserved as-is in root
- New code goes in `inkdrop/` package
