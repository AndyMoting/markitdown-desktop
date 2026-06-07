r"""InkDrop v14 — 文档转 Markdown 桌面工具

功能: 拖拽/批量文档 → Markdown + 图片提取 → 输出文件夹 · 自定义输出目录
支持: PDF/DOC/DOCX/PPTX/XLSX/XLS/HTML/CSV/JSON/XML/TXT/图片/邮件/ZIP
入口: python v14_custom_output.py [--help|--version|--debug|--convert FILE...]
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
import types as _types
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import NamedTuple

VERSION = "14.0.0"
APP_NAME = "inkdrop"

# 确保项目根目录在 sys.path 中 (sniffer/pdf_engine/doc_engine 都在那)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---- magika→filetype shim (省 42MB) ----
# 必须在 import markitdown 之前注入, 否则打包后 magika 被排除会崩。
# 升级 markitdown 后跑: rg "magika\." .venv/Lib/site-packages/markitdown --no-heading
# 如果输出只有 identify_stream, 安全。有新方法就补 sniffer.py。
import sniffer

sys.modules["magika"] = sniffer
for name in ("onnxruntime", "flatbuffers", "protobuf"):
    if name not in sys.modules:
        sys.modules[name] = _types.ModuleType(name)

_LOG = logging.getLogger(APP_NAME)

import pdf_engine
import doc_engine
from tkinterdnd2 import TkinterDnD
from markitdown import MarkItDown

# ============================================================
#  1. config  配置读写 (%APPDATA%\inkdrop\)
# ============================================================

_CONFIG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / APP_NAME
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_DEFAULT_CONFIG = {
    "pymupdf_accepted": None,
    "geometry": "",
    "debug_enabled": False,
    "output_dir": "",
}


def _load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if not isinstance(raw, dict):
                    _LOG.warning("config.json 格式不对, 用默认值")
                    return dict(_DEFAULT_CONFIG)
                return _DEFAULT_CONFIG | raw
    except json.JSONDecodeError:
        _LOG.warning("config.json 损坏, 用默认值")
    except PermissionError:
        _LOG.warning("没权限读 config.json, 用默认值")
    except OSError as e:
        _LOG.warning("读 config.json 失败 (%s), 用默认值", e)
    except Exception:
        _LOG.warning("加载配置时出错, 用默认值", exc_info=True)
    return dict(_DEFAULT_CONFIG)


def _save_config(cfg: dict) -> bool:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except PermissionError:
        _LOG.error("没权限写 config.json (%s)", _CONFIG_FILE)
    except OSError as e:
        _LOG.error("写 config.json 失败 (%s): %s", _CONFIG_FILE, e)
    except Exception:
        _LOG.error("保存配置时出错", exc_info=True)
    return False


_config = _load_config()


def _config_get(key: str):
    return _config.get(key, _DEFAULT_CONFIG.get(key))


def _config_set(key: str, value) -> bool:
    _config[key] = value
    return _save_config(_config)


# ============================================================
#  2. logging
# ============================================================

if getattr(sys, "frozen", False):
    _LOG_DIR = Path(sys.executable).parent / "logs"
else:
    _LOG_DIR = Path(__file__).resolve().parent / "logs"


def _init_logging(debug: bool):
    if _LOG.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)
    _LOG.addHandler(stderr_handler)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    cutoff = time.time() - 7 * 86400
    for f in _LOG_DIR.glob("*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except Exception:
            pass

    log_name = f"v14_{Path(sys.argv[0]).stem}.log"
    file_handler = logging.FileHandler(_LOG_DIR / log_name, encoding="utf-8")
    file_handler.setFormatter(fmt)
    _LOG.addHandler(file_handler)

    _configure_log_levels(debug)

    if debug:
        _LOG.debug("Python %s on %s", sys.version, sys.platform)
        _LOG.debug("cwd: %s", os.getcwd())
        _LOG.debug("args: %s", sys.argv)


def _configure_log_levels(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    _LOG.setLevel(level)
    for h in _LOG.handlers:
        if isinstance(h, logging.FileHandler):
            h.setLevel(logging.DEBUG if debug else logging.WARNING)


# ============================================================
#  3. ConvertResult
# ============================================================


class ConvertResult(NamedTuple):
    ok: bool
    output_dir: str
    image_count: int
    warning: str | None


# ============================================================
#  4. 编码检测
# ============================================================


def _garbled_ratio(text: str, sample_len: int = 2000) -> float:
    """文本乱码比例。>0.2 可能有问题。"""
    sample = text[:sample_len] if len(text) > sample_len else text
    if not sample:
        return 0.0
    bad = sum(
        1
        for ch in sample
        if ord(ch) == 0xFFFD or 0x80 <= ord(ch) <= 0x9F or 0xE000 <= ord(ch) <= 0xF8FF
    )
    return bad / len(sample)


def _text_diff_ratio(a: str, b: str, sample_len: int = 4000) -> float:
    """两个文本的差异度 (0=相同, 1=完全不同), 用字符集重叠率算。"""
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


# ============================================================
#  5. 图片提取  base64 图片 + PDF 内嵌图片
# ============================================================

_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/[\w+]+);base64,([A-Za-z0-9+/=]+)\)"
)


def _extract_images(markdown: str, images_dir: str) -> tuple[str, int]:
    """提取 base64 图片到 images_dir, 返回 (新 markdown, 图片数)。"""
    os.makedirs(images_dir, exist_ok=True)
    count: dict[str, int] = {}
    skipped = 0

    def _replace_match(m: re.Match) -> str:
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
            _LOG.warning("base64 解码失败, 跳过 %s", filename)
            skipped += 1
            return f"![{alt}](broken:{filename})"

        if not decoded:
            _LOG.warning("零字节图片, 跳过 %s", filename)
            skipped += 1
            return f"![{alt}](empty:{filename})"

        try:
            with open(filepath, "wb") as f:
                f.write(decoded)
        except OSError as e:
            _LOG.warning("图片写入失败 %s: %s", filename, e)
            skipped += 1
            return f"![{alt}](broken:{filename})"

        return f"![{alt}](images/{filename})"

    result = _DATA_URI_RE.sub(_replace_match, markdown)

    if skipped:
        _LOG.warning("跳过了 %d 张损坏/空图片", skipped)
    return result, sum(count.values())
def _build_pdf_images_section(page_images: dict[int, list[str]]) -> str:
    """给 PDF 提取的内嵌图片建 markdown 段落。"""
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
#  6. 转换核心
# ============================================================


def _get_output_root(filepath: str, save_to_tool: bool) -> str:
    custom = _config_get("output_dir")
    if custom:
        return custom
    if save_to_tool:
        if getattr(sys, "frozen", False):
            tool_dir = os.path.join(
                os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME
            )
        else:
            tool_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(tool_dir, "output")
    return os.path.dirname(filepath)


def _make_output_dir(output_root: str, base_name: str) -> str:
    """创建不重名的输出文件夹。"""
    folder = os.path.join(output_root, f"{base_name}_md")
    counter = 1
    while True:
        try:
            os.makedirs(folder, exist_ok=False)
            return folder
        except FileExistsError:
            folder = os.path.join(output_root, f"{base_name}_md({counter})")
            counter += 1


def _convert_one(filepath: str, save_to_tool: bool,
                  md: "MarkItDown | None" = None) -> ConvertResult:
    """转换单个文件, 返回 ConvertResult。v13: md 实例由调用方传入复用。"""
    output_root = _get_output_root(filepath, save_to_tool)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    folder = _make_output_dir(output_root, base_name)
    md_file = os.path.join(folder, f"{base_name}.md")
    images_dir = os.path.join(folder, "images")
    ext = os.path.splitext(filepath)[1].lower()

    # ---- 预处理: .doc → .docx ----
    docx_temp, source_path, pre_error = _preprocess_doc(filepath, ext, folder)
    if pre_error is not None:
        return pre_error

    if ext == ".ppt":
        return ConvertResult(
            False,
            "旧版 PowerPoint (.ppt) 不支持直接转换。\n"
            "请用 PowerPoint 打开文件, "
            "另存为 .pptx 后重新拖入。\n"
            "操作: 文件 → 另存为 → 文件类型选 \"PowerPoint 演示文稿 (*.pptx)\"",
            0, None,
        )

    # ---- 调用 markitdown ----
    text, img_count, call_error = _call_markitdown(source_path, images_dir, md)
    if call_error is not None:
        _cleanup_docx_temp(docx_temp, folder)
        return call_error

    _cleanup_docx_temp(docx_temp, folder)

    # ---- PDF 后处理: 双引擎对比 + 嵌入图片 + 输出校验 ----
    if ext == ".pdf" and _config_get("pymupdf_accepted") is True:
        text, img_count, warning = _postprocess_pdf(
            filepath, text, img_count, images_dir)
    else:
        warning = _check_output_short(filepath, text)

    # ---- 写输出 ----
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(text)

    return ConvertResult(True, folder, img_count, warning)


def _preprocess_doc(filepath: str, ext: str, folder: str):
    """.doc → .docx 预处理。返回 (docx_temp_path, source_path, error_or_None)。"""
    if ext != ".doc":
        return None, filepath, None
    if not doc_engine.is_available():
        return None, filepath, ConvertResult(
            False, "aspose-words-foss 不可用, 无法处理 .doc 文件", 0, None)
    _LOG.debug("预转 .doc -> .docx")
    docx_temp = doc_engine.doc_to_docx(filepath, work_dir=folder)
    if docx_temp is None:
        return None, filepath, ConvertResult(
            False, ".doc → .docx 转换失败", 0, None)
    return docx_temp, docx_temp, None


def _call_markitdown(source_path: str, images_dir: str,
                     md: "MarkItDown | None" = None):
    """调用 markitdown 转换并提取图片。返回 (text, img_count, error_or_None)。"""
    if md is None:
        md = MarkItDown()
    try:
        result = md.convert(source_path, keep_data_uris=True)
        text, img_count = _extract_images(result.text_content or "", images_dir)
        return text, img_count, None
    except Exception as e:
        _LOG.error("markitdown 转换失败: %s — %s", source_path, e)
        return "", 0, ConvertResult(False, str(e), 0, None)


def _postprocess_pdf(filepath: str, text: str, img_count: int,
                     images_dir: str) -> tuple[str, int, str | None]:
    """PDF 后处理: 双引擎文本对比 + 嵌入图片提取 + 输出量检查。
    返回 (text, img_count, warning)."""
    warning: str | None = None
    fitz_doc = None
    try:
        fitz_doc = pdf_engine.open_pdf(filepath)
    except Exception:
        _LOG.warning("无法打开 PDF: %s", filepath)

    if fitz_doc is None:
        warning = _check_output_short(filepath, text)
        return text, img_count, warning

    try:
        # 双引擎文本对比: pdfplumber vs PyMuPDF
        pymupdf_text = pdf_engine.extract_text(filepath, doc=fitz_doc)
        if pymupdf_text:
            diff = _text_diff_ratio(text, pymupdf_text)
            garbled_a = _garbled_ratio(text)
            garbled_b = _garbled_ratio(pymupdf_text)
            _LOG.debug(
                "PDF text diff=%.2f garbled(pdfplumber)=%.2f garbled(pymupdf)=%.2f",
                diff, garbled_a, garbled_b,
            )
            if diff > 0.3 and garbled_b < garbled_a:
                text = pymupdf_text
                warning = _merge_warning(warning, "文字已用备用引擎修正")
                _LOG.info("PyMuPDF 文字更好 (diff=%.2f)", diff)
            elif diff > 0.2:
                warning = _merge_warning(warning, "文字可能不准确, 建议人工复查")
                _LOG.warning("两引擎输出差异较大 (diff=%.2f)", diff)

        # 嵌入图片
        try:
            pdf_img_count, page_images = pdf_engine.extract_images(
                filepath, images_dir, doc=fitz_doc)
        except Exception as e:
            _LOG.warning("PDF 图片提取失败: %s", e)
            pdf_img_count, page_images = 0, {}
        if pdf_img_count > 0:
            text += _build_pdf_images_section(page_images)
            img_count += pdf_img_count

        # 输出量 vs 页数
        page_count = len(fitz_doc)
        warning = _merge_warning(
            warning, _check_output_short(filepath, text, page_count))
    finally:
        fitz_doc.close()

    return text, img_count, warning


def _check_output_short(filepath: str, text: str,
                        page_count: int = 0) -> str | None:
    """检查输出文本是否太短，返回 warning 或 None。"""
    plain = re.sub(r"[#*\[\]()`!|><\n\r\t ]+", "", text)
    if page_count > 0 and len(plain) < max(20, page_count * 30):
        if len(plain) < 20:
            _LOG.warning("%s: 输出极短 (%d chars)", filepath, len(plain))
            return "输出内容极少, 可能转换失败"
        elif len(plain) / page_count < 30:
            _LOG.warning("%s: 低文本密度 (%d chars / %d pages)",
                         filepath, len(plain), page_count)
            return f"{page_count} 页仅产出 {len(plain)} 字符, 建议复查"
    elif page_count == 0 and len(plain) < 20:
        _LOG.warning("%s: 输出极短 (%d chars)", filepath, len(plain))
        return "输出内容极少, 可能转换失败"
    return None


def _cleanup_docx_temp(docx_temp: str | None, folder: str):
    """清理 .doc → .docx 的临时文件。"""
    if not docx_temp:
        return
    try:
        os.remove(docx_temp)
    except OSError:
        pass
    tmp_dir = os.path.dirname(docx_temp)
    if tmp_dir != folder:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def _merge_warning(existing: str | None, new: str) -> str:
    if not new:
        return existing
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
        self._thread: threading.Thread | None = None
        self.running = False
        self.cancel_event = threading.Event()
        self._result_folders: list[str] = []

        self.root.title(f"📝 InkDrop v{VERSION}")
        self.root.resizable(True, True)
        self.root.minsize(700, 560)
        self._restore_or_center(700, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._setup_drag_drop()
        self._setup_keyboard()
        self._refresh_list()

    # ------ 窗口位置 ------

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
        # 居中
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        self.cancel_event.set()
        if self.running and self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        if self.root.state() not in ("zoomed", "iconic"):
            _config_set("geometry", self.root.geometry())
        else:
            _config_set("geometry", "")
        self.root.destroy()

    # ------ 拖拽 ------

    def _setup_drag_drop(self):
        self.root.drop_target_register("*")
        self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        if self.running:
            return
        raw = event.data
        paths = self._parse_drop_data(raw)
        added = 0
        for p in paths:
            if os.path.isdir(p):
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

    # ------ 键盘 ------

    def _setup_keyboard(self):
        self.root.bind("<Return>", lambda _: self._on_convert_click())
        self._listbox.bind("<Delete>", lambda _: self._remove_selected())

    # ------ 拖放数据解析 ------

    @staticmethod
    def _parse_drop_data(raw: str) -> list[str]:
        # Windows 拖放格式: {path1} {path2} ...
        paths: list[str] = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                j = raw.find("}", i + 1)
                if j == -1:
                    break
                path = raw[i + 1 : j]
                if path:
                    paths.append(path)
                i = j + 1
            else:
                i += 1
        if not paths:
            # 后备: shlex (处理含空格的路径)
            try:
                paths = shlex.split(raw, posix=False)
            except ValueError:
                paths = raw.split()
        return paths

    # ------ UI 构建 ------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        # 文件列表
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

        # 按钮栏
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

        # 转换 / 取消按钮
        self.convert_btn = ttk.Button(
            self.root, text="转换 0 个文件", command=self._on_convert_click, width=22
        )
        self.convert_btn.pack(pady=(6, 2))

        # 进度条
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

        # 结果区
        result_frame = ttk.LabelFrame(self.root, text="转换结果")
        result_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self.results_text = tk.Text(
            result_frame, height=8, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9),
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
        self.results_text.tag_config("summary", foreground="black",
                                     font=("", 9, "bold"))

        # Open All 按钮 (初始隐藏)
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
                    "*.pdf *.doc *.docx *.pptx *.xlsx *.xls *.html *.csv *.json "
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

    # ------ 结果展示 ------

    def _clear_results(self):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete("1.0", tk.END)
        self.results_text.config(state=tk.DISABLED)
        self.open_all_btn.pack_forget()
        self._result_folders.clear()

    def _append_result(self, text: str, tag: str, folder: str | None = None):
        if not self.root.winfo_exists():
            return
        self.results_text.config(state=tk.NORMAL)
        if folder:
            self.results_text.insert(tk.END, text + "  ", tag)
            tag_name = f"folder_{len(self._result_folders)}"
            self.results_text.tag_config(tag_name, foreground="blue", underline=True)
            self.results_text.tag_bind(
                tag_name, "<Button-1>",
                lambda _, f=folder: os.startfile(f),
            )
            self.results_text.tag_bind(
                tag_name, "<Enter>",
                lambda _: self.results_text.config(cursor="hand2"),
            )
            self.results_text.tag_bind(
                tag_name, "<Leave>",
                lambda _: self.results_text.config(cursor=""),
            )
            self.results_text.insert(tk.END, "[打开]", tag_name)
        else:
            self.results_text.insert(tk.END, text, tag)
        self.results_text.insert(tk.END, "\n")
        self.results_text.see(tk.END)
        self.results_text.config(state=tk.DISABLED)

    def _open_all_folders(self):
        for folder in self._result_folders:
            if os.path.isdir(folder):
                os.startfile(folder)

    # ------ 设置 ------

    def _open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        body = ttk.Frame(dialog, padding=(24, 16, 24, 0))
        body.pack(fill=tk.BOTH)
        body.columnconfigure(1, weight=1)

        r = 0

        # ---- PyMuPDF ----
        ttk.Label(body, text="PDF 图片提取 (PyMuPDF)",
                  font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        r += 1

        enabled = _config_get("pymupdf_accepted") is True
        self._pymupdf_status_var = tk.StringVar(
            value=f"· {'已启用' if enabled else '已禁用'}"
        )

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
                    "如果你的使用场景符合 AGPL-3.0 许可, 点\"是\"启用。\n"
                    "点\"否\"取消。",
                    detail="是否启用 PyMuPDF?",
                    icon="question", parent=dialog,
                )
                if choice:
                    if not _config_set("pymupdf_accepted", True):
                        messagebox.showerror("错误", "保存设置失败", parent=dialog)
                        return
                    if not pdf_engine.is_available():
                        _config_set("pymupdf_accepted", False)
                        messagebox.showwarning(
                            "PyMuPDF 不可用",
                            "PyMuPDF (fitz) 未能加载。请确认已安装 PyMuPDF。",
                            parent=dialog,
                        )
                        return
                    self._pymupdf_status_var.set("· 已启用")
                    pymupdf_toggle_btn.config(text="禁用")

        ttk.Label(body, textvariable=self._pymupdf_status_var).grid(
            row=r, column=0, sticky=tk.W, padx=(8, 0))
        pymupdf_toggle_btn = ttk.Button(
            body, text="禁用" if enabled else "启用",
            command=toggle_pymupdf, width=6,
        )
        pymupdf_toggle_btn.grid(row=r, column=1, sticky=tk.E, padx=(0, 8))
        r += 1

        # ---- DOC 引擎 ----
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=r, column=0, columnspan=2, sticky=tk.EW, pady=(10, 10))
        r += 1

        ttk.Label(body, text="旧版 Word 文档 (.doc)",
                  font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        r += 1

        doc_available = doc_engine.is_available()
        doc_status = "· 已就绪 (aspose-words-foss)" if doc_available else "· 不可用"
        ttk.Label(body, text=doc_status).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, padx=(8, 0))
        r += 1

        ttk.Label(body, text="纯 Python, MIT 协议, 无需额外安装",
                  foreground="gray", font=("", 8)).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 4), padx=(8, 0))
        r += 1

        # ---- 输出目录 ----
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=r, column=0, columnspan=2, sticky=tk.EW, pady=(10, 10))
        r += 1

        ttk.Label(body, text="自定义输出目录",
                  font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
        r += 1

        current_output = _config_get("output_dir")
        self._output_dir_var = tk.StringVar(
            value=current_output or "未设置 (默认: 源文件所在目录)"
        )

        def choose_output_dir():
            path = filedialog.askdirectory(
                title="选择输出目录", parent=dialog,
                initialdir=current_output or os.path.expanduser("~"),
            )
            if path:
                if not _config_set("output_dir", path):
                    messagebox.showerror("错误", "保存设置失败", parent=dialog)
                    return
                self._output_dir_var.set(path)
                output_clear_btn.config(state=tk.NORMAL)

        def clear_output_dir():
            if not _config_set("output_dir", ""):
                messagebox.showerror("错误", "保存设置失败", parent=dialog)
                return
            self._output_dir_var.set("未设置 (默认: 源文件所在目录)")
            output_clear_btn.config(state=tk.DISABLED)

        out_frame = ttk.Frame(body)
        out_frame.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4),
                       padx=(8, 0))
        out_frame.columnconfigure(0, weight=1)

        ttk.Label(out_frame, textvariable=self._output_dir_var,
                  foreground="gray", font=("", 8)).pack(side=tk.LEFT)

        ttk.Button(out_frame, text="选择...", width=6,
                   command=choose_output_dir).pack(side=tk.RIGHT, padx=(0, 4))

        output_clear_btn = ttk.Button(out_frame, text="清除", width=6,
                                      command=clear_output_dir)
        output_clear_btn.pack(side=tk.RIGHT)
        if not current_output:
            output_clear_btn.config(state=tk.DISABLED)

        r += 1

        # ---- 调试日志 ----
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=r, column=0, columnspan=2, sticky=tk.EW, pady=(10, 10))
        r += 1

        ttk.Label(body, text="调试日志",
                  font=("", 9, "bold")).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
        r += 1

        ttk.Label(body, text="警告和错误始终记录",
                  foreground="gray", font=("", 8)).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 4), padx=(8, 0))
        r += 1

        debug_enabled = _config_get("debug_enabled") is True
        self._debug_status_var = tk.StringVar(
            value=f"· {'已开启' if debug_enabled else '已关闭'}"
        )

        def toggle_debug():
            currently = _config_get("debug_enabled") is True
            if not _config_set("debug_enabled", not currently):
                messagebox.showerror("错误", "保存设置失败", parent=dialog)
                return
            _configure_log_levels(not currently)
            new_state = not currently
            self._debug_status_var.set("· 已开启" if new_state else "· 已关闭")
            self._debug_path_var.set(f"日志目录: {_LOG_DIR}" if new_state else "")
            debug_toggle_btn.config(text="关闭" if new_state else "开启")

        ttk.Label(body, textvariable=self._debug_status_var).grid(
            row=r, column=0, sticky=tk.W, padx=(8, 0))
        debug_toggle_btn = ttk.Button(
            body, text="关闭" if debug_enabled else "开启",
            command=toggle_debug, width=6,
        )
        debug_toggle_btn.grid(row=r, column=1, sticky=tk.E, padx=(0, 8))
        r += 1

        self._debug_path_var = tk.StringVar(
            value=f"日志目录: {_LOG_DIR}" if debug_enabled else ""
        )
        ttk.Label(body, textvariable=self._debug_path_var,
                  foreground="gray", font=("", 8)).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, padx=(8, 0), pady=(4, 2))
        r += 1

        # 按钮行
        actions = ttk.Frame(body)
        actions.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=(6, 2))
        r += 1

        def open_log_dir():
            if not _LOG_DIR.exists():
                _LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(_LOG_DIR))

        ttk.Button(actions, text="打开日志目录",
                   command=open_log_dir).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="关闭", command=dialog.destroy,
                   width=8).pack(side=tk.RIGHT, padx=(0, 8))

        # 居中
        dialog.update_idletasks()
        dh = dialog.winfo_reqheight()
        dw = max(dialog.winfo_reqwidth(), 440)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dw) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dh) // 2
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, min(x, sw - dw))
        y = max(0, min(y, sh - dh))
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")

    # ------ 转换流程 ------

    def _on_convert_click(self):
        if self.running:
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

        self._thread = threading.Thread(
            target=self._convert_thread,
            args=(list(self.file_paths), self.save_to_tool_var.get()),
            daemon=True,
        )
        self._thread.start()

    def _convert_thread(self, file_paths: list[str], save_to_tool: bool):
        total = len(file_paths)
        ok_count = 0
        md = MarkItDown()  # v13: 复用实例
        warn_count = 0
        fail_count = 0

        for i, fp in enumerate(file_paths):
            if self.cancel_event.is_set():
                self.root.after(0, self._append_result,
                                f"已取消 ({i}/{total})", "summary")
                self.root.after(0, self._on_all_done, i, total, cancelled=True)
                return

            filename = os.path.basename(fp)
            self.root.after(0, self._append_result, f"→ {filename} ...", "progress")

            t0 = time.time()
            try:
                result = _convert_one(fp, save_to_tool, md)
                elapsed = time.time() - t0
                _LOG.debug("%s -> %s (%.1fs, %d images, warning=%s)",
                           filename, result.output_dir, elapsed,
                           result.image_count, result.warning)
            except Exception as e:
                elapsed = time.time() - t0
                _LOG.error("%s FAILED (%.1fs): %s\n%s",
                           filename, elapsed, e, traceback.format_exc())
                result = ConvertResult(False, str(e), 0, None)

            if self.cancel_event.is_set():
                self.root.after(0, self._append_result,
                                f"已取消 ({i}/{total})", "summary")
                self.root.after(0, self._on_all_done, i, total, cancelled=True)
                return

            if result.ok:
                self.root.after(0, self._on_one_success,
                                filename, result.output_dir,
                                result.image_count, result.warning)
                if result.warning:
                    warn_count += 1
                else:
                    ok_count += 1
            else:
                fail_count += 1
                self.root.after(0, self._append_result,
                                f"✗  {filename}  —  {result.output_dir}", "fail")

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
                            "提示: 可在 设置 → 打开日志目录 查看详细诊断信息",
                            "progress")
        self.root.after(0, self._on_all_done, total, total, cancelled=False)

    def _update_progress(self, done: int, total: int):
        if not self.root.winfo_exists():
            return
        self.progress_bar.configure(value=done)
        self.progress_var.set(f"{done} / {total}")

    def _on_one_success(self, filename: str, folder: str,
                        img_count: int, warning: str | None):
        if not self.root.winfo_exists():
            return
        if self.cancel_event.is_set():
            return
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
        if not self.root.winfo_exists():
            return
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
                f"({len(self._result_folders)} 个文件夹就绪 "
                f"— 点击 [打开] 或下方的按钮)",
                "progress",
            )


# ============================================================
#  8. CLI 与入口
# ============================================================


def _headless_convert(file_paths: list[str], save_to_tool: bool):
    """命令行模式: 转换文件并输出结果。"""
    ok, warn, fail = 0, 0, 0
    md = MarkItDown()  # v13: 复用实例
    for fp in file_paths:
        print(f"→ {os.path.basename(fp)} ...", flush=True)
        t0 = time.time()
        try:
            result = _convert_one(fp, save_to_tool, md)
            elapsed = time.time() - t0
            if result.ok:
                msg = f"  成功: {result.output_dir}"
                if result.image_count:
                    msg += f"  ({result.image_count} 张图片)"
                if result.warning:
                    warn += 1
                    msg += f"  — {result.warning}"
                    print(msg)
                else:
                    ok += 1
                    print(msg)
            else:
                fail += 1
                print(f"  失败: {result.output_dir}")
            _LOG.debug("%s -> %s (%.1fs)", fp, result.output_dir, elapsed)
        except Exception as e:
            fail += 1
            _LOG.error("%s FAILED: %s\n%s", fp, e, traceback.format_exc())
            print(f"  错误: {e}")
    print()
    parts = [f"{ok} 成功"]
    if warn:
        parts.append(f"{warn} 需复查")
    if fail:
        parts.append(f"{fail} 失败")
    print(f"完成: {', '.join(parts)}")


def _show_pymupdf_dialog(args):
    """PyMuPDF 许可证弹窗 — 仅首次启动 GUI。"""
    if args.convert:
        return
    if _config_get("pymupdf_accepted") is not None:
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    choice = messagebox.askyesno(
        "可选组件: PyMuPDF",
        "PyMuPDF (AGPL-3.0) 用于提取 PDF 内嵌图片。\n\n"
        "如果你的使用场景符合 AGPL-3.0 许可, 点\"是\"启用。\n"
        "点\"否\"跳过 — 其他功能不受影响。\n\n"
        "(此对话框仅显示一次)",
        detail="是否启用 PyMuPDF?",
        icon="question",
    )
    root.destroy()
    _config_set("pymupdf_accepted", choice)
    if choice:
        _LOG.info("User enabled PyMuPDF")
        pdf_engine.is_available()


def _parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="inkdrop",
        description="InkDrop — 将文档转换为 Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              inkdrop                            启动图形界面
              inkdrop --debug                    启动界面并开启调试日志
              inkdrop --convert a.pdf b.doc      命令行模式
            """),
    )
    parser.add_argument("--version", action="version",
                        version=f"inkdrop v{VERSION}")
    parser.add_argument("--debug", action="store_true",
                        help="启用调试日志 (输出到程序目录 logs\\)")
    parser.add_argument("--convert", nargs="+", metavar="FILE",
                        help="命令行模式: 转换文件后退出 (不启动 GUI)")
    parser.add_argument("--save-to-tool", action="store_true",
                        help="输出到工具目录而不是源文件目录")
    parser.add_argument("--reset", action="store_true",
                        help="重置所有设置 (config、PyMuPDF、调试日志)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    global _config
    args = _parse_args(argv)

    if args.reset:
        try:
            shutil.rmtree(_CONFIG_DIR, ignore_errors=True)
            shutil.rmtree(_LOG_DIR, ignore_errors=True)
        except Exception:
            pass
        _config = dict(_DEFAULT_CONFIG)
        if not args.debug and not args.convert:
            print("设置已重置, 所有偏好已清除。")
            print("下次启动将重新显示 PyMuPDF 对话框。")
            return

    _init_logging(args.debug or _config_get("debug_enabled"))

    # 高 DPI (Windows)
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    if args.convert:
        _LOG.debug("命令行模式, %d 个文件", len(args.convert))
        _headless_convert(args.convert, args.save_to_tool)
        return

    # GUI
    _show_pymupdf_dialog(args)
    root = TkinterDnD.Tk()
    MarkItDownApp(root)
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
