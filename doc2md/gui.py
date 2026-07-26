r"""doc2md GUI — 文档转 Markdown 桌面界面 (CustomTkinter)

功能: 拖拽/批量文档 → Markdown + 图片提取 → 输出文件夹 · 自定义输出目录
支持: PDF/DOC/DOCX/PPTX/XLSX/XLS/HTML/CSV/JSON/XML/TXT/图片/邮件/ZIP
入口: python -m doc2md.gui [--help|--version|--debug|--reset]
      或 pip install .[gui] 后 doc2md-gui

转换核心在 doc2md.convert.convert_one — 本模块只做 UI。
设计决策(纸墨工作台、双主题)见 .interface-design/system.md。
"""

import argparse
import json
import logging
import os
import shlex
import shutil
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from doc2md import __version__ as VERSION
from doc2md.convert import convert_one
from doc2md.engines import doc as doc_engine
from doc2md.engines import pdf as pdf_engine
from doc2md.quality import check_quality

APP_NAME = "doc2md"

_LOG = logging.getLogger(APP_NAME)

# ============================================================
#  0. 纸墨双主题  (light, dark) 成对取色
# ============================================================

PALETTE = {
    'bg':            ('#F6F4EF', '#17140F'),  # 暖纸 / 墨室
    'card':          ('#FFFFFF', '#201C16'),
    'border':        ('#E5E0D6', '#322C24'),
    'text':          ('#1C1917', '#E8E3DA'),
    'muted':         ('#8A8177', '#9A9184'),
    'select':        ('#EDE8DE', '#3A342B'),
    'accent':        ('#0F766E', '#2DD4BF'),  # 墨水瓶深青
    'success':       ('#15803D', '#4ADE80'),  # 校对绿
    'warning':       ('#B45309', '#FBBF24'),  # 便签黄
    'danger':        ('#B91C1C', '#F87171'),  # 朱砂红
    'primary':       ('#1A1815', '#E7E2D9'),  # 墨条按钮: 纸上墨 / 墨上纸
    'primary_hover': ('#3A362F', '#CFC9BD'),
    'primary_text':  ('#FFFFFF', '#1A1815'),
    'ghost_hover':   ('#ECE8E0', '#2A251E'),
    'statusbar':     ('#ECE8E0', '#201C16'),
}


def C(key: str) -> tuple[str, str]:
    """CTk 双色对。"""
    return PALETTE[key]


def CR(key: str) -> str:
    """按当前外观解析成单色, 给 tk 原生组件用。"""
    pair = PALETTE[key]
    return pair[0] if ctk.get_appearance_mode() == "Light" else pair[1]


FONT = "Microsoft YaHei UI"


# ============================================================
#  1. config  配置读写 (%APPDATA%\doc2md\)
# ============================================================

_APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
_CONFIG_DIR = _APP_DIR / "config"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_DEFAULT_CONFIG = {
    "pymupdf_accepted": None,
    "geometry": "",
    "debug_enabled": False,
    "output_dir": "",
    "appearance": "system",
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

_LOG_DIR = _APP_DIR / "logs"


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

    file_handler = logging.FileHandler(_LOG_DIR / "doc2md-gui.log",
                                       encoding="utf-8")
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
#  3. 转换适配  convert_one dict → GUI 需要的额外信息
# ============================================================


def _collect_image_paths(images_dir: str) -> list[str]:
    """收集 images_dir 下所有文件路径并排序。"""
    if not os.path.isdir(images_dir):
        return []
    return sorted([
        os.path.join(images_dir, f)
        for f in os.listdir(images_dir)
        if os.path.isfile(os.path.join(images_dir, f))
    ])


def _read_output(filepath: str, output_dir: str) -> tuple[str, list[str]]:
    """从输出目录读回 markdown 文本和图片列表, 供质量条/图片条用。"""
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    md_file = os.path.join(output_dir, f"{base_name}.md")
    markdown = ""
    try:
        with open(md_file, "r", encoding="utf-8") as f:
            markdown = f.read()
    except OSError as e:
        _LOG.warning("读回输出失败 %s: %s", md_file, e)
    images = _collect_image_paths(os.path.join(output_dir, "images"))
    return markdown, images


# ============================================================
#  4. UI  MarkItDownApp — CustomTkinter 主界面
# ============================================================


class MarkItDownApp:
    def __init__(self, root):
        self.root = root
        self.file_paths: list[str] = []
        self._thread: threading.Thread | None = None
        self.running = False
        self.cancel_event = threading.Event()
        self._result_folders: list[str] = []

        self.root.title(f"doc2md v{VERSION}")
        self.root.resizable(True, True)
        self.root.minsize(860, 580)
        self._restore_or_center(960, 640)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._setup_drag_drop()
        self._setup_keyboard()
        self._apply_tk_theme()
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

    def _ghost_btn(self, parent, text, command, accent=False, width=None):
        """文字按钮 — 次级操作, 透明底 + hover 微底色。"""
        return ctk.CTkButton(
            parent, text=text, command=command,
            width=width or (len(text) * 14 + 16), height=28,
            fg_color="transparent", hover_color=C('ghost_hover'),
            text_color=C('accent') if accent else C('muted'),
            font=ctk.CTkFont(family=FONT, size=12),
            corner_radius=6,
        )

    def _build_ui(self):
        # 布局: grid — row0 头部 / row1 左队列 + 右回执 / row2 状态栏
        self.root.grid_columnconfigure(0, minsize=300)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # ---- Header ----
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky=tk.EW,
                    padx=20, pady=(14, 10))
        ctk.CTkLabel(header, text="doc2md",
                     font=ctk.CTkFont(family="Segoe UI", size=24,
                                      weight="bold"),
                     text_color=C('text')).pack(side=tk.LEFT)
        ctk.CTkLabel(header, text="喂给 AI 的文档预处理器",
                     font=ctk.CTkFont(family=FONT, size=12),
                     text_color=C('muted')).pack(side=tk.LEFT,
                                                 padx=(12, 0), pady=(6, 0))
        self._ghost_btn(header, "设置", self._open_settings).pack(
            side=tk.RIGHT)

        # ---- 左列: 文件队列 ----
        left = ctk.CTkFrame(self.root, fg_color="transparent")
        left.grid(row=1, column=0, sticky=tk.NSEW, padx=(20, 8), pady=(0, 14))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        cap_row = ctk.CTkFrame(left, fg_color="transparent")
        cap_row.grid(row=0, column=0, sticky=tk.EW, pady=(0, 6))
        self._queue_caption = ctk.CTkLabel(
            cap_row, text="文件队列",
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color=C('muted'))
        self._queue_caption.pack(side=tk.LEFT)
        self._ghost_btn(cap_row, "＋ 添加文件", self._add_files,
                        accent=True).pack(side=tk.RIGHT)

        list_card = ctk.CTkFrame(left, fg_color=C('card'), corner_radius=10,
                                 border_width=1, border_color=C('border'))
        list_card.grid(row=1, column=0, sticky=tk.NSEW)
        self._list_frame = list_card

        self._listbox = tk.Listbox(
            list_card, selectmode=tk.EXTENDED,
            font=(FONT, 9), relief=tk.FLAT, borderwidth=0,
            highlightthickness=0, activestyle='none',
        )
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                           padx=(12, 4), pady=12)
        self._listbox.drop_target_register("*")
        self._listbox.dnd_bind("<<Drop>>", self._on_drop)

        self._list_scroll = ctk.CTkScrollbar(
            list_card, orientation="vertical", command=self._listbox.yview,
            width=12)
        self._list_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4),
                               pady=10)
        self._listbox.config(yscrollcommand=self._list_scroll.set)

        # 空态提示 (盖在列表中央, 有文件时隐藏)
        self._empty_hint = tk.Label(
            list_card,
            text="将文件或文件夹\n拖到这里\n\n或点击「添加文件」",
            font=(FONT, 10), justify=tk.CENTER, cursor='hand2',
        )
        self._empty_hint.drop_target_register("*")
        self._empty_hint.dnd_bind("<<Drop>>", self._on_drop)
        self._empty_hint.bind("<Button-1>", lambda _: self._add_files())

        ops_row = ctk.CTkFrame(left, fg_color="transparent")
        ops_row.grid(row=2, column=0, sticky=tk.EW, pady=(6, 10))
        self._ghost_btn(ops_row, "移除所选", self._remove_selected).pack(
            side=tk.LEFT)
        self._ghost_btn(ops_row, "清空", self._clear_all).pack(
            side=tk.LEFT, padx=(8, 0))

        # ---- 墨条: 开始转换 ----
        self.convert_btn = ctk.CTkButton(
            left, text="开始转换", command=self._on_convert_click,
            height=46, corner_radius=10,
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            fg_color=C('primary'), hover_color=C('primary_hover'),
            text_color=C('primary_text'), text_color_disabled=C('muted'),
        )
        self.convert_btn.grid(row=3, column=0, sticky=tk.EW)

        progress_row = ctk.CTkFrame(left, fg_color="transparent")
        progress_row.grid(row=4, column=0, sticky=tk.EW, pady=(10, 0))

        self.progress_bar = ctk.CTkProgressBar(
            progress_row, height=6, corner_radius=3,
            fg_color=C('select'), progress_color=C('accent'))
        self.progress_bar.set(0)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True,
                               padx=(0, 10))
        self.progress_var = tk.StringVar(value="0 / 0")
        ctk.CTkLabel(progress_row, textvariable=self.progress_var,
                     font=ctk.CTkFont(family=FONT, size=11),
                     text_color=C('muted')).pack(side=tk.RIGHT)

        # ---- 右列: 转换回执 ----
        right = ctk.CTkFrame(self.root, fg_color="transparent")
        right.grid(row=1, column=1, sticky=tk.NSEW, padx=(8, 20),
                   pady=(0, 14))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="转换回执",
                     font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
                     text_color=C('muted')).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 6))

        results_card = ctk.CTkFrame(right, fg_color=C('card'),
                                    corner_radius=10,
                                    border_width=1, border_color=C('border'))
        results_card.grid(row=1, column=0, sticky=tk.NSEW)

        self.results_text = tk.Text(
            results_card, wrap=tk.WORD, state=tk.DISABLED,
            font=(FONT, 9), relief=tk.FLAT, borderwidth=0,
            highlightthickness=0, padx=12, pady=10, spacing3=4,
        )
        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                               padx=(2, 0), pady=2)

        self._result_scroll = ctk.CTkScrollbar(
            results_card, orientation="vertical",
            command=self.results_text.yview, width=12)
        self._result_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4),
                                 pady=10)
        self.results_text.config(yscrollcommand=self._result_scroll.set)

        # ---- 质量条 (row=2) ----
        self._build_quality_strip(right)

        # ---- 图片条 (row=3, 初始隐藏) ----
        self._build_image_gallery(right)

        # ---- 打开所有文件夹 (row=4, 初始隐藏) ----
        self.open_all_btn = ctk.CTkButton(
            right, text="打开所有文件夹", command=self._open_all_folders,
            height=34, corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=12),
            fg_color="transparent", hover_color=C('ghost_hover'),
            border_width=1, border_color=C('border'),
            text_color=C('text'),
        )
        self.open_all_btn.grid(row=4, column=0, sticky=tk.EW, pady=(8, 0))
        self.open_all_btn.grid_remove()

        # ---- 状态栏 ----
        self._status_var = tk.StringVar(value="就绪")
        status_bar = ctk.CTkFrame(self.root, fg_color=C('statusbar'),
                                  corner_radius=0, height=26)
        status_bar.grid(row=2, column=0, columnspan=2, sticky=tk.EW)
        ctk.CTkLabel(status_bar, textvariable=self._status_var,
                     font=ctk.CTkFont(family=FONT, size=11),
                     text_color=C('muted')).pack(side=tk.LEFT, padx=14)

    # ------ 主题应用 (tk 原生组件手动跟随) ------

    def _apply_tk_theme(self):
        card, text, muted = CR('card'), CR('text'), CR('muted')
        self._listbox.config(
            bg=card, fg=text,
            selectbackground=CR('select'), selectforeground=text)
        self._empty_hint.config(bg=card, fg=muted)
        self.results_text.config(bg=card, fg=text)
        self.results_text.tag_config("ok", foreground=CR('success'))
        self.results_text.tag_config("warn", foreground=CR('warning'))
        self.results_text.tag_config("fail", foreground=CR('danger'))
        self.results_text.tag_config("progress", foreground=muted)
        self.results_text.tag_config("summary", foreground=text,
                                     font=(FONT, 9, "bold"))
        # 已有的 [打开] 链接 tag 重新上色
        for tag in self.results_text.tag_names():
            if tag.startswith("folder_"):
                self.results_text.tag_config(tag, foreground=CR('accent'))
        self._gallery_canvas.config(bg=card)
        self._gallery_inner.config(bg=card)
        for w in self._gallery_inner.winfo_children():
            w.config(bg=card)
            for c in w.winfo_children():
                c.config(bg=card)
                if isinstance(c, tk.Label) and c.cget("text"):
                    c.config(fg=muted)

    # ------ 质量条 ------

    def _build_quality_strip(self, parent):
        """最近一次转换的质量指标, 单行条挂在回执下方。"""
        self._quality_score_var = tk.StringVar(value="—")
        self._quality_heading_var = tk.StringVar(value="—")
        self._quality_tables_var = tk.StringVar(value="—")
        self._quality_images_var = tk.StringVar(value="—")
        self._quality_garbled_var = tk.StringVar(value="—")

        strip = ctk.CTkFrame(parent, fg_color=C('card'), corner_radius=10,
                             border_width=1, border_color=C('border'))
        strip.grid(row=2, column=0, sticky=tk.EW, pady=(8, 0))
        inner = ctk.CTkFrame(strip, fg_color="transparent")
        inner.pack(fill=tk.X, padx=12, pady=7)

        ctk.CTkLabel(inner, text="质量",
                     font=ctk.CTkFont(family=FONT, size=12),
                     text_color=C('muted')).pack(side=tk.LEFT)
        self._quality_score_label = ctk.CTkLabel(
            inner, textvariable=self._quality_score_var,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=C('text'))
        self._quality_score_label.pack(side=tk.LEFT, padx=(8, 6))
        self._quality_score_bar = ctk.CTkProgressBar(
            inner, height=6, corner_radius=3, width=90,
            fg_color=C('select'), progress_color=C('accent'))
        self._quality_score_bar.set(0)
        self._quality_score_bar.pack(side=tk.LEFT, padx=(0, 10))

        self._quality_value_labels: dict[str, ctk.CTkLabel] = {}
        for key, cap, var in [
            ("heading", "标题", self._quality_heading_var),
            ("garbled", "乱码", self._quality_garbled_var),
            ("tables", "表格", self._quality_tables_var),
            ("images", "图片", self._quality_images_var),
        ]:
            ctk.CTkLabel(inner, text=cap,
                         font=ctk.CTkFont(family=FONT, size=12),
                         text_color=C('muted')).pack(side=tk.LEFT,
                                                     padx=(12, 4))
            val = ctk.CTkLabel(inner, textvariable=var,
                               font=ctk.CTkFont(family=FONT, size=12,
                                                weight="bold"),
                               text_color=C('text'))
            val.pack(side=tk.LEFT)
            self._quality_value_labels[key] = val

    def _update_quality_panel(self, markdown: str):
        try:
            report = check_quality(markdown)
        except Exception as e:
            _LOG.warning("质量检查失败: %s", e)
            return

        self._quality_score_var.set(str(report.score))
        if report.score >= 70:
            color = C('success')
        elif report.score >= 40:
            color = C('warning')
        else:
            color = C('danger')
        self._quality_score_label.configure(text_color=color)
        self._quality_score_bar.set(report.score / 100)
        self._quality_score_bar.configure(progress_color=color)

        self._quality_heading_var.set(
            "正常" if report.heading_structure_ok else "层级断裂")
        self._quality_value_labels["heading"].configure(
            text_color=C('success') if report.heading_structure_ok
            else C('warning'))
        self._quality_tables_var.set(str(report.table_count))
        self._quality_images_var.set(str(report.image_count))
        self._quality_garbled_var.set(
            "检测到" if report.garbled_detected else "无")
        self._quality_value_labels["garbled"].configure(
            text_color=C('danger') if report.garbled_detected
            else C('success'))

    def _clear_quality_panel(self):
        self._quality_score_var.set("—")
        self._quality_score_label.configure(text_color=C('text'))
        self._quality_score_bar.set(0)
        self._quality_score_bar.configure(progress_color=C('accent'))
        self._quality_heading_var.set("—")
        self._quality_tables_var.set("—")
        self._quality_images_var.set("—")
        self._quality_garbled_var.set("—")
        for lbl in self._quality_value_labels.values():
            lbl.configure(text_color=C('text'))

    # ------ 图片条 ------

    def _build_image_gallery(self, parent):
        self._gallery_frame = ctk.CTkFrame(parent, fg_color=C('card'),
                                           corner_radius=10, border_width=1,
                                           border_color=C('border'))
        self._gallery_frame.grid(row=3, column=0, sticky=tk.EW, pady=(8, 0))
        self._gallery_images: list[str] = []
        self._gallery_photos: list = []

        self._gallery_canvas = tk.Canvas(self._gallery_frame, height=76,
                                         highlightthickness=0)
        self._gallery_scroll = ctk.CTkScrollbar(
            self._gallery_frame, orientation="horizontal",
            command=self._gallery_canvas.xview, height=12)
        self._gallery_canvas.config(xscrollcommand=self._gallery_scroll.set)

        self._gallery_scroll.pack(side=tk.BOTTOM, fill=tk.X, padx=10,
                                  pady=(0, 4))
        self._gallery_canvas.pack(side=tk.TOP, fill=tk.X, expand=True,
                                  padx=12, pady=(10, 0))

        self._gallery_inner = tk.Frame(self._gallery_canvas)
        self._gallery_canvas.create_window(
            (0, 0), window=self._gallery_inner, anchor=tk.NW)
        self._gallery_inner.bind(
            "<Configure>",
            lambda _: self._gallery_canvas.config(
                scrollregion=self._gallery_canvas.bbox("all")),
        )
        self._gallery_frame.grid_remove()

    def _update_image_gallery(self, images: list[str]):
        if not _HAS_PIL or not images:
            self._gallery_frame.grid_remove()
            return

        from PIL import ImageTk

        card = CR('card')
        self._gallery_inner.config(bg=card)
        for child in self._gallery_inner.winfo_children():
            child.destroy()
        self._gallery_photos.clear()
        self._gallery_images = images

        for idx, img_path in enumerate(images):
            try:
                pil_img = Image.open(img_path)
                pil_img.thumbnail((56, 56))
                photo = ImageTk.PhotoImage(pil_img)
                self._gallery_photos.append(photo)
            except Exception as e:
                _LOG.warning("缩略图加载失败 %s: %s", img_path, e)
                continue

            frame = tk.Frame(self._gallery_inner, bg=card)
            frame.pack(side=tk.LEFT, padx=3, pady=3)

            lbl = tk.Label(frame, image=photo, bg=card, bd=0,
                           highlightthickness=0)
            lbl.pack()
            lbl.bind("<Button-1>",
                     lambda _, i=idx: self._open_image_viewer(i))
            lbl.bind("<Enter>",
                     lambda _: self._gallery_canvas.config(cursor="hand2"))
            lbl.bind("<Leave>",
                     lambda _: self._gallery_canvas.config(cursor=""))

            name = os.path.basename(img_path)
            if len(name) > 12:
                name = name[:10] + "…"
            tk.Label(frame, text=name, font=(FONT, 7),
                     bg=card, fg=CR('muted')).pack()

        self._gallery_frame.grid()

    def _clear_image_gallery(self):
        for child in self._gallery_inner.winfo_children():
            child.destroy()
        self._gallery_photos.clear()
        self._gallery_images = []
        self._gallery_frame.grid_remove()

    def _open_image_viewer(self, index: int = 0):
        if not _HAS_PIL or not self._gallery_images:
            return

        images = self._gallery_images
        total = len(images)

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("图片查看器")
        dialog.transient(self.root)
        dialog.configure(fg_color=C('bg'))
        dialog.after(200, dialog.grab_set)

        img_label = ctk.CTkLabel(dialog, text="")
        img_label.pack(padx=12, pady=(12, 4))

        info_var = tk.StringVar()
        ctk.CTkLabel(dialog, textvariable=info_var,
                     font=ctk.CTkFont(family=FONT, size=12),
                     text_color=C('muted')).pack()

        nav_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        nav_frame.pack(pady=10)

        prev_btn = ctk.CTkButton(nav_frame, text="上一张", width=80,
                                 height=30,
                                 font=ctk.CTkFont(family=FONT, size=12),
                                 fg_color="transparent",
                                 hover_color=C('ghost_hover'),
                                 border_width=1, border_color=C('border'),
                                 text_color=C('text'))
        prev_btn.pack(side=tk.LEFT, padx=4)

        next_btn = ctk.CTkButton(nav_frame, text="下一张", width=80,
                                 height=30,
                                 font=ctk.CTkFont(family=FONT, size=12),
                                 fg_color="transparent",
                                 hover_color=C('ghost_hover'),
                                 border_width=1, border_color=C('border'),
                                 text_color=C('text'))
        next_btn.pack(side=tk.LEFT, padx=4)

        ctk.CTkButton(nav_frame, text="关闭", width=64, height=30,
                      font=ctk.CTkFont(family=FONT, size=12),
                      fg_color=C('primary'), hover_color=C('primary_hover'),
                      text_color=C('primary_text'),
                      command=dialog.destroy).pack(side=tk.LEFT, padx=4)

        current = [index]

        def show(idx: int):
            if idx < 0 or idx >= total:
                return
            current[0] = idx
            path = images[idx]
            try:
                pil_img = Image.open(path)
                orig_w, orig_h = pil_img.size
                max_w, max_h = 800, 600
                ratio = min(max_w / orig_w, max_h / orig_h, 1.0)
                w = max(1, int(orig_w * ratio))
                h = max(1, int(orig_h * ratio))
                photo = ctk.CTkImage(light_image=pil_img,
                                     dark_image=pil_img, size=(w, h))
                img_label.configure(image=photo)
                img_label._image_ref = photo
                info_var.set(
                    f"{idx + 1} / {total}  —  {os.path.basename(path)}"
                    f"  ({orig_w}×{orig_h})")
                dialog.title(f"图片查看器 — {os.path.basename(path)}")
            except Exception as e:
                _LOG.error("图片查看失败 %s: %s", path, e)
                info_var.set(f"无法加载: {os.path.basename(path)}")

            prev_btn.configure(
                state=tk.NORMAL if idx > 0 else tk.DISABLED)
            next_btn.configure(
                state=tk.NORMAL if idx < total - 1 else tk.DISABLED)

        prev_btn.configure(command=lambda: show(current[0] - 1))
        next_btn.configure(command=lambda: show(current[0] + 1))

        dialog.bind("<Left>", lambda _: show(current[0] - 1))
        dialog.bind("<Right>", lambda _: show(current[0] + 1))
        dialog.bind("<Escape>", lambda _: dialog.destroy())

        show(index)

        dialog.update_idletasks()
        dw = dialog.winfo_reqwidth()
        dh = dialog.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dw) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dh) // 2
        dialog.geometry(f"+{x}+{y}")

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
            self._listbox.insert(tk.END, " " + os.path.basename(p))
        n = len(self.file_paths)
        self._queue_caption.configure(
            text=f"文件队列 ({n})" if n else "文件队列")
        if n:
            self._empty_hint.place_forget()
        else:
            self._empty_hint.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.convert_btn.configure(
            text=f"开始转换 ({n})" if n else "开始转换",
            state=tk.NORMAL if n else tk.DISABLED,
        )
        self.progress_bar.set(0)
        self.progress_var.set(f"0 / {n}" if n else "0 / 0")
        self._status_var.set(f"{n} 个文件已添加" if n else "就绪")
        self._clear_results()

    # ------ 结果展示 ------

    def _clear_results(self):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete("1.0", tk.END)
        self.results_text.config(state=tk.DISABLED)
        self.open_all_btn.grid_remove()
        self._result_folders.clear()
        self._clear_quality_panel()
        self._clear_image_gallery()

    def _append_result(self, text: str, tag: str, folder: str | None = None):
        if not self.root.winfo_exists():
            return
        self.results_text.config(state=tk.NORMAL)
        if folder:
            self.results_text.insert(tk.END, text + "  ", tag)
            tag_name = f"folder_{len(self._result_folders)}"
            self.results_text.tag_config(tag_name, foreground=CR('accent'),
                                         underline=True)
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
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("设置")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(fg_color=C('bg'))
        dialog.after(200, dialog.grab_set)

        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill=tk.BOTH, padx=28, pady=20)

        def section(text, top=14):
            ctk.CTkLabel(body, text=text,
                         font=ctk.CTkFont(family=FONT, size=12,
                                          weight="bold"),
                         text_color=C('text')).pack(anchor=tk.W,
                                                    pady=(top, 2))

        def hint(text):
            ctk.CTkLabel(body, text=text,
                         font=ctk.CTkFont(family=FONT, size=11),
                         text_color=C('muted')).pack(anchor=tk.W)

        switch_kw = dict(
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=C('text'),
            progress_color=C('accent'), fg_color=C('select'),
            button_color=('#FFFFFF', '#E8E3DA'),
            button_hover_color=('#F6F4EF', '#CFC9BD'),
        )

        # ---- 外观 ----
        section("外观", top=0)
        appearance_map = {"跟随系统": "system", "浅色": "light",
                          "深色": "dark"}
        appearance_rev = {v: k for k, v in appearance_map.items()}

        def on_appearance(label):
            mode = appearance_map[label]
            if not _config_set("appearance", mode):
                messagebox.showerror("错误", "保存设置失败", parent=dialog)
                return
            ctk.set_appearance_mode(mode)
            self._apply_tk_theme()

        appearance_seg = ctk.CTkSegmentedButton(
            body, values=list(appearance_map),
            command=on_appearance,
            font=ctk.CTkFont(family=FONT, size=12),
            selected_color=('#D6D0C4', '#4A4438'),
            selected_hover_color=('#CFC9BD', '#554E40'),
            unselected_color=C('select'),
            unselected_hover_color=C('ghost_hover'),
            text_color=C('text'),
            fg_color=C('select'),
        )
        appearance_seg.set(appearance_rev.get(
            _config_get("appearance") or "system", "跟随系统"))
        appearance_seg.pack(anchor=tk.W, pady=(4, 0))

        # ---- PyMuPDF ----
        section("PDF 图片提取 (PyMuPDF)")
        hint("AGPL-3.0 协议组件, 用于 PDF 文字纠错与内嵌图片提取")

        pymupdf_var = tk.BooleanVar(
            value=_config_get("pymupdf_accepted") is True)

        def toggle_pymupdf():
            if pymupdf_var.get():
                choice = messagebox.askyesno(
                    "可选组件: PyMuPDF",
                    "PyMuPDF (AGPL-3.0) 用于提取 PDF 内嵌图片。\n\n"
                    "如果你的使用场景符合 AGPL-3.0 许可, 点\"是\"启用。",
                    detail="是否启用 PyMuPDF?",
                    icon="question", parent=dialog,
                )
                if not choice:
                    pymupdf_var.set(False)
                    return
                if not _config_set("pymupdf_accepted", True):
                    messagebox.showerror("错误", "保存设置失败", parent=dialog)
                    pymupdf_var.set(False)
                    return
                if not pdf_engine.is_available():
                    _config_set("pymupdf_accepted", False)
                    pymupdf_var.set(False)
                    messagebox.showwarning(
                        "PyMuPDF 不可用",
                        "PyMuPDF (fitz) 未能加载。请确认已安装 PyMuPDF。",
                        parent=dialog,
                    )
            else:
                if not _config_set("pymupdf_accepted", False):
                    messagebox.showerror("错误", "保存设置失败", parent=dialog)
                    pymupdf_var.set(True)

        ctk.CTkSwitch(body, text="启用 PyMuPDF", variable=pymupdf_var,
                      command=toggle_pymupdf, **switch_kw).pack(
            anchor=tk.W, pady=(6, 0))

        # ---- DOC 引擎 ----
        section("旧版 Word 文档 (.doc)")
        doc_ok = doc_engine.is_available()
        hint("已就绪 (aspose-words-foss, MIT)" if doc_ok
             else "不可用 — pip install doc2md[doc]")

        # ---- 输出目录 ----
        section("自定义输出目录")
        current_output = _config_get("output_dir")
        output_var = tk.StringVar(
            value=current_output or "未设置 (默认: 源文件所在目录)")
        ctk.CTkLabel(body, textvariable=output_var,
                     font=ctk.CTkFont(family=FONT, size=11),
                     text_color=C('muted')).pack(anchor=tk.W)

        out_row = ctk.CTkFrame(body, fg_color="transparent")
        out_row.pack(anchor=tk.W, pady=(6, 0))

        def choose_output_dir():
            path = filedialog.askdirectory(
                title="选择输出目录", parent=dialog,
                initialdir=_config_get("output_dir")
                or os.path.expanduser("~"),
            )
            if path:
                if not _config_set("output_dir", path):
                    messagebox.showerror("错误", "保存设置失败",
                                         parent=dialog)
                    return
                output_var.set(path)

        def clear_output_dir():
            if not _config_set("output_dir", ""):
                messagebox.showerror("错误", "保存设置失败", parent=dialog)
                return
            output_var.set("未设置 (默认: 源文件所在目录)")

        btn_kw = dict(
            height=30, corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=12),
            fg_color="transparent", hover_color=C('ghost_hover'),
            border_width=1, border_color=C('border'),
            text_color=C('text'),
        )
        ctk.CTkButton(out_row, text="选择…", width=80,
                      command=choose_output_dir, **btn_kw).pack(
            side=tk.LEFT)
        ctk.CTkButton(out_row, text="清除", width=64,
                      command=clear_output_dir, **btn_kw).pack(
            side=tk.LEFT, padx=(8, 0))

        # ---- 调试日志 ----
        section("调试日志")
        hint("警告和错误始终记录")

        debug_var = tk.BooleanVar(
            value=_config_get("debug_enabled") is True)

        def toggle_debug():
            new_state = debug_var.get()
            if not _config_set("debug_enabled", new_state):
                messagebox.showerror("错误", "保存设置失败", parent=dialog)
                debug_var.set(not new_state)
                return
            _configure_log_levels(new_state)

        ctk.CTkSwitch(body, text="开启调试日志", variable=debug_var,
                      command=toggle_debug, **switch_kw).pack(
            anchor=tk.W, pady=(6, 0))

        # ---- 目录 ----
        section("目录")
        hint(f"日志: {_LOG_DIR}")
        hint(f"配置: {_CONFIG_DIR}")

        dir_row = ctk.CTkFrame(body, fg_color="transparent")
        dir_row.pack(anchor=tk.W, pady=(6, 0), fill=tk.X)

        def open_log_dir():
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(_LOG_DIR))

        def open_config_dir():
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(_CONFIG_DIR))

        ctk.CTkButton(dir_row, text="打开日志目录", width=104,
                      command=open_log_dir, **btn_kw).pack(side=tk.LEFT)
        ctk.CTkButton(dir_row, text="打开配置目录", width=104,
                      command=open_config_dir, **btn_kw).pack(
            side=tk.LEFT, padx=(8, 0))
        ctk.CTkButton(dir_row, text="关闭", width=64,
                      command=dialog.destroy,
                      height=30, corner_radius=8,
                      font=ctk.CTkFont(family=FONT, size=12),
                      fg_color=C('primary'),
                      hover_color=C('primary_hover'),
                      text_color=C('primary_text')).pack(side=tk.RIGHT)

        # 居中 (只定位不定尺寸 — CTk 会对 geometry 的宽高二次缩放)
        dialog.update_idletasks()
        dw = dialog.winfo_reqwidth()
        dh = dialog.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dw) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dh) // 2
        x = max(0, x)
        y = max(0, y)
        dialog.geometry(f"+{x}+{y}")

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
        self.convert_btn.configure(text="取消", state=tk.NORMAL)
        self._clear_results()

        total = len(self.file_paths)
        self._total = total
        self.progress_bar.set(0)
        self.progress_var.set(f"0 / {total}")

        self._thread = threading.Thread(
            target=self._convert_thread,
            args=(list(self.file_paths),),
            daemon=True,
        )
        self._thread.start()

    def _convert_thread(self, file_paths: list[str]):
        from markitdown import MarkItDown

        total = len(file_paths)
        ok_count = 0
        warn_count = 0
        fail_count = 0
        md = MarkItDown()  # 复用实例
        output_root = _config_get("output_dir") or None
        use_pymupdf = _config_get("pymupdf_accepted") is True

        for i, fp in enumerate(file_paths):
            if self.cancel_event.is_set():
                self.root.after(0, self._append_result,
                                f"已取消 ({i}/{total})", "summary")
                self.root.after(0, self._on_all_done, i, total, True)
                return

            filename = os.path.basename(fp)
            self.root.after(0, self._append_result,
                            f"→ {filename} ...", "progress")

            t0 = time.time()
            try:
                result = convert_one(fp, output_root, md=md,
                                     use_pymupdf=use_pymupdf)
                elapsed = time.time() - t0
                _LOG.debug("%s -> %s (%.1fs, %d images, warning=%s)",
                           filename, result["output_dir"], elapsed,
                           result["image_count"], result["warning"])
            except Exception as e:
                elapsed = time.time() - t0
                _LOG.error("%s FAILED (%.1fs): %s\n%s",
                           filename, elapsed, e, traceback.format_exc())
                result = {"ok": False, "output_dir": "", "image_count": 0,
                          "warning": None, "error": str(e)}

            if self.cancel_event.is_set():
                self.root.after(0, self._append_result,
                                f"已取消 ({i}/{total})", "summary")
                self.root.after(0, self._on_all_done, i, total, True)
                return

            if result["ok"]:
                markdown, images = _read_output(fp, result["output_dir"])
                self.root.after(0, self._on_one_success,
                                filename, result["output_dir"],
                                result["image_count"], result["warning"],
                                images, markdown)
                if result["warning"]:
                    warn_count += 1
                else:
                    ok_count += 1
            else:
                fail_count += 1
                self.root.after(0, self._append_result,
                                f"✗  {filename}  —  {result['error']}",
                                "fail")

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
        self.root.after(0, self._on_all_done, total, total, False)

    def _update_progress(self, done: int, total: int):
        if not self.root.winfo_exists():
            return
        self.progress_bar.set(done / total if total else 0)
        self.progress_var.set(f"{done} / {total}")

    def _on_one_success(self, filename: str, folder: str,
                        img_count: int, warning: str | None,
                        images: list[str] | None = None,
                        markdown: str = ""):
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
        if markdown:
            self._update_quality_panel(markdown)
        if images and _HAS_PIL:
            self._update_image_gallery(images)

    def _on_all_done(self, done: int, total: int, cancelled: bool):
        if not self.root.winfo_exists():
            return
        self.running = False
        self.progress_bar.set(0)
        self.progress_var.set("0 / 0")
        n = len(self.file_paths)
        self.convert_btn.configure(
            text=f"开始转换 ({n})" if n else "开始转换",
            state=tk.NORMAL if n else tk.DISABLED,
        )
        if not cancelled and self._result_folders:
            self.open_all_btn.grid()
            self._append_result(
                f"({len(self._result_folders)} 个文件夹就绪 "
                f"— 点击 [打开] 或下方的按钮)",
                "progress",
            )
            self._status_var.set(
                f"完成 — {len(self._result_folders)} 个文件夹就绪")
        else:
            self._status_var.set("就绪")


