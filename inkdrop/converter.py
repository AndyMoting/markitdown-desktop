"""Core conversion: file -> Markdown + images + quality report.

Wraps the existing doc2md.convert_one() pipeline for library use.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from doc2md import convert_one

try:
    from inkdrop.quality import check_quality
except ImportError:
    check_quality = None  # type: ignore


@dataclass
class ConversionResult:
    markdown: str
    images: list[Path] = field(default_factory=list)
    quality: Optional[object] = None
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
        Path(result["output_dir"]) / f"{base_name}.md"
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

    # Write a copy at output_dir root for easy access
    if markdown:
        root_md = output_dir / f"{base_name}.md"
        root_md.write_text(markdown, encoding="utf-8")

    # Collect extracted images
    images = []
    images_dir = output_dir / "images"
    if images_dir.exists():
        images = sorted(images_dir.glob("*.*"))

    quality = check_quality(markdown) if check_quality else None

    return ConversionResult(
        markdown=markdown,
        images=images,
        quality=quality,
        warning=result.get("warning"),
        output_dir=Path(result["output_dir"]) if result["output_dir"] else None
    )
