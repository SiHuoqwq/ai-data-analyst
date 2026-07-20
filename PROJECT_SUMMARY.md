# AI Data Analyst — 项目完整信息汇总

> 最后更新: 2026-07-20

---

## 基本信息

| 项目 | 详情 |
|------|------|
| **存放位置** | `D:\claude\ai-data-analyst` |
| **GitHub** | https://github.com/SiHuoqwq/ai-data-analyst (Public, 19 commits) |
| **Git 代理** | `http://127.0.0.1:7897` (仓库级别) |
| **记忆文件** | `D:\claude\.claude-user\projects\D--claude\memory\project_ai_data_analyst.md` |
| **定位** | 第二个 AI 作品集项目，与 RAG Notebook 形成能力互补 |

---

## 功能

- **文件上传解析**：支持 CSV / XLSX，自动生成数据质量报告
- **14 个分析工具**：统计描述、分组聚合、趋势分析、异常值检测、数据筛选排序
- **5 种可视化图表**：柱状图、折线图、饼图、散点图、热力图（SimHei 中文字体）
- **Agent 多步推理**：LangGraph 编排，自动选择合适工具组合
- **SSE 过程推送**：分析过程、工具调用和图表实时推送；最终回答当前不是 token 级逐字流式
- **分析报告生成**：LLM 自动生成结构化 Markdown 报告
- **对话持久化**：SQLite 存储所有对话历史和图表记录

---

## 技术栈

### 后端

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | FastAPI | 0.115.6 | REST API + SSE 分析过程事件 |
| Agent 编排 | LangGraph | 0.2.61 | StateGraph, Tool Calling, astream |
| LLM 集成 | LangChain | 0.3.15 | LLM 调用辅助 |
| LLM Provider | DeepSeek API | `deepseek-chat` | 默认，抽象层预留 OpenAI |
| HTTP 客户端 | httpx | 0.28.1 | LLM API 调用 |
| 数据库 ORM | SQLAlchemy | 2.0.36 | 4 张表 (Files, Conversations, Messages, Charts) |
| 数据库 | SQLite | — | `app.db`，本地持久化 |
| 数据处理 | pandas | 2.2.3 | 解析、统计、聚合、过滤 |
| 数值计算 | numpy | 1.26.4 | 数值运算 |
| 文件解析 | openpyxl | 3.1.5 | Excel 读取 |
| 可视化 | matplotlib | 3.9.3 | 5 种图表，SimHei 中文字体 |
| 可视化 | seaborn | 0.13.2 | 热力图 |
| 数据验证 | Pydantic | v2 | Schema 定义 |
| 配置管理 | pydantic-settings | 2.7.1 | 环境变量配置 |
| 文件上传 | python-multipart | 0.0.20 | multipart/form-data |
| 服务器 | uvicorn | 0.34.0 | ASGI 服务器 |
| 测试 | pytest | 8.3.4 | 20 个测试（含主链路集成测试） |
| 异步测试 | pytest-asyncio | 0.25.0 | 异步测试支持 |

