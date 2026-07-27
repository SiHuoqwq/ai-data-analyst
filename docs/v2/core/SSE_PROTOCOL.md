# V2 SSE 事件协议

> 合同状态：V2 设计合同，当前尚未实现。当前系统仍使用 `/api/v1/chat/stream` 的 V1 事件；本文描述 V2 目标协议。实现阶段以 Pydantic 事件 Schema、协议测试和正式数据库迁移为最终事实来源。

## 1. 定位与第一阶段范围

SSE 用于把 AnalysisRun 的持久化状态变化增量推送给前端。REST 和数据库是最终事实来源，SSE 不是唯一状态存储。

V2 第一阶段：

- 不要求 token 级答案流式；
- 只在最终助手 Message 已提交后发送 `answer.completed`；
- 计划生成、计划校验、确定性执行、结果校验和回答生成通过 `run.status.payload.current_phase` 表达；
- 前端收到 terminal event 后仍通过 REST 获取 canonical Run、Steps、Artifacts 和 Message；
- 当前 `/api/v1` 的 `tool`、`chart`、`text`、`error`、`done` 不是本文协议的一部分。

第一阶段业务事件固定为：

```text
run.started
run.status
step.started
step.completed
artifact.created
answer.completed
run.completed
run.failed
run.cancelled
heartbeat
```

`answer.delta`、独立计划事件和步骤进度事件属于后续兼容扩展，不是第一阶段实现要求。

## 2. Wire format

```text
id: evt_01J...
event: step.started
data: {"event_id":"evt_01J...","event_type":"step.started","run_id":"run_01J...","sequence":4,"timestamp":"2026-07-20T10:10:04Z","schema_version":"1.0","payload":{}}

```

统一 envelope：

```json
{
  "event_id": "evt_01J...",
  "event_type": "step.started",
  "run_id": "run_01J...",
  "sequence": 4,
  "timestamp": "2026-07-20T10:10:04Z",
  "schema_version": "1.0",
  "payload": {}
}
```

字段约束：

| 字段 | 约束 |
|---|---|
| `event_id` | 全局唯一，同时作为 SSE `id`，用于去重和 Last-Event-ID |
| `event_type` | 必须是已注册的 dot-notation 事件名 |
| `run_id` | 当前连接目标 Run；不得混入其他 Run |
| `sequence` | Run 内从 1 递增，数据库 unique `(run_id, sequence)` |
| `timestamp` | UTC ISO-8601 |
| `schema_version` | 第一阶段为 `1.0` |
| `payload` | 由 event_type 对应的严格 Pydantic model 校验 |

SSE 每个事件只发送一个 `data:` JSON；不依赖换行拼接未声明字段。

## 3. 事件 payload

### 3.1 `run.started`

在 committed user Message、queued AnalysisRun 和 durable event 同一事务提交后发送。

```json
{
  "status": "queued",
  "conversation_id": "conv_01J...",
  "dataset_version_id": "dver_01J...",
  "trigger_message_id": "msg_01J...",
  "parent_run_id": null,
  "retry_of_run_id": null
}
```

每个 Run 只发送一次。

### 3.2 `run.status`

用于表达非终态状态或当前内部阶段。Run 的公共状态只允许 queued/running/completed/failed/cancelled。

```json
{
  "status": "running",
  "current_phase": "plan_validation",
  "progress": {
    "completed_steps": 1,
    "total_steps": 5
  },
  "summary": "正在校验分析计划"
}
```

`current_phase` 可取：

```text
plan_generation
plan_validation
execution
result_validation
answer_generation
```

前端不能把 current_phase 当成额外 Run status。

### 3.3 `step.started`

```json
{
  "step_id": "step_01J...",
  "plan_step_id": "monthly_sales",
  "step_sequence": 2,
  "phase": "execution",
  "operation": "query_dataset",
  "display_name": "按月份汇总销售额",
  "status": "running",
  "attempt": 1
}
```

`step_sequence` 是展示顺序，envelope `sequence` 才是事件顺序。

### 3.4 `step.completed`

只在 RunStep 已持久化为 completed 后发送。

```json
{
  "step_id": "step_01J...",
  "status": "completed",
  "summary": "已生成 12 个月汇总结果",
  "row_count": 12,
  "artifact_ids": ["art_01J..."],
  "warnings": [],
  "duration_ms": 126
}
```

失败步骤不发送伪装的 `step.completed`。第一阶段由 `run.failed` 携带 `failed_step_id`。

### 3.5 `artifact.created`

只在 Artifact 已持久化为 ready 后发送。第一阶段核心类型为 text、metric、table、chart。

```json
{
  "artifact_id": "art_01J...",
  "step_id": "step_01J...",
  "artifact_type": "chart",
  "title": "月度销售额趋势",
  "status": "ready",
  "summary": {"chart_type": "line"},
  "preview_url": "/api/v2/artifacts/art_01J..."
}
```

Chart Artifact：

