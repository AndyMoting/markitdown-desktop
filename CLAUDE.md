# InkDrop

给 markitdown 做 Windows GUI，打包为便携 exe。项目目录 `D:\Projects\MD\`。

## 铁律

- **commit 不加 Co-Authored-By**，不挂 AI 名字在贡献者列表
- **版本独立文件** `versions/vN_xxx.py`，历史快照，不修不改不合入。后续只改 `releases/v*py`
- `CHANGELOG.md` 每版必记
- 先写计划
- 新建 venv 后先 `pip install -r requirements.txt`，否则所有文件都报 ModuleNotFoundError
- `_convert_one` 签名: `(filepath, save_to_tool, md=None)`，第三个参数传入复用的 MarkItDown 实例。CLI 的 `_headless_convert` 同理复用

## 运行环境

- venv: `D:\Projects\.venv\Scripts\python.exe`（Python 3.12）
- 依赖见 `requirements.txt`。PyMuPDF (AGPL) 已隔离，可替换；其余 MIT/BSD。

## 当前状态（2026-06-08）

```
D:\Projects\MD\
├── README.md           # 对外
├── CHANGELOG.md        # 对内，每版必记
├── CLAUDE.md           # 本文件
├── requirements.txt
├── pdf_engine.py       # PDF 引擎薄接口 (PyMuPDF)
├── doc_engine.py       # DOC 引擎薄接口 (aspose-words-foss)
├── sniffer.py          # magika→filetype shim
├── InkDrop.spec        # PyInstaller 配置
├── build.bat / build.ps1  # 双击/CLI 构建
├── .github/workflows/  # CI（tag 触发自动发版）
├── .gitignore
├── versions/           # 开发迭代
│   ├── v1_demo.py
│   ├── ...
│   └── v14_custom_output.py
├── releases/           # 发布版本
│   └── v1.0.0.py       # 当前发布
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
| v14 | 自定义输出目录、config 移 exe 同级 | done |
| v1.0.0 | 首次正式发布 | done |

## 构建与发布

- 双击 `build.bat` 交互式构建（选版本+ZIP），命令行 `.\build.ps1 -Version latest -NoPause`
- UPX 装到 `D:\Tools\upx\`，构建时自动压缩（165→84 MB）
- CI: push tag `v*` 自动构建 + Release；也可 GitHub Actions 页面手动触发
- exe 名 `InkDrop.exe`，输出 `dist\InkDrop\`，ZIP `dist\InkDrop.zip`
- PyInstaller stderr 用 .NET Process 流式输出（PS 5.1 兼容）

## 改名记录 (2026-06-07)

- 项目名 MarkItDown GUI → InkDrop
- APP_NAME `markitdown-gui` → `inkdrop`
- 类名 `MarkItDownApp` 保留不动（库名，旧版本同理）
- 窗口标题 `InkDrop v{VERSION}`

## 格式支持

| 格式 | 文字 | 表格 | 图片 |
|------|------|------|------|
| PDF | ✅ | ✅ | ✅ (内嵌图片) |
| DOC | ✅ | ✅ | ✅ (doc_engine→.docx 管线) |
| DOCX | ✅ | ✅ | ✅ |
| PPTX | ✅ | ✅ | ✅ |
| XLSX/XLS | ✅ | ✅ | ❌ |
| 图片/邮件/ZIP | ❓ 未实测 |
| PPT | ❌ | ❌ | ❌ (提示用户另存 .pptx) |

