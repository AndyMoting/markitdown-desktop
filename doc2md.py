"""Convert documents to Markdown via CLI. Zero GUI dependencies.

Usage:
    python doc2md.py file1.pdf file2.docx ...
    python doc2md.py --debug *.pptx
    python doc2md.py --out ./output/ *.pdf

Supports: PDF, DOC, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML, TXT,
          images, email, EPUB, ZIP
"""

import argparse
import base64
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path

# Fix Windows GBK encoding if needed
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_log = logging.getLogger("doc2md")

# ---- Lazy imports ----
_fitz = None
_aw = None


def _get_fitz():
    global _fitz
    if _fitz is None:
        try:
            import fitz as _f
            _fitz = _f
        except ImportError:
            _fitz = False
    return _fitz if _fitz is not False else None


def _get_aw():
    global _aw
    if _aw is None:
        try:
            import aspose.words_foss as _a
            _aw = _a
        except ImportError:
            _aw = False
    return _aw if _aw is not False else None


# ---- Config ----
_CONFIG = {"pymupdf_accepted": True}


# ---- Helpers ----
_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/[\w+]+);base64,([A-Za-z0-9+/=]+)\)"
)


def _extract_images(markdown: str, images_dir: str) -> tuple[str, int]:
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


def _garbled_ratio(text: str, sample_len: int = 2000) -> float:
    sample = text[:sample_len] if len(text) > sample_len else text
    if not sample:
        return 0.0
    bad = sum(
        1 for ch in sample
        if ord(ch) == 0xFFFD or 0x80 <= ord(ch) <= 0x9F or 0xE000 <= ord(ch) <= 0xF8FF
    )
    return bad / len(sample)


def _text_diff_ratio(a: str, b: str, sample_len: int = 4000) -> float:
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


# ---- PDF engine ----
def _pdf_extract_images(pdf_path: str, images_dir: str) -> tuple[int, dict]:
    fitz = _get_fitz()
    if fitz is None:
        return 0, {}
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
                        continue
                    filename = f"pdf_p{page_num + 1:02d}_i{img_idx + 1:02d}.{ext}"
                    filepath = os.path.join(images_dir, filename)
                    os.makedirs(images_dir, exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)
                    page_imgs.append(f"images/{filename}")
                    total += 1
                except Exception:
                    continue
            if page_imgs:
                page_images[page_num + 1] = page_imgs
    finally:
        doc.close()
    return total, page_images


def _pdf_extract_text(pdf_path: str) -> str:
    fitz = _get_fitz()
    if fitz is None:
        return ""
    doc = fitz.open(pdf_path)
    pages: list[str] = []
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                pages.append(text)
    finally:
        doc.close()
    return "\n\n".join(pages)


# ---- DOC engine ----
def _doc_to_docx(doc_path: str, work_dir: str) -> str | None:
    aw = _get_aw()
    if aw is None:
        return None
    doc_name = Path(doc_path).stem
    docx_path = os.path.join(work_dir, f"{doc_name}.docx")
    counter = 1
    while os.path.exists(docx_path):
        docx_path = os.path.join(work_dir, f"{doc_name}({counter}).docx")
        counter += 1
    try:
        doc = aw.Document(doc_path)
        doc.save(docx_path, aw.SaveFormat.DOCX)
        _log.debug(".doc -> .docx: %s", doc_path)
    except Exception as e:
        _log.warning("aspose failed to convert %s: %s", doc_path, e)
        try:
            os.remove(docx_path)
        except OSError:
            pass
        return None
    return docx_path


# ---- Core conversion ----
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


def convert_one(filepath: str, output_root: str | None = None) -> dict:
    """Convert a single file to Markdown.

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
        aw = _get_aw()
        if aw is None:
            return {"ok": False, "output_dir": "",
                    "image_count": 0, "warning": None,
                    "error": "aspose-words-foss not installed, cannot process .doc"}
        _log.debug("pre-convert .doc -> .docx")
        docx_temp = _doc_to_docx(filepath, folder)
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
    try:
        md = MarkItDown()
        result = md.convert(source_path, keep_data_uris=True)
        text, img_count = _extract_images(result.text_content or "", images_dir)
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
    if ext == ".pdf" and _CONFIG["pymupdf_accepted"]:
        fitz = _get_fitz()
        if fitz is not None:
            fitz_doc = fitz.open(filepath)
            try:
                pymupdf_text = _pdf_extract_text(filepath)
                if pymupdf_text:
                    diff = _text_diff_ratio(text, pymupdf_text)
                    garbled_a = _garbled_ratio(text)
                    garbled_b = _garbled_ratio(pymupdf_text)
                    _log.debug("PDF diff=%.2f garbled(plumber)=%.2f garbled(pymupdf)=%.2f",
                               diff, garbled_a, garbled_b)
                    if diff > 0.3 and garbled_b < garbled_a:
                        text = pymupdf_text
                        warning = "文字已用备用引擎修正"
                pdf_img_count, page_images = _pdf_extract_images(filepath, images_dir)
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


# ---- CLI ----
def main():
    parser = argparse.ArgumentParser(
        prog="doc2md",
        description="Convert documents to Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  doc2md report.pdf
  doc2md --out ./output/ a.docx b.pptx
  doc2md --debug *.pdf

Supports: PDF, DOC, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML, TXT
Requires: markitdown pdfplumber PyMuPDF aspose-words-foss (pip install)
""")
    parser.add_argument("files", nargs="+", help="Files to convert")
    parser.add_argument("--out", "-o", help="Output root directory (default: source file directory)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-pymupdf", action="store_true", help="Disable PyMuPDF PDF processing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.no_pymupdf:
        _CONFIG["pymupdf_accepted"] = False

    ok = warn = fail = 0
    t0_total = time.time()
    for fp in args.files:
        if not os.path.isfile(fp):
            print(f"[FAIL]  {fp}  —  file not found")
            fail += 1
            continue
        print(f"-> {os.path.basename(fp)} ...", flush=True)
        t0 = time.time()
        try:
            r = convert_one(fp, args.out)
            elapsed = time.time() - t0
            if r["ok"]:
                msg = f"[OK]  {r['output_dir']}"
                if r["image_count"]:
                    msg += f" ({r['image_count']} images)"
                if r["warning"]:
                    warn += 1
                    msg += f"  — {r['warning']}"
                    print(msg)
                else:
                    ok += 1
                    print(msg)
                _log.debug("%s -> %s (%.1fs)", fp, r["output_dir"], elapsed)
            else:
                fail += 1
                print(f"[FAIL]  {fp}  —  {r['error']}")
        except Exception:
            fail += 1
            _log.exception("Unexpected error: %s", fp)
            print(f"[FAIL]  {fp}  —  unexpected error, see log")

    elapsed_total = time.time() - t0_total
    parts = [f"{ok} ok"]
    if warn:
        parts.append(f"{warn} warning")
    if fail:
        parts.append(f"{fail} failed")
    print(f"\nDone: {', '.join(parts)} ({elapsed_total:.1f}s)")


if __name__ == "__main__":
    main()
