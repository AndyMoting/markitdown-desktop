"""Text-quality heuristics for choosing between extraction engines,
plus a Markdown quality report for the GUI preview panel."""

import re
from dataclasses import dataclass


def garbled_ratio(text: str, sample_len: int = 2000) -> float:
    """Fraction of replacement/control/private-use characters in a sample."""
    sample = text[:sample_len] if len(text) > sample_len else text
    if not sample:
        return 0.0
    bad = sum(
        1 for ch in sample
        if ord(ch) == 0xFFFD or 0x80 <= ord(ch) <= 0x9F or 0xE000 <= ord(ch) <= 0xF8FF
    )
    return bad / len(sample)


def text_diff_ratio(a: str, b: str, sample_len: int = 4000) -> float:
    """Rough dissimilarity of two extractions: 0.0 identical, 1.0 disjoint."""
    sa = a[:sample_len] if len(a) > sample_len else a
    sb = b[:sample_len] if len(b) > sample_len else b
    if not sa or not sb:
        return 1.0
    sa_clean = re.sub(r"\s+", "", sa)
    sb_clean = re.sub(r"\s+", "", sb)
    if not sa_clean or not sb_clean:
        return 1.0
    max_len = max(len(sa_clean), len(sb_clean))
    min_len = min(len(sa_clean), len(sb_clean))
    len_diff = (max_len - min_len) / max_len if max_len else 0
    set_a = set(sa_clean)
    set_b = set(sb_clean)
    union = set_a | set_b
    intersection = set_a & set_b
    set_diff = 1.0 - (len(intersection) / len(union)) if union else 0.0
    return 0.4 * len_diff + 0.6 * set_diff


@dataclass
class QualityReport:
    score: int  # 0-100
    heading_structure_ok: bool
    table_count: int
    image_count: int
    garbled_detected: bool


_GARBLED_RE = re.compile(r"�|[\x80-\x9f]")
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
    image_count = len(_IMAGE_RE.findall(markdown))

    garbled_detected = bool(_GARBLED_RE.search(markdown))

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
        return True
    prev_level = 0
    for h in headings:
        level = len(h)
        if level > prev_level + 1:
            return False
        prev_level = level
    return True