- V2 目标是结构化、可校验的中立 chart spec；
- renderer 采用 ECharts、Vega-Lite 或其他方案留待开放问题确认；
- V1 兼容 Artifact 可引用后端生成的静态 PNG；
- payload 和 API 不得暴露服务器物理路径，只返回 artifact_id 和受控 API URL。

### 3.6 `answer.completed`

第一阶段只发送完整、已提交答案的引用，不发送 token delta。

```json
{
  "answer_message_id": "msg_01K...",
  "content_format": "markdown",
  "artifact_ids": ["art_01J..."]
}
```

前端通过 Message API 获取完整正文；不得仅凭临时缓冲区创建 committed Message。

### 3.7 `run.completed`

与 AnalysisRun completed、answer Message committed 在同一事务中持久化。

```json
{
  "status": "completed",
  "answer_message_id": "msg_01K...",
  "artifact_ids": ["art_01J..."],
  "completed_at": "2026-07-20T10:10:20Z"
}
```

这是正常路径最后一个业务事件。

### 3.8 `run.failed`

```json
{
  "status": "failed",
  "error": {
    "code": "TOOL_EXECUTION_FAILED",
    "message": "分析步骤执行失败",
    "retryable": true,
    "failed_step_id": "step_01J..."
  },
  "partial_artifact_ids": [],
  "retry_of_run_id": null
}
```

错误必须脱敏；模型原始输出、密钥、storage key 和异常堆栈不得进入普通前端 payload。

### 3.9 `run.cancelled`

服务端确认执行停止并完成必要清理后发送。

```json
{
  "status": "cancelled",
  "reason": "user_requested",
  "cancelled_at": "2026-07-20T10:10:12Z",
  "partial_artifact_ids": []
}
```

取消请求确认前 Run 仍保持 queued/running，并可通过 `run.status` 表达“取消请求已接收”；第一阶段不增加 `cancelling` 状态。

### 3.10 `heartbeat`

```json
{
  "server_time": "2026-07-20T10:10:15Z",
  "last_event_sequence": 8
}
```

heartbeat 不改变业务状态，可以不写入 durable event 表，也不占用业务 sequence；实现必须在协议测试中固定该选择。

## 4. 顺序与事务保证

写 durable event 时：

1. 锁定 AnalysisRun 或使用原子 sequence 分配；
2. 分配 `last_event_sequence + 1`；
3. 在同一事务中更新领域状态并插入 run_events；
4. Commit 成功后发布；
5. 发布失败不回滚业务状态，重连通过 replay 获取事件。

必须满足：

- `run.started` 最先；
- `step.started` 早于对应 `step.completed`；
- Artifact ready 后才能 `artifact.created`；
- `answer.completed` 早于 `run.completed`；
- terminal 事件只能有一个：`run.completed`、`run.failed` 或 `run.cancelled`；
- terminal event 后不再产生业务事件。

## 5. 断线重连与 replay

Endpoint：

```text
GET /api/v2/runs/{run_id}/events
Accept: text/event-stream
Last-Event-ID: evt_01J...
```

也可支持 `after_sequence` query。客户端断线后：

1. GET Run 获取 canonical status 和 `last_event_sequence`；
2. 使用 Last-Event-ID 或 after_sequence 重新连接；
3. 服务端按 sequence 重放 durable events；
4. 重放完成后切换实时订阅；
5. terminal Run 重放结束后关闭；
6. retention 过期返回 410，前端通过 REST 重建 Run/Steps/Artifacts/Message。

浏览器断开不自动取消 Run。用户取消必须调用 cancel API。

## 6. 前端 reducer

前端对每个 Run 保存 `seen_event_ids` 和 `last_sequence`：

- event_id 已见：忽略；
- sequence 等于 last+1：应用；
- sequence 大于 last+1：暂停增量应用并触发 replay/reconcile；
- Step 和 Artifact 按 ID upsert，禁止简单 append；
- terminal event 后请求 REST canonical state；
- 前端不能自行把 running 推断为 completed。

最小映射：

| 事件 | Store 行为 |
|---|---|
| `run.started` | upsert queued Run |
| `run.status` | 更新 status/current_phase/progress |
| `step.started` | upsert running Step |
| `step.completed` | Step completed，关联 artifact IDs |
| `artifact.created` | upsert ready Artifact |
| `answer.completed` | 保存 answer message 引用并拉取正文 |
| `run.completed` | Run completed，REST reconcile |
| `run.failed` | Run failed，保存结构化错误 |
| `run.cancelled` | Run cancelled，保留可用部分产物 |
| `heartbeat` | 只更新连接健康信息 |

## 7. Retention 与合同测试

- terminal、step completed、artifact 和 answer 事件必须持久化并可在保留期内重放；
- heartbeat 无需长期保留；
- 事件过期不影响 Run/Step/Artifact 的 REST 恢复；
- 所有 payload 必须通过 Pydantic Schema；
- 合同测试覆盖正常完成、失败、取消、重复事件、sequence gap、断线重放、retention 过期和非法 payload；
- 第一阶段明确断言不会发送 `answer.delta`；
- 当前 V1 SSE 事件不得混入 V2 Endpoint。
