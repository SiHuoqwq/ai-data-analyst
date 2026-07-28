# 最小 V2 后端运行说明

## 实现范围

当前实现提供两种可切换的 V2 分析闭环：

```text
为 V1 文件创建 Conversation
→ 提交分析问题
→ 原子保存 user Message、queued AnalysisRun 和 run.started
→ Fake Provider 生成固定计划，或 DeepSeek 生成受限结构化计划
→ 服务端校验白名单工具和严格参数
→ pandas 执行分组、月度趋势和异常组合计算
→ matplotlib 生成柱状图或折线图
→ 保存 RunStep 和 text/metric/table/chart Artifact
→ Fake 返回固定结论，或 DeepSeek 仅根据本 Run 的结构化证据总结
→ 原子保存最终 assistant Message 和 completed 终态
→ REST 查询最终状态和会话历史，SSE 重放过程事件
```

`/api/v1` 与 `/api/v2` 同时注册。V2 安全默认仍是 `FakeAnalysisProvider`；显式配置后可使用 `DeepSeekProvider`。自动测试始终使用 Fake 或 Mock HTTP Transport，不发起真实模型请求。

## 安全启动

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

不要直接迁移用户当前的 `app.db`。验证时应使用临时数据库，或者先把 V1 数据库复制到仓库外，再对副本执行迁移。

空临时数据库示例：

```powershell
$env:ALEMBIC_DATABASE_URL = "sqlite:///D:/Codex/Temp/ai-data-analyst-v2.db"
python -m alembic upgrade head

$env:DATABASE_URL = $env:ALEMBIC_DATABASE_URL
$env:V2_PROVIDER = "fake"
python -m app.run
```

`alembic.ini` 的缺省文件名是 `app_v2.db`，但开发和测试推荐始终显式设置 `ALEMBIC_DATABASE_URL`，防止误迁移其他数据库。

迁移验证命令：

```powershell
$env:ALEMBIC_DATABASE_URL = "sqlite:///D:/Codex/Temp/ai-data-analyst-migration-check.db"
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

首次 revision 在空库中建立 V1 四表和 V2 四表。在已有 V1 库副本中只增加：

- `analysis_runs`
- `run_steps`
- `artifacts`
- `run_events`

`downgrade base` 只删除上述 V2 表，保留 V1 的 `files`、`conversations`、`messages` 和 `charts`。

## Provider 配置

### Fake 模式

`.env` 配置：

```dotenv
V2_PROVIDER=fake
V2_FAKE_STEP_DELAY_SECONDS=0
```

Fake Provider 不读取 API Key、不访问外部网络。测试通过 FastAPI 依赖覆盖注入可控的慢速或失败 Provider，用于验证取消和失败路径；Mock 逻辑不在 API 路由中。

真实 smoke test 可以临时设置 `V2_FAKE_STEP_DELAY_SECONDS=0.5`，制造可取消窗口。固定输入 `[fake:fail]` 只用于 Fake Provider 诊断，可确定地产生 failed Run；它不会进入其他 Provider。

### DeepSeek 模式

仅在人工验收时显式设置：

```dotenv
V2_PROVIDER=deepseek
DEEPSEEK_API_KEY=replace-with-local-secret
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
V2_LLM_TIMEOUT_SECONDS=75
V2_LLM_MAX_RETRIES=1
V2_MAX_TOOL_ROUNDS=5
V2_MAX_PROMPT_CHARS=24000
```

缺少 API Key 时，创建 Run 前返回：

```json
{
  "error": {
    "code": "PROVIDER_NOT_CONFIGURED",
    "message": "真实分析服务尚未配置 API Key",
    "details": {},
    "retryable": false,
    "request_id": "..."
  }
}
```

网络超时和 5xx/429 最多按配置重试一次；401/403 不重试。工具调用总轮次受 `V2_MAX_TOOL_ROUNDS` 限制。字段错误时，Provider 最多在剩余轮次预算内修正一次，之后失败并持久化明确错误码。

发送给模型的内容只包含字段名、类型、缺失摘要、有限历史、聚合结果预览和 Artifact 引用；不发送完整数据集、文件物理路径、数据库连接、`.env` 或 API Key。日志不记录完整 Prompt、原始数据或完整模型响应。

## API

Base path：`/api/v2`。

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/conversations` | 为现有 V1 文件创建 Conversation |
| `POST` | `/conversations/{conversation_id}/runs` | 创建 Message 和 AnalysisRun |
| `GET` | `/runs/{run_id}` | 查询 Run canonical 状态 |
| `GET` | `/runs/{run_id}/steps` | 查询 RunStep |
| `GET` | `/runs/{run_id}/artifacts` | 查询结构化 Artifact |
| `GET` | `/artifacts/{artifact_id}` | 查询单个 Artifact |
| `GET` | `/artifacts/{artifact_id}/download` | 下载静态图表 |
| `GET` | `/runs/{run_id}/events` | SSE 事件流与持久事件重放 |
| `POST` | `/runs/{run_id}/cancel` | 请求合作式取消 |

