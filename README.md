# AI Data Analyst

AI 数据分析助手 — 上传 CSV/XLSX 数据，通过自然语言与 AI Agent 交互，自动完成**统计分析、图表生成和报告输出**。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-teal?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61dafb?logo=react" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-6.0-3178c6?logo=typescript" alt="TypeScript">
  <img src="https://img.shields.io/badge/LangGraph-0.2-orange" alt="LangGraph">
  <img src="https://img.shields.io/badge/Tailwind-4.3-38bdf8?logo=tailwindcss" alt="Tailwind">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

## 功能

- **文件上传解析**：支持 CSV / XLSX，自动生成数据质量报告
- **14 个分析工具**：统计描述、分组聚合、趋势分析、异常值检测、数据筛选排序
- **5 种可视化图表**：柱状图、折线图、饼图、散点图、热力图（中文标题无乱码）
- **Agent 多步推理**：LangGraph 编排，自动选择合适的工具组合
- **SSE 过程推送**：分析过程、工具调用和图表通过 SSE 实时推送；最终回答当前不是 token 级逐字流式
- **分析报告生成**：LLM 自动生成结构化 Markdown 报告
- **对话持久化**：SQLite 存储所有对话历史和图表记录

## 界面

三栏工作台布局，深色专业风：

```
┌────────────┬──────────────────────────┬────────────────┐
│ LeftSidebar│       ChatPanel          │ ContextPanel   │
│ (18%)      │       (60%)              │ (22%)          │
│            │                          │                │
│ 文件上传    │ AI 对话区                 │ 阶段指示器      │
│ 历史文件    │ - Markdown 渲染           │ 数据概览        │
│            │ - 工具调用卡片             │ 分析任务进度    │
│            │ - 图表内联展示             │ 图表结果        │
│            │ - 过程事件输出             │ 报告生成按钮    │
└────────────┴──────────────────────────┴────────────────┘
```

## 架构

```
用户浏览器 (React + TypeScript)
       │  HTTP + SSE
       ▼
   FastAPI (路由层)
       │
   ┌───▼────────────────────────────┐
   │   LangGraph Agent (编排层)      │
   │   ┌────────┐   ┌────────────┐  │
   │   │ agent  │◄─►│ 14 Tools   │  │
   │   └────────┘   └────────────┘  │
   └───┬────────────────────────────┘
       │
   ┌───▼────────────────────────────┐
   │   Services (业务层)             │
   │   parser / profiler /          │
   │   chart_engine / report_gen    │
   └───┬────────────────────────────┘
       │
   ┌───▼──────────┬─────────────────┐
   │ DeepSeek API │ SQLite (ORM)    │
   └──────────────┴─────────────────┘
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **Web 框架** | FastAPI | REST API + SSE 分析过程事件 |
| **Agent 编排** | LangGraph + LangChain | StateGraph, Tool Calling, astream |
| **LLM** | DeepSeek API (`deepseek-chat`) | 默认 Provider；OpenAI Provider 仅预留，尚未实现 |
| **数据处理** | pandas + numpy | CSV/XLSX 解析、统计、聚合、过滤 |
| **可视化** | matplotlib + seaborn | 5 种图表，SimHei 中文字体 |
| **数据库** | SQLite + SQLAlchemy | 文件、对话、消息、图表 4 表 |
| **前端** | React 19 + TypeScript 6 | SPA，17 个组件 |
| **构建** | Vite 8 + Tailwind CSS 4 | HMR + 暗色主题 |
| **Markdown** | react-markdown + remark-gfm | AI 回复渲染 |
| **测试** | pytest + pytest-asyncio | 单元测试 + API 主链路集成测试 |

## 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+
- DeepSeek API Key（[申请地址](https://platform.deepseek.com)）

### 安装

```bash
# 克隆仓库
git clone https://github.com/SiHuoqwq/ai-data-analyst.git
cd ai-data-analyst

# 安装 Python 依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxxxx
# BACKEND_HOST、BACKEND_PORT 和 FRONTEND_ORIGIN 也由该文件统一配置

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 启动

```bash
# 终端 1：启动后端（读取根目录 .env）
py -m app.run

# 终端 2：启动前端
cd frontend && npm run dev
```

打开 http://localhost:5173 开始使用。

默认后端地址为 `http://127.0.0.1:8000`。`app.run`、CORS 和 Vite 开发代理均读取根目录 `.env` 中的同一套配置。

### 最小 V2 后端

