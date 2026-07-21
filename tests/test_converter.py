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