# ============================================================
#  5. 入口
# ============================================================


def _show_pymupdf_dialog():
    """PyMuPDF 许可证弹窗 — 仅首次启动。"""
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
        prog="doc2md-gui",
        description="doc2md GUI — 将文档转换为 Markdown (命令行请用 doc2md)",
    )
    parser.add_argument("--version", action="version",
                        version=f"doc2md-gui v{VERSION}")
    parser.add_argument("--debug", action="store_true",
                        help=f"启用调试日志 (输出到 {_LOG_DIR})")
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
        if not args.debug:
            print("设置已重置, 所有偏好已清除。")
            print("下次启动将重新显示 PyMuPDF 对话框。")
            return

    _init_logging(args.debug or _config_get("debug_enabled"))

    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        print("缺少 GUI 依赖 tkinterdnd2。请先安装:")
        print("  pip install doc2md[gui]   或   pip install tkinterdnd2 "
              "Pillow customtkinter")
        sys.exit(1)

    class _DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        """CustomTkinter 根窗口 + tkinterdnd2 拖放。"""
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.TkdndVersion = TkinterDnD._require(self)

    ctk.set_appearance_mode(_config_get("appearance") or "system")

    _show_pymupdf_dialog()
    root = _DnDCTk(fg_color=C('bg'))
    MarkItDownApp(root)
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
