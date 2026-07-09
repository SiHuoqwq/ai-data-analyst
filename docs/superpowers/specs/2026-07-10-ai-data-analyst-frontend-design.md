# AI Data Analyst — 前端设计文档

## 概述

为 AI Data Analyst 构建产品级前端界面，参考 ChatGPT Advanced Data Analysis 的交互体验。

## 技术选型

| 层 | 技术 | 理由 |
|---|------|------|
| 框架 | React 18 + TypeScript | 类型安全，生态成熟 |
| 样式 | Tailwind CSS | 原子化样式，深色主题易实现 |
| 组件库 | shadcn/ui | 无依赖、可定制、深色模式原生支持 |
| HTTP | axios | SSE 流式读取 |
| 构建 | Vite | 快速 HMR，TypeScript 原生支持 |

## 色彩系统

```
底色:     #0f172a (Slate 900)    — 页面背景
面板:     #0c1324 / #1a2744      — 侧栏、卡片
边框:     #1e293b / #334155      — 分割线
强调色:   #2563eb / #60a5fa      — 按钮、链接、选中态
成功:     #34d399                 — 任务完成、数据正常
警告:     #f59e0b                 — 进行中、需关注
文字主:   #e2e8f0                 — 正文
文字次:   #94a3b8                 — 辅助说明
文字弱:   #64748b                 — 占位符
```

## 布局架构

```
┌──────────────────────────────────────────────────────┐
│  顶部状态栏: 产品名 | 当前文件 | 模型状态 | 连接指示  │
├──────────┬───────────────────────────┬────────────────┤
│ 左侧 18% │      中间 flex            │  右侧 22%      │
│          │                           │                │
│ 📁 上传  │   💬 AI 对话              │ 📊 Context     │
│   区域   │                           │    Panel       │
│          │   ┌─────────────────┐     │                │
│ 历史文件 │   │ 🤖 AI 消息      │     │ 动态切换:      │
│ · file1  │   │ 工具调用过程    │     │ 上传→分析→完成 │
│ · file2  │   │ 图表内嵌展示    │     │                │
│ · file3  │   └─────────────────┘     │ · 数据预览     │
│          │                           │ · 任务步骤     │
│          │   ┌─────────────────┐     │ · 关键发现     │
│          │   │ 👤 用户消息     │     │ · 图表缩略图   │
│          │   └─────────────────┘     │ · 报告入口     │
│          │                           │                │
│          │   ┌─────────────────┐     │                │
│          │   │ 输入框          │     │                │
│          │   └─────────────────┘     │                │
└──────────┴───────────────────────────┴────────────────┘
```

## 组件树

```
App
├── TopBar
│   ├── Logo + 产品名
│   ├── CurrentFileBadge (当前文件)
│   ├── ModelStatus (模型名 + 绿点)
│   └── ConnectionStatus
├── MainLayout (三栏)
│   ├── LeftSidebar
│   │   ├── FileUploadZone (拖拽上传)
│   │   └── FileHistoryList
│   │       └── FileHistoryItem (文件名、行列数、时间、选中态)
│   ├── ChatPanel (中间)
│   │   ├── MessageList
│   │   │   ├── UserMessage
│   │   │   └── AssistantMessage
│   │   │       ├── ToolCallCard (工具调用卡片)
│   │   │       ├── MarkdownContent (正文渲染)
│   │   │       └── ChartInline (内嵌图表)
│   │   └── ChatInput (输入框 + 发送按钮)
│   └── ContextPanel (右侧)
│       ├── StageIndicator (三阶段标签)
│       ├── DataOverview (上传阶段)
│       │   ├── FieldInfoTable
│       │   └── QualityReport
│       ├── TaskProgress (分析阶段)
│       │   └── ToolCallStep[]
│       └── ResultsView (完成阶段)
│           ├── ChartThumbnail[]
│           ├── KeyFindings[]
│           └── ReportButton
```

## Context Panel 三阶段

### 阶段 1 — 上传阶段（文件刚上传/选中，尚未提问）

显示：
- 数据概览：行数、列数、文件类型、上传时间
- 字段信息表：列名、类型、缺失率、唯一值数
- 数据质量摘要：缺失值数量、重复行数、异常值预警

数据来源：`GET /api/v1/files/{id}` → FileDetail

### 阶段 2 — 分析阶段（用户发送消息后，Agent 执行中）

