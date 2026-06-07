r"""MarkItDown GUI v9 — 文档转 Markdown 桌面工具

功能: 拖拽/批量文档 → Markdown + 图片提取 → 输出文件夹
支持: PDF/DOCX/PPTX/XLSX/XLS/HTML/CSV/JSON/XML/TXT/图片/邮件/ZIP
入口: python v9_clean.py [--help|--version|--debug|--convert FILE...]

=== 代码导航 ===
  1. config      配置读写 (%APPDATA%\markitdown-gui\)
  2. logging     日志 (WARNING+ 写文件, --debug 看全量)
  3. PyMuPDF     懒加载 (AGPL-3.0, 需用户同意)
  4. 编码检测    乱码检测 + 双引擎对比
  5. 图片提取    base64 图片 + PDF 内嵌图片
  6. 转换核心    _convert_one — 单文件转换入口
  7. UI          MarkItDownApp — tkinter 界面
  8. CLI/入口    argparse + headless + GUI 启动
"""

import argparse
import base64
import ctypes
import json
import logging
import os
import re
import shlex
import shutil
import sys
import textwrap
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import TkinterDnD

from markitdown import MarkItDown

VERSION = "9.0.0"
APP_NAME = "markitdown-gui"

# ============================================================
#  1. config  配置读写
# ============================================================

_CONFIG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / APP_NAME
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_DEFAULT_CONFIG = {"pymupdf_accepted": None, "geometry": "", "debug_enabled": False}


def _load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if not isinstance(raw, dict):
                    _log.warning("config.json 不是有效的 JSON 对象，将使用默认配置")
                    return dict(_DEFAULT_CONFIG)
                cfg = _DEFAULT_CONFIG | raw
                return cfg
    except json.JSONDecodeError:
        _log.warning("config.json 已损坏，将使用默认配置")
    except PermissionError:
        _log.warning("没有权限读取 config.json，将使用默认配置")
    except OSError as e:
        _log.warning("读取 config.json 失败 (%s)，将使用默认配置", e)
    except Exception:
        _log.warning("加载配置时发生未知错误，将使用默认配置", exc_info=True)
    return dict(_DEFAULT_CONFIG)


def _save_config(cfg: dict) -> bool:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except PermissionError:
        _log.error("没有权限写入 config.json (%s)", _CONFIG_FILE)
    except OSError as e:
        _log.error("写入 config.json 失败 (%s): %s", _CONFIG_FILE, e)
    except Exception:
        _log.error("保存配置时发生未知错误", exc_info=True)
    return False


_config = _load_config()


def _config_get(key: str):
    return _config.get(key, _DEFAULT_CONFIG.get(key))


def _config_set(key: str, value) -> bool:
    _config[key] = value
    return _save_config(_config)


# ============================================================
#  2. logging  日志系统 (文件常驻 WARNING+, --debug 降级全量)
# ============================================================

_LOG_DIR = Path(os.environ.get("TEMP", os.path.expanduser("~"))) / APP_NAME

_log = logging.getLogger(APP_NAME)


def _setup_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    _log.setLevel(level)

    if not _log.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        # stderr —— DEBUG 时才显示（GUI 用户看不到 stderr）
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.WARNING)
        sh.setFormatter(fmt)
        _log.addHandler(sh)

        # 文件 —— **始终写**，至少 WARNING 以上
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        # 清理旧日志，保留最近 10 个
        old = sorted(_LOG_DIR.glob("*.log"), key=os.path.getmtime)
        for f in old[:-9]:
            try:
                f.unlink()
            except Exception:
                pass
        fh = logging.FileHandler(
            _LOG_DIR / f"v9_{Path(sys.argv[0]).stem}.log",
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG if debug else logging.WARNING)
        fh.setFormatter(fmt)
        _log.addHandler(fh)

    # 只控制文件 handler 的级别
    else:
        for h in _log.handlers:
            if isinstance(h, logging.FileHandler):
                h.setLevel(logging.DEBUG if debug else logging.WARNING)
        _log.setLevel(logging.DEBUG if debug else logging.INFO)

    if debug:
        _log.debug("Python %s on %s", sys.version, sys.platform)
        _log.debug("cwd: %s", os.getcwd())
        _log.debug("args: %s", sys.argv)

# ============================================================
#  3. PyMuPDF  懒加载 (AGPL-3.0, 需 _config_get("pymupdf_accepted") is True)
# ============================================================

_fitz = None


def _get_fitz():
    """懒加载 fitz。未启用 PyMuPDF 时返回 None。"""
    global _fitz
    if _config_get("pymupdf_accepted") is not True:
        return None
    if _fitz is None:
        import fitz as _f

        _fitz = _f
    return _fitz


