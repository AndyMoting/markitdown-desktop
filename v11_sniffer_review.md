# magika→filetype shim 审计背景

## 项目背景

### 是什么

MarkItDown GUI — 给微软 [markitdown](https://github.com/microsoft/markitdown) 做的 Windows 桌面工具。用户拖拽/批量选文件 → 一键转为 Markdown + 提取图片 → 输出到文件夹。技术栈 tkinter + PyMuPDF + markitdown，PyInstaller 打包为便携 exe，通过 GitHub Releases 分发。

### 目标用户

个人用户，场景是自己转自己的文档（工作文件、学习资料等），不处理陌生人上传。Windows 桌面环境，有文件扩展名。

### 核心约束

- **便携**：用户不装 Python，下载解压双击即用
- **体积敏感**：GitHub Releases 分发，压缩包越小下载越快
- **功能无损**：所有格式转换能力不能降级
- **依赖合规**：全部 MIT/BSD，PyMuPDF AGPL 已做引擎隔离（`pdf_engine.py` 薄接口，未来可零成本切引擎）

### 版本状态

v11 整理版本，不引入新功能。基于 v10 修 4 个 bug + 抽 pdf_engine + 切 onedir 打包。sniffer shim 是打包体积优化过程中顺带做的。

## 依赖链

### markitdown[all] 拖进来的全家桶

```
markitdown[all]
├── magika          #  3MB  文件类型 ML 检测（Google）
│   ├── onnxruntime # 33MB  神经网络推理引擎（Microsoft）
│   ├── flatbuffers #  0.5MB 序列化库（Google）
│   └── protobuf    #  1MB   序列化库（Google）
├── pdfplumber      #  8MB  PDF 文字提取
│   ├── pdfminer    #  8MB  PDF 解析底层
│   └── pypdfium2   #  7MB  PDF 页渲染（仅 page.to_image() 用到）
├── python-pptx     #  1MB  PPTX 转换
├── pandas + numpy  # 27MB  XLSX/XLS 转换
├── openpyxl        #       XLSX
├── xlrd            #       XLS
├── mammoth         #       DOCX
├── PIL             # 13MB  图片处理
├── cryptography    # 10MB  加密（依赖链）
└── magika → onnxruntime + flatbuffers + protobuf (~36MB)
```

### 本项目直接引入的

| 库 | 大小 | 用途 |
|----|------|------|
| PyMuPDF | 37MB | PDF 内嵌图片提取（C 扩展 + DLL） |
| tkinterdnd2 | 0.3MB | 拖拽 |
| filetype | 19KB | 文件类型检测（替代 magika） |
| sniffer | ~3KB | magika API shim（本项目手写） |
| pdf_engine | ~5KB | PyMuPDF 薄接口（本项目手写） |

### 打包后体积分布（160MB onedir）

| 组件 | raw | 能否砍 |
|------|-----|--------|
| PyMuPDF (.pyd+.dll) | 37MB | 核心功能 |
| onnxruntime | — | 已砍 (magika→filetype) |
| numpy+pandas+numpy.libs | 27MB | XLSX 必需 |
| PIL | 13MB | 图片处理 |
| cryptography | 10MB | 依赖链 |
| pdfminer | 8MB | PDF 文字 |
| Python+tcl/tk 运行时 | 13MB | 不能砍 |
| 其他 DLL/PYD | 50MB | 依赖链 |
| **pypdfium2_raw** | — | 已砍 (exclude) |
| **magika/onnx/flat/proto** | — | 已砍 (sniffer) |

## 问题

markitdown 硬依赖 magika（Google 的深度学习文件类型检测器），magika 又强行拖入 onnxruntime（33MB）+ flatbuffers + protobuf。这些库对文档转换无实际价值——markitdown 只把 magika 的输出当"二次确认"，主判断是文件扩展名。

在这个项目的场景下（用户拖带扩展名的文件，不是做安全扫描），用 ML 模型猜文件类型是大炮打蚊子。

PyInstaller 打包后这些依赖占 ~42MB（raw），zip 后约 ~13MB。

## 方案

用 `filetype`（19KB，零依赖，纯魔数匹配）替代 magika。写一个 `sniffer.py` thin shim，实现 magika 被 markitdown 用到的 API 子集，在 `import markitdown` 前注入 `sys.modules["magika"] = sniffer`。

## magika→markitdown 接口合约（仅这些被用到）

文件：`markitdown/_markitdown.py`

```python
# Line 15
import magika

# Line 121 — 只调一次构造函数
self._magika = magika.Magika()

# Line 724 — 唯一的方法调用
result = self._magika.identify_stream(file_stream)

# 用到的 result 字段：
result.status                                    # 比较 == "ok"
result.prediction.output.label                   # 比较 != "unknown"
result.prediction.output.mime_type
result.prediction.output.extensions              # 取 [0] 作为扩展名
result.prediction.output.is_text                 # bool
```

markitdown **从不调用** `Magika` 的任何其他方法，不接触 model path，不调 `identify_bytes`。

## sniffer.py 实现要点

### 返回类型

用 `dataclass` + `Enum` 模拟 magika 的返回结构，匹配上述字段名和类型：

```
MagikaResult
  .status: Status(OK="ok")
  .prediction: MagikaPrediction
    .output: ContentTypeInfo
      .label: ContentTypeLabel(value=str)  — 枚举值，支持 == 字符串比较
      .mime_type: str
      .extensions: list[str]
      .is_text: bool
```

关键：`ContentTypeLabel.__eq__` 同时支持与 `ContentTypeLabel` 和 `str` 比较，因为 markitdown 写的是 `label != "unknown"`。

### identify_stream 逻辑

1. 用 `filetype.guess(file_stream)` 读魔数 → 匹配到返回结果
2. 没匹配到 → 从 `file_stream.name` 取扩展名 → 查 `_EXT_TO_MIME` 映射表（html/csv/json/xml/txt/eml 等文本格式）
3. 也拿不到 → 返回 label="unknown"

### 对 file_stream 的副作用

markitdown 在调 `identify_stream` 后会自己 `seek(0)` 重新读流，所以 sniffer 不需要保证流位置不变。但为安全起见实现了 `tell()` / `seek()` 恢复。

## 注入点（v11_tidy.py 第 38-47 行）

```python
import sniffer
sys.modules["magika"] = sniffer
for _mod in ("onnxruntime", "flatbuffers", "protobuf"):
    if _mod not in sys.modules:
        sys.modules[_mod] = type(sys)(_mod)
```

必须在 `from markitdown import MarkItDown` 之前执行。

> **v12 已修正**: `type(sys)(_mod)` → `types.ModuleType(_mod)`，注释精简为 3 行升级检查说明。

## 打包排除

`MarkItDown.spec` 的 excludes 列表：`['pypdfium2', 'pypdfium2_raw', 'magika', 'onnxruntime', 'flatbuffers', 'protobuf']`

hiddenimports 显式声明：`['fitz', 'pymupdf', 'sniffer', 'filetype', 'pdf_engine']`

## 已验证

11 种格式全部通过：PDF/DOCX/PPTX/XLSX/XLS/DOCX(多文件)/TXT，转换结果与使用原生 magika 时一致。

## 已知风险

1. **filetype 覆盖盲区**：不认识 `.md` `.rst` `.ini` 等文本格式（无魔数），fallback 到扩展名。只要文件有扩展名就不影响。
2. **流不带 name 属性**：如果 markitdown 未来传纯 BytesIO（name=None），`_guess_from_path` 返回空，最终 label="unknown"。markitdown 的 `_get_stream_info_guesses` 会回退到扩展名/mimetypes 猜测，转换仍能完成，但可能走错 converter。
3. **ContentTypeLabel 的类型身份**：如果 markitdown 未来用 `isinstance(label, Enum)` 而非 `== "unknown"`，我们的 dataclass 会露馅。
4. **markitdown 升级**：新版本可能新增 magika API 调用（如 `identify_bytes`、`model_path` 参数），shim 需同步更新。