### 前端

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | React | 19.2.7 | SPA |
| 语言 | TypeScript | 6.0.2 | 类型安全 |
| 构建 | Vite | 8.1.1 | HMR 开发 + 生产构建 |
| 样式 | Tailwind CSS | 4.3.2 | 暗色主题 (#0f172a 背景, #2563eb 强调) |
| HTTP | axios | 1.18.1 | API 请求 |
| 图标 | lucide-react | 1.24.0 | SVG 图标 |
| Markdown | react-markdown | 10.1.0 | AI 回复渲染 |
| Markdown 扩展 | remark-gfm | 4.0.1 | GFM 表格/删除线支持 |
| 代码高亮 | rehype-highlight | 7.0.2 | 报告代码块高亮 |
| Lint | oxlint | 1.71.0 | 代码检查 |

---

## 项目结构

```
ai-data-analyst/
├── app/                          # 后端 Python 代码
│   ├── main.py                   # FastAPI 入口 + 静态文件挂载 + CORS
│   ├── config.py                 # 环境变量配置 (DEEPSEEK_API_KEY 等)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── files.py              # 文件上传/列表/详情/预览 (4 endpoints)
│   │   ├── chat.py               # SSE 分析过程事件 (Agent Tool Calling)
│   │   ├── conversations.py      # 对话历史查询 (2 endpoints)
│   │   └── report.py             # 分析报告生成
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent.py              # LangGraph Agent 编排 (StateGraph + ToolNode)
│   │   ├── parser.py             # CSV/XLSX 解析 (pandas)
│   │   ├── profiler.py           # 数据质量分析 (IQR 异常值检测 + 统计画像)
│   │   ├── chart_engine.py       # matplotlib 图表引擎 (5 种图表, SimHei 中文)
│   │   ├── report_generator.py   # LLM 自动生成 Markdown 报告
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── statistics.py     # describe_data, value_counts, correlation_analysis
│   │   │   ├── aggregation.py    # group_analysis, filter_data, sort_data
│   │   │   ├── analysis.py       # trend_analysis, detect_outliers, data_summary
│   │   │   └── visualization.py  # 5 个图表工具 (bar, line, pie, scatter, heatmap)
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── base.py           # LLM Provider 抽象基类
│   │       ├── factory.py        # 工厂函数 (根据配置选择 Provider)
│   │       ├── deepseek.py       # DeepSeek 实现
│   │       └── openai.py         # OpenAI 预留 (stub)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── chat.py               # ChatRequest, ChatEvent, MessageItem, Conversation Schema
│   │   ├── file.py               # FileInfo, ColumnInfo, DataProfile Schema
│   │   └── chart.py              # Chart 相关 Schema
│   └── db/
│       ├── __init__.py
│       ├── database.py           # SQLAlchemy 引擎 + Session 管理
│       ├── models.py             # 4 张 ORM 模型 (File, Conversation, Message, Chart)
│       └── conversation_store.py # 对话 CRUD 操作
├── frontend/                     # 前端 React + TypeScript 代码
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── App.tsx               # 根组件 (三栏布局 + 状态管理)
│       ├── main.tsx              # React 入口
│       ├── index.css             # Tailwind + 全局样式
│       ├── types/
│       │   └── index.ts          # TypeScript 类型定义 (File, Message, Chart 等)
│       ├── api/
│       │   ├── client.ts         # axios 实例 + 基础配置
│       │   ├── files.ts          # 文件上传/列表/详情/预览 API
│       │   ├── chat.ts           # SSE 分析过程事件 API (fetch + ReadableStream)
│       │   ├── conversations.ts  # 对话历史 API
│       │   └── report.ts         # 报告生成 API
│       └── components/
│           ├── layout/           # 4 个布局组件
│           │   ├── TopBar.tsx        # 顶部导航栏 (Logo + 标题 + 链接)
│           │   ├── LeftSidebar.tsx   # 左侧栏 (文件上传 + 历史文件 + 对话历史)
│           │   ├── ChatPanel.tsx     # 中央对话区 (消息列表 + 输入框 + 新对话)
│           │   └── ContextPanel.tsx  # 右侧面板 (数据概览 + 进度 + 结果)
│           ├── chat/             # 6 个对话组件
│           │   ├── MessageList.tsx       # 消息列表 (自动滚动)
│           │   ├── ChatInput.tsx         # 输入框 + 发送按钮
│           │   ├── UserMessage.tsx       # 用户消息气泡
│           │   ├── AssistantMessage.tsx  # AI 回复 (Markdown 渲染)
│           │   ├── ToolCallCard.tsx      # 工具调用卡片 (名称 + 参数 + 状态)
│           │   └── ChartInline.tsx       # 图表内联展示
│           ├── context/          # 4 个上下文面板组件
│           │   ├── StageIndicator.tsx    # 分析阶段指示器
│           │   ├── DataOverview.tsx      # 数据概览 (行列数 + 列信息)
│           │   ├── TaskProgress.tsx      # 分析任务进度
│           │   └── ResultsView.tsx       # 分析结果 + 图表列表
│           └── files/            # 3 个文件侧栏组件
│               ├── FileUploadZone.tsx    # 拖拽/点击上传区域
│               ├── FileHistoryItem.tsx   # 历史文件条目
│               └── FileHistoryList.tsx   # 历史文件列表
├── tests/                        # pytest 测试 (20 个)
│   ├── __init__.py
│   ├── test_llm.py               # LLM Provider 测试
│   ├── test_parser.py            # 文件解析测试
│   ├── test_profiler.py          # 数据画像测试
│   └── test_tools.py             # 分析工具测试
├── docs/superpowers/             # 设计与计划文档
│   ├── specs/
│   │   ├── 2026-07-09-ai-data-analyst-design.md          # 后端设计 Spec
│   │   └── 2026-07-10-ai-data-analyst-frontend-design.md # 前端设计 Spec
│   └── plans/
│       ├── 2026-07-09-ai-data-analyst-implementation.md          # 后端实现计划
│       └── 2026-07-10-ai-data-analyst-frontend-implementation.md # 前端实现计划
├── storage/                      # 上传的数据文件 + 生成的图表图片
├── app.db                        # SQLite 数据库文件
├── .env                          # 环境变量 (DEEPSEEK_API_KEY)
├── .env.example                  # 环境变量模板
├── .gitignore
├── requirements.txt              # Python 依赖 (15 个包)
├── start.bat                     # 一键启动后端脚本
├── test_data.csv                 # 测试用 CSV 数据
├── generate_resume.py            # 简历生成脚本 (python-docx)
├── 刘燚_简历_AI应用开发.docx      # 简历 (Word 格式)
├── 刘燚_简历_AI应用开发.pdf       # 简历 (PDF 格式)
└── README.md                     # GitHub README (英文, 含架构图 + API 文档)
```

---

## 14 个分析工具明细

### 统计类 (statistics.py)
| 工具名 | 输入 | 输出 |
|--------|------|------|
| `describe_data` | columns[] | mean, std, min, 25%, 50%, 75%, max |
| `value_counts` | column, top_n | 值分布 Top N |
| `correlation_analysis` | columns[] | 相关系数矩阵 |

### 聚合类 (aggregation.py)
| 工具名 | 输入 | 输出 |
|--------|------|------|
| `group_analysis` | group_col, agg_col, method | 分组聚合结果 (mean/sum/count/min/max) |
| `filter_data` | column, op, value | 条件筛选结果 (eq/gt/lt/ge/le/contains) |
| `sort_data` | column, order, top_n | 排序 Top N |

### 分析类 (analysis.py)
| 工具名 | 输入 | 输出 |
|--------|------|------|
| `trend_analysis` | date_col, value_col | 前后半段均值变化趋势 |
| `detect_outliers` | column | IQR 异常值列表 |
| `data_summary` | 无 (自动) | 综合性数据摘要 |

### 可视化类 (visualization.py)
| 工具名 | 图表类型 | 中文字体 |
|--------|----------|----------|
| `draw_bar_chart` | 柱状图 | SimHei |
| `draw_line_chart` | 折线图 | SimHei |
| `draw_pie_chart` | 饼图 | SimHei |
| `draw_scatter_chart` | 散点图 | SimHei |
| `draw_heatmap_chart` | 相关系数热力图 | SimHei |

---

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/files/upload` | 上传 CSV/XLSX 文件 (multipart/form-data) |
| `GET` | `/api/v1/files` | 文件列表 |
| `GET` | `/api/v1/files/{id}` | 文件详情 + 列信息 + 数据画像 |
| `GET` | `/api/v1/files/{id}/preview` | 数据预览 (前 N 行, ?rows=10) |
| `GET` | `/api/v1/files/{id}/conversations` | 文件的对话历史列表 |
| `GET` | `/api/v1/conversations/{id}` | 对话详情 (含所有消息) |
| `POST` | `/api/v1/chat/stream` | SSE 推送分析过程，Agent 自动调用工具 |
| `POST` | `/api/v1/report/generate` | 生成 Markdown 分析报告 |
| `GET` | `/health` | 健康检查 |

### SSE 事件类型

| 事件 | 含义 | 数据格式 |
|------|------|----------|
| `text` | Agent 回答文本（当前通常整段返回） | `{"content": "..."}` |
| `tool` | 工具调用开始/完成 | `{"tool": "...", "args": {...}, "status": "..."}` |
| `chart` | 图表生成完毕实时推送 | `{"chart_path": "...", "chart_type": "..."}` |
| `done` | 对话完成 | `{"conversation_id": "...", "chart_paths": [...]}` |

---

## 数据库模型 (4 张表)

| 表名 | 主要字段 |
|------|----------|
| `files` | id, filename, file_path, file_type, columns_json, row_count, profile_json, created_at |
| `conversations` | id, file_id (FK), title, created_at |
| `messages` | id, conversation_id (FK), role, content, tool_calls_json, chart_paths_json, created_at |
| `charts` | id, message_id (FK), chart_type, chart_path, metadata_json, created_at |

---

## 界面布局

```
┌──────────────┬────────────────────────────┬──────────────────┐
│ LeftSidebar  │       ChatPanel            │ ContextPanel     │
│ (18%)        │       (60%)                │ (22%)            │
│              │                            │                  │
│ FileUpload   │ AI 对话区                   │ StageIndicator   │
│   Zone       │ - UserMessage              │ DataOverview     │
│              │ - AssistantMessage         │ TaskProgress     │
│ FileHistory  │   (Markdown 渲染)           │ ResultsView      │
│   List       │ - ToolCallCard              │ - 图表列表        │
│              │ - ChartInline              │ - 报告生成按钮    │
│ 对话历史列表  │                            │                  │
│              │ ChatInput                  │                  │
│              │ (底部固定)                  │                  │
└──────────────┴────────────────────────────┴──────────────────┘
```

---

## 完整提交历史 (19 commits, 按时间倒序)

```
3d44bae feat: add conversation history API and UI, fix Vite proxy port
43a930d docs: polish README with architecture, badges, and full API reference
e71e1c8 fix: real-time chart push via SSE and Chinese font rendering
c3d0dd3 fix: include chart_paths in SSE done event for frontend chart display
e85c4b3 feat: add Phase 2 frontend — chat, context panel, file sidebar components
03df438 feat: add three-column layout shell with TopBar, sidebars, and chat panel
3f6bf4c feat: add TypeScript types and API client layer
30c1720 feat: scaffold Vite + React + TypeScript + Tailwind frontend
ff553ac feat: add static file mount for chart images
d7652a1 docs: add frontend implementation plan — 8 tasks, Vite + React + Tailwind
4637277 docs: add frontend design spec for AI Data Analyst UI
1842024 feat: add report generator, report API, README, and start.bat
892f040 feat: add SSE chat API with conversation persistence and Agent streaming
6793be0 feat: add Agent Controller with LangGraph and 14-tool Tool Calling
f297398 feat: add 9 analysis tools and chart engine with 5 visualization tools
b45c6d1 feat: add file upload API with parse, profile, list, detail, and preview endpoints
3823b9c feat: add Data Profiler with report generation and IQR outlier detection
62285e0 feat: add CSV/Excel parser service with column info extraction
309773d feat: add LLM provider abstraction with DeepSeek and OpenAI stubs
fd775bf feat: add Pydantic models for file, chat, and chart schemas
d94f129 feat: add SQLite database layer with File, Conversation, Message, Chart models
cccf250 feat: project skeleton with FastAPI app and config
```

---

## 本地运行

```bash
# 克隆仓库
git clone https://github.com/SiHuoqwq/ai-data-analyst.git
cd ai-data-analyst

# 安装 Python 依赖 (需要 Python 3.10+)
pip install -r requirements.txt

# 配置 DeepSeek API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxxxx

# 安装前端依赖 (需要 Node.js 18+)
cd frontend && npm install && cd ..

# 终端 1：启动后端 (默认端口 8000，读取根目录 .env)
py -m app.run

# 终端 2：启动前端 (端口 5173)
cd frontend && npm run dev
```

---

## 使用流程

1. 上传 CSV 或 XLSX 数据文件
2. 左侧自动显示文件信息，右侧显示数据概览
3. 在聊天框输入自然语言问题，例如：
   - "分析一下这份数据的基本情况"
   - "画一张月度销售额柱状图"
   - "做相关性分析，画热力图"
   - "检测 sales 列的异常值"
4. AI Agent 自动选择工具、执行分析、生成图表 (SSE 实时推送)
5. 分析完成后点击"生成分析报告"导出完整报告

---

## 架构图

```
用户浏览器 (React + TypeScript)
       │  HTTP REST + SSE
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

---

## 各层文件数量统计

| 层级 | 文件数 | 说明 |
|------|--------|------|
| API 路由 | 4 | files, chat, conversations, report |
| 业务服务 | 10 | agent, parser, profiler, chart_engine, report_generator, 4 tools, 1 llm 目录 |
| 数据模型 | 3 | Pydantic Schema (chat, file, chart) |
| 数据库 | 3 | engine, ORM models, CRUD store |
| LLM Provider | 4 | base, factory, deepseek, openai |
| 前端组件 | 17 | layout(4) + chat(6) + context(4) + files(3) |
| 前端 API | 5 | client, files, chat, conversations, report |
| 测试 | 4 | llm, parser, profiler, tools |
| 设计文档 | 4 | 2 specs + 2 plans |
| 总计 | ~55 | 含 __init__.py、配置等 |

---

## 已知配置项

| 配置 | 值 | 位置 |
|------|-----|------|
| DeepSeek API Key | `sk-xxxxx` | `.env` (DEEPSEEK_API_KEY) |
| 后端端口 | 8000（默认，可通过 BACKEND_PORT 配置） | `.env` / `app.run` / Vite proxy |
| 前端端口 | 5173 | Vite 默认 |
| Git 代理 | `http://127.0.0.1:7897` | `git config http.proxy` |
| 中文字体 | SimHei | matplotlib 配置 |
| CORS Origin | `http://localhost:5173` | `app/main.py` |
