# 发布架构

## 设计目标

本项目将“模型理解”与“数据计算”分离。模型只能输出受限的高层意图；
服务端负责字段解析、工作流编译、参数校验、pandas 计算、图表规划和证据
校验。这样可以降低模型编造数字、调用任意工具或跨 Run 混用证据的风险。

## 系统组件

```mermaid
flowchart TB
    UI["Frontend V2\nReact + TypeScript"]
    V1["/api/v1\n文件、画像、预览、会话历史"]
    V2["/api/v2\nConversation、Run、Step、Artifact、SSE"]
    RP["Provider\nFake / DeepSeek"]
    INTENT["Domain Intent\n严格 Pydantic Schema"]
    COMPILER["PlanCompiler + PlanValidator"]
    ANALYTICS["Deterministic Analytics\npandas"]
    CHART["ChartPlanner + matplotlib"]
    EVIDENCE["Evidence Registry\n结构化结论校验"]
    DB[("SQLite\nV1 + V2 tables")]
    FS[("文件系统\nuploads + charts")]

    UI -->|REST| V1
    UI -->|REST + SSE| V2
    V1 --> DB
    V1 --> FS
    V2 --> RP
    RP --> INTENT
    INTENT --> COMPILER
    COMPILER --> ANALYTICS
    ANALYTICS --> CHART
    ANALYTICS --> EVIDENCE
    CHART --> EVIDENCE
    EVIDENCE --> V2
    V2 --> DB
    V2 --> FS
```

## 分析运行时序

```mermaid
sequenceDiagram
    actor User as 用户
    participant FE as Frontend V2
    participant API as FastAPI V2
    participant EX as AnalysisExecutor
    participant P as Provider
    participant A as pandas / ChartPlanner
    participant DB as SQLite

    User->>FE: 提交问题
    FE->>API: 创建 Conversation（首次）
    FE->>API: 创建 Run + Idempotency-Key
    API->>DB: 原子保存 user Message、queued Run、run.started
    API-->>FE: run_id + events_url
    FE->>API: 订阅 SSE
    EX->>P: 生成高层 AnalysisIntent
    EX->>EX: 编译并校验固定工作流
    EX->>A: 执行确定性统计和图表
    A-->>EX: 结构化结果
    EX->>DB: 保存 Step、Artifact、Evidence 事件
    EX->>P: 基于受限 Evidence 生成结构化结论
    EX->>DB: 保存 assistant Message 与 completed Run
    API-->>FE: SSE 事件
    FE->>API: 刷新时查询 Run / Steps / Artifacts
```

## 数据模型

```mermaid
erDiagram
    FILES ||--o{ CONVERSATIONS : contains
    CONVERSATIONS ||--o{ MESSAGES : contains
    MESSAGES ||--o{ CHARTS : owns
    CONVERSATIONS ||--o{ ANALYSIS_RUNS : owns
    FILES ||--o{ ANALYSIS_RUNS : dataset_version_adapter
    MESSAGES ||--o| ANALYSIS_RUNS : triggers
    MESSAGES ||--o| ANALYSIS_RUNS : answers
    ANALYSIS_RUNS ||--o{ RUN_STEPS : contains
    ANALYSIS_RUNS ||--o{ ARTIFACTS : produces
    RUN_STEPS ||--o{ ARTIFACTS : produces
    ANALYSIS_RUNS ||--o{ RUN_EVENTS : emits
```

V2 过渡期继续使用 V1 `files`、`conversations` 和 `messages`。新的
`analysis_runs`、`run_steps`、`artifacts` 和 `run_events` 通过外键与
它们关联。正式 Dataset / DatasetVersion 仍属于后续架构演进，不在当前
发布范围。

## 状态与恢复

- Run：`queued → running → completed | failed | cancelled`
- Step：`pending → running → completed | failed | cancelled`
- SSE 提供实时体验，但不是唯一事实来源。
- 单个 Run 的 `sequence` 严格递增，`event_id` 用于去重。
- 页面刷新或 SSE 中断后，通过 REST 查询持久化状态。
- 终态不可回退；取消是合作式、幂等的。

## 安全边界

- 浏览器不接收服务器物理路径。
- table Artifact 只返回受限行数，不推送完整原始数据集。
- Markdown 不渲染原始 HTML。
- Prompt、API Key、完整模型响应和 Evidence Registry 不写入日志。
- DeepSeek 不能输出底层工具、字段来源、聚合规则、Python 或 SQL。
- Fake Provider 是默认发布验证路径，不访问外部模型。
