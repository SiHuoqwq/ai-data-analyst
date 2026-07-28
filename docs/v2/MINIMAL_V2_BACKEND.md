# 最小 V2 后端运行说明

## 实现范围

当前实现提供一条不调用真实 LLM 的最小分析闭环：

```text
提交分析问题
→ 创建 queued AnalysisRun 和 run.started
→ Fake Provider 生成固定计划
→ 串行执行确定性数据检查与图表步骤
→ 保存 RunStep 和 text/metric/table/chart Artifact
→ 保存最终助手消息
→ AnalysisRun completed
→ REST 查询最终状态，SSE 重放过程事件
```

`/api/v1` 与 `/api/v2` 同时注册。V1 路由、旧 SSE 和 DeepSeek 代码保持原样；V2 默认且当前只允许 `FakeAnalysisProvider`。

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

## Fake Provider

`.env` 配置：

```dotenv
V2_PROVIDER=fake
V2_FAKE_STEP_DELAY_SECONDS=0
```

当前 V2 不实现 DeepSeek Provider。把 `V2_PROVIDER` 设置为其他值会返回：

```json
{
  "error": {
    "code": "PROVIDER_NOT_AVAILABLE",
    "message": "当前 V2 Provider 不可用",
    "details": {
      "configured_provider": "deepseek"
    },
    "retryable": false,
    "request_id": "..."
  }
}
```

Fake Provider 不读取 API Key、不访问外部网络。测试通过 FastAPI 依赖覆盖注入可控的慢速或失败 Provider，用于验证取消和失败路径；Mock 逻辑不在 API 路由中。

真实 smoke test 可以临时设置 `V2_FAKE_STEP_DELAY_SECONDS=0.5`，制造可取消窗口。固定输入 `[fake:fail]` 只用于 Fake Provider 诊断，可确定地产生 failed Run；它不会进入其他 Provider。

## API

Base path：`/api/v2`。

| 方法 | 路径 | 用途 |
|---|---|---|
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

当前 V2 适配并复用了：

- V1 CSV/XLSX parser；
- pandas 数值字段与首个分类字段的确定性分组均值；
- V1 matplotlib/seaborn 柱状图引擎；
- V1 文件、Conversation 和 Message 持久化。

上述适配产生真实的 metric、table 和 chart Artifact，不把普通结果退化为单一 Markdown 字符串。

尚未迁移：

- 其余 V1 统计、过滤、排序、趋势、异常检测工具；
- 完整 AnalysisPlan revision 与 PlanValidator；
- Dataset、DatasetVersion 的正式 V2 表和上传 API；
- 结构化交互式图表 Schema；
- DeepSeek V2 Provider；
- 报告导出和完整报告管理。

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

测试全部使用临时 SQLite、匿名 CSV 和临时图表目录，不读取真实 `app.db`，不调用真实 LLM，不在仓库 storage 留下测试图片。
