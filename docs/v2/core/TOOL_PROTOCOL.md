# V2 分析工具协议

> 合同状态：V2 设计合同，当前尚未实现。当前 `/api/v1` 工具仍主要返回字符串；本文描述 V2 目标协议。实现阶段以 Pydantic Schema、生成的 OpenAPI 和正式数据库迁移为最终事实来源。

## 1. 协议目标

工具协议是 Agent 计划和确定性执行引擎之间的边界。它不承诺某个具体 Python 函数或 LangGraph 节点，也不允许模型直接操作文件路径、全局 DataFrame 或原始 SQL。

统一原则：

- 工具输入使用严格 Pydantic schema，`extra="forbid"`。
- `dataset_version_id`、`run_id`、`run_step_id` 由服务端执行上下文注入，不进入模型可控参数。
- 工具只使用固定的 DatasetVersion snapshot；不能读取 Dataset 最新版本或任意 file_id。
- 结果必须有 summary、preview、row_count、truncated 和 Artifact 引用。
- 大结果写入 Artifact，模型和普通前端请求只接收摘要/有限预览。
- 工具错误是结构化值，不以自然语言字符串伪装成功结果。
- 同一 `idempotency_key` 重试必须返回相同结果或明确“状态未知”，不能重复产生不可追踪 Artifact。

## 2. 工具边界评估

| 工具 | 责任 | 不负责 |
|---|---|---|
| `inspect_dataset` | 返回 schema、画像摘要、缺失/重复/类型告警和有限样例 | 不修改数据、不生成业务结论 |
| `query_dataset` | 按结构化 metrics/dimensions/filters/sort/limit 执行确定性查询 | 不接受原始 SQL、不直接解释因果 |
| `analyze_distribution` | 对列或指标计算分布、分位数、频数和质量摘要 | 不自行选择业务字段、不改变清洗版本 |
| `analyze_time_series` | 按时间粒度聚合、比较周期、计算变化摘要 | 不把前后半段均值自动称为业务趋势结论 |
| `detect_anomalies` | 按声明的方法和字段产生异常点、阈值和方法说明 | 不判断异常是否为业务错误 |
| `create_visualization` | 从确定性结果生成结构化图表规范和可选渲染文件 | 不读取任意本地路径、不只保存无法复现的 PNG |
| `retrieve_artifact` | 获取受限摘要/预览/元数据 | 不把完整大表直接塞进模型上下文 |

工具数量不是目标。新增工具必须证明它不能由现有结构化 query/分析操作组合完成，并补充 schema、大小限制、错误和评测。

## 3. 调用上下文

本合同统一使用：

- `ToolCall`：服务端创建的调用 envelope，主键字段为 `tool_call_id`；
- `ToolResult`：工具返回的结构化结果 envelope，必须引用同一个 `tool_call_id`；
- 数据库若需要持久化，可将 ToolCall/ToolResult 内容保存在对应 RunStep 的 input/output 字段中；第一阶段不额外引入含义重复的独立业务实体。

```json
{
  "tool_call_id": "tc_01J...",
  "request_id": "req_01J...",
  "run_id": "run_01J...",
  "run_step_id": "step_01J...",
  "dataset_version_id": "dver_01J...",
  "operation": "query_dataset",
  "parameters": {},
  "idempotency_key": "run_01J...:query_sales:1",
  "deadline_at": "2026-07-20T12:00:30Z"
}
```

以上 envelope 由应用服务创建。模型只生成 `operation` 和经过计划 schema 约束的 parameters；最终执行时服务端覆盖/注入前三个 ID、版本和 deadline。

## 4. 严格输入模型

### 4.1 通用输入

每个工具参数模型都必须包含：

| 字段 | 来源 | 说明 |
|---|---|---|
| `request_id` | 服务端 | 请求追踪，不由模型设置 |
| `dataset_version_id` | 服务端上下文 | 只读绑定，不能出现在模型自由参数中 |
| `run_id` | 服务端上下文 | 关联执行事实 |
| `run_step_id` | 服务端上下文 | 关联步骤 |
| `parameters` | 计划/服务端 | 对应 operation 专属 Pydantic model |
| `limits` | 服务端 policy | max rows/bytes/time，模型不能放宽 |

### 4.2 QueryParameters

逻辑字段：

- `metrics: list[MetricSpec]`，最多 20；
- `dimensions: list[DimensionSpec]`，最多 20；
- `filters: list[FilterSpec]`，最多 50；
- `aggregation: AggregationSpec`；
- `sort: list[SortSpec]`，最多 10；
- `limit: int`，服务端上限默认 1000；
- `offset` 或 cursor 仅供 Artifact 预览，不能用于无限扫描；
- `null_policy`、`date_parse_policy` 等只能取允许枚举。

不包含：`sql`、`python_code`、`file_path`、`storage_key`、`file_id`、任意数据库表名。

### 4.3 AnalyzeParameters

`analyze_distribution`、`analyze_time_series` 和 `detect_anomalies` 使用各自严格模型；共享 Metric/Dimension/Filter 结构，但 operation-specific 规则由 PlanValidator 和 ToolValidator 双重检查。

示例：

```json
{
  "metric": {
    "field": "sales",
    "aggregation": "sum",
    "alias": "total_sales"
  },
  "time_dimension": {
    "field": "order_date",
    "time_grain": "month"
  },
  "comparison": "previous_period",
  "method": "robust_iqr"
}
```

### 4.4 VisualizationParameters

```json
{
  "source_step_id": "monthly_sales",
  "source_artifact_id": null,
  "chart_type": "line",
  "x_field": "order_date",
  "y_fields": ["total_sales"],
  "color_field": null,
  "title": "月度销售额",
  "sort": "asc",
  "options": {
    "show_values": false,
    "allow_zoom": true
  }
}
```

