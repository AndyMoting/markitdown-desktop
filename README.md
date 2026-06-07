# InkDrop

拖文件进去，点按钮，出 Markdown。基于 [markitdown](https://github.com/microsoft/markitdown)，跟 AI 边聊边做，做完发现一行命令就够了。

## 背景

看到一篇文章讲 markitdown——文档转 Markdown，AI 直接消费。顺手想到打包成 exe，不写代码的人也能用。这个念头太顺了，搜都没搜就开始写。

第一晚写到清晨 5 点，一口气 10 个版本：批量、拖拽、后台线程、进度条、PDF 双引擎纠错、内嵌图片提取、日志系统。隔两天补了 .doc 桥接、CLI、CI/CD，打成 84MB exe。

发布当晚追了三个连环 bug 到凌晨 2 点。修完盯着跑通的 exe，突然意识到——

```powershell
pip install "markitdown[all]"
python -c "from markitdown import MarkItDown; print(MarkItDown().convert('file.pdf').text_content)"
```

会用命令行的不需要 GUI，需要 GUI 的不知道 markitdown。需求是自己编的。

一周，16 个版本，三个连环 bug，六七十块 API。买了句"不做错的事比做好错的事重要"。详见 [复盘](复盘.md)。

## 支持的格式

| 格式 | 文字 | 表格 | 图片 | 备注 |
|------|:----:|:----:|:----:|------|
| PDF | + | + | + | 内嵌图片，双引擎纠错 |
| DOC / DOCX | + | + | + | .doc 经 aspose 桥接 |
| PPTX | + | + | + | |
| XLSX / XLS | + | + | - | |
| HTML / CSV / JSON / XML / TXT | + | - | - | |
| 图片 / 邮件 / ZIP | ? | ? | ? | 未实测 |
| PPT | - | - | - | 另存 .pptx 后重试 |

## 怎么做的

约束就一个：一个 exe，不用装 Python，能跑。

每个选择退路都只有一条，意味着每个方案在动手前就要想清楚代价再接受。不是解决才冒出来的问题，是提前看到了前面的坑。

GUI 没得选。PyQt 要商业授权，Electron 打包 200MB。tkinter 丑，但 Python 自带、打包零配置。

PDF 单一引擎是残次品——pdfplumber 中文常乱码，PyMuPDF 中文好但 AGPL 协议。两个都跑、自动选优、隔离代码——这是约束下的最优解，不是堆功能。PyMuPDF 拆到 [pdf_engine.py](pdf_engine.py)，跟 MIT 隔离。

.doc 是捡来的。准备放弃时碰巧搜到 aspose-words-foss（MIT），纯 Python 能转。`.doc → aspose → .docx → markitdown`，用户无感。

文件检测不用 magika。 Google 的 AI 模型打包 42MB，filetype.py 几 KB 干一样的事。[sniffer.py](sniffer.py) 桥接——开发时用 magika，打包自动切 filetype。

打包 onedir 不用 onefile。onefile 启动 8 秒，onedir 秒开，UPX 压到 84MB，U 盘直接跑。

[pdf_engine.py](pdf_engine.py)、[doc_engine.py](doc_engine.py)、[sniffer.py](sniffer.py) 各管一块，GUI 和 [doc2md.py](doc2md.py) CLI 共享同一套核心。[build.bat](build.bat) 双击选版本，[build.ps1](build.ps1) 给 CI。

## 项目结构

```
releases/v1.0.0.py     build.bat / build.ps1
versions/v1-v14.py     InkDrop.spec
doc2md.py              .github/workflows/
pdf_engine.py          samples/
doc_engine.py          CHANGELOG.md / 复盘.md
sniffer.py             文件阅读规范.md / LICENSE
```

## 构建

```bash
pip install -r requirements.txt
powershell -File build.ps1       # 产物 dist\InkDrop\，约 84MB
python doc2md.py file1 file2     # CLI 直接跑，不需要构建
```

装 [UPX](https://github.com/upx/upx/releases) 到 `D:\Tools\upx\` 自动压缩。

## 版本

16 个文件，从 demo 到放弃，每个阶段可追溯：

| 版本 | 核心 |
|------|------|
| [v1](versions/v1_demo.py) | 最小 GUI |
| [v2](versions/v2_compat.py) | 补齐依赖 |
| [v3](versions/v3_output.py) | 图片独立文件 |
| [v4](versions/v4_batch.py) | 批量+线程+进度条 |
| [v5](versions/v5_dragdrop.py) | 拖拽 |
| [v6](versions/v6_pdf_images.py) | PDF 内嵌图片 |
| [v7](versions/v7_polish.py) | 日志、Cancel、CLI |
| [v8](versions/v8_review.py) | 线程安全、双引擎 |
| [v9](versions/v9_clean.py) | 死代码清理 |
| [v10](versions/v10_test.py) | 首次打包 |
| [v11](versions/v11_tidy.py) | 引擎抽离、瘦身 |
| [v12](versions/v12_doc.py) | .doc 支持 |
| [v13](versions/v13_optimize.py) | 实例复用 |
| [v14](versions/v14_custom_output.py) | 自定义输出 |
| **[v1.0.0](releases/v1.0.0.py)** | 正式发布 |
| **v1.0.1** | 致命修复 |

第一晚 v1 到 v10（06-03 23:00 → 06-04 05:15），隔两天 v11 到 v14 加 v1.0.0（06-07 → 06-08 凌晨）。详见 [CHANGELOG.md](CHANGELOG.md)。

## 依赖

[markitdown](https://github.com/microsoft/markitdown) · [PyMuPDF](https://github.com/pymupdf/PyMuPDF) · [pdfplumber](https://github.com/jsvine/pdfplumber) · [aspose-words-foss](https://pypi.org/project/aspose-words-foss/) · [python-pptx](https://github.com/scanny/python-pptx) · [pandas](https://github.com/pandas-dev/pandas) · [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) · [filetype](https://github.com/h2non/filetype.py) · [PyInstaller](https://github.com/pyinstaller/pyinstaller) · [UPX](https://upx.github.io/)

更多格式读写参考 [文件阅读规范](文件阅读规范.md)。

## 许可

MIT。PyMuPDF (AGPL) 隔离在 [pdf_engine.py](pdf_engine.py)，可替换。