创建请求必须携带 `Idempotency-Key`：

```http
POST /api/v2/conversations/{conversation_id}/runs
Idempotency-Key: demo-request-001
Content-Type: application/json
```

```json
{
  "message": "检查销售数据并生成概览",
  "dataset_version_id": "existing-v1-file-id",
  "context": {
    "include_message_ids": [],
    "include_artifact_ids": []
  }
}
```

响应：

```json
{
  "data": {
    "message": {
      "id": "uuid",
      "role": "user",
      "content_text": "检查销售数据并生成概览",
      "status": "committed"
    },
    "run": {
      "id": "uuid",
      "status": "queued",
      "dataset_version_id": "existing-v1-file-id"
    },
    "events_url": "/api/v2/runs/{run_id}/events"
  },
  "meta": {
    "request_id": "uuid",
    "schema_version": "1.0"
  }
}
```

同一 Conversation 中，相同幂等键和相同请求返回同一 Run；相同键配合不同请求返回 `409 IDEMPOTENCY_CONFLICT`。

## Conversation 与 Message 闭环

### 创建 Conversation

迁移期仍使用 V1 `files` 和 `conversations` 表。新上传文件尚无会话时，先调用：

```http
POST /api/v2/conversations
Content-Type: application/json
```

```json
{
  "file_id": "existing-v1-file-id",
  "title": "销售趋势分析"
}
```

`title` 可省略或只包含空白，服务端使用稳定默认值 `新分析`。文件不存在时返回统一的 `404 DATASET_NOT_FOUND`。创建操作不会调用 Provider，也不会创建空的用户或助手消息。

成功响应：

```json
{
  "data": {
    "id": "conversation-uuid",
    "file_id": "existing-v1-file-id",
    "title": "销售趋势分析",
    "mode": "agent",
    "created_at": "2026-07-28T12:00:00Z"
  },
  "meta": {
    "request_id": "request-uuid",
    "schema_version": "1.0"
  }
}
```

创建后可以通过现有 `GET /api/v1/conversations/{conversation_id}` 读取会话和消息。

### Run 与消息关系

0001 migration 已包含冻结合同定义的真实外键：

- `trigger_message_id` 指向本次 Run 的 user Message；
- `answer_message_id` 指向 completed Run 的 assistant Message。

因此本轮没有增加重复的 `input_message_id` / `output_message_id` 数据库列。V2 API 保留合同字段，并额外返回以下兼容别名：

- `input_message_id = trigger_message_id`
- `output_message_id = answer_message_id`
- `finished_at = completed_at`
- `error = failure`

提交分析问题时，user Message、queued AnalysisRun 和 `run.started` 在同一数据库事务中提交。事件创建或 Run 创建失败时，事务回滚，不留下孤儿 user Message。

completed 时，最终回答保存为一条 assistant Message，并在同一终态事务中写入 `answer_message_id`、`answer.completed` 和 `run.completed`。Artifact payload 不写入助手正文，仍通过 Artifact API 查询。

### 幂等、失败和取消

- 相同 Conversation、Idempotency-Key 和相同请求返回原 Run 和原 user Message；
- 幂等重放不会再次提交后台执行，不重复创建 assistant Message；
- 相同 Key 对应不同请求返回 `409 IDEMPOTENCY_CONFLICT`，消息数量不变；
- failed Run 保留 user Message，`answer_message_id`/`output_message_id` 为 null，不生成伪成功助手消息；
- cancelled Run 采用相同规则，重复取消不增加消息；
- 已生成的部分 Artifact 可按 Run 继续查询。

### 同一 Conversation 多轮分析

同一 Conversation 可以顺序创建多个 Run，消息历史保存为：

```text
user 1
assistant 1
user 2
assistant 2
```

每个 Run 只引用自己的 trigger/answer Message，Artifact 继续按 `run_id` 隔离。Fake Provider 不读取历史消息进行推理。DeepSeek 最多读取最近 10 条 user/assistant 消息，并受总字符限制；历史只帮助理解追问，所有数字仍需由本次 Run 的工具重新计算。

前端未来的标准调用顺序：

```text
POST /api/v2/conversations
POST /api/v2/conversations/{conversation_id}/runs
GET  /api/v2/runs/{run_id}/events
GET  /api/v2/runs/{run_id}
GET  /api/v2/runs/{run_id}/artifacts
GET  /api/v1/conversations/{conversation_id}
```

## SSE

事件使用标准 wire format：

```text
id: event-uuid
event: artifact.created
data: {"event_id":"event-uuid","event_type":"artifact.created","run_id":"run-uuid","sequence":5,"timestamp":"2026-07-28T10:00:00Z","schema_version":"1.0","payload":{}}

```

