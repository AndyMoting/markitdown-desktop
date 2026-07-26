"""Core conversion pipeline: one input file -> one Markdown output folder."""

import logging
import os
import re

from doc2md.engines import doc as doc_engine
from doc2md.engines import pdf as pdf_engine
from doc2md.images import extract_images
from doc2md.quality import garbled_ratio, text_diff_ratio

_log = logging.getLogger("doc2md")


def _make_output_dir(output_root: str, base_name: str) -> str:
    folder = os.path.join(output_root, f"{base_name}_md")
    counter = 1
    while True:
        try:
            os.makedirs(folder, exist_ok=False)
            return folder
        except FileExistsError:
            folder = os.path.join(output_root, f"{base_name}_md({counter})")
            counter += 1


def convert_one(filepath: str, output_root: str | None = None,
                md=None, use_pymupdf: bool = True) -> dict:
    """Convert a single file to Markdown.

    Pass a pre-created MarkItDown() instance as *md* to reuse across files.
    Set *use_pymupdf* to False to skip PDF text correction and embedded
    image extraction.
    Returns dict with keys: ok, output_dir, image_count, warning, error
    """
    from markitdown import MarkItDown

    if output_root is None:
        output_root = os.path.dirname(filepath)

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    folder = _make_output_dir(output_root, base_name)
    md_file = os.path.join(folder, f"{base_name}.md")
    images_dir = os.path.join(folder, "images")
    ext = os.path.splitext(filepath)[1].lower()
    warning: str | None = None
    docx_temp: str | None = None
    source_path = filepath

    # .doc -> .docx
    if ext == ".doc":
        if not doc_engine.is_available():
            return {"ok": False, "output_dir": "",
                    "image_count": 0, "warning": None,
                    "error": "aspose-words-foss not installed, cannot process .doc"}
        _log.debug("pre-convert .doc -> .docx")
        docx_temp = doc_engine.doc_to_docx(filepath, work_dir=folder)
        if docx_temp is None:
            return {"ok": False, "output_dir": "",
                    "image_count": 0, "warning": None,
                    "error": ".doc -> .docx conversion failed"}
        source_path = docx_temp

    # .ppt not supported
    if ext == ".ppt":
        return {"ok": False, "output_dir": "",
                "image_count": 0, "warning": None,
                "error": "旧版 PowerPoint (.ppt) 不支持。请用 PowerPoint 另存为 .pptx 后重试。"}

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
        return {"ok": False, "output_dir": "",
                "image_count": 0, "warning": None, "error": str(e)}

    # cleanup temp
    if docx_temp:
        try:
            os.remove(docx_temp)
        except OSError:
            pass

    # PDF post-processing
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

    return {"ok": True, "output_dir": folder, "image_count": img_count, "warning": warning, "error": None}
