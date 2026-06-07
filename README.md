# MarkItDown GUI

文档转 Markdown 桌面工具。拖拽文件 → 一键转换 → 输出 Markdown + 图片。

## 功能

| 格式 | 文字 | 表格 | 图片 |
|------|:----:|:----:|:----:|
| PDF | ✅ | ✅ | ✅ (内嵌图片) |
| DOC | ✅ | ✅ | ✅ |
| DOCX | ✅ | ✅ | ✅ |
| PPTX | ✅ | ✅ | ✅ |
| XLSX / XLS | ✅ | ✅ | ❌ |
| HTML / CSV / JSON / XML / TXT | ✅ | ❌ | ❌ |
| 图片 / 邮件 / ZIP | ❓ 未实测，markitdown 声称支持 |
| PPT | ❌ 提示用户另存为 .pptx | | |
| PPT | ❌ 提示用户另存为 .pptx | | |

- 批量转换 + 拖拽添加文件
- PDF 双引擎（pdfplumber 文字 + PyMuPDF 内嵌图片）
- .doc 自动转 .docx 后处理
- 图片提取为独立文件，不污染 Markdown
- 后台线程，不卡界面

## 下载

[GitHub Releases](https://github.com/你的用户名/MD/releases) 下载 `MarkItDown.zip`，解压后运行 `MarkItDown.exe`。

## 自己构建

双击 `build.bat`，选版本号，回车。需 Python 3.12 + venv。

```
# 首次环境
python -m venv D:\Projects\.venv
D:\Projects\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 构建
.\build.ps1 -Version latest
```

可选：装 [UPX](https://github.com/upx/upx/releases) 到 `D:\Tools\upx\`，构建时自动压缩，体积减半。

## 项目结构

```
├── build.bat / build.ps1     # 构建入口（双击/命令行）
├── MarkItDown.spec           # PyInstaller 配置
├── requirements.txt          # 依赖（版本锁定）
├── pdf_engine.py             # PDF 引擎薄接口 (PyMuPDF)
├── doc_engine.py             # DOC 引擎薄接口 (aspose-words-foss)
├── sniffer.py                # 文件类型检测 shim
├── versions/                 # 各版本源码（v1-v13）
├── samples/                  # 测试样本
└── .github/workflows/        # CI（tag 触发自动发版）
```

## 版本迭代规则

- 每个版本独立文件 `vN_xxx.py`，不在旧版上改
- 改动记录 `CHANGELOG.md`

## 许可

本项目 MIT。PyMuPDF 为 AGPL，通过 `pdf_engine.py` 隔离，可替换。
