# Task 2: Converter module (refactor doc2md.py into library)

**Files to create:**
- `D:\Projects\MD\markitdown-desktop\inkdrop\converter.py`
- `D:\Projects\MD\markitdown-desktop\tests\test_converter.py`

## Pre-step: Write the failing test FIRST (TDD)

Create `tests/test_converter.py`:
```python
"""Tests for inkdrop.converter module."""
from pathlib import Path
from inkdrop.converter import convert, ConversionResult


def test_convert_returns_result(sample_pdf, tmp_dir):
    output_dir = tmp_dir / "output"
    result = convert(sample_pdf, output_dir)
    assert isinstance(result, ConversionResult)
    assert isinstance(result.markdown, str)
    assert isinstance(result.images, list)
    assert hasattr(result, 'quality')


def test_convert_creates_markdown_file(sample_pdf, tmp_dir):
    output_dir = tmp_dir / "output"
    result = convert(sample_pdf, output_dir)
    md_files = list(output_dir.glob("*.md"))
    assert len(md_files) >= 1
```

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_converter.py -v`
Expected: FAIL — ModuleNotFoundError: `inkdrop.converter`

## Step: Implement converter module

Create `inkdrop/converter.py`:
```python
"""Core conversion: file → Markdown + images + quality report.

Wraps the existing doc2md.convert_one() pipeline for library use.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from doc2md import convert_one
from inkdrop.quality import check_quality


@dataclass
class ConversionResult:
    markdown: str
    images: list[Path] = field(default_factory=list)
    quality: Optional["QualityReport"] = None
    warning: str | None = None
    error: str | None = None
    output_dir: Path | None = None


def convert(input_path: Path, output_dir: Path) -> ConversionResult:
    """Convert a document to Markdown.
    
    Args:
        input_path: Path to the source document
        output_dir: Directory for output (md + images)
    
    Returns:
        ConversionResult with markdown content, images, and quality report
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        return ConversionResult(
            markdown="",
            error=f"File not found: {input_path}"
        )

    ext = input_path.suffix.lower()
    if ext == ".ppt":
        return ConversionResult(
            markdown="",
            error="旧版 PowerPoint (.ppt) 不支持。请另存为 .pptx 后重试。"
        )

    result = convert_one(
        str(input_path),
        str(output_dir)
    )

    if not result["ok"]:
        return ConversionResult(
            markdown="",
            error=result.get("error", "Unknown error"),
            warning=result.get("warning")
        )

    # Read the generated markdown
    base_name = input_path.stem
    md_file = None
    for candidate in [
        output_dir / f"{base_name}_md" / f"{base_name}.md",
        result["output_dir"] / f"{base_name}.md"
    ]:
        if candidate.exists():
            md_file = candidate
            break

    # Find md by glob fallback
    if md_file is None:
        for md_candidate in output_dir.rglob("*.md"):
            md_file = md_candidate
            break

    markdown = md_file.read_text(encoding="utf-8") if md_file else ""

    # Collect extracted images
    images = []
    images_dir = output_dir / "images"
    if images_dir.exists():
        images = sorted(images_dir.glob("*.*"))

    quality = check_quality(markdown)

    return ConversionResult(
        markdown=markdown,
        images=images,
        quality=quality,
        warning=result.get("warning"),
        output_dir=Path(result["output_dir"]) if result["output_dir"] else None
    )
```

## After: Run tests and commit

Run: `D:\Projects\.venv\Scripts\pytest.exe D:\Projects\MD\markitdown-desktop\tests\test_converter.py -v`
Expected: PASS

Commit:
```powershell
git add -A
git commit -m "feat: add converter module wrapping doc2md pipeline"
```

## Interfaces
- **Consumes:** `convert_one` from `doc2md.py` (already exists at project root)
- **Consumes:** `check_quality` from `inkdrop.quality` (Task 3 will create this)
- **Produces:** `convert(input_path, output_dir) -> ConversionResult`
- **Produces:** `ConversionResult` dataclass

## Global Constraints
- Do NOT modify `doc2md.py` — import from it
- Do NOT modify existing engine files
- Python 3.12+ at `D:\Projects\.venv\Scripts\python.exe`

## Important
`inkdrop.quality` module doesn't exist yet. For now, import it lazily inside the function or you can write a minimal stub. The full quality module comes in Task 3. Use this pattern:

```python
try:
    from inkdrop.quality import check_quality
except ImportError:
    check_quality = None  # type: ignore
```

And guard the call:
```python
quality = check_quality(markdown) if check_quality else None
```

This way tests pass without Task 3 being done yet.
