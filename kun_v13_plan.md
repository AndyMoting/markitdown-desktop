# Kun v13 Optimization Log (DeepSeek -> Claude handout)

> **作者**: Kun (DeepSeek v4 Pro, 2026-06-07)
> **给谁看**: Claude (下次接着改这个项目时参考)
> **基线**: v12_doc.py (1184 行)

---

## 1. v12 审计结论

v12 功能完整、bug 已修、无阻塞问题。本轮只做**无功能变更的结构/性能优化**。

### 审计发现清单

| # | 类别 | 位置 | 严重度 | 说明 |
|---|------|------|--------|------|
| A1 | 性能 | _convert_one() L370 | 中 | 每文件 new MarkItDown()，内部插件/MIME 探测重复初始化 |
| A2 | 结构 | _convert_one() | 高 | 单函数 ~200 行，杂糅 .doc 预处理 + markitdown + PDF 双引擎 + 图片 + 校验 |
| A3 | 重复 | L490-505 | 低 | "输出 < 20 字符" 检查在 PDF/非PDF 分支各写一遍，逻辑相同 |
| A4 | 死代码 | doc_engine.py | 低 | doc_to_text() / save_to_markdown() 从未被 v12 调用 |
| A5 | 资源 | _convert_one() finally | 低 | docx_temp 清理分两个 try/except，可用 tempfile 统一 |
| A6 | 代码 | _extract_images() | 低 | e.finditer + 手动切片拼接 -> e.sub + 回调更简洁 |

---

## 2. v13 改动方案

### 原则
- **零功能变更** — 同一个输入必须产出同一个输出
- **不改 UI** — tkinter 布局/交互不动
- **不引新依赖**

### 2.1 性能优化

**MarkItDown() 实例复用**

`
# v12: 每个文件 new 一次
for fp in file_paths:
    md = MarkItDown()          # <- 重复开销
    result = md.convert(...)

# v13: 线程内复用
md = MarkItDown()               # <- 只创建一次
for fp in file_paths:
    result = md.convert(...)
`

- 影响：批量 10 文件省 9 次插件加载 + MIME 初始化
- 风险：MarkItDown 实例是线程安全的（纯函数转换），无需担心

### 2.2 结构重构

**_convert_one() 拆分为 5 个小函数**

`
_convert_one(filepath, save_to_tool, md)
  ├── _preprocess_doc(filepath, ext, folder)      # .doc -> .docx 预处理
  ├── _call_markitdown(source_path, images_dir, md) # markitdown + 图片提取
  ├── _postprocess_pdf(filepath, text, img_count,
  │                     images_dir)                # PDF 双引擎 + 嵌入图片
  ├── _check_output_short(text, page_count=0)       # 输出校验（去重）
  └── _cleanup_docx_temp(docx_temp, folder)         # 临时文件清理
`

**好处**：
- 每个函数 20~60 行，可独立理解和测试
- PDF 逻辑和非 PDF 逻辑物理隔离
- 输出校验去重，PDF/非PDF 都走同一入口

### 2.3 死代码清理

doc_engine.py 删除两个未被调用的函数：
- doc_to_text() — markitdown 已经提供文本提取
- save_to_markdown() — 目前走 docx 管道更稳定

不影响功能，如需回溯可查 git / CHANGELOG。

### 2.4 代码简化

- _extract_images(): e.finditer + for 循环手动构建新字符串 -> e.sub + 回调闭包
- temp dir 清理: 统一用 shutil.rmtree（已存在），不再分 os.remove + mtree 两步

---

## 3. 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| 13_optimize.py | 新建 | 主文件，基于 v12 重构 |
| doc_engine.py | 修改 | 删除死代码 |
| CHANGELOG.md | 修改 | 追加 v13 条目 |
| CLAUDE.md | 修改 | 更新当前版本 |
| MarkItDown.spec | 修改 | 入口改为 v13_optimize.py |
| uild.ps1 | 修改 | 版本号字符串改为 v13 |
| kun_v13_plan.md | 新建 | 本文件，给 Claude 的交接日志 |

**不动**：pdf_engine.py、sniffer.py、equirements.txt

---

## 4. 验证清单

- [ ] 13_optimize.py 语法正确（Python 可 import）
- [ ] MarkItDown.spec 指向 13_optimize.py
- [ ] uild.ps1 引用 v13
- [ ] 打包成功（onedir, dist/MarkItDown/）
- [ ] 基本功能：GUI 启动 -> 添加文件 -> 转换 -> 输出正确

---

## 5. 给 Claude 的后续建议

1. v13 是纯重构，如果出 bug 大概率是函数签名传参问题。对比 v12 的 _convert_one 和 v13 的拆分版即可定位。
2. doc_engine.save_to_markdown() 已删，如果未来想绕过 markitdown 直接用 aspose 出 markdown，从 git 历史恢复即可。
3. 包体大小目标：保持 ~165MB（onedir），v13 不应引入新体积。
4. 如果 markitdown 未来升级改变了 API，检查 _call_markitdown() 即可，所有 markitdown 调用都在这一个函数里。
