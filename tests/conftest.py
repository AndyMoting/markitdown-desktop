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
    pdf = tmp_dir / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf content")
    return pdf