仓库同时包含可切换 Fake/DeepSeek Provider 的 `/api/v2` 分析闭环。默认 Fake 模式不需要密钥；DeepSeek 模式通过白名单结构化计划调用 pandas 工具，并只基于聚合证据生成结论。迁移、启动、API、SSE、配置、安全边界和 V1/V2 共存说明见 [最小 V2 后端运行说明](docs/v2/MINIMAL_V2_BACKEND.md)。

## 使用流程

1. 上传 CSV 或 Excel 数据文件
2. 左侧自动显示文件信息，右侧显示数据概览
3. 在聊天框输入自然语言问题，例如：
   - "分析一下这份数据的基本情况"
   - "画一张月度销售额柱状图"
   - "做相关性分析，画热力图"
   - "检测 sales 列的异常值"
4. AI Agent 自动选择工具、执行分析、生成图表
5. 分析完成后点击"生成分析报告"导出完整报告

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/files/upload` | 上传 CSV/XLSX 文件 |
| `GET` | `/api/v1/files` | 文件列表 |
| `GET` | `/api/v1/files/{id}` | 文件详情（含列信息 + 数据画像） |
| `GET` | `/api/v1/files/{id}/preview` | 文件预览（前 N 行） |
| `POST` | `/api/v1/chat/stream` | SSE 分析过程推送（Agent 自动调用工具） |
| `POST` | `/api/v1/report/generate` | 根据指定对话生成 Markdown 分析报告 |
| `GET` | `/health` | 健康检查 |

SSE 事件类型：`tool` | `text` | `chart` | `error` | `done`。`text` 当前通常是完整回答片段，不代表模型 token 级流式。

## 分析工具（14 个）

| 分类 | 工具 | 功能 |
|------|------|------|
| **统计** | `describe_data` | 数值列均值/标准差/四分位数 |
| | `value_counts` | 列值分布 Top N |
| | `correlation_analysis` | 数值列相关系数矩阵 |
| **聚合** | `group_analysis` | 分组聚合（mean/sum/count/min/max） |
| | `filter_data` | 条件筛选（eq/gt/lt/ge/le/contains） |
| | `sort_data` | 排序取 Top N |
| **分析** | `trend_analysis` | 前后半段均值变化趋势 |
| | `detect_outliers` | IQR 异常值检测 |
| | `data_summary` | 综合摘要 |
| **可视化** | `draw_bar_chart` | 柱状图 |
| | `draw_line_chart` | 折线图 |
| | `draw_pie_chart` | 饼图 |
| | `draw_scatter_chart` | 散点图 |
| | `draw_heatmap_chart` | 相关系数热力图 |

## 项目结构

```
ai-data-analyst/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 环境变量配置
│   ├── api/                 # 路由层
│   │   ├── files.py         # 文件上传/查询 (4 endpoints)
│   │   ├── chat.py          # SSE 分析过程事件
│   │   └── report.py        # 报告生成
│   ├── services/            # 业务层
│   │   ├── agent.py         # LangGraph Agent 编排
│   │   ├── parser.py        # CSV/XLSX 解析
│   │   ├── profiler.py      # 数据质量分析
│   │   ├── chart_engine.py  # matplotlib 图表引擎
│   │   ├── report_generator.py  # LLM 报告生成
│   │   ├── tools/           # 14 个分析工具
│   │   │   ├── statistics.py    # 统计工具
│   │   │   ├── aggregation.py   # 聚合工具
│   │   │   ├── analysis.py      # 分析工具
│   │   │   └── visualization.py # 可视化工具
│   │   └── llm/             # LLM Provider 抽象层
│   │       ├── base.py      # 抽象基类
│   │       ├── factory.py   # 工厂函数
│   │       ├── deepseek.py  # DeepSeek 实现
│   │       └── openai.py    # OpenAI 预留
│   ├── models/              # Pydantic Schema
│   │   ├── chat.py
│   │   └── file.py
│   └── db/                  # 数据库层
│       ├── database.py      # SQLAlchemy 引擎
│       ├── models.py        # 4 张 ORM 模型
│       └── conversation_store.py  # 对话 CRUD
├── frontend/
│   └── src/
│       ├── App.tsx          # 根组件（三栏布局）
│       ├── api/             # API 客户端
│       ├── types/           # TypeScript 类型
│       └── components/
│           ├── layout/      # TopBar, Sidebars, ChatPanel
│           ├── chat/        # MessageList, ChatInput, ChartInline
│           ├── context/     # DataOverview, TaskProgress, ResultsView
│           └── files/       # FileUploadZone, FileHistoryList
├── tests/                   # pytest (15 tests)
├── storage/                 # 上传文件 + 图表图片
├── requirements.txt
└── README.md
```

## 运行测试

```bash
py -m pytest tests/ -v
```

## License

MIT
