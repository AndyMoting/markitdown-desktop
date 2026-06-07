"""DOC engine abstraction — currently aspose-words-foss (MIT).

Thin wrapper around aspose-words-foss for converting legacy .doc (OLE2)
files to .docx so markitdown can process them through its DOCX pipeline.

To swap engines, replace the bodies of is_available / doc_to_docx.
"""

import logging
import os
import tempfile
from pathlib import Path

_log = logging.getLogger("markitdown-gui")
_aw = None


def _get_aw():
    """Lazy import aspose.words_foss. Returns module, or None if not installed."""
    global _aw
    if _aw is None:
        try:
            import aspose.words_foss as _a

            _aw = _a
        except ImportError:
            _aw = False  # sentinel: tried and failed
    return _aw if _aw is not False else None


def is_available() -> bool:
    """Check if aspose-words-foss can be imported."""
    return _get_aw() is not None


def doc_to_docx(doc_path: str, work_dir: str | None = None) -> str | None:
    """Convert a legacy .doc file to .docx.

    Returns the path to the temporary .docx file, or None on failure.
    The caller owns the returned file — delete it when done.

    If *work_dir* is given, the temporary .docx is created there instead
    of the system temp directory.
    """
    aw = _get_aw()
    if aw is None:
        return None

    doc_name = Path(doc_path).stem
    tmp_dir = work_dir or tempfile.mkdtemp(prefix="doc_engine_")
    docx_path = os.path.join(tmp_dir, f"{doc_name}.docx")

    # Handle filename collisions
    counter = 1
    while os.path.exists(docx_path):
        docx_path = os.path.join(tmp_dir, f"{doc_name}({counter}).docx")
        counter += 1

    try:
        doc = aw.Document(doc_path)
        doc.save(docx_path, aw.SaveFormat.DOCX)
        _log.debug("doc(%s) -> docx(%s)", doc_path, docx_path)
    except Exception:
        _log.warning("aspose-words-foss failed to convert %s", doc_path, exc_info=True)
        # clean up on failure
        try:
            os.remove(docx_path)
        except OSError:
            pass
        return None

    return docx_path