显示：
- AI 任务步骤列表（从 SSE `tool` 事件实时更新）
- 每步状态：等待 → 执行中 → 完成/失败
- 工具名 + 参数概要

数据来源：SSE stream `tool` 事件

### 阶段 3 — 完成阶段（Agent 回复完成）

显示：
- 生成的图表缩略图（点击放大）
- 关键发现摘要（从 AI 回复中提取）
- 报告生成按钮
- 下载/导出入口

数据来源：SSE `done` 事件 + `GET /api/v1/report/generate`

## 数据流

```
用户上传文件
  → POST /api/v1/files/upload
  → 更新 FileHistoryList + ContextPanel(阶段1)

用户选中历史文件
  → GET /api/v1/files/{id}
  → 更新 ContextPanel(阶段1)
  → 高亮左侧文件项

用户发送消息
  → POST /api/v1/chat/stream (SSE)
  → ContextPanel 切换到阶段2
  → 实时更新 TaskProgress
  → 消息区流式渲染 Markdown
  → SSE 结束 → ContextPanel 切换到阶段3
  → 显示图表和关键发现

用户点击生成报告
  → POST /api/v1/report/generate
  → 渲染 Markdown 报告
```

## 后端适配（最小改动）

需要增加一个静态文件挂载以提供图表 PNG：

```python
# app/main.py 增加
from fastapi.staticfiles import StaticFiles
app.mount("/storage/charts", StaticFiles(directory="storage/charts"), name="charts")
```

前端通过 `/storage/charts/{filename}` 访问图表图片。

## MVP 范围

**包含：**
1. 三栏布局 + 顶部状态栏
2. 文件上传（拖拽）+ 历史文件列表
3. 文件选中 → Context Panel 阶段1（数据概览 + 字段信息 + 质量报告）
4. 对话输入 + SSE 流式输出 + Markdown 渲染
5. 工具调用过程展示（消息内 + Context Panel 阶段2）
6. 图表内嵌展示 + Context Panel 阶段3
7. 报告生成入口

**不包含（后续迭代）：**
- 复杂动画/过渡效果
- 多文件同时分析
- 用户认证
- 对话历史管理面板
- 图表交互缩放
- 主题切换

## 项目结构（前端）

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── api/
│   │   ├── client.ts          # axios 实例
│   │   ├── files.ts           # 文件 API
│   │   ├── chat.ts            # SSE 聊天
│   │   └── report.ts          # 报告 API
│   ├── types/
│   │   └── index.ts           # TypeScript 类型定义
│   ├── hooks/
│   │   ├── useSSE.ts          # SSE 流式读取 hook
│   │   └── useFiles.ts        # 文件管理 hook
│   ├── components/
│   │   ├── layout/
│   │   │   ├── TopBar.tsx
│   │   │   ├── LeftSidebar.tsx
│   │   │   ├── ChatPanel.tsx
│   │   │   └── ContextPanel.tsx
│   │   ├── chat/
│   │   │   ├── MessageList.tsx
│   │   │   ├── UserMessage.tsx
│   │   │   ├── AssistantMessage.tsx
│   │   │   ├── ToolCallCard.tsx
│   │   │   ├── ChartInline.tsx
│   │   │   └── ChatInput.tsx
│   │   ├── files/
│   │   │   ├── FileUploadZone.tsx
│   │   │   ├── FileHistoryList.tsx
│   │   │   └── FileHistoryItem.tsx
│   │   └── context/
│   │       ├── DataOverview.tsx
│   │       ├── TaskProgress.tsx
│   │       ├── ResultsView.tsx
│   │       └── StageIndicator.tsx
│   └── lib/
│       └── utils.ts
```

## 设计决策

1. **Vite（非 Next.js）** — 纯 SPA，无需 SSR，Vite 够用且更轻
2. **shadcn/ui 深色模式** — 组件原生支持 dark mode，只要 `<html class="dark">`
3. **SSE 用 fetch + ReadableStream** — 比 EventSource 更灵活（支持 POST）
4. **Markdown 渲染用 react-markdown + rehype-highlight** — 代码高亮 + 表格渲染
5. **图表图片直接 `<img>` 标签** — 简单可靠，不做 Canvas 交互
6. **Context Panel 阶段切换用状态机** — `idle → upload → analyzing → complete`
