"""v7_polish.py — MarkItDown GUI v7
v6 基础上 + config + argparse/logging + cancel + save-to-tool + open-folder + window-memory + PDF编码修复
"""
import argparse
import atexit
import base64
import json
import logging
import os
import re
import shutil
import subprocess
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

VERSION = "7.0.0"
APP_NAME = "markitdown-gui"

# --------------- config ---------------

_CONFIG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / APP_NAME
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_DEFAULT_CONFIG = {"pymupdf_accepted": None, "geometry": "", "debug_enabled": False}


def _load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = _DEFAULT_CONFIG | json.load(f)
                return cfg
    except Exception:
        pass
    return dict(_DEFAULT_CONFIG)


def _save_config(cfg: dict):
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


_config = _load_config()


def _config_get(key: str):
    return _config.get(key, _DEFAULT_CONFIG.get(key))


def _config_set(key: str, value):
    _config[key] = value
    _save_config(_config)


# --------------- logging ---------------

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
            _LOG_DIR / f"v7_{Path(sys.argv[0]).stem}.log",
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

# --------------- PyMuPDF lazy ---------------

_fitz = None


def _get_fitz():
    global _fitz
    if _fitz is None:
        import fitz as _f

        _fitz = _f
    return _fitz


# --------------- helpers ---------------

_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/\w+);base64,([A-Za-z0-9+/=]+)\)"
)


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


def _text_diff_ratio(a: str, b: str, sample_len: int = 2000) -> float:
    """两个文本的差异比例（0.0=完全相同, 1.0=完全不同）。
    用于对比 pdfplumber 和 PyMuPDF 的输出是否一致。"""
    sa = a[:sample_len] if len(a) > sample_len else a
    sb = b[:sample_len] if len(b) > sample_len else b
    if not sa or not sb:
        return 1.0

    # 去掉空白再比
    sa_clean = re.sub(r"\s+", "", sa)
    sb_clean = re.sub(r"\s+", "", sb)

    if not sa_clean or not sb_clean:
        return 1.0

    # 长度差异
    len_diff = abs(len(sa_clean) - len(sb_clean)) / max(len(sa_clean), len(sb_clean))

    # 字符级逐位比较
    min_len = min(len(sa_clean), len(sb_clean))
    char_diff = sum(1 for i in range(min_len) if sa_clean[i] != sb_clean[i]) / min_len

    # 综合：长度差异占 30%，字符差异占 70%
    return 0.3 * len_diff + 0.7 * char_diff


def _extract_images(markdown: str, images_dir: str) -> tuple[str, int]:
    """提取 base64 图片，存到 images_dir。返回 (新的 markdown, 图片数量)。"""
    count: dict[str, int] = {}

    def _replace(match):
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

        os.makedirs(images_dir, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(data))

        return f"![{alt}](images/{filename})"

    result = _DATA_URI_RE.sub(_replace, markdown)
    total = sum(count.values())
    return result, total


def _extract_pdf_images(pdf_path: str, images_dir: str) -> tuple[int, dict[int, list[str]]]:
    """用 PyMuPDF 提取 PDF 内嵌图片，存到 images_dir。无图片或无 fitz 返回 (0, {})。"""
    fitz = _get_fitz()
    if fitz is None:
        return 0, {}

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


def _extract_pdf_text_pymupdf(pdf_path: str) -> str:
    """用 PyMuPDF 按页提取文字，作为 pdfplumber 乱码时的后备。"""
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