# ============================================================
#  4. 编码检测  _garbled_ratio / _text_diff_ratio
# ============================================================


def _garbled_ratio(text: str, sample_len: int = 2000) -> float:
    """检测文本异常比例。>0.2 视为可能有问题。"""
    sample = text[:sample_len] if len(text) > sample_len else text
    if not sample:
        return 0.0
    bad = 0
    for ch in sample:
        cp = ord(ch)
        # U+FFFD / C1 control / private use
        if cp == 0xFFFD or 0x80 <= cp <= 0x9F or 0xE000 <= cp <= 0xF8FF:
            bad += 1
    return bad / len(sample)


def _text_diff_ratio(a: str, b: str, sample_len: int = 4000) -> float:
    """两个文本的差异比例（0.0=完全相同, 1.0=完全不同）。
    使用字符集重叠率 + 长度比衡量差异，避免逐位对齐的缺陷。
    """
    sa = a[:sample_len] if len(a) > sample_len else a
    sb = b[:sample_len] if len(b) > sample_len else b
    if not sa or not sb:
        return 1.0

    sa_clean = re.sub(r"\s+", "", sa)
    sb_clean = re.sub(r"\s+", "", sb)
    if not sa_clean or not sb_clean:
        return 1.0

    # 长度差异 (0~1)
    max_len = max(len(sa_clean), len(sb_clean))
    min_len = min(len(sa_clean), len(sb_clean))
    len_diff = (max_len - min_len) / max_len

    # 字符集交集差异 (0~1): 两个输出的独有字符集有多大
    set_a = set(sa_clean)
    set_b = set(sb_clean)
    union = set_a | set_b
    intersection = set_a & set_b
    set_diff = 1.0 - (len(intersection) / len(union)) if union else 0.0

    # 综合：长度差异 40% + 字符集差异 60%
    return 0.4 * len_diff + 0.6 * set_diff


# ============================================================
#  5. 图片提取  base64 图片 + PDF 内嵌图片
# ============================================================

_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/\w+);base64,([A-Za-z0-9+/=]+)\)"
)


