"""Command-line interface for doc2md."""

import argparse
import logging
import os
import sys
import time

from doc2md.convert import convert_one

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

    from markitdown import MarkItDown
    md = MarkItDown()
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
            r = convert_one(fp, args.out, md=md, use_pymupdf=not args.no_pymupdf)
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
