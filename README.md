# doc2md

把 PDF / DOC / DOCX / PPTX / XLSX 等文档批量转成干净的 Markdown（含图片提取），
喂给 AI 用。基于 [microsoft/markitdown](https://github.com/microsoft/markitdown)，
补上它没有的部分：PDF 双引擎纠错、内嵌图片落盘、`.doc` 桥接、质量启发式，
以及一个桌面 GUI。

> 项目曾于 2026-06 归档（验证记录见 [复盘.md](复盘.md)），2026-07-26 重启，
> 形态调整为 `doc2md` Python 包：CLI 核心 + 可选 GUI。

## 安装

```bash
pip install .            # CLI 核心
pip install .[all]       # CLI + PDF 纠错 + .doc 支持 + GUI
```

或开发模式：仓库根 `pip install -r requirements.txt` 后直接运行。

## 用法

```bash
# CLI
doc2md report.pdf                     # 输出到源文件旁 report_md/
doc2md --out ./output/ a.docx b.pptx  # 批量 + 指定输出目录
doc2md https://example.com/post -o .  # 网页转 Markdown
doc2md --on-conflict skip *.pdf       # 同名输出: rename(默认)/overwrite/skip
python -m doc2md file.pdf             # 不安装直接跑

# GUI（拖拽、批量队列、转换回执、质量分、Markdown 预览、深浅主题）
doc2md-gui
python -m doc2md.gui
```

GUI 里：回执行可点击，质量条/图片条/预览随选中的文件切换；「添加链接」
或直接拖入链接可转网页（输出默认收进 `~/Documents/doc2md`）。

输出结构：

```
report_md/
├── report.md
└── images/
    ├── img_001.png
    └── pdf_p01_i01.jpg
```

## 格式支持

| 格式 | 文字 | 表格 | 图片 |
|------|------|------|------|
| PDF | ✅ | ✅ | ✅ (内嵌图片, 需 PyMuPDF) |
| DOC | ✅ | ✅ | ✅ (aspose→.docx 管线) |
| DOCX / PPTX | ✅ | ✅ | ✅ |
| XLSX / XLS | ✅ | ✅ | ❌ |
| HTML/CSV/JSON/XML/TXT | ✅ | — | — |
| PPT | ❌ 提示另存为 .pptx |

## 架构

```
CLI (doc2md.cli) ─┐
                  ├→ 转换管线 (doc2md.convert) → 引擎层 → 输出
GUI (doc2md.gui) ─┘             ↓
                     ┌─────────┴─────────┐
                engines/pdf.py      engines/doc.py
                (PyMuPDF, 懒加载)    (aspose-words-foss)
```

- PDF 双引擎：pdfplumber 提取 + PyMuPDF 对比纠错（乱码率/差异度启发式，
  见 `doc2md/quality.py`）
- GUI 设计决策见 `.interface-design/system.md`

## 项目结构

```
markitdown-desktop/
├── doc2md/
│   ├── __init__.py        # 公共 API（convert_one）
│   ├── cli.py             # doc2md 命令
│   ├── gui.py             # doc2md-gui 命令（CustomTkinter）
│   ├── convert.py         # 核心转换管线
│   ├── images.py          # base64 图片落盘
│   ├── quality.py         # 乱码/差异启发式 + Markdown 质量报告
│   └── engines/
│       ├── pdf.py         # PyMuPDF（AGPL 隔离，懒加载）
│       └── doc.py         # aspose-words-foss
├── pyproject.toml         # 打包与入口点
├── CHANGELOG.md           # 迭代记录
├── 复盘.md                 # 2026-06 归档期的验证记录（保留）
└── 文件阅读规范.md         # 各格式读写参考
```

## 依赖与协议

| 依赖 | 协议 | 说明 |
|------|------|------|
| markitdown | MIT | 转换核心 |
| PyMuPDF | AGPL-3.0 | ⚠️ 可选 extra，打包分发前做合规审查 |
| aspose-words-foss | MIT | 非官方分支，.doc 桥接 |
| customtkinter / tkinterdnd2 / Pillow | MIT 系 | GUI 可选 extra |

MIT License。GUI 历史版本（InkDrop、PyInstaller 构建、CI）见 Git 记录。
