# V2 REST API 合同草案

> 合同状态：V2 设计合同，当前尚未实现。当前可运行 API 仍是 `/api/v1`；本文中的 `/api/v2` 路由均不存在于当前运行时代码。实现阶段以 Pydantic Schema、生成的 OpenAPI 和正式数据库迁移为最终事实来源。

## 1. 范围与版本

- Base path：`/api/v2`。
- 本文只定义合同，不实现路由。
- 所有 JSON 使用 UTF-8、snake_case、UTC ISO-8601 时间。
- ID 是服务端生成的不透明字符串；客户端不能解析其结构。
- REST 是最终状态事实来源；SSE 是增量事件通道。

## 2. 通用响应

### 2.1 单资源成功

```json
{
  "data": {},
  "meta": {
    "request_id": "req_01J...",
    "schema_version": "1.0"
  }
}
```

### 2.2 游标分页

```json
{
  "data": [],
  "meta": {
    "request_id": "req_01J...",
    "schema_version": "1.0",
    "next_cursor": "opaque_cursor_or_null",
    "has_more": false
  }
}
```

默认 `limit=20`，最大 100。cursor 是服务端不透明值，不能由客户端拼接。

### 2.3 错误

```json
{
  "error": {
    "code": "DATASET_NOT_FOUND",
    "message": "数据集不存在",
    "details": {},
    "retryable": false,
    "request_id": "req_01J..."
  }
}
```

通用状态码：

- `400` 请求语义错误；
- 第一阶段是单用户本地项目，不定义登录、认证、授权或租户错误；未来如引入多用户能力，通过版本化合同补充 401/403；
- `404` 资源不存在或不可见；
- `409` 状态冲突、幂等键参数冲突、版本不匹配；
- `413` 上传或响应请求超限；
- `415` 文件格式不支持；
- `422` Pydantic/schema 校验失败；
- `429` 运行并发或频率限制；
- `500` 未分类服务错误；
- `503` 执行器/存储临时不可用。

## 3. 资源摘要

### DatasetSummary

```json
{
  "id": "dset_01J...",
  "name": "销售数据",
  "description": null,
  "status": "active",
  "default_version_id": "dver_01J...",
  "version_count": 1,
  "default_version": {
    "version_number": 1,
    "status": "ready",
    "row_count": 10000,
    "column_count": 12
  },
  "created_at": "2026-07-20T10:00:00Z",
  "updated_at": "2026-07-20T10:01:00Z"
}
```

### RunSummary

```json
{
  "id": "run_01J...",
  "conversation_id": "conv_01J...",
  "dataset_version_id": "dver_01J...",
  "trigger_message_id": "msg_01J...",
  "answer_message_id": null,
  "status": "running",
  "current_phase": "plan_generation",
  "progress": {"completed_steps": 0, "total_steps": null},
  "failure": null,
  "created_at": "2026-07-20T10:10:00Z",
  "updated_at": "2026-07-20T10:10:01Z"
}
```

## 4. Dataset API

### 4.1 POST `/api/v2/datasets`

上传 CSV/XLSX，原子创建 Dataset 和第一个 ingesting DatasetVersion。

请求：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `file` | binary | 是 | CSV/XLSX；大小由服务端 policy 限制 |
| `name` | string | 否 | 缺省使用安全化文件名 |
| `description` | string | 否 | 数据集说明 |

Header：`Idempotency-Key` 必填。相同 key+相同文件 hash 返回首次结果；相同 key+不同参数返回 409。

响应：`201 Created`

```json
{
  "data": {
    "dataset": {"id": "dset_01J...", "name": "销售数据", "status": "active"},
    "version": {
      "id": "dver_01J...",
      "dataset_id": "dset_01J...",
      "version_number": 1,
      "source_type": "upload",
      "status": "ingesting",
      "original_filename": "sales.csv"
    }
  },
  "meta": {"request_id": "req_01J...", "schema_version": "1.0"}
}
```

错误：400 空文件；409 幂等冲突；413 文件过大；415 非 CSV/XLSX；422 文件名/表单错误；503 存储不可用。

幂等：通过 Idempotency-Key 幂等。前端场景：上传入口和上传进度初始化。

### 4.2 GET `/api/v2/datasets`

Query：`cursor`、`limit`、`status=active|archived`、`search`、`sort=updated_at_desc`。

响应：`200`，`data: DatasetSummary[]`，游标分页。

错误：400 非法 cursor/limit。幂等：是。前端场景：数据集列表、搜索与恢复最近工作。

### 4.3 GET `/api/v2/datasets/{dataset_id}`

响应：`200`，DatasetDetail，包含 DatasetSummary、default version 摘要、版本数、对话数和允许操作。

错误：404。幂等：是。不分页。前端场景：数据集工作区头部和版本选择器初始化。

### 4.4 GET `/api/v2/datasets/{dataset_id}/versions`

Query：`cursor`、`limit`、`status`。

