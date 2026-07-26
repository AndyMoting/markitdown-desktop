"""Command-line interface for doc2md."""

import argparse
import logging
import os
import sys
import time

from doc2md.convert import convert_one, is_url

_log = logging.getLogger("doc2md")


def main():
    # Fix Windows GBK encoding if needed
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="doc2md",
        description="Convert documents to Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  doc2md report.pdf
  doc2md --out ./output/ a.docx b.pptx
  doc2md https://example.com/post --out ./output/
  doc2md --on-conflict skip *.pdf

Supports: PDF, DOC, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML, TXT, http(s) URL
Requires: markitdown pdfplumber PyMuPDF aspose-words-foss (pip install)
""")
    parser.add_argument("files", nargs="+", help="Files or http(s) URLs to convert")
    parser.add_argument("--out", "-o", help="Output root directory (default: source file directory; URL 源默认当前目录)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-pymupdf", action="store_true", help="Disable PyMuPDF PDF processing")
    parser.add_argument("--on-conflict", choices=["rename", "overwrite", "skip"],
                        default="rename",
                        help="输出目录已存在时: rename 加序号(默认) / overwrite 覆盖 / skip 跳过")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from markitdown import MarkItDown
    md = MarkItDown()
    ok = warn = fail = skipped = 0
    t0_total = time.time()
    for fp in args.files:
        if not is_url(fp) and not os.path.isfile(fp):
            print(f"[FAIL]  {fp}  —  file not found")
            fail += 1
            continue
        label = fp if is_url(fp) else os.path.basename(fp)
        print(f"-> {label} ...", flush=True)
        t0 = time.time()
        try:
            r = convert_one(fp, args.out, md=md,
                            use_pymupdf=not args.no_pymupdf,
                            on_conflict=args.on_conflict)
            elapsed = time.time() - t0
            if r["skipped"]:
                skipped += 1
                print(f"[SKIP]  {r['output_dir']} already exists")
            elif r["ok"]:
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
    if skipped:
        parts.append(f"{skipped} skipped")
    if fail:
        parts.append(f"{fail} failed")
    print(f"\nDone: {', '.join(parts)} ({elapsed_total:.1f}s)")


if __name__ == "__main__":
    main()
