"""Core conversion pipeline: one input (file or URL) -> one Markdown output folder."""

import logging
import os
import re
import shutil
from urllib.parse import urlparse

from doc2md.engines import doc as doc_engine
from doc2md.engines import pdf as pdf_engine
from doc2md.images import extract_images
from doc2md.quality import garbled_ratio, text_diff_ratio

_log = logging.getLogger("doc2md")

_URL_PREFIXES = ("http://", "https://")


def is_url(source: str) -> bool:
    return source.startswith(_URL_PREFIXES)


def output_base_name(source: str) -> str:
    """输出目录/文件的基名。本地文件取文件名去扩展; URL 取路径末段或域名。"""
    if is_url(source):
        parsed = urlparse(source)
        seg = os.path.splitext(parsed.path.rstrip("/").rsplit("/", 1)[-1])[0]
        name = seg or parsed.netloc or "page"
        return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_.") or "page"
    return os.path.splitext(os.path.basename(source))[0]


def _is_our_output(folder: str, base_name: str) -> bool:
    """护栏: 只把 '含 {base}.md 的目录' 或空目录认作我们的输出, 防误删用户目录。"""
    try:
        entries = os.listdir(folder)
    except OSError:
        return False
    if not entries:
        return True
    return f"{base_name}.md" in entries


def _make_output_dir(output_root: str, base_name: str,
                     on_conflict: str = "rename") -> str | None:
    """创建输出目录。返回路径; on_conflict='skip' 且已存在时返回 None。"""
    folder = os.path.join(output_root, f"{base_name}_md")

    if os.path.isdir(folder) and on_conflict in ("overwrite", "skip"):
        if _is_our_output(folder, base_name):
            if on_conflict == "skip":
                return None
            shutil.rmtree(folder, ignore_errors=True)
        else:
            _log.warning("%s 不像 doc2md 的输出, 回落为序号命名", folder)

    counter = 1
    while True:
        try:
            os.makedirs(folder, exist_ok=False)
            return folder
        except FileExistsError:
            folder = os.path.join(output_root, f"{base_name}_md({counter})")
            counter += 1


def _result(ok: bool, output_dir: str = "", image_count: int = 0,
            warning: str | None = None, error: str | None = None,
            skipped: bool = False) -> dict:
    return {"ok": ok, "output_dir": output_dir, "image_count": image_count,
            "warning": warning, "error": error, "skipped": skipped}


def convert_one(filepath: str, output_root: str | None = None,
                md=None, use_pymupdf: bool = True,
                on_conflict: str = "rename") -> dict:
    """Convert a single file or http(s) URL to Markdown.

    Pass a pre-created MarkItDown() instance as *md* to reuse across files.
    Set *use_pymupdf* to False to skip PDF text correction and embedded
    image extraction.
    *on_conflict* controls existing-output handling: "rename" (default,
    numbered suffix), "overwrite", or "skip".
    Returns dict with keys: ok, output_dir, image_count, warning, error,
    skipped.
    """
    from markitdown import MarkItDown

    source_is_url = is_url(filepath)

    if output_root is None:
        output_root = os.getcwd() if source_is_url else os.path.dirname(filepath)

    base_name = output_base_name(filepath)
    folder = _make_output_dir(output_root, base_name, on_conflict)
    if folder is None:
        existing = os.path.join(output_root, f"{base_name}_md")
        _log.info("skip existing output: %s", existing)
        return _result(True, existing, skipped=True)
    md_file = os.path.join(folder, f"{base_name}.md")
    images_dir = os.path.join(folder, "images")
    ext = "" if source_is_url else os.path.splitext(filepath)[1].lower()
    warning: str | None = None
    docx_temp: str | None = None
    source_path = filepath

    # .doc -> .docx
    if ext == ".doc":
        if not doc_engine.is_available():
            return _result(False,
                           error="aspose-words-foss not installed, "
                                 "cannot process .doc")
        _log.debug("pre-convert .doc -> .docx")
        docx_temp = doc_engine.doc_to_docx(filepath, work_dir=folder)
        if docx_temp is None:
            return _result(False, error=".doc -> .docx conversion failed")
        source_path = docx_temp

    # .ppt not supported
    if ext == ".ppt":
        return _result(False,
                       error="旧版 PowerPoint (.ppt) 不支持。"
                             "请用 PowerPoint 另存为 .pptx 后重试。")

    # markitdown
    if md is None:
        md = MarkItDown()
    try:
        result = md.convert(source_path, keep_data_uris=True)
        text, img_count = extract_images(result.text_content or "", images_dir)
    except Exception as e:
        _log.error("markitdown failed: %s — %s", filepath, e)
        if docx_temp:
            try:
                os.remove(docx_temp)
            except OSError:
                pass
        return _result(False, error=str(e))

    # cleanup temp
    if docx_temp:
        try:
            os.remove(docx_temp)
        except OSError:
            pass

    # PDF post-processing (仅本地 PDF; URL 源无本地文件可供 PyMuPDF 处理)
    fitz_doc = pdf_engine.open_pdf(filepath) if ext == ".pdf" and use_pymupdf else None
    if fitz_doc is not None:
        try:
            pymupdf_text = pdf_engine.extract_text(filepath, doc=fitz_doc)
            if pymupdf_text:
                diff = text_diff_ratio(text, pymupdf_text)
                garbled_a = garbled_ratio(text)
                garbled_b = garbled_ratio(pymupdf_text)
                _log.debug("PDF diff=%.2f garbled(plumber)=%.2f garbled(pymupdf)=%.2f",
                           diff, garbled_a, garbled_b)
                if diff > 0.3 and garbled_b < garbled_a:
                    text = pymupdf_text
                    warning = "文字已用备用引擎修正"
            pdf_img_count, page_images = pdf_engine.extract_images(
                filepath, images_dir, doc=fitz_doc)
            if pdf_img_count > 0:
                lines = ["", "---", "", "## PDF 内嵌图片", "",
                         f"_从 PDF 提取了 {pdf_img_count} 张图片。_", ""]
                for pn in sorted(page_images):
                    lines.append(f"### 第 {pn} 页")
                    lines.append("")
                    for img_path in page_images[pn]:
                        lines.append(f"![{os.path.basename(img_path)}]({img_path})")
                        lines.append("")
                text += "\n".join(lines)
                img_count += pdf_img_count
            page_count = len(fitz_doc)
            plain = re.sub(r"[#*\[\]()`!|><\n\r\t ]+", "", text)
            if page_count > 0 and len(plain) < max(20, page_count * 30):
                if len(plain) < 20:
                    warning = (warning + "; " if warning else "") + "输出内容极少，可能转换失败"
                elif len(plain) / page_count < 30:
                    warning = (warning + "; " if warning else "") + \
                        f"{page_count} 页仅产出 {len(plain)} 字符，建议复查"
        finally:
            fitz_doc.close()
    else:
        plain = re.sub(r"[#*\[\]()`!|><\n\r\t ]+", "", text)
        if len(plain) < 20:
            warning = "输出内容极少，可能转换失败"

    # Write output
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(text)

    return _result(True, folder, img_count, warning)