响应：`200`，版本摘要按 version_number desc 游标分页。

错误：404 Dataset；400 cursor。幂等：是。前端场景：版本历史、切换或比较入口。

### 4.5 GET `/api/v2/dataset-versions/{version_id}`

响应：`200`

```json
{
  "data": {
    "id": "dver_01J...",
    "dataset_id": "dset_01J...",
    "version_number": 1,
    "parent_version_id": null,
    "source_type": "upload",
    "status": "ready",
    "original_filename": "sales.csv",
    "size_bytes": 102400,
    "row_count": 10000,
    "column_count": 12,
    "schema": {"schema_version": "1.0", "columns": []},
    "profile": {"schema_version": "1.0", "quality": {}},
    "error": null,
    "created_at": "2026-07-20T10:00:00Z",
    "ready_at": "2026-07-20T10:01:00Z"
  },
  "meta": {"request_id": "req_01J...", "schema_version": "1.0"}
}
```

storage_key、hash 以外的内部执行字段默认不返回；hash 可作为高级详情字段。

错误：404。幂等：是。不分页。前端场景：数据画像、字段选择、运行绑定确认。

## 5. Conversation API

### 5.1 POST `/api/v2/conversations`

请求：

```json
{
  "dataset_id": "dset_01J...",
  "default_version_id": "dver_01J...",
  "title": "销售趋势分析"
}
```

`default_version_id` 可空，服务端使用 Dataset.default_version_id；必须属于 dataset_id 且 ready/可读。

响应：`201`，ConversationDetail（messages=[]，runs=[]）。

错误：404 Dataset/Version；409 Dataset archived 或版本不属于 Dataset；422 校验错误。

幂等：使用可选 Idempotency-Key。前端场景：新建分析会话。

### 5.2 GET `/api/v2/conversations/{conversation_id}`

Query：

- `message_cursor`、`message_limit`（默认 50，最大 100）；
- `include=recent_runs` 可选；
- 不内联 Artifact 全量内容。

响应：`200`，包含 Conversation、按时间排序的 Message page、每条消息关联的 RunSummary、next cursor。

错误：404；400 cursor。幂等：是。消息分页：是。前端场景：打开历史会话、刷新恢复。

## 6. AnalysisRun API

### 6.1 POST `/api/v2/conversations/{conversation_id}/runs`

在同一事务中创建 committed user Message、queued AnalysisRun 和 `run.started` durable event。

请求：

```json
{
  "message": "按月份分析销售额趋势",
  "dataset_version_id": "dver_01J...",
  "confirm_version_switch": false,
  "reply_to_message_id": null,
  "parent_run_id": null,
  "retry_of_run_id": null,
  "context": {
    "include_message_ids": [],
    "include_artifact_ids": []
  }
}
```

规则：

- `dataset_version_id` 是用户/前端选择，不是模型选择；为空时按 conversation default 解析，并把最终值写入 Run。
- 追问传 parent_run_id 时默认固定父 Run 版本；若请求版本不同，需要显式确认字段 `confirm_version_switch=true`（可在最终合同中加入）。
- context 中 ID 只是用户显式引用，服务端仍验证归属并生成最终 context snapshot。

Header：`Idempotency-Key` 必填。

响应：`202 Accepted`

```json
{
  "data": {
    "message": {
      "id": "msg_01J...",
      "role": "user",
      "content_text": "按月份分析销售额趋势",
      "status": "committed"
    },
    "run": {
      "id": "run_01J...",
      "status": "queued",
      "dataset_version_id": "dver_01J..."
    },
    "events_url": "/api/v2/runs/run_01J.../events"
  },
  "meta": {"request_id": "req_01J...", "schema_version": "1.0"}
}
```

错误：404 Conversation/Version/parent Run；409 archived、版本冲突、幂等参数冲突、并发上限；422 请求；429 运行限流；503 执行器不可用。

幂等：必须。相同 Conversation + Idempotency-Key 返回同一 Message/Run。前端场景：提交分析问题、重跑、追问。

### 6.2 GET `/api/v2/runs/{run_id}`

响应：`200` RunDetail，包含：

- RunSummary；
- active plan 摘要（goal、revision、status、step_count、warnings）；
- progress；
- trigger/answer Message 摘要；
- Artifact type/count；
- `last_event_sequence`；
- `allowed_actions`（cancel/retry/open_artifact 等）。

错误：404。幂等：是。不分页。前端场景：SSE 后核对最终状态、刷新恢复、失败页。

### 6.3 GET `/api/v2/runs/{run_id}/steps`

Query：`cursor`、`limit`（默认 50，最大 100）、`phase`、`status`。

响应：`200`，RunStep page，按 sequence asc。默认不返回完整 `input_json`、worker、lease 或内部 error stack；返回脱敏 input summary、output summary、error、artifact_ids。

错误：404 Run；400 cursor。幂等：是。分页：是。前端场景：进度面板、步骤折叠详情、失败定位。

