"""v6_pdf_images.py — MarkItDown GUI v6
v5 基础上 + PDF 内嵌图片提取（PyMuPDF）
"""
import base64
import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import fitz  # PyMuPDF
from tkinterdnd2 import TkinterDnD

from markitdown import MarkItDown

# 匹配 markdown 中的 base64 图片: ![...](data:image/png;base64,xxxx)
_DATA_URI_RE = re.compile(
    r"!\[([^\]]*)\]\(data:(image/\w+);base64,([A-Za-z0-9+/=]+)\)"
)


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
    """用 PyMuPDF 提取 PDF 内嵌图片，存到 images_dir。
    返回 (图片总数, {页码: ["images/xxx.jpg", ...]})。
    无图片时返回 (0, {})。
    """
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


def _build_pdf_images_section(page_images: dict[int, list[str]], doc_name: str) -> str:
    """构建 markdown 段落，列出从 PDF 提取的内嵌图片。"""
    lines = [
        "",
        "---",
        "",
        "## PDF Embedded Images",
        "",
        f"_Extracted {sum(len(v) for v in page_images.values())} image(s) from the PDF._",
        "",
    ]
    for page_num in sorted(page_images):
        lines.append(f"### Page {page_num}")
        lines.append("")
        for img_path in page_images[page_num]:
            filename = os.path.basename(img_path)
            lines.append(f"![{filename}]({img_path})")
            lines.append("")

    return "\n".join(lines)


def _convert_one(filepath: str) -> tuple[bool, str, int]:
    """转换单个文件。返回 (成功?, 输出文件夹, 图片数量)。"""
    directory = os.path.dirname(filepath)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    folder = os.path.join(directory, f"{base_name}_converted")

    counter = 1
    while os.path.exists(folder):
        folder = os.path.join(directory, f"{base_name}_converted({counter})")
        counter += 1

    md_file = os.path.join(folder, f"{base_name}_converted.md")
    images_dir = os.path.join(folder, "images")

    md = MarkItDown()
    result = md.convert(filepath, keep_data_uris=True)
    text, img_count = _extract_images(result.text_content, images_dir)

    # PDF 专有：提取内嵌图片
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        pdf_img_count, page_images = _extract_pdf_images(filepath, images_dir)
        if pdf_img_count > 0:
            text += _build_pdf_images_section(page_images, base_name)
            img_count += pdf_img_count

    os.makedirs(folder, exist_ok=True)
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(text)

    return True, folder, img_count


# --------------- UI ---------------

class MarkItDownApp:
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.file_paths: list[str] = []
        self.running = False

        self.root.title("MarkItDown Converter — v6 PDF Images")
        self.root.resizable(True, True)
        self.root.minsize(520, 400)
        self._center_window(650, 520)
        self._build_ui()
        self._setup_drag_drop()

    def _center_window(self, w: int, h: int):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

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
        """解析 tkinterdnd2 的拖放数据。
        Windows 上格式为 {path1} {path2} ... 每个路径用花括号括起。
        """
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
        list_frame = ttk.LabelFrame(self.root, text="Files  (drag & drop files here or onto window)")
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

        ttk.Button(btn_frame, text="Add Files", command=self._add_files).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(btn_frame, text="Remove Selected", command=self._remove_selected).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_frame, text="Clear All", command=self._clear_all).pack(
            side=tk.LEFT, padx=4
        )

        self.output_dir_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            btn_frame,
            text="Save to tool folder",
            variable=self.output_dir_var,
        ).pack(side=tk.LEFT, padx=12)

        # ===== 转换按钮 =====
        self.convert_btn = ttk.Button(
            self.root, text="Convert 0 File(s)", command=self._convert_all, width=22
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
        result_frame = ttk.LabelFrame(self.root, text="Results")
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

        self.results_text.tag_config("ok", foreground="green")
        self.results_text.tag_config("fail", foreground="red")
        self.results_text.tag_config("progress", foreground="royalblue")
        self.results_text.tag_config("summary", foreground="black", font=("", 9, "bold"))

    # ------ 文件列表操作 ------

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select files to convert",
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
            text=f"Convert {n} File(s)" if n else "Convert 0 File(s)",
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

    def _append_result(self, text: str, tag: str):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, text + "\n", tag)
        self.results_text.see(tk.END)
        self.results_text.config(state=tk.DISABLED)

    # ------ 批量转换 ------

    def _convert_all(self):
        if not self.file_paths or self.running:
            return

        self.running = True
        self.convert_btn.config(state=tk.DISABLED)
        self._clear_results()

        total = len(self.file_paths)
        self.progress_bar.configure(maximum=total, value=0)
        self.progress_var.set(f"0 / {total}")

        thread = threading.Thread(
            target=self._convert_thread, args=(list(self.file_paths),), daemon=True
        )
        thread.start()

    def _convert_thread(self, file_paths: list[str]):
        total = len(file_paths)
        ok_count = 0
        fail_count = 0
        errors: list[tuple[str, str]] = []

        for i, fp in enumerate(file_paths):
            filename = os.path.basename(fp)
            self.root.after(
                0, self._append_result, f"→ {filename} ...", "progress"
            )

            try:
                success, info, img_count = _convert_one(fp)
            except Exception as e:
                success, info, img_count = False, str(e), 0

            if success:
                ok_count += 1
                msg = f"✓  {filename}  →  {os.path.basename(info)}"
                if img_count:
                    msg += f"  ({img_count} images)"
                self.root.after(0, self._append_result, msg, "ok")
            else:
                fail_count += 1
                errors.append((filename, info))
                self.root.after(0, self._append_result, f"✗  {filename}  —  {info}", "fail")

            done = i + 1
            self.root.after(0, self._update_progress, done, total)

        summary = f"Done: {ok_count} succeeded"
        if fail_count:
            summary += f", {fail_count} failed"
        self.root.after(0, self._append_result, summary, "summary")
        self.root.after(0, self._on_all_done)

    def _update_progress(self, done: int, total: int):
        self.progress_bar.configure(value=done)
        self.progress_var.set(f"{done} / {total}")

    def _on_all_done(self):
        self.running = False
        n = len(self.file_paths)
        self.convert_btn.config(
            text=f"Convert {n} File(s)" if n else "Convert 0 File(s)",
            state=tk.NORMAL if n else tk.DISABLED,
        )


def main():
    root = TkinterDnD.Tk()
    MarkItDownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
