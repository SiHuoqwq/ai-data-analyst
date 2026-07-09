# AI Data Analyst

AI 数据分析助手 — 上传 CSV/Excel 数据，通过自然语言与 AI Agent 交互完成数据分析、图表生成和报告输出。

## 技术栈

- **FastAPI** — Web 框架，SSE 流式响应
- **LangGraph** — Agent 编排，Tool Calling 多步推理
- **DeepSeek API** — LLM（可切换 OpenAI）
- **pandas + matplotlib + seaborn** — 数据处理与可视化
- **SQLite** — 对话与图表持久化

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 启动
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://localhost:8000/docs 使用 Swagger UI 交互。

## API 端点

| 端点 | 说明 |
|------|------|
| `POST /api/v1/files/upload` | 上传 CSV/Excel 文件，自动解析并生成数据报告 |
| `GET /api/v1/files` | 文件列表 |
| `GET /api/v1/files/{id}` | 文件详情（含列信息 + 数据质量报告） |
| `GET /api/v1/files/{id}/preview` | 文件预览（前 N 行） |
| `POST /api/v1/chat/stream` | SSE 流式对话（Agent 自动调用工具） |
| `POST /api/v1/report/generate` | 生成分析报告 |

## 分析工具（14个）

**统计**: describe_data, value_counts, correlation_analysis
**聚合**: group_analysis, filter_data, sort_data
**分析**: trend_analysis, detect_outliers, data_summary
**可视化**: draw_bar_chart, draw_line_chart, draw_pie_chart, draw_scatter_chart, draw_heatmap_chart

## 项目结构

```
app/
├── main.py              # FastAPI 入口
├── config.py            # 配置管理
├── api/                 # 路由层
│   ├── files.py         # 文件上传/查询
│   ├── chat.py          # SSE 聊天
│   └── report.py        # 报告生成
├── services/            # 业务层
│   ├── agent.py         # LangGraph Agent
│   ├── parser.py        # CSV/Excel 解析
│   ├── profiler.py      # 数据质量分析
│   ├── chart_engine.py  # 图表渲染
│   ├── report_generator.py
│   ├── tools/           # 14 个分析工具
│   └── llm/             # LLM Provider 抽象
├── models/              # Pydantic Schema
└── db/                  # SQLAlchemy + SQLite
```

## License

MIT
