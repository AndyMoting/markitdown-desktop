# InkDrop 2.0 设计文档

> 重定位：从"通用文档转 Markdown"改为"喂给 AI 的文档预处理器"

## 背景

原项目 InkDrop（markitdown-desktop）是一个 Windows GUI 包装器，把 Microsoft markitdown CLI 包上拖拽界面。原作者在 v1.0.0 后归档，结论是目标用户不存在：会转文档的人用 CLI，不会的人不需要 Markdown。

**新定位**：核心场景不是"转文档"，而是"把各种格式喂给 LLM/RAG 做分析、总结、问答"。GUI 的价值在于：
1. **转化质量可视化** — 预览渲染效果，确认结构/表格/图片没丢
2. **多模态友好** — 图片完好提取，AI 能"看到"原文档中的图

## 架构

```
┌─────────────────────────────────────────────┐
│  Browser (HTMX + Picocss)                    │
│  拖拽上传 / 实时预览 / 图片画廊 / 质量报告      │
└──────────────────┬──────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────┐
│  FastAPI App                                 │
│  ├── /api/upload     → 接收文件，创建 job      │
│  ├── /api/convert    → 触发转换               │
│  ├── /api/status     → 进度 + 质量报告         │
│  ├── /api/preview    → Markdown → HTML        │
│  ├── /api/images     → 提取的图片             │
│  └── /api/download   → zip 打包下载            │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  inkdrop/ 包 (原有代码重构)                    │
│  ├── converter.py    → 统一入口               │
│  └── engines/        → 原有引擎移入            │
│      ├── pdf_engine.py                       │
│      ├── doc_engine.py                       │
│      └── sniffer.py                          │
└─────────────────────────────────────────────┘
```

## 后端设计

### 引擎层改造

- 新建 `inkdrop/` 包目录
- `doc2md.py` → `inkdrop/converter.py`：`convert(input_path, output_dir) → Result`
- `pdf_engine.py` / `doc_engine.py` / `sniffer.py` 移入 `inkdrop/engines/`
- 返回结构化结果：

```python
@dataclass
class Result:
    markdown: str
    images: list[Path]
    quality: QualityReport

@dataclass
class QualityReport:
    score: int              # 0-100
    heading_structure: bool # H1→H2→H3 是否连续
    table_count: int
    image_count: int
    garbled_detected: bool  # 疑似乱码字符
```

### API 路由

| 路由 | 方法 | 作用 |
|------|------|------|
| `/` | GET | 首页（上传界面） |
| `/api/upload` | POST | multipart 文件上传，返回 job_id |
| `/api/convert/{job_id}` | POST | 触发后台转换 |
| `/api/status/{job_id}` | GET | 进度 + 质量报告 (JSON) |
| `/api/preview/{job_id}` | GET | 渲染后的 HTML 片段 |
| `/api/source/{job_id}` | GET | 原始 Markdown 文本 |
| `/api/images/{job_id}/{name}` | GET | 单张图片 |
| `/api/download/{job_id}` | GET | 打包 zip (md + images) |

### 后台任务

- 转换在 `asyncio.create_task` 或 `run_in_executor` 中执行（markitdown 是同步库）
- 进度写入内存 dict，前端 HTMX 轮询 `/api/status`
- 单文件限制 50MB，超时 60s

## 前端设计

**技术栈**：HTMX + Jinja2 模板 + Picocss + `<dialog>` 原生模态框

**布局**（三栏响应式）：

```
┌─────────────────────────────────────────────────┐
│  InkDrop · 喂给 AI 的文档预处理器                  │
├─────────────┬───────────────────┬───────────────┤
│  上传区      │   Markdown 预览    │  图片画廊      │
│  · 拖拽文件  │   · 渲染 HTML      │   · 缩略图     │
│  · 批量列表  │   · 代码高亮       │   · 点击放大   │
│  · 进度条    │   · 表格渲染       │   · 格式/大小  │
│  · 质量总分  │                   │               │
│             ├───────────────────┤               │
│             │   原始 Markdown    │               │
│             │   (可复制)         │               │
├─────────────┴───────────────────┴───────────────┤
│  [复制 MD]  [下载 zip]  [再转一个]                 │
└─────────────────────────────────────────────┘
```

**关键交互**（HTMX 实现）：
- 拖拽上传：`hx-post="/api/upload" hx-encoding="multipart/form-data"`
- 进度轮询：`hx-get="/api/status/{job_id}" hx-trigger="every 1s" hx-swap="none"` + 收到完成时刷新预览
- 图片放大：`<dialog>` + 少量 JS

## 数据流

```
用户上传 file.pdf
    ↓
保存到 tmp/{job_id}/input/file.pdf
    ↓
converter.convert() 调用 markitdown/engines
    ↓
输出 tmp/{job_id}/output/result.md + images/*.png
    ↓
quality_check(result.md) → QualityReport
    ↓
推送预览 HTML + 图片画廊到前端
```

## 错误处理

| 场景 | 处理 |
|------|------|
| 格式不支持 | 422 + 提示"请另存为 PDF/DOCX" |
| PDF 乱码 | 质量报告标记，不阻断，给出提示 |
| 文件 >50MB | 拒绝上传 |
| 转换超时 60s | 返回部分结果 + 错误信息 |
| PyMuPDF AGPL | 保持 lazy-import 隔离，不打包分发 |

## 临时文件管理

- 上传文件存 `tmp/{job_id}/`
- 任务完成 5 分钟后自动清理
- 用户主动下载后立即清理
- 启动时清理残留旧文件

## 测试策略

- **单元测试** (pytest)：converter 各引擎、quality_check、sniffer
- **API 测试** (httpx + pytest)：所有路由的 happy path + 错误路径
- **集成测试**：端到端上传→转换→预览→下载
- **Allure 报告**：测试结果可视化

## 项目结构（目标）

```
markitdown-desktop/
├── inkdrop/                    # 新建核心包
│   ├── __init__.py
│   ├── converter.py            # 统一转换入口
│   ├── quality.py              # 质量检查
│   ├── app.py                  # FastAPI 应用
│   ├── templates/              # Jinja2 模板
│   │   ├── index.html
│   │   └── preview.html
│   ├── static/                 # Picocss + 少量 JS
│   └── engines/                # 原有引擎
│       ├── pdf_engine.py
│       ├── doc_engine.py
│       └── sniffer.py
├── tests/                      # pytest 测试
│   ├── test_converter.py
│   ├── test_api.py
│   └── test_quality.py
├── docs/
│   └── superpowers/specs/
│       └── 2025-07-21-inkdrop2-design.md
├── requirements.txt            # 新增 fastapi, uvicorn, jinja2, httpx
└── README.md
```

## 不在范围内

- 不做移动端
- 不做多用户/登录系统
- 不做云部署配置（本地运行即可）
- 不替换 markitdown 引擎（保持原有 PDF/DOC 处理逻辑）
- 不做实时协作
