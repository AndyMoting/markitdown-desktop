"""Quality analysis for converted Markdown."""

import re
from dataclasses import dataclass


@dataclass
class QualityReport:
    score: int  # 0-100
    heading_structure_ok: bool
    table_count: int
    image_count: int
    garbled_detected: bool


_GARBLED_RE = re.compile(r"\ufffd|[\x80-\x9f]")
_HEADING_RE = re.compile(r"^(#{1,6})\s", re.MULTILINE)
_TABLE_RE = re.compile(r"^\|.*\|$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def check_quality(markdown: str) -> QualityReport:
    """Analyze converted markdown quality.

    Checks heading hierarchy, table count, image count,
    and detects garbled characters.
    """
    if not markdown or not markdown.strip():
        return QualityReport(
            score=0,
            heading_structure_ok=False,
            table_count=0,
            image_count=0,
            garbled_detected=False,
        )

    headings = _HEADING_RE.findall(markdown)
    heading_structure_ok = _check_heading_hierarchy(headings)

    table_count = len(_TABLE_RE.findall(markdown))
    images = _IMAGE_RE.findall(markdown)
    image_count = len(images)

    garbled_detected = bool(_GARBLED_RE.search(markdown))

    # Score calculation
    score = 50  # base

    if heading_structure_ok:
        score += 20
    else:
        score -= 10

    if table_count > 0:
        score += 10

    if image_count > 0:
        score += 10

    if garbled_detected:
        score -= 30

    # Bonus for content length
    text_len = len(re.sub(r"[#*\[\]()`!|><\n\r\t ]+", "", markdown))
    if text_len > 500:
        score += 10
    elif text_len < 20:
        score -= 20

    score = max(0, min(100, score))

    return QualityReport(
        score=score,
        heading_structure_ok=heading_structure_ok,
        table_count=table_count,
        image_count=image_count,
        garbled_detected=garbled_detected,
    )


def _check_heading_hierarchy(headings: list[str]) -> bool:
    """Check if heading levels are sequential (no skipping)."""
    if not headings:
        return True  # No headings = no structural problem

    prev_level = 0
    for h in headings:
        level = len(h)
        if level > prev_level + 1:
            return False  # Skipped a level (e.g., h1 -> h3)
        prev_level = level

    return True
