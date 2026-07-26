"""Text-quality heuristics for choosing between extraction engines."""

import re


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
