# 📝 InkDrop

文档转 Markdown 桌面工具。拖拽文件进来，一键转成 Markdown，图片自动提取为独立文件。

## 下载

[Releases](https://github.com/你的用户名/md/releases) 下载 `InkDrop.zip`，解压运行 `InkDrop.exe`，无需安装。

## 支持的格式

| 格式 | 文字 | 表格 | 图片 |
|------|:----:|:----:|:----:|
| PDF | ✅ | ✅ | ✅ 内嵌图片 |
| Word (.doc / .docx) | ✅ | ✅ | ✅ |
| PowerPoint (.pptx) | ✅ | ✅ | ✅ |
| Excel (.xlsx / .xls) | ✅ | ✅ | ❌ |
| HTML / CSV / JSON / XML / TXT | ✅ | ❌ | ❌ |
| PPT (旧版) | ❌ 请用 PowerPoint 另存为 .pptx | | |

## 使用

1. 打开 `InkDrop.exe`
2. 拖拽文件进来（或点 Add Files）
3. 点 Convert，等待完成
4. 输出在每个文件的 `*_md/` 子目录

支持批量转换、取消、窗口位置记忆。

## 构建

```
pip install -r requirements.txt
powershell -File build.ps1
```

产物在 `dist\InkDrop\`。装 [UPX](https://github.com/upx/upx/releases) 到 `PATH` 可压缩一半体积。

## 许可

MIT。依赖 PyMuPDF (AGPL) 通过 `pdf_engine.py` 隔离，可替换。
