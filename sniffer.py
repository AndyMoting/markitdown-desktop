"""magika API shim backed by filetype (19 KB, zero deps).

Replaces magika.Magika().identify_stream() using magic-number detection.
MarkItDown only calls Magika() and identify_stream(), so we only need to
mock those two interfaces.

Saves ~42 MB in PyInstaller builds (magika + onnxruntime + flatbuffers +
protobuf).
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import BinaryIO, List

try:
    import filetype
except ImportError:
    import sys
    print(
        "错误: 缺少 filetype 库。markitdown 依赖的文件类型检测组件未安装。\n"
        "请运行: pip install filetype",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# magika-compatible return types
# ---------------------------------------------------------------------------

class Status(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class ContentTypeLabel:
    """Enum-like label.  MarkItDown compares to the string "unknown"."""
    value: str

    def __hash__(self):
        return hash(self.value)

    def __eq__(self, other):
        if isinstance(other, ContentTypeLabel):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"ContentTypeLabel.{self.value}"


@dataclass(frozen=True)
class ContentTypeInfo:
    label: ContentTypeLabel
    mime_type: str
    extensions: List[str]
    is_text: bool


@dataclass(frozen=True)
class MagikaPrediction:
    output: ContentTypeInfo


@dataclass(frozen=True)
class MagikaResult:
    status: Status
    prediction: MagikaPrediction


# ---------------------------------------------------------------------------
# MIME / extension lookup for filetype-only formats
# ---------------------------------------------------------------------------

_EXT_TO_MIME = {
    ".html": "text/html",
    ".htm": "text/html",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".txt": "text/plain",
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".log": "text/plain",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "application/toml",
    ".rst": "text/x-rst",
}


def _guess_from_path(file_stream) -> tuple[str, str, bool]:
    """Try to infer type from the file_stream's .name attribute."""
    name = getattr(file_stream, "name", "")
    ext = os.path.splitext(name)[1].lower()
    if ext:
        mime = _EXT_TO_MIME.get(ext)
        if mime:
            return ext.lstrip("."), mime, mime.startswith("text/") or mime in (
                "application/json", "application/xml", "message/rfc822",
                "application/toml")
    return "", "", False


# ---------------------------------------------------------------------------
# Magika replacement
# ---------------------------------------------------------------------------

class Magika:
    """Drop-in replacement for magika.Magika().

    Uses filetype (magic numbers) for binary formats; falls back to
    file-extension heuristics for text formats.
    """

    def __init__(self, model_path: str | None = None):
        pass  # filetype needs no model

    def identify_stream(self, file_stream: BinaryIO) -> MagikaResult:
        cur = file_stream.tell()
        try:
            ft = filetype.guess(file_stream)
        except Exception:
            ft = None
        finally:
            try:
                file_stream.seek(cur)
            except OSError:
                pass  # upstream seek(0) will handle it

        if ft is not None and ft.extension:
            return MagikaResult(
                status=Status.OK,
                prediction=MagikaPrediction(
                    output=ContentTypeInfo(
                        label=ContentTypeLabel(ft.extension),
                        mime_type=ft.mime,
                        extensions=[ft.extension],
                        is_text=ft.mime.startswith("text/") if ft.mime else False,
                    )
                ),
            )

        # Not a recognised binary type — try the filename
        ext, mime, is_text = _guess_from_path(file_stream)
        if ext:
            return MagikaResult(
                status=Status.OK,
                prediction=MagikaPrediction(
                    output=ContentTypeInfo(
                        label=ContentTypeLabel(ext),
                        mime_type=mime,
                        extensions=[ext],
                        is_text=is_text,
                    )
                ),
            )

        return MagikaResult(
            status=Status.OK,
            prediction=MagikaPrediction(
                output=ContentTypeInfo(
                    label=ContentTypeLabel("unknown"),
                    mime_type="application/octet-stream",
                    extensions=[],
                    is_text=False,
                )
            ),
        )