def _extract_images(markdown: str, images_dir: str) -> tuple[str, int]:
    """提取 base64 图片，存到 images_dir。返回 (新的 markdown, 图片数量)。"""
    count: dict[str, int] = {}
    skipped = 0

    def _replace(match):
        nonlocal skipped
        alt = match.group(1) or "image"
        mime = match.group(2)
        data = match.group(3)

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
            _log.warning("base64 解码失败，跳过图片 %s", filename)
            skipped += 1
            return f"![{alt}](broken:{filename})"

        if not decoded:
            _log.warning("零字节图片，跳过 %s", filename)
            skipped += 1
            return f"![{alt}](empty:{filename})"

        os.makedirs(images_dir, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(decoded)

        return f"![{alt}](images/{filename})"

    result = _DATA_URI_RE.sub(_replace, markdown)
    total = sum(count.values())
    if skipped:
        _log.warning("共跳过 %d 张损坏/空图片", skipped)
    return result, total


def _extract_pdf_images(pdf_path: str, images_dir: str,
                       doc=None) -> tuple[int, dict[int, list[str]]]:
    """用 PyMuPDF 提取 PDF 内嵌图片，存到 images_dir。无图片或无 fitz 返回 (0, {})。
    可传入已打开的 doc 以复用。"""
    fitz = _get_fitz()
    if fitz is None:
        return 0, {}

    should_close = doc is None
    if doc is None:
        doc = fitz.open(pdf_path)

    page_images: dict[int, list[str]] = {}
    total = 0

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            if not image_list:
                continue

            page_imgs: list[str] = []
            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    ext = base_image["ext"]
                    if ext == "jpeg":
                        ext = "jpg"

                    if not image_bytes:
                        _log.warning("PDF p%d 零字节图片 xref=%d，跳过", page_num + 1, xref)
                        continue

                    filename = f"pdf_p{page_num + 1:02d}_i{img_idx + 1:02d}.{ext}"
                    filepath = os.path.join(images_dir, filename)

                    os.makedirs(images_dir, exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)

                    page_imgs.append(f"images/{filename}")
                    total += 1
                except Exception:
                    _log.warning("PDF p%d 图片 xref=%d 提取失败", page_num + 1, xref)
                    continue

            if page_imgs:
                page_images[page_num + 1] = page_imgs
    finally:
        if should_close:
            doc.close()

    return total, page_images


def _extract_pdf_text_pymupdf(pdf_path: str, doc=None) -> str:
    """用 PyMuPDF 按页提取文字，作为 pdfplumber 乱码时的后备。
    可传入已打开的 doc 以复用。"""
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


def _build_pdf_images_section(page_images: dict[int, list[str]]) -> str:
    """构建 markdown 段落，列出从 PDF 提取的内嵌图片。"""
    lines = [
        "",
        "---",
        "",
        "## PDF 内嵌图片",
        "",
        f"_从 PDF 提取了 {sum(len(v) for v in page_images.values())} 张图片。_",
        "",
    ]
    for page_num in sorted(page_images):
        lines.append(f"### 第 {page_num} 页")
        lines.append("")
        for img_path in page_images[page_num]:
            filename = os.path.basename(img_path)
            lines.append(f"![{filename}]({img_path})")
            lines.append("")

    return "\n".join(lines)


# ============================================================
#  6. 转换核心  _get_output_root / _convert_one / _merge_warning
# ============================================================


def _get_output_root(filepath: str, save_to_tool: bool) -> str:
    """根据选项决定输出根目录。"""
    if save_to_tool:
        if getattr(sys, "frozen", False):
            # frozen 模式下 exe 目录可能不可写（Program Files），用 APPDATA
            tool_dir = os.path.join(
                os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME
            )
        else:
            tool_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(tool_dir, "output")
    return os.path.dirname(filepath)


def _convert_one(
    filepath: str, save_to_tool: bool
) -> tuple[bool, str, int, str | None]:
    """转换单个文件。返回 (成功?, 输出文件夹, 图片数量, 警告信息)。"""
    output_root = _get_output_root(filepath, save_to_tool)
    base_name = os.path.splitext(os.path.basename(filepath))[0]

    # 原子化创建输出文件夹（避免 TOCTOU 竞态）
    folder = os.path.join(output_root, f"{base_name}_md")
    counter = 1
    while True:
        try:
            os.makedirs(folder, exist_ok=False)
            break
        except FileExistsError:
            folder = os.path.join(output_root, f"{base_name}_md({counter})")
            counter += 1

    md_file = os.path.join(folder, f"{base_name}.md")
    images_dir = os.path.join(folder, "images")
    warning: str | None = None

    md = MarkItDown()
    result = md.convert(filepath, keep_data_uris=True)
    text, img_count = _extract_images(result.text_content, images_dir)

    ext = os.path.splitext(filepath)[1].lower()

    # PDF 专有：编码检查 + 内嵌图片（仅在 PyMuPDF 启用时）
    if ext == ".pdf" and _config_get("pymupdf_accepted") is True:
        # 打开 fitz doc 一次，复用
        fitz = _get_fitz()
        fitz_doc = None
        if fitz:
            try:
                fitz_doc = fitz.open(filepath)
            except Exception:
                _log.warning("无法打开 PDF: %s", filepath)

        if fitz_doc:
            try:
                # 文字对比
                pymupdf_text = _extract_pdf_text_pymupdf(filepath, doc=fitz_doc)
                if pymupdf_text:
                    diff = _text_diff_ratio(text, pymupdf_text)
                    garbled_a = _garbled_ratio(text)
                    garbled_b = _garbled_ratio(pymupdf_text)
                    _log.debug("PDF text diff=%.2f, garbled(pdfplumber)=%.2f, garbled(pymupdf)=%.2f",
                               diff, garbled_a, garbled_b)

                    if diff > 0.3 and garbled_b < garbled_a:
                        text = pymupdf_text
                        warning = "文字已用备用引擎修正"
                        _log.info("PyMuPDF text preferred (diff=%.2f)", diff)
                    elif diff > 0.2:
                        warning = "文字可能不准确，建议人工复查"
                        _log.warning("Text differs between engines (diff=%.2f), keeping original", diff)

                # 内嵌图片
                pdf_img_count, page_images = _extract_pdf_images(
                    filepath, images_dir, doc=fitz_doc)
                if pdf_img_count > 0:
                    text += _build_pdf_images_section(page_images)
                    img_count += pdf_img_count

                # 页数 vs 输出量
                page_count = len(fitz_doc)
                # 去掉 markdown 标记的纯文本
                plain = re.sub(r"[#*\[\]()`!|><\n\r\t ]+", "", text)
                if page_count > 0 and len(plain) < max(20, page_count * 30):
                    if len(plain) < 20:
                        warning = _merge_warning(warning, "输出内容极少，可能转换失败")
                        _log.warning("%s: very short output (%d chars)", filepath, len(plain))
                    elif len(plain) / page_count < 30:
                        warning = _merge_warning(warning,
                                                 f"{page_count} 页仅产出 {len(plain)} 字符，建议复查")
                        _log.warning("%s: low text density (%d chars / %d pages)",
                                     filepath, len(plain), page_count)
            finally:
                fitz_doc.close()
    else:
        # 非 PDF 或 PyMuPDF 未启用：仅做短输出检测
        plain = re.sub(r"[#*\[\]()`!|><\n\r\t ]+", "", text)
        if len(plain) < 20:
            warning = _merge_warning(warning, "输出内容极少，可能转换失败")
            _log.warning("%s: very short output (%d chars)", filepath, len(plain))

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(text)

    return True, folder, img_count, warning


def _merge_warning(existing: str | None, new: str) -> str:
    if existing:
        return f"{existing}; {new}"
    return new


# ============================================================
#  7. UI  MarkItDownApp — tkinter 主界面
# ============================================================

class MarkItDownApp:
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.file_paths: list[str] = []
        self.running = False
        self.cancel_event = threading.Event()
        self._result_folders: list[str] = []  # 本次转换成功的文件夹，用于 Open All

        self.root.title(f"MarkItDown 转换器 v{VERSION}")
        self.root.resizable(True, True)
        self.root.minsize(700, 560)
        self._restore_or_center(700, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._setup_drag_drop()
        self._setup_keyboard()

        # Open Folder 点击绑定（鼠标 + 键盘）
        self.results_text.tag_bind("open_folder", "<Button-1>", self._on_folder_click)
        self.results_text.tag_bind("open_folder", "<Enter>",
                                   lambda _: self.results_text.config(cursor="hand2"))
        self.results_text.tag_bind("open_folder", "<Leave>",
                                   lambda _: self.results_text.config(cursor=""))

    def _restore_or_center(self, w: int, h: int):
        saved = _config_get("geometry")
        if saved:
            try:
                self.root.geometry(saved)
                self.root.update_idletasks()
                cw = self.root.winfo_width()
                ch = self.root.winfo_height()
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                if cw > 0 and ch > 0 and cw <= sw and ch <= sh:
                    return
            except Exception:
                pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        if self.root.state() != "zoomed":
            _config_set("geometry", self.root.geometry())
        else:
            _config_set("geometry", "")
        self.root.destroy()

    # ------ 拖拽 (tkinterdnd2) ------

    def _setup_drag_drop(self):
        self.root.drop_target_register("*")
        self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        raw = event.data
        paths = self._parse_drop_data(raw)
        added = 0
        for p in paths:
            if os.path.isdir(p):
                # 拖入文件夹 → 递归展开添加其中的文件
                for root_dir, _, files in os.walk(p):
                    for fname in files:
                        fpath = os.path.join(root_dir, fname)
                        if fpath not in self.file_paths:
                            self.file_paths.append(fpath)
                            added += 1
            elif os.path.isfile(p) and p not in self.file_paths:
                self.file_paths.append(p)
                added += 1
        if added:
            self._refresh_list()

    def _setup_keyboard(self):
        """键盘快捷键。"""
        self.root.bind("<Return>", lambda _: self._on_convert_click())
        self._listbox.bind("<Delete>", lambda _: self._remove_selected())

    @staticmethod
    def _parse_drop_data(raw: str) -> list[str]:
        """解析拖放数据。Windows 上格式为 {path1} {path2} ..."""
        paths: list[str] = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                j = raw.find("}", i + 1)
                if j == -1:
                    break
                path = raw[i + 1:j]
                if path:
                    paths.append(path)
                i = j + 1
            else:
                i += 1
        if not paths:
            # 后备：用 shlex 解析（处理含空格的路径）
            try:
                paths = shlex.split(raw)
            except ValueError:
                paths = raw.split()
        return paths

    # ------ UI 构建 ------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        # ===== 文件列表 =====
        list_frame = ttk.LabelFrame(self.root, text="文件列表")
        list_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self._listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._listbox.drop_target_register("*")
        self._listbox.dnd_bind("<<Drop>>", self._on_drop)

        list_scroll = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self._listbox.yview
        )
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.config(yscrollcommand=list_scroll.set)

        # ===== 按钮栏 =====
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, **pad)

        ttk.Button(btn_frame, text="添加文件", command=self._add_files).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(btn_frame, text="移除所选", command=self._remove_selected).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_frame, text="清空列表", command=self._clear_all).pack(
            side=tk.LEFT, padx=4
        )

        self.save_to_tool_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            btn_frame,
            text="保存到工具目录",
            variable=self.save_to_tool_var,
        ).pack(side=tk.LEFT, padx=12)

        ttk.Button(btn_frame, text="设置", command=self._open_settings).pack(
            side=tk.RIGHT, padx=(4, 0)
        )

        # ===== 转换 / 取消按钮 =====
        self.convert_btn = ttk.Button(
            self.root, text="转换 0 个文件", command=self._on_convert_click, width=22
        )
        self.convert_btn.pack(pady=(6, 2))

        # ===== 进度条 =====
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill=tk.X, **pad)

        self.progress_bar = ttk.Progressbar(
            progress_frame, mode="determinate", length=400
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.progress_var = tk.StringVar(value="0 / 0")
        ttk.Label(progress_frame, textvariable=self.progress_var, width=10).pack(
            side=tk.RIGHT
        )

        # ===== 结果区域 =====
        result_frame = ttk.LabelFrame(self.root, text="转换结果")
        result_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self.results_text = tk.Text(
            result_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        result_scroll = ttk.Scrollbar(
            result_frame, orient=tk.VERTICAL, command=self.results_text.yview
        )
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_text.config(yscrollcommand=result_scroll.set)

        self.results_text.tag_config("ok", foreground="green", underline=True)
        self.results_text.tag_config("warn", foreground="#CC8800", underline=True)
        self.results_text.tag_config("fail", foreground="red")
        self.results_text.tag_config("progress", foreground="royalblue")
        self.results_text.tag_config("summary", foreground="black", font=("", 9, "bold"))

        # Open All 按钮（初始隐藏）
        self.open_all_btn = ttk.Button(
            self.root, text="打开所有文件夹", command=self._open_all_folders
        )

    # ------ 文件列表操作 ------

    def _add_files(self):
        if self.running:
            return
        paths = filedialog.askopenfilenames(
            title="选择要转换的文件",
            filetypes=[
                (
                    "支持的文件",
                    "*.pdf *.docx *.pptx *.xlsx *.xls *.html *.csv *.json "
                    "*.xml *.txt *.jpg *.png *.gif *.bmp *.tiff *.eml *.msg "
                    "*.epub *.zip",
                ),
                ("所有文件", "*.*"),
            ],
            parent=self.root,
        )
        added = 0
        for p in paths:
            if os.path.isfile(p) and p not in self.file_paths:
                self.file_paths.append(p)
                added += 1
        if added:
            self._refresh_list()

    def _remove_selected(self):
        if self.running:
            return
        indices = self._listbox.curselection()
        for i in reversed(indices):
            del self.file_paths[i]
        self._refresh_list()

    def _clear_all(self):
        if self.running:
            return
        self.file_paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for p in self.file_paths:
            self._listbox.insert(tk.END, os.path.basename(p))
        n = len(self.file_paths)
        self.convert_btn.config(
            text=f"转换 {n} 个文件" if n else "转换 0 个文件",
            state=tk.NORMAL if n else tk.DISABLED,
        )
        self.progress_bar.configure(value=0)
        self.progress_var.set(f"0 / {n}" if n else "0 / 0")
        self._clear_results()

    # ------ 结果区域 ------

    def _clear_results(self):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete("1.0", tk.END)
        self.results_text.config(state=tk.DISABLED)
        self.open_all_btn.pack_forget()
        self._result_folders.clear()

    def _append_result(self, text: str, tag: str, folder: str | None = None):
        self.results_text.config(state=tk.NORMAL)
        if folder:
            pos = self.results_text.index(tk.END).rstrip()
            self.results_text.insert(tk.END, text + "  ", tag)
            tag_name = f"folder_{len(self._result_folders)}"
            self.results_text.tag_config(tag_name, foreground="blue", underline=True)
            self.results_text.tag_bind(tag_name, "<Button-1>",
                                       lambda _, f=folder: os.startfile(f))
            self.results_text.tag_bind(tag_name, "<Enter>",
                                       lambda _: self.results_text.config(cursor="hand2"))
            self.results_text.tag_bind(tag_name, "<Leave>",
                                       lambda _: self.results_text.config(cursor=""))
            self.results_text.insert(tk.END, "[打开]", tag_name)
        else:
            self.results_text.insert(tk.END, text, tag)
        self.results_text.insert(tk.END, "\n")
        self.results_text.see(tk.END)
        self.results_text.config(state=tk.DISABLED)

    def _on_folder_click(self, event):
        """点击 open_folder tag 的行。"""
        index = self.results_text.index(f"@{event.x},{event.y}")
        tags = self.results_text.tag_names(index)
        for t in tags:
            if t.startswith("folder_"):
                idx = int(t.split("_")[1])
                if idx < len(self._result_folders):
                    os.startfile(self._result_folders[idx])
                return

    def _open_all_folders(self):
        for folder in self._result_folders:
            if os.path.isdir(folder):
                os.startfile(folder)

    # ------ Settings ------

    def _open_settings(self):
        """设置窗口：查看/修改 PyMuPDF 开关、调试日志。"""
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        body = ttk.Frame(dialog, padding=(24, 16, 24, 0))
        body.pack(fill=tk.BOTH)
        body.columnconfigure(1, weight=1)

        r = 0

        # ===== PyMuPDF =====
        ttk.Label(body, text="PDF 图片提取 (PyMuPDF)",
                  font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 4)); r += 1

        enabled = _config_get("pymupdf_accepted") is True
        self._pymupdf_status_var = tk.StringVar(
            value=f"· {'已启用' if enabled else '已禁用'}")

        def toggle_pymupdf():
            currently = _config_get("pymupdf_accepted") is True
            if currently:
                if not _config_set("pymupdf_accepted", False):
                    messagebox.showerror("错误", "保存设置失败", parent=dialog)
                    return
                self._pymupdf_status_var.set("· 已禁用")
                pymupdf_toggle_btn.config(text="启用")
            else:
                choice = messagebox.askyesno(
                    "可选组件: PyMuPDF",
                    "PyMuPDF (AGPL-3.0) 用于提取 PDF 内嵌图片。\n\n"
                    "如果你的使用场景符合 AGPL-3.0 许可要求，点击\"是\"启用。\n"
                    "点击\"否\"取消。",
                    detail="是否启用 PyMuPDF？",
                    icon="question", parent=dialog)
                if choice:
                    if not _config_set("pymupdf_accepted", True):
                        messagebox.showerror("错误", "保存设置失败", parent=dialog)
                        return
                    self._pymupdf_status_var.set("· 已启用")
                    pymupdf_toggle_btn.config(text="禁用")
                    try:
                        _get_fitz()
                    except Exception:
                        pass

        ttk.Label(body, textvariable=self._pymupdf_status_var).grid(
            row=r, column=0, sticky=tk.W, padx=(8, 0))
        pymupdf_toggle_btn = ttk.Button(
            body, text="禁用" if enabled else "启用",
            command=toggle_pymupdf, width=6)
        pymupdf_toggle_btn.grid(row=r, column=1, sticky=tk.E, padx=(0, 8))
        r += 1

        # 分隔线
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=r, column=0, columnspan=2, sticky=tk.EW, pady=(10, 10))
        r += 1

        # ===== 调试日志 =====
        ttk.Label(body, text="调试日志",
                  font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 2)); r += 1

        ttk.Label(body, text="警告和错误始终记录",
                  foreground="gray", font=("", 8)).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 4), padx=(8, 0)); r += 1

        debug_enabled = _config_get("debug_enabled") is True
        self._debug_status_var = tk.StringVar(
            value=f"· {'已开启' if debug_enabled else '已关闭'}")

        def toggle_debug():
            currently = _config_get("debug_enabled") is True
            if not _config_set("debug_enabled", not currently):
                messagebox.showerror("错误", "保存设置失败", parent=dialog)
                return
            if not currently:
                for h in _log.handlers:
                    if isinstance(h, logging.FileHandler):
                        h.setLevel(logging.DEBUG)
                _log.setLevel(logging.DEBUG)
                self._debug_status_var.set("· 已开启")
                self._debug_path_var.set(f"日志目录: {_LOG_DIR}")
                debug_toggle_btn.config(text="关闭")
            else:
                for h in _log.handlers:
                    if isinstance(h, logging.FileHandler):
                        h.setLevel(logging.WARNING)
                _log.setLevel(logging.INFO)
                self._debug_status_var.set("· 已关闭")
                self._debug_path_var.set("")
                debug_toggle_btn.config(text="开启")

        ttk.Label(body, textvariable=self._debug_status_var).grid(
            row=r, column=0, sticky=tk.W, padx=(8, 0))
        debug_toggle_btn = ttk.Button(
            body, text="关闭" if debug_enabled else "开启",
            command=toggle_debug, width=6)
        debug_toggle_btn.grid(row=r, column=1, sticky=tk.E, padx=(0, 8))
        r += 1

        # 日志路径
        self._debug_path_var = tk.StringVar(
            value=f"日志目录: {_LOG_DIR}" if debug_enabled else "")
        self._debug_path_label = ttk.Label(
            body, textvariable=self._debug_path_var,
            foreground="gray", font=("", 8))
        self._debug_path_label.grid(
            row=r, column=0, columnspan=2, sticky=tk.W,
            padx=(8, 0), pady=(4, 2))
        r += 1

        # 按钮行
        actions = ttk.Frame(body)
        actions.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=(6, 2)); r += 1

        def open_log_dir():
            if not _LOG_DIR.exists():
                _LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(_LOG_DIR))

        ttk.Button(actions, text="打开日志目录",
                   command=open_log_dir).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="关闭", command=dialog.destroy,
                   width=8).pack(side=tk.RIGHT, padx=(0, 8))

        # 布局完成后自适应尺寸并居中
        dialog.update_idletasks()
        dh = dialog.winfo_reqheight()
        dw = max(dialog.winfo_reqwidth(), 420)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dw) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dh) // 2
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, min(x, sw - dw))
        y = max(0, min(y, sh - dh))
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")

    # ------ 转换 ------

    def _on_convert_click(self):
        if self.running:
            # Cancel
            self.cancel_event.set()
            self._append_result("正在取消...", "progress")
            return
        if not self.file_paths:
            return
        self._start_convert()

    def _start_convert(self):
        self.running = True
        self.cancel_event.clear()
        self.convert_btn.config(text="取消", state=tk.NORMAL)
        self._clear_results()

        total = len(self.file_paths)
        self.progress_bar.configure(maximum=total, value=0)
        self.progress_var.set(f"0 / {total}")

        thread = threading.Thread(
            target=self._convert_thread,
            args=(list(self.file_paths), self.save_to_tool_var.get()),
            daemon=False,
        )
        thread.start()

    def _convert_thread(self, file_paths: list[str], save_to_tool: bool):
        total = len(file_paths)
        ok_count = 0
        warn_count = 0
        fail_count = 0

        for i, fp in enumerate(file_paths):
            if self.cancel_event.is_set():
                done = i + 1
                self.root.after(0, self._append_result,
                                f"已取消 ({i}/{total})", "summary")
                self.root.after(0, self._on_all_done, done, total, cancelled=True)
                return

            filename = os.path.basename(fp)
            self.root.after(0, self._append_result, f"→ {filename} ...", "progress")

            t0 = time.time()
            try:
                success, info, img_count, warning = _convert_one(fp, save_to_tool)
                elapsed = time.time() - t0
                _log.debug("%s -> %s (%.1fs, %d images, warning=%s)",
                           filename, info, elapsed, img_count, warning)
            except Exception as e:
                elapsed = time.time() - t0
                _log.error("%s FAILED (%.1fs): %s\n%s", filename, elapsed, e,
                           traceback.format_exc())
                success, info, img_count, warning = False, str(e), 0, None

            if success:
                # 延迟到主线程：追加结果文件夹 + 写结果行
                self.root.after(0, self._on_one_success,
                                filename, info, img_count, warning)
                if warning:
                    warn_count += 1
                else:
                    ok_count += 1
            else:
                fail_count += 1
                self.root.after(0, self._append_result,
                                f"✗  {filename}  —  {info}", "fail")

            done = i + 1
            self.root.after(0, self._update_progress, done, total)

        parts = [f"{ok_count} 成功"]
        if warn_count:
            parts.append(f"{warn_count} 需复查")
        if fail_count:
            parts.append(f"{fail_count} 失败")
        summary = f"完成: {', '.join(parts)}"
        self.root.after(0, self._append_result, summary, "summary")
        if warn_count or fail_count:
            self.root.after(0, self._append_result,
                            "提示: 可在 设置 → 打开日志目录 查看详细诊断信息", "progress")
        self.root.after(0, self._on_all_done, total, total, cancelled=False)

    def _update_progress(self, done: int, total: int):
        self.progress_bar.configure(value=done)
        self.progress_var.set(f"{done} / {total}")

    def _on_one_success(self, filename: str, folder: str, img_count: int,
                        warning: str | None):
        """在主线程执行：追加结果文件夹 + 写结果行。"""
        self._result_folders.append(folder)
        msg = f"✓  {filename}  →  {os.path.basename(folder)}"
        if img_count:
            msg += f"  ({img_count} 张图片)"
        if warning:
            msg += f"  — {warning}"
            self._append_result(msg, "warn", folder=folder)
        else:
            self._append_result(msg, "ok", folder=folder)

    def _on_all_done(self, done: int, total: int, cancelled: bool):
        self.running = False
        self.progress_bar.configure(value=0)
        self.progress_var.set("0 / 0")
        n = len(self.file_paths)
        self.convert_btn.config(
            text=f"转换 {n} 个文件" if n else "转换 0 个文件",
            state=tk.NORMAL if n else tk.DISABLED,
        )
        if not cancelled and self._result_folders:
            self.open_all_btn.pack(pady=(0, 6))
            self._append_result(
                f"({len(self._result_folders)} 个文件夹就绪 — 点击 [打开] 或下方的按钮)",
                "progress")


