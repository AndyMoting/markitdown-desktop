"""PDF engine abstraction — currently PyMuPDF (AGPL-3.0).

Thin wrapper around PyMuPDF for text extraction and embedded image extraction.
To swap engines, replace the bodies of open_pdf / extract_text / extract_images.
"""

import logging
import os

_log = logging.getLogger("markitdown-gui")
_fitz = None


def _get_fitz():
    """Lazy import fitz. Returns module, or None if not installed."""
    global _fitz
    if _fitz is None:
        try:
            import fitz as _f

            _fitz = _f
        except ImportError:
            _fitz = False  # sentinel: tried and failed
    return _fitz if _fitz is not False else None


def is_available() -> bool:
    """Check if PyMuPDF can be imported."""
    return _get_fitz() is not None


def open_pdf(pdf_path: str):
    """Open a PDF file and return the document object.

    Returns None if PyMuPDF is not available or the file cannot be opened.
    The caller should call .close() on the returned document when done.
    """
    fitz = _get_fitz()
    if fitz is None:
        return None
    return fitz.open(pdf_path)


def extract_text(pdf_path: str, doc=None) -> str:
    """Extract text from PDF page by page.

    Pass an already-open doc to reuse.  Returns empty string if the
    engine is unavailable.
    """
    fitz = _get_fitz()
    if fitz is None:
        return ""

    should_close = doc is None
    if doc is None:
        doc = fitz.open(pdf_path)

    pages: list[str] = []
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                pages.append(text)
    finally:
        if should_close:
            doc.close()

    return "\n\n".join(pages)


def extract_images(
    pdf_path: str, images_dir: str, doc=None
) -> tuple[int, dict[int, list[str]]]:
    """Extract embedded images from every page.

    Pass an already-open doc to reuse.  Images are written to *images_dir*
    with names like ``pdf_p01_i01.jpg``.  Returns (total_count, {page: [relpath]}).
    """
    fitz = _get_fitz()
    if fitz is None:
        return 0, {}

    should_close = doc is None
    if doc is None:
        doc = fitz.open(pdf_path)

    page_images: dict[int, list[str]] = {}
    total = 0
    seen_xref: set[int] = set()

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            if not image_list:
                continue

            page_imgs: list[str] = []
            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                if xref in seen_xref:
                    continue
                seen_xref.add(xref)
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    ext = base_image["ext"]
                    if ext == "jpeg":
                        ext = "jpg"

                    if not image_bytes:
                        _log.warning(
                            "PDF p%d 零字节图片 xref=%d，跳过", page_num + 1, xref
                        )
                        continue

                    filename = (
                        f"pdf_p{page_num + 1:02d}_i{img_idx + 1:02d}.{ext}"
                    )
                    filepath = os.path.join(images_dir, filename)

                    os.makedirs(images_dir, exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)

                    page_imgs.append(f"images/{filename}")
                    total += 1
                except Exception:
                    _log.warning(
                        "PDF p%d 图片 xref=%d 提取失败", page_num + 1, xref
                    )
                    continue

            if page_imgs:
                page_images[page_num + 1] = page_imgs
    finally:
        if should_close:
            doc.close()

    return total, page_images
