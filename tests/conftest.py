"""Shared test fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory(prefix="inkdrop_test_") as d:
        yield Path(d)


@pytest.fixture
def sample_pdf(tmp_dir):
    """Create a minimal PDF. Disables PyMuPDF post-processing (synthetic PDFs can't survive it)."""
    import doc2md
    doc2md._CONFIG["pymupdf_accepted"] = False
    pdf = tmp_dir / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf content")
    return pdf