# ============================================================
#  8. CLI 与入口  argparse / headless / GUI 启动
# ============================================================

HEADLESS_VERSION = "9.0.0"


def _headless_convert(file_paths: list[str], save_to_tool: bool):
    """命令行模式：转换文件并输出结果。"""
    ok, warn, fail = 0, 0, 0
    for fp in file_paths:
        print(f"→ {os.path.basename(fp)} ...", flush=True)
        t0 = time.time()
        try:
            success, folder, img_count, warning = _convert_one(fp, save_to_tool)
            elapsed = time.time() - t0
            if success:
                msg = f"  成功: {folder}"
                if img_count:
                    msg += f"  ({img_count} 张图片)"
                if warning:
                    warn += 1
                    msg += f"  — {warning}"
                    print(msg)
                else:
                    ok += 1
                    print(msg)
            else:
                fail += 1
                print(f"  失败: {folder}")
            _log.debug("%s -> %s (%.1fs)", fp, folder, elapsed)
        except Exception as e:
            fail += 1
            _log.error("%s FAILED: %s\n%s", fp, e, traceback.format_exc())
            print(f"  错误: {e}")
    print()
    parts = [f"{ok} 成功"]
    if warn:
        parts.append(f"{warn} 需复查")
    if fail:
        parts.append(f"{fail} 失败")
    print(f"完成: {', '.join(parts)}")


