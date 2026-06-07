# MarkItDown GUI

给 markitdown 做 Windows GUI，打包为便携 exe。项目目录 `D:\Projects\MD\`。

## 铁律

- **每个版本独立文件** `vN_xxx.py`，绝不在旧版上改
- `CHANGELOG.md` 每版必记
- 先写计划
- 新建 venv 后先 `pip install -r requirements.txt`，否则所有文件都报 ModuleNotFoundError

## 运行环境

- venv: `D:\Projects\.venv\Scripts\python.exe`（Python 3.12）
- 依赖见 `requirements.txt`，全部 MIT/BSD

## 当前状态（2026-06-07）

```
D:\Projects\MD\
├── CHANGELOG.md
├── requirements.txt
├── pdf_engine.py   # PDF 引擎薄接口 (PyMuPDF)
├── doc_engine.py   # DOC 引擎薄接口 (aspose-words-foss)
├── sniffer.py      # magika→filetype shim
├── v1_demo.py
├── ... (v2–v10 历史版本)
├── v11_tidy.py
├── v12_doc.py
├── v13_optimize.py  # 当前版本
├── build.ps1         # 打包脚本 (右键运行, 无需 .spec)
├── build/
├── dist/           # MarkItDown\ (onedir, ~165MB)
└── samples/
```

## 版本历史

| v | 核心改动 | 状态 |
|----|----------|------|
| v1 | 最小 demo | done |
| v2 | 装包修 PDF/DOCX/XLSX/XLS；keep_data_uris | done |
| v3 | 图片 base64->文件；输出到子目录 | done |
| v4 | 批量转换 + 后台线程 + 进度条 | done |
| v5 | 拖拽 (tkinterdnd2) | done |
| v6 | PDF 内嵌图片提取 (PyMuPDF) | done |
| v7 | debug/logging + cancel + save-to-tool + CLI + 窗口记忆 | done |
| v8 | 线程安全、config 健壮性、PyMuPDF 开关、UX 改进 | done |
| v9 | 代码导航、死代码清理、requirements.txt | done |
| v10 | 打包测试 (PyInstaller)，exe 产出 118MB | done |
| v11 | pdf_engine + sniffer + 修 ~16 bug + onedir 打包 (160MB) | done |
| v12 | doc_engine (.doc 支持) + 代码全面清理 | done |
| v13 | _convert_one 拆分为 6 函数 + MarkItDown 实例复用 + 去死代码 | done |

## 依赖

见 `requirements.txt`。PyMuPDF (AGPL) 已通过 pdf_engine.py 隔离，aspose-words-foss (MIT) 处理 .doc，其余 MIT/BSD。

## 格式支持

| 格式 | 文字 | 表格 | 图片 |
|------|------|------|------|
| PDF | v | v | v (内嵌图片) |
| DOC | v | v | v (doc_engine→.docx 管线) |
| DOCX | v | v | v |
| PPTX | v | v | v |
| XLSX/XLS | v | v | - |
| PPT | - | - | - (提示用户另存 .pptx) |