def _get_output_root(filepath: str, save_to_tool: bool) -> str:
    """根据选项决定输出根目录。"""
    if save_to_tool:
        if getattr(sys, "frozen", False):
            tool_dir = os.path.dirname(sys.executable)
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
    folder = os.path.join(output_root, f"{base_name}_md")

    counter = 1
    while os.path.exists(folder):
        folder = os.path.join(output_root, f"{base_name}_md({counter})")
        counter += 1

    md_file = os.path.join(folder, f"{base_name}.md")
    images_dir = os.path.join(folder, "images")
    warning: str | None = None

    md = MarkItDown()
    result = md.convert(filepath, keep_data_uris=True)
    text, img_count = _extract_images(result.text_content, images_dir)

    ext = os.path.splitext(filepath)[1].lower()

    # PDF 专有：编码检查 + 内嵌图片
    if ext == ".pdf":
        # 用 PyMuPDF 再提取一次，对比差异
        pymupdf_text = _extract_pdf_text_pymupdf(filepath)
        if pymupdf_text:
            diff = _text_diff_ratio(text, pymupdf_text)
            garbled_a = _garbled_ratio(text)
            garbled_b = _garbled_ratio(pymupdf_text)
            _log.debug("PDF text diff=%.2f, garbled(pdfplumber)=%.2f, garbled(pymupdf)=%.2f",
                       diff, garbled_a, garbled_b)

            # 差异大 + PyMuPDF 更干净 → 用 PyMuPDF
            if diff > 0.3 and garbled_b < garbled_a:
                text = pymupdf_text
                warning = "文字已用备用引擎修正"
                _log.info("PyMuPDF text preferred (diff=%.2f)", diff)
            elif diff > 0.2:
                # 差异不算特别大，但也不小 → 保留原版但警告
                warning = "文字可能不准确，建议人工复查"
                _log.warning("Text differs between engines (diff=%.2f), keeping original", diff)

        pdf_img_count, page_images = _extract_pdf_images(filepath, images_dir)
        if pdf_img_count > 0:
            text += _build_pdf_images_section(page_images)
            img_count += pdf_img_count

    # 通用检测：输出是否异常短（去掉 markdown 标记后的纯文本长度）
    plain = re.sub(r"[#*\[\]()`!|\-><\n\r\t ]+", "", text)
    if len(plain) < 20:
        warning = _merge_warning(warning, "输出内容极少，可能转换失败")
        _log.warning("%s: very short output (%d chars)", filepath, len(plain))

    # PDF 专用：页数 vs 输出量
    if ext == ".pdf":
        try:
            fitz = _get_fitz()
            if fitz:
                doc = fitz.open(filepath)
                page_count = len(doc)
                doc.close()
                # 每页平均 < 30 个非空白字符 → 可疑
                if page_count > 0 and len(plain) / page_count < 30:
                    warning = _merge_warning(warning,
                                             f"{page_count} 页仅产出 {len(plain)} 字符，建议复查")
                    _log.warning("%s: low text density (%d chars / %d pages)", filepath, len(plain), page_count)
        except Exception:
            pass

    os.makedirs(folder, exist_ok=True)
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(text)

    return True, folder, img_count, warning


def _merge_warning(existing: str | None, new: str) -> str:
    if existing:
        return f"{existing}; {new}"
    return new


# --------------- UI ---------------

