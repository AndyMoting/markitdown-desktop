"""v3_output.py — MarkItDown GUI v3
v2 基础上 + 图片存为文件（不塞 base64） + 输出到同名文件夹
"""
import base64
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from markitdown import MarkItDown

# 匹配 markdown 中的 base64 图片: ![...](data:image/png;base64,xxxx)
_DATA_URI_RE = re.compile(r'!\[([^\]]*)\]\(data:(image/\w+);base64,([A-Za-z0-9+/=]+)\)')


def _extract_images(markdown: str, images_dir: str) -> tuple[str, int]:
    """提取 base64 图片，存到 images_dir，返回 (新的 markdown, 图片数量)。"""
    count = {"png": 0, "jpeg": 0, "gif": 0, "bmp": 0, "tiff": 0, "webp": 0}

    def _replace(match):
        alt = match.group(1) or "image"
        mime = match.group(2)  # "image/png"
        data = match.group(3)

        ext = mime.split("/")[1]
        if ext == "jpeg":
            ext = "jpg"
        count[ext] = count.get(ext, 0) + 1
        n = count[ext]
        ext_final = "jpg" if ext == "jpeg" else ext

        filename = f"img_{n:03d}.{ext_final}"
        filepath = os.path.join(images_dir, filename)

        os.makedirs(images_dir, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(data))

        return f"![{alt}](images/{filename})"

    result = _DATA_URI_RE.sub(_replace, markdown)
    total = sum(count.values())
    return result, total


class MarkItDownApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MarkItDown Converter — v3")
        self.root.resizable(False, False)
        self._center_window(440, 240)
        self._build_ui()

    def _center_window(self, w: int, h: int):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # ---- 文件选择 ----
        file_frame = ttk.Frame(self.root)
        file_frame.pack(fill=tk.X, **pad)

        ttk.Label(file_frame, text="File:").pack(side=tk.LEFT)

        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=36)
        self.file_entry.pack(side=tk.LEFT, padx=(6, 6))

        ttk.Button(file_frame, text="Browse", command=self._browse).pack(side=tk.LEFT)

        # ---- 输出位置 ----
        self.output_dir_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.root,
            text="Save to tool folder (D:\\Projects\\MD)",
            variable=self.output_dir_var,
        ).pack(**pad, anchor=tk.W)

        # ---- 转换按钮 ----
        self.convert_btn = ttk.Button(
            self.root, text="Convert", command=self._convert, width=20
        )
        self.convert_btn.pack(pady=(4, 4))

        # ---- 状态 ----
        self.status_var = tk.StringVar(value="Status: Ready")
        ttk.Label(self.root, textvariable=self.status_var).pack()

        # ---- 输出路径 ----
        self.output_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.output_var, foreground="gray").pack()

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a file to convert",
            filetypes=[
                (
                    "Supported files",
                    "*.pdf *.docx *.pptx *.xlsx *.xls *.html *.csv *.json *.xml *.txt *.jpg *.png *.gif *.bmp *.tiff *.eml *.msg *.epub *.zip",
                ),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_var.set(path)
            self.output_var.set("")

    def _convert(self):
        filepath = self.file_var.get().strip()
        if not filepath:
            messagebox.showwarning("No file", "Please select a file first.")
            return
        if not os.path.isfile(filepath):
            messagebox.showerror("Error", f"File not found:\n{filepath}")
            return

        # 决定输出父目录
        if self.output_dir_var.get():
            parent_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            parent_dir = os.path.dirname(filepath)

        # 产出文件夹: {原文件名}_converted/
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        folder = os.path.join(parent_dir, f"{base_name}_converted")

        # 去重
        counter = 1
        while os.path.exists(folder):
            folder = os.path.join(parent_dir, f"{base_name}_converted({counter})")
            counter += 1

        md_file = os.path.join(folder, f"{base_name}_converted.md")
        images_dir = os.path.join(folder, "images")

        self.status_var.set("Status: Converting...")
        self.convert_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()

        try:
            md = MarkItDown()
            result = md.convert(filepath, keep_data_uris=True)
            text = result.text_content

            # 提取 base64 图片到文件（无图则不动 images 目录）
            text, img_count = _extract_images(text, images_dir)

            os.makedirs(folder, exist_ok=True)
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(text)

            self.status_var.set("Status: Done")
            self.output_var.set(
                f"Output: {folder}  (images: {img_count})"
            )
        except Exception as e:
            self.status_var.set("Status: Failed")
            self.output_var.set("")
            messagebox.showerror("Conversion error", str(e))
        finally:
            self.convert_btn.config(state=tk.NORMAL)


def main():
    root = tk.Tk()
    MarkItDownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
