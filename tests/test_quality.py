"""Tests for inkdrop.quality module."""
from inkdrop.quality import check_quality, QualityReport


def test_check_quality_returns_report():
    md = "# Title\n\nSome content\n\n## Section\n\nMore content"
    report = check_quality(md)
    assert isinstance(report, QualityReport)


def test_quality_good_structure():
    md = "# Title\n\nParagraph\n\n## Section\n\nText\n\n### Subsection\n\nEnd"
    report = check_quality(md)
    assert report.heading_structure_ok is True
    assert report.score >= 50


def test_quality_broken_heading_hierarchy():
    md = "# Title\n\nText\n\n### Skipped level\n\nMore text"
    report = check_quality(md)
    assert report.heading_structure_ok is False


def test_quality_detects_tables():
    md = "# Title\n\n| Col1 | Col2 |\n|------|------|\n| A    | B    |"
    report = check_quality(md)
    assert report.table_count >= 1


def test_quality_detects_garbled():
    md = "Lorem ipsum " + "\ufffd" * 50 + " dolor sit amet"
    report = check_quality(md)
    assert report.garbled_detected is True


def test_quality_empty():
    report = check_quality("")
    assert report.score == 0


def test_quality_images():
    md = "![img1](images/a.png)\n\n![img2](images/b.jpg)"
    report = check_quality(md)
    assert report.image_count == 2