持久业务事件：

- `run.started`
- `run.status`
- `step.started`
- `step.completed`
- `artifact.created`
- `answer.completed`
- `run.completed`
- `run.failed`
- `run.cancelled`

单个 Run 的所有事件（包括 `heartbeat`）使用同一持久化 `sequence`，从 1 严格递增。支持 `after_sequence` 和 `Last-Event-ID` 重放。terminal Run 发送完持久事件后关闭连接。

`heartbeat` 每 15 秒最多持久化并发送一次，占用统一 sequence；多个订阅者复用同一事件序列。本阶段不发送 `answer.delta`。

REST 与数据库是最终事实来源。页面刷新后应重新查询 Run、Steps 和 Artifacts，不应仅依赖内存中的 SSE 状态。

## Artifact

所有 payload 在写入前经过严格 Pydantic 校验：

- `text`：`format` 和 `content`
- `metric`：`label`、原始值、展示值和单位
- `table`：结构化 columns 与最多 100 行有限 preview
- `chart`：静态渲染器、图表类型、标题、浏览器 URL 和替代文本

Chart Artifact 返回：

```json
{
  "renderer": "static-image",
  "chart_type": "bar",
  "title": "数据概览",
  "image_url": "/api/v2/artifacts/{artifact_id}/download",
  "alt_text": "按分类展示销售额的柱状图"
}
```

API 和 SSE 不返回 `storage_key`、`./storage/...`、Windows 物理路径或异常堆栈。

## 已迁移的确定性能力

当前 V2 提供：

- V1 CSV/XLSX parser；
- 中英文数值、类别、日期字段识别及缺失摘要；
- 严格 Pydantic 工具参数，拒绝未知字段、聚合方式、Python、SQL 和路径参数；
- 多维分组的 count、sum、mean、min、max 和布尔比例；
- 按月、按类别的多指标趋势统计；
- 基于分位数和最小样本量的高报名低完成率组合识别；
- 基于环比和首末变化的增长、下滑和波动信号；
- 中文字体静态柱状图和折线图；
- V1 文件、Conversation 和 Message 持久化。

上述工具产生真实的 metric、table 和 chart Artifact；DeepSeek 最终回答只接收这些结果的结构化证据，不允许把样例行猜测成全量结论。

尚未迁移：

- 其余 V1 分布、相关性、IQR 异常值、散点图、热力图等工具；
- 完整 AnalysisPlan revision 与 PlanValidator；
- Dataset、DatasetVersion 的正式 V2 表和上传 API；
- 结构化交互式图表 Schema；
- 报告导出和完整报告管理。

## 演示问题

首轮工具覆盖以下两类自然语言问题及近似表达：

1. 对课程类别、难度、购买渠道和学习设备做多维分组，比较完成率、退款率、评分和报名人数，识别高报名低完成率组合并生成表格与柱状图。
2. 按月、按课程类别统计报名人数、实付金额和平均完成率，记录增长、下滑和波动规则并生成趋势表和折线图。

模型负责选择字段和组织结论；所有统计值由 pandas 工具计算。当前不承诺任意开放式数据科学问题，也未迁移全部 V1 工具。

## 合作式取消

- queued Run：取消请求立即进入 `cancelled` 并写终止事件；
- running Run：先记录 `cancel_requested_at`，执行器在计划生成后、每个步骤前后和终态提交前检查；
- 重复取消 cancelled Run 返回同一事实状态，不生成第二个终止事件；
- completed/failed Run 返回 `409 RUN_NOT_CANCELLABLE`；
- 已开始的同步 pandas/matplotlib 调用不能强制杀死，必须等到下一个合作检查点。

取消不会把历史 Run 改回 queued/running。再次分析应创建新 Run。

## V1/V2 过渡适配

本轮没有实现完整 Dataset/DatasetVersion 和 V2 Conversation 数据迁移。为形成最小真实闭环：

- V2 `conversation_id` 暂时引用 V1 `conversations.id`；
- V2 `dataset_version_id` 暂时引用不可变使用的 V1 `files.id`；
- trigger/answer Message 暂时保存在 V1 `messages`；
- V2 Run、Step、Artifact 和 Event 使用独立新表。

这是最小实现相对目标数据模型的过渡偏差。它避免伪造 DatasetVersion，也避免在本轮扩大到完整 V1→V2 数据迁移。实现正式 DatasetVersion 后必须通过新 migration 和适配层替换这些临时 FK，不能把 `files.id` 永久解释成 DatasetVersion。

## 测试

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q
```

测试全部使用临时 SQLite、匿名 CSV/XLSX、临时图表目录和 `httpx.MockTransport`，不读取真实 `app.db`，不调用真实 LLM，不在仓库 storage 留下测试图片。
