# doc2md 设计系统

> 由 interface-design skill 沉淀。改 GUI 前先读这份, 决策已定, 不重新发明。

## 方向与气质

**纸墨工作台** — 安静、克制、像一台校对台。用户把一批杂格式文档拖进来,
产出干净 Markdown 喂 AI。左边进料, 右边出回执。

## 实现介质

CustomTkinter 6.0 (圆角/主题/hover 由库承担) + tk 原生 Listbox/Text/Canvas
(功能件, 主题靠 `_apply_tk_theme()` 手动跟随)。字体: 中文 Microsoft YaHei UI,
纯拉丁 wordmark/数字用 Segoe UI。**Segoe UI/Consolas 没有 CJK 字形,
任何显示中文的组件禁止用它们** (会掉进宋体回退)。

## 令牌 (PALETTE, 全部成对 light/dark)

| 令牌 | 浅色(暖纸) | 深色(墨室) | 用途 |
|---|---|---|---|
| bg | #F6F4EF | #17140F | 窗口底 |
| card | #FFFFFF | #201C16 | 卡片 |
| border | #E5E0D6 | #322C24 | 1px 卡片描边 |
| text | #1C1917 | #E8E3DA | 主文字 |
| muted | #8A8177 | #9A9184 | 次文字/标题 caption |
| accent | #0F766E | #2DD4BF | 墨水瓶深青, 唯一强调色, 只用于链接/进度 |
| primary | #1A1815 | #E7E2D9 | 墨条按钮 (深色模式反转为纸色) |
| success/warning/danger | 校对绿/便签黄/朱砂红 | 提亮版 | 仅状态语义 |

## 结构决策

- **双栏工作台**: 左 300px 队列 (caption + 卡片列表 + 链接操作 + 墨条按钮 +
  进度), 右侧自适应回执 (caption + 回执卡 + 质量条 + 图片条 + 打开按钮),
  底部状态栏。布局用 grid + `grid_remove()` 隐藏, **不用 pack 混排底部组件**
  (pack 按打包顺序分配, expand 组件会把后打包的挤出窗口)。
- **焦点**: 空态 = 拖放提示; 有文件 = 墨条按钮; 转换后 = 回执。
- **操作分级**: 主操作墨条 (46px 圆角 10); 次级全部是透明底文字按钮
  (`_ghost_btn`); 边框按钮只给"打开所有文件夹"这类第二动作。
- **签名元素**: ① 墨条按钮 (深浅模式黑白反转) ② 回执式结果流水
  (→ 进行中 / ✓ 成功 / ✗ 失败 + [打开] 链接) ③ 单行质量条
  (分数+色条+四指标)。

## 拒绝过的默认值 (别改回去)

- emoji 图标 (🚀📄📋📊✅❌) → 文字 + 语义色
- 默认蓝 (#2563EB) / ttk 原生灰 → 纸墨令牌
- 三小按钮工具栏 + Notebook 标签页 → 双栏 + 质量条
- CTkToplevel 的 `geometry("WxH+x+y")` 会被 CTk 二次缩放 →
  弹窗只写 `+x+y` 定位, 尺寸让内容撑

## 组件记录

- 墨条按钮 — 46px 高 · corner 10 · YaHei 15 bold · primary/primary_hover
- ghost 按钮 — 28px 高 · corner 6 · YaHei 12 · transparent/ghost_hover
- 卡片 — corner 10 · border_width 1 · border
- 进度条 — 6px 高 · corner 3 · select 底 / accent 前景
- 质量条 — 卡片内单行: 质量 caption + 18px 分数(按分值上色) + 90px 色条 +
  标题/乱码/表格/图片 四组 caption+值
- 设置窗 — CTkSwitch (accent progress) · CTkSegmentedButton 外观三选
  (selected #D6D0C4/#4A4438, text 用 text 令牌)
- 段选(视图切换) — 右列 "转换回执|预览" 与设置窗同款纸色段选;
  互斥卡片用 grid 同格 + grid_remove 切换
- 选中行高亮 — 回执行整行 tag `file_{i}` 可点击, 选中加 `selline`
  背景 tag (select 令牌) 并 tag_lower 垫底, 不盖语义前景色;
  链接 tag 用自增序号命名, 禁止用列表长度 (跳过行会导致重名改绑)

## 验证方式

改完跑 scratchpad 的 gui_screenshot.py (PrintWindow 截图, 被遮挡也能截),
看浅色 + 深色 + 设置窗三张; 转换链路由脚本内真实跑一遍 test_sample.pdf。