`source_step_id` 必须是 dependency；执行时解析为本 Run 内 ready Artifact。`source_artifact_id` 只能引用已存在且属于同一 DatasetVersion 的 Artifact。前端 renderer 可以使用 ECharts、Vega-Lite 或其他实现，但后端保存的结构化 spec 必须是可迁移、可审计的中间表示。

## 5. 统一返回结构

每个工具无论成功或业务失败，都返回同一 envelope：

```json
{
  "status": "success",
  "summary": {
    "description": "按月份返回销售额汇总",
    "columns": ["order_date", "total_sales"]
  },
  "preview": [
    {"order_date": "2026-01", "total_sales": 1234.5}
  ],
  "row_count": 12,
  "truncated": false,
  "artifact_ids": ["art_01J..."],
  "warnings": [],
  "error": null,
  "execution": {
    "duration_ms": 42,
    "scanned_rows": 10000,
    "tool_schema_version": "1.0"
  }
}
```

失败示例：

```json
{
  "status": "error",
  "summary": {},
  "preview": [],
  "row_count": 0,
  "truncated": false,
  "artifact_ids": [],
  "warnings": [],
  "error": {
    "code": "SCHEMA_FIELD_NOT_FOUND",
    "type": "validation",
    "message": "字段 region 不存在于当前数据版本",
    "details": {"field": "region", "available_fields": ["category", "sales"]},
    "retryable": false,
    "user_action": "选择当前数据版本中的字段"
  },
  "execution": {
    "duration_ms": 3,
    "scanned_rows": 0,
    "tool_schema_version": "1.0"
  }
}
```

成功不代表业务结论成立：空结果、采样、数据质量告警和统计限制必须体现在 `warnings`/`summary` 中，由 ResultValidator 决定能否进入回答阶段。

## 6. ErrorCode 约定

| code | type | retryable | 说明 |
|---|---|---:|---|
| `INVALID_INPUT` | validation | 否 | JSON 形状或枚举错误 |
| `SCHEMA_FIELD_NOT_FOUND` | validation | 否 | 字段不存在 |
| `SCHEMA_TYPE_MISMATCH` | validation | 否 | 聚合/操作与字段类型不兼容 |
| `DATASET_VERSION_NOT_READY` | state | 否 | 版本仍 ingesting/failed/archived |
| `ARTIFACT_NOT_FOUND` | not_found | 否 | 来源产物不存在或不属于当前版本 |
| `EMPTY_RESULT` | business | 否 | 查询合法但无结果 |
| `RESULT_TOO_LARGE` | limit | 否 | 必须加筛选/维度/limit；可返回 artifact 预览 |
| `EXECUTION_TIMEOUT` | runtime | 是 | 在 deadline 内未完成 |
| `EXECUTION_FAILED` | runtime | 依据详情 | 引擎异常，不能把堆栈返回模型 |
| `IDEMPOTENCY_UNKNOWN` | consistency | 需人工 | 外部存储状态无法确认，禁止盲重试 |
| `CANCELLED` | cancelled | 否 | Run 已取消 |
| `ARTIFACT_WRITE_FAILED` | storage | 是 | 结果计算成功但产物写入失败 |

内部 exception 必须映射为上述 code；前端只依赖 code、retryable 和 user_action，不解析自然语言。

## 7. 大结果和 Artifact 策略

推荐初始 policy（服务端固定，后续可配置）：

- 模型 preview 最多 20 行、64 KiB JSON；
- 普通 REST preview 最多 100 行、1 MiB；
- 单次同步工具最长 30 秒；超时进入失败或异步恢复策略；
- `row_count`/`scanned_rows` 仍记录完整统计，不把全量行写入响应；
- 结果超过 preview 限制时写 Artifact，`truncated=true`，模型只得 summary + artifact_id；
- Artifact 下载采用短时 URL 或受控流，不直接暴露 storage_key；
- 清洗数据、报告和错误日志按内容类型设置不同保留和访问策略。

## 8. 幂等、事务和重试

1. RunStep 生成由 `(run_id, plan_step_id, attempt)` 派生的幂等键。
2. 工具开始前写 `step.started`，并在同一事务中把 Step 标记 running。
3. 成功结果写入 Artifact 后，Step completed、Artifact ready、`step.completed`/`artifact.created` 事件在一个数据库事务内提交。
4. 计算成功但 Artifact 写入失败时，Step 不得标记 completed，错误 code 为 ARTIFACT_WRITE_FAILED。
5. 读取同一幂等键时优先返回已有 completed 结果；running 返回当前状态；unknown 不自动重复执行。
6. retryable 只表示可以创建新的 attempt，不表示可以绕过字段/版本校验。

## 9. 模型可见性

模型收到：

- operation 允许值和严格参数 schema；
- 当前版本的字段名、类型和质量摘要；
- 工具 summary、有限 preview、warnings、artifact_id；
- 之前相关步骤的结构化摘要。

模型不收到：

- storage_key、本地路径、数据库连接、任意 SQL/Python；
- 未被 Context Builder 选中的完整历史；
- 超出预算的全量表；
- 内部异常堆栈、API key、worker/lease 信息。

## 10. 工具协议测试

至少建立以下契约测试：

- 每个 operation 的 Pydantic schema `extra=forbid` 和 JSON Schema snapshot；
- 服务端注入 DatasetVersion，模型提供的 file_id/dataset_version_id 被拒绝；
- 成功、空结果、截断、字段错误、超时、Artifact 写入失败的 envelope 均可解析；
- 所有结果 `row_count` 与 preview/truncated 语义一致；
- 失败工具不产生 ready Artifact；
- 重复幂等键不产生第二份业务 Artifact；
- 工具响应不会包含 storage_key、原始异常堆栈或 secret。
