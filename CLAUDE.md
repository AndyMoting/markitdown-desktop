# doc2md（原 InkDrop）

活跃维护中（2026-07-26 重启，曾于 2026-06 归档，验证记录见 复盘.md）。
形态：`doc2md` Python 包 = CLI 核心 + CustomTkinter GUI（`doc2md-gui`）。
已决策：不做 Web 方向；FastAPI 旧线只留在 backup/web-gui-0721 分支。

## 铁律

- **commit 不加 Co-Authored-By**，不挂 AI 名字在贡献者列表
- `CHANGELOG.md` 每版必记
- 先写计划
- 新建 venv 后先 `pip install -r requirements.txt`，否则所有文件都报 ModuleNotFoundError
- `convert_one` 签名: `(filepath, output_root=None, md=None, use_pymupdf=True, on_conflict="rename")`，*md* 传入复用的 MarkItDown 实例；*filepath* 可为 http(s) URL
- 改 GUI 前先读 `.interface-design/system.md`（设计决策已定）和
  `.claude/skills/interface-design`；显示中文的组件禁用 Segoe UI/Consolas（无 CJK 字形）
- GUI 验证用 scratchpad 的 PrintWindow 截图脚本实看，不要只跑不看

## 运行环境

- venv: `D:\Projects\.venv\Scripts\python.exe`（Python 3.12）
- 依赖见 `requirements.txt`。PyMuPDF (AGPL) 已隔离在 `doc2md/engines/pdf.py`（懒加载），可替换；其余 MIT/BSD。

## 当前状态（2026-07-26, v2.1.0）

```
markitdown-desktop/
├── doc2md/                  # Python 包（cli/gui/convert/images/quality/engines）
├── .interface-design/       # GUI 设计系统（改 UI 先读）
├── .claude/skills/          # interface-design 项目 skill
├── pyproject.toml           # 入口点: doc2md / doc2md-gui；extras: pdf/doc/gui/all
├── requirements.txt
├── README.md                # 对外
├── CHANGELOG.md             # 对内，每版必记
└── CLAUDE.md                # 本文件
```

运行：仓库根 `python -m doc2md file.pdf`（CLI）/ `python -m doc2md.gui`（GUI）。
GUI 的 config/logs 在 `%APPDATA%\doc2md\`。
历史（InkDrop GUI versions/releases、PyInstaller、CI）全部在 Git 记录里。

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
| v2.0.0 | 平铺脚本 → doc2md 包 + pyproject 入口点 | done |
| v2.1.0 | 重启：GUI 回归（CustomTkinter 双主题双栏工作台）+ 解除归档 | done |
| v2.2.0 | 同名输出策略 + URL 转换 + 回执行联动 + Markdown 预览 | done |

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

