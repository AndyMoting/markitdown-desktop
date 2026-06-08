# markitdown-desktop — 项目归档说明

**状态**：已归档，停止功能开发。  
**结论**：经场景验证，目标用户群不存在。  
**替代方案**：[microsoft/markitdown](https://github.com/microsoft/markitdown)（官方 CLI）

```bash
pip install markitdown[all]
markitdown file.pdf > file.md
```

---

## 1. 项目背景与假设

验证假设：为 `markitdown` 提供 Windows 原生 GUI，可降低非技术用户的文档转 Markdown 门槛。

- **输入**：PDF、DOC、DOCX、PPTX、XLSX、HTML、CSV、JSON、XML、TXT、图片、邮件、EPUB、ZIP
- **输出**：Markdown + 内嵌图片提取
- **目标用户**：不熟悉命令行、需要批量文档转换的 Windows 用户

---

## 2. 验证方法

快速迭代，6 天完成 16 个版本（v1_demo → v14_custom_output → v1.0.0），覆盖以下工程维度：

| 维度 | 验证内容 | 迭代版本 |
|------|---------|---------|
| GUI 框架 | tkinter 拖拽、批量队列、进度反馈 | v1-v5 |
| 格式引擎 | markitdown 核心 + PDF 双引擎纠错 + DOC 桥接 | v6-v12 |
| 打包分发 | PyInstaller onefile / onedir / UPX 压缩 | v9-v10 |
| 稳定性 | 线程安全、编码处理、日志一致性 | v11-v14 |
| 发布验证 | 端到端测试、CI 构建、版本发布 | v1.0.0 |

---

## 3. 验证结论

**目标用户群不存在。**

- 具备文档批量处理需求的用户，已具备命令行基础能力；
- 不具备命令行能力的用户，无 Markdown 使用场景；
- 官方 CLI 一行命令即可覆盖全部需求，GUI 封装无增量价值。

项目归档，资源释放。

---

## 4. 技术实现概要（供参考）

### 4.1 架构

```
GUI (tkinterdnd2) → CLI (doc2md.py) → 引擎层 → 输出
                         ↓
              ┌─────────┴─────────┐
         pdf_engine.py    doc_engine.py    sniffer.py
         (PyMuPDF)        (aspose-words)   (filetype shim)
```

### 4.2 关键设计决策

| 决策 | 原因 | 代价 |
|------|------|------|
| PDF 双引擎（pdfplumber + PyMuPDF）| 单引擎对复杂 PDF 提取失败率高 | 同一文件重复 I/O，性能损耗 |
| AGPL 隔离（pdf_engine.py 懒加载）| PyMuPDF 为 AGPL-3.0，需避免主程序传染 | 增加模块边界复杂度 |
| .doc 桥接（aspose-words-foss）| markitdown 原生不支持 .doc | 引入第三方依赖，空白模板风险 |
| filetype 替代 magika | magika 模型 42MB，打包体积敏感 | MIME 识别准确率下降 |

### 4.3 已知限制

- 仅支持 Windows（tkinterdnd2 依赖）
- 打包产物 84MB（onedir）或 8 秒启动（onefile）
- PyMuPDF AGPL 协议传染性未完全消除（静态链接场景）

---

## 5. 项目结构（清理后）

```
markitdown-desktop/
├── doc2md.py              # CLI 入口，零 GUI 依赖
├── pdf_engine.py          # PDF 引擎（AGPL 隔离）
├── doc_engine.py          # DOC 引擎
├── sniffer.py             # 文件类型嗅探（magika API shim）
├── build.ps1 / build.bat  # PyInstaller 构建脚本
├── InkDrop.spec           # PyInstaller 配置
├── requirements.txt       # 依赖清单
├── CHANGELOG.md           # 16 版本迭代记录
├── 复盘.md                 # 需求验证与工程决策记录
├── 文件阅读规范.md         # 各格式读写参考
├── .github/workflows/     # CI 配置（已停用）
└── README.md              # 本文件
```

历史版本见 Git 记录：`git log --all --full-history -- versions/`

---

## 6. 构建（归档状态，仅供技术参考）

```bash
pip install -r requirements.txt
python doc2md.py file.pdf              # CLI 直接运行
powershell -File build.ps1              # 构建 GUI 产物（约 84MB）
```

---

## 7. 依赖与合规风险

| 依赖 | 协议 | 说明 |
|------|------|------|
| markitdown | MIT | 无风险 |
| PyMuPDF | AGPL-3.0 | ⚠️ 打包进可执行文件可能触发协议传染 |
| aspose-words-foss | MIT | 非官方 aspose 分支，功能受限 |
| tkinterdnd2 | MIT | Windows 拖拽支持，部分环境需额外 DLL |

**注意**：若将 PyMuPDF 静态链接或打包进独立可执行文件，整个产物可能需遵循 AGPL-3.0 协议。企业使用前应进行合规审查。

---

## 8. 相关文档

- [复盘.md](复盘.md) —— 需求验证过程与工程决策分析
- [CHANGELOG.md](CHANGELOG.md) —— 版本迭代与技术债务记录
- [文件阅读规范.md](文件阅读规范.md) —— 各格式读写实现参考
- [microsoft/markitdown](https://github.com/microsoft/markitdown) —— 推荐使用的官方工具

---

## 9. 许可

MIT License。  
**法律提示**：包含 AGPL 依赖的打包产物协议状态未经验证，使用风险自负。

🔒 2026-06-08 更新：已移除所有含个人信息的测试样本，并从 Git 历史彻底删除。
