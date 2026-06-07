"""v2_compat.py — MarkItDown GUI v2
v1 基础上 + 安装缺失依赖（PDF/XLSX 已通） + keep_data_uris 保留图片
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from markitdown import MarkItDown


class MarkItDownApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MarkItDown Converter — v2")
        self.root.resizable(False, False)
        self._center_window(420, 200)
        self._build_ui()

    def _center_window(self, w: int, h: int):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}

        # ---- 文件选择 ----
        file_frame = ttk.Frame(self.root)
        file_frame.pack(fill=tk.X, **pad)

        ttk.Label(file_frame, text="File:").pack(side=tk.LEFT)

        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=36)
        self.file_entry.pack(side=tk.LEFT, padx=(6, 6))

        ttk.Button(file_frame, text="Browse", command=self._browse).pack(side=tk.LEFT)

        # ---- 转换按钮 ----
        self.convert_btn = ttk.Button(
            self.root, text="Convert", command=self._convert, width=20
        )
        self.convert_btn.pack(pady=(10, 4))

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
                ("Supported files", "*.pdf *.docx *.pptx *.xlsx *.html *.csv *.json *.xml *.txt *.jpg *.png *.gif *.bmp *.tiff *.eml *.msg *.epub *.zip"),
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

        directory = os.path.dirname(filepath)
        base = os.path.splitext(os.path.basename(filepath))[0]
        output = os.path.join(directory, f"{base}_converted.md")

        counter = 1
        while os.path.exists(output):
            output = os.path.join(directory, f"{base}_converted({counter}).md")
            counter += 1

        self.status_var.set("Status: Converting...")
        self.convert_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()

        try:
            md = MarkItDown()
            result = md.convert(filepath, keep_data_uris=True)
            with open(output, "w", encoding="utf-8") as f:
                f.write(result.text_content)
            self.status_var.set("Status: Done")
            self.output_var.set(f"Output: {output}")
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