class MarkItDownApp:
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.file_paths: list[str] = []
        self.running = False
        self.cancel_event = threading.Event()
        self._result_folders: list[str] = []  # 本次转换成功的文件夹，用于 Open All

        self.root.title(f"MarkItDown 转换器 v{VERSION}")
        self.root.resizable(True, True)
        self.root.minsize(520, 400)
        self._restore_or_center(650, 520)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._setup_drag_drop()

        # Open Folder 点击绑定
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
                return
            except Exception:
                pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        _config_set("geometry", self.root.geometry())
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
            if os.path.isfile(p) and p not in self.file_paths:
                self.file_paths.append(p)
                added += 1
        if added:
            self._refresh_list()

    @staticmethod
    def _parse_drop_data(raw: str) -> list[str]:
        paths: list[str] = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                j = raw.find("}", i + 1)
                if j == -1:
                    break
                paths.append(raw[i + 1:j])
                i = j + 1
            else:
                i += 1
        if not paths:
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
        paths = filedialog.askopenfilenames(
            title="选择要转换的文件",
            filetypes=[
                (
                    "Supported files",
                    "*.pdf *.docx *.pptx *.xlsx *.xls *.html *.csv *.json "
                    "*.xml *.txt *.jpg *.png *.gif *.bmp *.tiff *.eml *.msg "
                    "*.epub *.zip",
                ),
                ("All files", "*.*"),
            ],
        )
        added = 0
        for p in paths:
            if os.path.isfile(p) and p not in self.file_paths:
                self.file_paths.append(p)
                added += 1
        if added:
            self._refresh_list()

    def _remove_selected(self):
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
        """设置窗口：查看/修改 PyMuPDF 开关。"""
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        dw, dh = 420, 260
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dw) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")

        pad = {"padx": 16, "pady": 6}
        section_pad = {"padx": 16, "pady": (10, 4)}

        # ---- PyMuPDF ----
        ttk.Label(dialog, text="PDF 图片提取 (PyMuPDF):",
                  font=("", 9, "bold")).pack(anchor=tk.W, **section_pad)
        enabled = _config_get("pymupdf_accepted") is True
        status = "已启用" if enabled else "已禁用"
        self._pymupdf_status_var = tk.StringVar(value=f"状态: {status}")
        ttk.Label(dialog, textvariable=self._pymupdf_status_var).pack(anchor=tk.W, padx=24)

        pymupdf_btn_frame = ttk.Frame(dialog)
        pymupdf_btn_frame.pack(fill=tk.X, padx=16, pady=(4, 10))

        def toggle_pymupdf():
            currently = _config_get("pymupdf_accepted") is True
            if currently:
                _config_set("pymupdf_accepted", False)
                self._pymupdf_status_var.set("状态: 已禁用")
                pymupdf_toggle_btn.config(text="启用")
            else:
                choice = messagebox.askyesno(
                    "可选组件: PyMuPDF",
                    "PyMuPDF (AGPL-3.0) 用于提取 PDF 内嵌图片。\n\n"
                    "如果你的使用场景符合 AGPL-3.0 许可要求，点击\"是\"启用。\n"
                    "点击\"否\"取消。",
                    detail="是否启用 PyMuPDF？",
                    icon="question",
                    parent=dialog,
                )
                if choice:
                    _config_set("pymupdf_accepted", True)
                    self._pymupdf_status_var.set("状态: 已启用")
                    pymupdf_toggle_btn.config(text="禁用")
                    try:
                        _get_fitz()
                    except Exception:
                        pass

        pymupdf_toggle_btn = ttk.Button(
            pymupdf_btn_frame, text="禁用" if enabled else "启用", command=toggle_pymupdf,
            width=8
        )
        pymupdf_toggle_btn.pack(side=tk.LEFT, padx=(0, 8))

        # ---- Debug ----
        ttk.Label(dialog, text="调试日志 (警告和错误始终记录):",
                  font=("", 9, "bold")).pack(anchor=tk.W, **section_pad)
        debug_enabled = _config_get("debug_enabled") is True
        self._debug_status_var = tk.StringVar(
            value=f"状态: {'已开启' if debug_enabled else '已关闭'}"
            + (f"\n日志目录: {_LOG_DIR}" if debug_enabled else "")
        )
        ttk.Label(dialog, textvariable=self._debug_status_var).pack(anchor=tk.W, padx=24)

        debug_frame = ttk.Frame(dialog)
        debug_frame.pack(fill=tk.X, padx=16, pady=(4, 10))

        def toggle_debug():
            currently = _config_get("debug_enabled") is True
            _config_set("debug_enabled", not currently)
            if not currently:
                # 开启 debug → 降文件 handler 到 DEBUG
                for h in _log.handlers:
                    if isinstance(h, logging.FileHandler):
                        h.setLevel(logging.DEBUG)
                _log.setLevel(logging.DEBUG)
                self._debug_status_var.set(f"状态: 已开启\n日志目录: {_LOG_DIR}")
                debug_toggle_btn.config(text="关闭")
            else:
                # 关闭 debug → 文件 handler 升回 WARNING（不删！）
                for h in _log.handlers:
                    if isinstance(h, logging.FileHandler):
                        h.setLevel(logging.WARNING)
                _log.setLevel(logging.INFO)
                self._debug_status_var.set("状态: 已关闭 (警告和错误仍会记录)")
                debug_toggle_btn.config(text="开启")

        debug_toggle_btn = ttk.Button(
            debug_frame, text="关闭" if debug_enabled else "开启", command=toggle_debug,
            width=8
        )
        debug_toggle_btn.pack(side=tk.LEFT, padx=(0, 8))

        def open_log_dir():
            if not _LOG_DIR.exists():
                _LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(_LOG_DIR))

        ttk.Button(debug_frame, text="打开日志目录", command=open_log_dir).pack(
            side=tk.LEFT, padx=4
        )

        # ---- 关闭 ----
        ttk.Button(dialog, text="关闭", command=dialog.destroy).pack(pady=(8, 8))

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
                self._result_folders.append(info)
                msg = f"✓  {filename}  →  {os.path.basename(info)}"
                if img_count:
                    msg += f"  ({img_count} 张图片)"
                if warning:
                    warn_count += 1
                    msg += f"  — {warning}"
                    self.root.after(0, self._append_result, msg, "warn", folder=info)
                else:
                    ok_count += 1
                    self.root.after(0, self._append_result, msg, "ok", folder=info)
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

    def _on_all_done(self, done: int, total: int, cancelled: bool):
        self.running = False
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


# --------------- main ---------------

HEADLESS_VERSION = "7.0.0"


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

    if args.convert:
        # headless 模式
        _log.debug("headless mode, %d file(s)", len(args.convert))
        _headless_convert(args.convert, args.save_to_tool)
        return

    # GUI 模式
    _show_pymupdf_dialog()

    root = TkinterDnD.Tk()
    MarkItDownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