def _show_pymupdf_dialog():
    """PyMuPDF 许可证弹窗 — 仅首次启动。"""
    if _config_get("pymupdf_accepted") is not None:
        return

    # 弹窗前必须先有 root（哪怕不显示），否则 widget 创建报错
    root = tk.Tk()
    root.withdraw()
    choice = messagebox.askyesno(
        "可选组件: PyMuPDF",
        "PyMuPDF (AGPL-3.0) 用于提取 PDF 内嵌图片。\n\n"
        "如果你的使用场景符合 AGPL-3.0 许可要求，点击\"是\"启用。\n"
        "点击\"否\"跳过 — 其他功能不受影响。\n\n"
        "（此对话框仅显示一次）",
        detail="是否安装并启用 PyMuPDF？",
        icon="question",
    )
    root.destroy()
    _config_set("pymupdf_accepted", choice)
    if choice:
        _log.info("User enabled PyMuPDF")
        _get_fitz()
    else:
        _log.info("User skipped PyMuPDF")


def _parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="markitdown-gui",
        description="MarkItDown GUI — 将文档转换为 Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              markitdown-gui                        启动图形界面
              markitdown-gui --debug                启动图形界面并开启调试日志
              markitdown-gui --convert a.pdf b.docx  命令行模式
            """),
    )
    parser.add_argument("--version", action="version",
                        version=f"markitdown-gui v{VERSION}")
    parser.add_argument("--debug", action="store_true",
                        help="启用调试日志 (输出到 %%TEMP%%\\markitdown-gui\\)")
    parser.add_argument("--convert", nargs="+", metavar="FILE",
                        help="命令行模式: 转换文件后退出 (不启动 GUI)")
    parser.add_argument("--save-to-tool", action="store_true",
                        help="输出到工具目录而不是源文件目录")
    parser.add_argument("--reset", action="store_true",
                        help="重置所有设置 (config、PyMuPDF 选择)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = _parse_args(argv)

    if args.reset:
        try:
            shutil.rmtree(_CONFIG_DIR, ignore_errors=True)
            shutil.rmtree(_LOG_DIR, ignore_errors=True)
        except Exception:
            pass
        # 重载 config
        global _config
        _config = dict(_DEFAULT_CONFIG)
        if not args.debug and not args.convert:
            print("设置已重置，所有偏好已清除。")
            print("下次启动将重新显示 PyMuPDF 对话框。")
            return

    _setup_logging(args.debug or _config_get("debug_enabled"))

    # 高 DPI 支持 (Windows)
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    if args.convert:
        # 命令行模式
        _log.debug("命令行模式, %d 个文件", len(args.convert))
        _headless_convert(args.convert, args.save_to_tool)
        return

    # GUI 模式
    _show_pymupdf_dialog()

    root = TkinterDnD.Tk()
    MarkItDownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
