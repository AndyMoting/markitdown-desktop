"""Extract base64 data-URI images from Markdown into real files."""

import base64
import logging
import os
import re

_log = logging.getLogger("doc2md")

_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/[\w+]+);base64,([A-Za-z0-9+/=]+)\)"
)


def extract_images(markdown: str, images_dir: str) -> tuple[str, int]:
    """Extract base64 images to files. Returns (new_markdown, image_count)."""
    os.makedirs(images_dir, exist_ok=True)
    count: dict[str, int] = {}
    skipped = 0

    def _replace(m: re.Match) -> str:
        nonlocal skipped
        alt = m.group(1) or "image"
        mime = m.group(2)
        data = m.group(3)
        ext = mime.split("/")[1]
        if ext == "jpeg":
            ext = "jpg"
        count[ext] = count.get(ext, 0) + 1
        n = count[ext]
        filename = f"img_{n:03d}.{ext}"
        filepath = os.path.join(images_dir, filename)
        try:
            decoded = base64.b64decode(data)
        except Exception:
            _log.warning("base64 decode failed, skip %s", filename)
            skipped += 1
            return f"![{alt}](broken:{filename})"
        if not decoded:
            _log.warning("zero-byte image, skip %s", filename)
            skipped += 1
            return f"![{alt}](empty:{filename})"
        try:
            with open(filepath, "wb") as f:
                f.write(decoded)
        except OSError as e:
            _log.warning("write failed %s: %s", filename, e)
            skipped += 1
            return f"![{alt}](broken:{filename})"
        return f"![{alt}](images/{filename})"

    result = _DATA_URI_RE.sub(_replace, markdown)
    if skipped:
        _log.warning("skipped %d broken/empty images", skipped)
    return result, sum(count.values())
