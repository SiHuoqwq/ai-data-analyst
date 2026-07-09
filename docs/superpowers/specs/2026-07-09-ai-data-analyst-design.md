# AI Data Analyst — 设计文档

## 项目定位

AI 数据分析助手，用户上传 CSV/Excel 数据后，通过自然语言与 AI 交互完成数据分析、图表生成和报告输出。

面向 AI 应用开发岗位，作为作品集第二个项目，与 RAG Notebook 形成能力互补。

## 技术选型

| 层 | 技术 | 选型理由 |
|---|------|----------|
| Web 框架 | FastAPI | 与 RAG Notebook 一致，SSE 原生支持 |
| AI 编排 | LangGraph | 支持 Agent 多步骤推理 + Tool Calling |
| LLM | DeepSeek v4-pro（默认），预留 OpenAI 切换 | LLM Provider 抽象层 |
| 数据处理 | pandas + numpy | 数据分析标配 |
| 可视化 | matplotlib + seaborn | 成熟稳定，输出 PNG |
| 数据库 | SQLite | 轻量零配置，单用户足够 |
| 前端 | 待定（Phase 2） | Phase 1 先通过 API 文档验证 |

## 架构

```
用户上传 CSV/Excel
        │
        ▼
┌───────────────────┐
│  Parser           │  → DataFrame + 结构化元信息
│  Data Profiler    │  → 数据质量报告
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Agent Controller │  → 理解任务 → 拆分步骤 → 选择工具 → 汇总
└───────┬───────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│              Analysis Tools (预定义函数)        │
│  statistics: describe / value_counts / corr   │
│  aggregation: groupby / filter / sort         │
│  analysis: trend / outliers / summary         │
│  visualization: bar / line / pie / scatter    │
└───────────────────────┬───────────────────────┘
        │
        ▼
┌───────────────────┐
│  Chart Engine     │  → matplotlib/seaborn → PNG
│  Report Generator  │  → 结构化报告 → Markdown
└───────────────────┘
        │
        ▼
┌───────────────────┐
│     SQLite        │
└───────────────────┘
```

## LLM Provider 抽象层

```
app/services/llm/
├── base.py        # BaseLLM: chat(messages, tools) → {content, tool_calls}
│                  #          chat_stream(messages) → AsyncIterator[str]
├── deepseek.py    # DeepSeek provider
├── openai.py      # OpenAI provider (预留)
└── factory.py     # get_llm(provider="deepseek") → BaseLLM
```

换模型只需改 `LLM_PROVIDER` 环境变量。

## 数据库设计

- **files** — 文件名、路径、类型、行列数、列信息(JSON)、profile 报告(Markdown)
- **conversations** — 关联 file_id、标题、模式
- **messages** — 关联 conv_id、角色、内容、tool_calls(JSON)、chart_ids(JSON)
- **charts** — 关联 message_id、类型、标题、PNG 路径、生成配置(JSON)

## 项目目录结构

```
ai-data-analyst/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── files.py          # POST /upload, GET /files, GET /files/{id}/preview
│   │   ├── chat.py           # POST /chat/stream (SSE)
│   │   └── report.py         # POST /report/generate
│   ├── services/
│   │   ├── parser.py
│   │   ├── profiler.py
│   │   ├── agent.py          # Agent Controller (LangGraph)
│   │   ├── tools/
│   │   │   ├── statistics.py # describe, value_counts, correlation_analysis
│   │   │   ├── aggregation.py# group_analysis, filter_data, sort_data
│   │   │   ├── analysis.py   # trend_analysis, detect_outliers, data_summary
│   │   │   └── visualization.py # draw_bar/line/pie/scatter/heatmap
│   │   ├── chart_engine.py
│   │   ├── report_generator.py
│   │   └── llm/
│   │       ├── base.py, deepseek.py, openai.py, factory.py
│   ├── models/
│   │   ├── file.py, chat.py, chart.py
│   └── db/
│       ├── database.py, models.py
├── storage/  (uploads/ + charts/)
├── tests/
├── .env.example, .gitignore, requirements.txt, README.md
```

## 开发阶段

### Phase 1（当前目标）

可用的单体应用，通过 Swagger UI 交互：

1. 文件上传 + CSV/Excel 解析
2. Data Profiler 自动数据质量分析
3. 8-10 个 Analysis Tools
4. Agent Controller（LangGraph Tool Calling）
5. SSE 流式 Chat API
6. Chart Engine 图表生成
7. Report Generator 自动报告

### Phase 2

- 前端 SPA
- 历史记录完整管理
- Agent 任务规划增强

### Phase 3

- Sandbox 代码执行
- RAG（文档+数据结合）
- 多用户系统
- 云部署

## 不在第一阶段做的

- Sandbox / 代码执行引擎
- RAG / 向量数据库
- Docker 沙箱
- 用户认证
- 前端 UI

## 设计决策记录

1. **Tool Calling 替代代码生成**：第一阶段 LLM 选择预定义工具而非生成 pandas 代码，避免沙箱复杂度，分析能力仍完整。
2. **复用 RAG Notebook 经验**：FastAPI + LangGraph + SSE + SQLite + 对话管理，直接借鉴已有模式。
3. **LLM Provider 抽象**：不做死绑定，方便后续切换模型或对比效果。
