# CHANGELOG

## Infrastructure — 2026-06-07

**文件**: `build.ps1`、`MarkItDown.spec`、`requirements.txt`、`.github/workflows/release.yml`

- `build.ps1` 重写: 支持 `-Version`/`-SkipZip`/`-NoPause`/`-SkipUPX` 参数，非交互模式适用于 CI
- `MarkItDown.spec`: PyInstaller 配置独立文件，入口由 build.ps1 按版本动态替换
- `requirements.txt`: 所有依赖锁定 `==x.y.z` 版本
- `.github/workflows/release.yml`: 推 tag 自动构建 + Release
- UPX 自动检测 (`D:\Tools\upx\` 或 PATH)，PyInstaller 自动调用压缩

---

## v13 — 2026-06-07 (Kun / DeepSeek v4 Pro)

**文件**: `v13_optimize.py`、`doc_engine.py`

**状态**: 纯重构，零功能变更。Kun 优化日志见 `kun_v13_plan.md`。

**性能优化**:
- `_convert_thread` 中复用 `MarkItDown()` 实例（批量 N 文件省 N-1 次初始化）
- CLI 模式 `_headless_convert` 同样复用

**结构重构** — `_convert_one()` 从 ~200 行拆分为 6 个函数:
- `_convert_one()` — 主流程，精简到 ~50 行
- `_preprocess_doc()` — .doc → .docx 预处理
- `_call_markitdown()` — markitdown 调用 + 图片提取
- `_postprocess_pdf()` — PDF 双引擎对比 + 嵌入图片 + 输出校验
- `_check_output_short()` — 输出量校验（PDF/非PDF 去重）
- `_cleanup_docx_temp()` — 临时文件清理

**代码简化**:
- `_extract_images()`: `re.finditer` + 手动切片 → `re.sub` + 回调闭包（更简洁）

**死代码清理**:
- `doc_engine.py` 删除 `doc_to_text()` 和 `save_to_markdown()`（从未被调用）

**注意给 Claude**:
- `_convert_one` 新签名: `(filepath, save_to_tool, md=None)`，第三个参数传入复用的 MarkItDown 实例
- 如需还原死代码，从 git/v12 历史恢复


## v12 — 2026-06-07

**文件**: `v12_doc.py`、`doc_engine.py`、`pdf_engine.py`、`sniffer.py`

**状态**: 代码清理 + 新增 .doc 支持

**新增**:
- .doc (Word 97-2003 二进制) 支持: `doc_engine.py` 薄接口, 内部用 aspose-words-foss (MIT) 先转 .docx 再走 markitdown DOCX 管线, 文字+表格+图片全保留
- 依赖: `aspose-words-foss>=26.4.0` → fpdf2 + fonttools + pydantic, 纯 Python, MIT
- 设置窗口新增 "旧版 Word 文档 (.doc)" 引擎状态行

**代码清理** (v11 审计):
- magika shim: `type(sys)(_mod)` → `types.ModuleType()`, 注释改成 3 行关键信息
- `self._thread = None`: `__init__` 里显式初始化, 删掉 `hasattr` 防御
- `_init_logging()` + `_configure_log_levels()`: 拆开初始化和级别切换
- `ConvertResult` NamedTuple: `_convert_one` 不再返回语义重载的裸 tuple
- `_extract_images`: 展开嵌套闭包+nonlocal, 改为 finditer + parts 线性拼接
- 日志文件名: 硬编码 v11 → VERSION 变量
- 临时目录清理: `os.rmdir` → `shutil.rmtree`
- `sniffer.py` `__eq__`: 处理 str 反向比较, `return NotImplemented`
- `doc_engine.py`: 删 `import shutil` 死代码
- spec 更新: hiddenimports 加 doc_engine + aspose.words_foss

**审计修复** (2026-06-07):
- 取消按钮: `_convert_thread` 和 `_on_one_success` 加 `cancel_event` 二次检查，防止延迟回调污染已取消的 UI
- PDF 图片去重: `pdf_engine.extract_images` 加 `seen_xref` 缓存，同 xref 跨页出现只存一次
- 依赖提示: `sniffer.py` filetype 导入加 try/except，缺库时打印中文安装提示而非 traceback
- 临时文件安全: `doc_engine.doc_to_docx` 接收 `work_dir` 参数，临时 docx 写入输出目录，`rmtree` 前校验不删输出目录
- `sniffer.py` `ContentTypeLabel.__hash__`: 删除重复定义
- 日志目录: `open_log_dir` 打开前确保目录存在
- .ppt 友好提示: 检测到 .ppt 文件时告知用户用 PowerPoint 另存为 .pptx，不报技术错误
- 打包修复: magika shim 注入移到 markitdown 导入之前，修复 exe 启动崩溃

## v11 — 2026-06-07

**文件**: `v11_tidy.py`、`pdf_engine.py`、`sniffer.py`

**状态**: 整理版本，不引入新功能

**改动**:
- 抽 `pdf_engine.py` 薄接口：`is_available()` / `extract_text()` / `extract_images()`，隔离 PyMuPDF，未来可零成本切引擎
- 删 v10 中三个 PyMuPDF 直接函数（`_get_fitz`、`_extract_pdf_images`、`_extract_pdf_text_pymupdf`），主文件不再 `import fitz`
- 修 Bug 1：关窗崩溃 — `_on_close` 先 `cancel_event.set()` + `thread.join(timeout=3)` 再 `root.destroy()`
- 修 Bug 2：日志双重切换 — `toggle_debug` 改为调用 `_setup_logging()`，不再手动操作 handler level
- 修 Bug 3：daemon 线程 — `_start_convert` 设 `daemon=True` + `self._thread`，关窗时 OS 自动回收
- 修 Bug 4：PyMuPDF 对话 guard — `_show_pymupdf_dialog(args)` 在 `args.convert` 时跳过 GUI 弹窗
- 打包切 `--onedir`：启动秒开，分发为文件夹
- `sniffer.py`：magika→filetype shim，省 ~42MB（magika + onnxruntime + flatbuffers + protobuf），`requirements.txt` 加 `filetype>=1.2.0`
- spec excludes 追加 pypdfium2（白占 7MB）和 magika/onnxruntime（已替换），raw 192→160MB，zip 88→75MB

## v10 — 2026-06-04

**文件**: `v10_test.py`

**状态**: 打包测试分支，基于 v9_clean.py，功能代码完整保留

**改动**:
- 版本号 10.0.0，log 前缀 `v10_`
- 代码与 v9 一致（CLI 完整保留），后续只调整打包参数
- 修复: 窗口最大化关闭不保存 geometry，恢复时校验尺寸

---

## v9 — 2026-06-04

**文件**: `v9_clean.py`、`requirements.txt`

**改动 (工程化)**:
- 文件头代码导航: 8 节索引，30 秒定位目标代码
- 死代码清理: 删除未使用的 `atexit`、`subprocess`
- 节头规范化: 统一 `====` 样式，8 个独立区域可 grep
- `requirements.txt`: 记录所有依赖及版本，PyMuPDF 注释说明 AGPL
- 细节: log 文件名 `v9_` 前缀、版本号 9.0.0

**修复** (2026-06-04):
- 窗口 geometry: 最大化关闭不再保存全屏尺寸，恢复时校验尺寸不超过屏幕

---

## v8 — 2026-06-04

**文件**: `v8_review.py`

**改动 (全面审查修复)**:

**关键修复**:
- 线程安全: `_result_folders` 操作全部移到主线程，`_add_files`/`_remove_selected` 加 `running` guard
- Config 健壮性: `_load_config` 区分异常类型并 log，`_save_config` 返回 bool 不再静默吞错
- PyMuPDF 开关生效: `_get_fitz()` 和 `_convert_one` 检查 `pymupdf_accepted` 配置，未启用则完全跳过
- 文本对比算法: `_text_diff_ratio` 改用字符集交集 + 长度比较替逐位对齐，消除误判
- Frozen 模式路径: 输出到 `%APPDATA%\markitdown-gui\output\` 替代 `sys.executable` 目录
- PDF 优化: `_convert_one` 中只打开一次 fitz doc，三个函数复用
- 图片错误处理: `base64.b64decode` 加 try/except，零字节图片跳过并 log

**UX 改进**:
- 文件对话框标签中文化 ("支持的文件" / "所有文件")
- 高 DPI 支持 (Windows `SetProcessDpiAwareness`)
- 键盘快捷键: Enter 转换, Delete 删除选中
- 拖拽文件夹自动递归展开添加文件
- 拖放解析增强: 后备使用 `shlex.split` 处理含空格路径
- 进度条完成/取消后归零
- 设置窗口屏幕边界 clamp
- 输出文件夹原子化创建 (TOCTOU 修复)
- 纯文本检测正则修正 (不再误删连字符)

**修复** (2026-06-04):
- 窗口 geometry 保存/恢复: 最大化关闭不再保存，恢复后校验尺寸不超过屏幕

**已知限制 (文档化)**:
- CMap 映射错误: 两个引擎输出一致但都错的 PDF 文字无法自动检测
- 取消粒度: 仅文件间检查，单文件大 PDF 转换中无法中断 (markitdown API 限制)
- 异形图片编码: JBIG2/JPX/CMYK 原样保留不转码
- 无图片去重: 跨页重复 logo/水印保存多份

---

## v7 — 2026-06-04

**文件**: `v7_polish.py`

**改动**:
- Debug/logging 系统：`--debug` 开启日志输出到 `%TEMP%\markitdown-gui\`，保留最近 10 个
- Cancel 按钮：转换中可中断，`threading.Event` + Convert/Cancel 切换
- Save to tool folder：checkbox 勾选后输出到工具目录 `output/` 子目录
- Open Folder：结果行可点击打开文件夹，底部 "Open All Folders" 按钮
- CLI 参数：`--help` `--version` `--debug` `--convert` `--save-to-tool`
- 窗口记忆：退出时保存位置/大小到 `%APPDATA%\markitdown-gui\config.json`
- PyMuPDF 许可证弹窗：首次启动提示 AGPL 许可，用户选择 Enable/Skip
- PyMuPDF 懒加载：`import fitz` 按需导入，没选 Enable 不影响其他功能
- PDF 中文编码修复：检测乱码比例，严重时用 PyMuPDF `get_text()` 替代 pdfplumber

---

## v6 — 2026-06-04

**文件**: `v6_pdf_images.py`

**改动**:
- PDF 内嵌图片提取：PyMuPDF (`fitz`) 逐页提取，存为 `pdf_p{页码}_i{序号}.jpg`
- 提取的图片追加到 markdown 末尾 "PDF Embedded Images" 段落，按页码分组
- 新增依赖: PyMuPDF (fitz)

**效果**：测试 PDF 第 3 页的 1 张内嵌图片被提取出来（41 KB jpg），之前 v5 及更早版本 PDF 无图片输出。

**已知限制**:
- PDF 扫描件/渲染型 PDF（无内嵌图片元数据）无法用此方式提取，需用 PDF 页渲染方案
- `.doc` 未支持

---

## v5 — 2026-06-04

**文件**: `v5_dragdrop.py`

**改动**:
- 拖拽文件到窗口，自动加入列表（tkinterdnd2）
- root 和 listbox 均注册为 drop target，支持拖放到窗口任意位置
- 解析 `{path1} {path2} ...` 格式的拖放数据
- Add Files 按钮保留，两种方式并存
- 依赖: `tkinterdnd2`

**注意**: 初版用 Win32 ctypes（WM_DROPFILES），64-bit Python 上 SetWindowLongPtrW 崩溃，改用 tkinterdnd2。

---

## v4 — 2026-06-04

**文件**: `v4_batch.py`

**改动**:
- 批量转换：一次选多个文件
- 后台线程：转换不卡界面，实时看进度
- 进度条 + 结果列表（绿色 ✓ / 红色 ✗）
- 每完成一个文件立刻显示结果
- 最后汇总：N 成功 M 失败
- 窗口可缩放，列表和结果区自适应

---

## v3 — 2026-06-04

**文件**: `v3_output.py`

**改动**:
- 图片存为独立文件到 `images/` 子目录，不再塞 base64 进 markdown
- 输出到同名文件夹：`{文件名}_converted/`
  ```
  Doc1_converted/
    ├── Doc1_converted.md
    └── images/
        ├── img_001.png
        └── img_002.png
  ```
- 新增 checkbox：可选择保存到工具目录

**效果**：PPTX 的 md 文件从 1525 KB 降到 13 KB，所有图片独立存储

**已知限制**:
- PDF 图片不保留
- `.doc` 未支持

---

## v2 — 2026-06-04

**文件**: `v2_compat.py`

**改动**:
- 安装缺失依赖：`pdfminer.six` + `pdfplumber`（PDF）、`mammoth`（DOCX）、`pandas` + `openpyxl`（XLSX）、`xlrd`（XLS）
- `keep_data_uris=True`：DOCX/PPTX 等格式的图片以 base64 保留在 markdown 中
- 文件筛选器补充 `.epub`、`.xml`

**已知限制**:
- PDF 图片不保留（pdfplumber 只提取文字，待后续用 PyMuPDF 处理）
- `.doc` 未支持

---

## v1 — 2026-06-03

**文件**: `v1_demo.py`

**功能**:
- 最小 GUI：文件选择 + 一键转换
- 调用 markitdown Python API (`MarkItDown().convert()`)
- 输出 `{原文件名}_converted.md` 到同目录
- 同名去重：自动加序号 `(1)`、`(2)`...
- 异常弹窗提示

**技术栈**: tkinter + markitdown，零额外依赖

**限制**:
- 不支持拖拽
- 不支持批量
- PDF/XLSX/DOC 不可用（缺依赖或格式不支持）