### 6.4 GET `/api/v2/runs/{run_id}/artifacts`

Query：`cursor`、`limit`、`artifact_type`、`status=ready`。

响应：`200`，ArtifactSummary page。

错误：404 Run；400 filter。幂等：是。分页：是。前端场景：结果区、下载列表、报告输入来源。

### 6.5 POST `/api/v2/runs/{run_id}/cancel`

请求：`{"reason": "user_requested"}`。对 queued/running Run 发出取消请求。最小状态枚举不包含 `cancelling`：服务端可记录 `cancel_requested_at`，在清理和执行器确认停止后原子进入 cancelled；确认前状态保持 queued/running。

响应：`202` RunSummary。

错误：404；409 Run 已 completed/failed 或当前阶段不可取消。对已 cancelled 或已有同一取消请求的 Run 返回当前事实状态，保持幂等。前端场景：停止分析。

完整运行重试不原地恢复 failed Run。前端再次调用创建 Run API，并传 `retry_of_run_id`。

## 7. Artifact API

### 7.1 GET `/api/v2/artifacts/{artifact_id}`

Query：

- `preview_cursor`、`preview_limit`（仅 table/dataset_preview；默认 50，最大 100）；
- `include=config` 可获取前端渲染需要的结构化 chart spec；
- 不返回 storage_key。

响应：`200`

```json
{
  "data": {
    "id": "art_01J...",
    "dataset_version_id": "dver_01J...",
    "run_id": "run_01J...",
    "run_step_id": "step_01J...",
    "artifact_type": "table",
    "status": "ready",
    "title": "月度销售额",
    "content_format": "parquet",
    "size_bytes": 4096,
    "row_count": 12,
    "schema": {},
    "summary": {},
    "preview": [],
    "preview_meta": {"next_cursor": null, "has_more": false},
    "config": null,
    "download_available": true,
    "created_at": "2026-07-20T10:11:00Z"
  },
  "meta": {"request_id": "req_01J...", "schema_version": "1.0"}
}
```

错误：404；409 Artifact not ready/quarantined；400 preview cursor。幂等：是。预览分页：table 类是。前端场景：主结果、详情抽屉、交互图表。

### 7.2 GET `/api/v2/artifacts/{artifact_id}/download`

响应策略：

- local storage：`200` 流式文件响应；
- object store：`302/307` 到短时签名 URL；
- inline-only metric：`409 DOWNLOAD_NOT_AVAILABLE`。

Headers：安全文件名、正确 Content-Type、Content-Length；禁止泄露 storage_key。

错误：404；409 not ready/not downloadable；410 deleted；416 range error。幂等：是。分页：否。前端场景：下载表格、报告、导出图表或清洗数据。

## 8. SSE Endpoint

### GET `/api/v2/runs/{run_id}/events`

Accept：`text/event-stream`。支持：

- `Last-Event-ID` header；
- 可选 `after_sequence` query，二者同时存在时使用更大的已确认位置；
- durable event replay 后切换实时订阅；
- Run terminal 且所有事件发送完后关闭连接。

响应：`200 text/event-stream`。事件格式见 `SSE_PROTOCOL.md`。

连接建立前错误：404 Run；400 invalid sequence；410 event retention expired；429 connection limit。连接建立后的运行错误使用 `run.failed` event，不改变 HTTP status。

幂等：读取操作。前端场景：运行进度、Artifact 实时出现和完整答案提交。第一阶段不要求 token 级答案增量。

## 9. API 幂等矩阵

| Endpoint | 幂等要求 | Key/机制 |
|---|---|---|
| POST datasets | 是 | Idempotency-Key + file hash + normalized fields |
| POST conversations | 建议 | Idempotency-Key |
| POST runs | 必须 | Conversation + Idempotency-Key + request hash |
| POST cancel | 是 | Run 当前状态 |
| 所有 GET | 是 | 资源版本与 cursor |

服务端至少保留幂等记录 24 小时；具体时长为 OPEN_QUESTIONS 中的产品/运维决定。

## 10. 缓存与并发

- Dataset/Version/Artifact detail 可返回 ETag；`If-None-Match` 命中返回 304。
- 可编辑 Dataset/Conversation metadata 后续 PATCH 必须使用 `If-Match` 或 `updated_at` 乐观锁；本阶段未定义 PATCH。
- Run/Step 状态不允许客户端 PATCH。
- 前端不能根据本地 SSE 自行宣告 completed，必须收到 durable `run.completed` 或 GET Run 验证。

## 11. OpenAPI 与合同测试

实现后：

- Pydantic schema 是 OpenAPI 唯一来源；
- 错误 envelope 和 cursor meta 使用共享 model；
- 为每个 endpoint 建立 success/error/idempotency 合同测试；
- 前端类型从 OpenAPI 生成或由合同检查，不再手工维护第二份不一致类型；
- SSE schema 单独版本化并建立事件 fixture，不依赖 OpenAPI 自动表达 streaming payload。
