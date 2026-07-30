# 析数 Frontend V2

面向数据集理解与分析结果展示的 AI 数据分析工作区。当前版本已接入 V1 数据集能力和 V2 分析闭环。后端默认使用无需密钥的确定性测试模式，也可以由开发者显式启用 DeepSeek 真实分析模式；前端复用同一套 Run、SSE 和 Artifact 协议。

## 环境要求

- Node.js 20 或更高版本
- npm 10 或更高版本
- Python 后端默认运行在 `http://127.0.0.1:8000`
- 后端默认设置 `V2_PROVIDER=fake`；真实模型验收时可设为 `deepseek`

## 安装

```bash
cd frontend-v2
npm ci
```

如需主动更新依赖锁文件，可改用 `npm install`。日常复现和 CI 建议使用 `npm ci`。

## 启动

先在仓库根目录启动后端：

```powershell
$env:V2_PROVIDER = "fake"
python -m app.migrate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

也可以直接运行仓库根目录的 `start.bat`。FastAPI 启动只检查数据库
revision，不会自动执行迁移；缺少迁移时 `/health` 和 `/api/v2` 返回
`503 DATABASE_MIGRATION_REQUIRED`。

再启动前端：

```bash
cd frontend-v2
npm run dev
```

前端默认地址为 `http://localhost:5174`。Vite 会将 `/api` 和 `/health` 代理到后端。

真实分析模式由后端配置，前端不接收或保存模型密钥：

```powershell
$env:V2_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "replace-with-local-secret"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

超时、有限重试、工具轮次和数据最小化规则见 `docs/v2/MINIMAL_V2_BACKEND.md`。自动测试不会调用真实 DeepSeek。

后端地址不同时，可在仓库根目录 `.env` 中设置：

```dotenv
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
```

前后端分开部署时，可在前端构建环境设置：

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

## 构建与测试

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

预览生产构建：

```bash
npm run preview
```

## 已接入的用户流程

```text
选择数据集
→ 首次提问时创建 Conversation
→ 创建分析任务
→ 订阅 SSE 实时事件
→ 展示运行状态和真实执行步骤
→ 渲染 text / metric / table / chart 结果
→ 通过 REST 恢复刷新或断线后的状态
→ 在同一 Conversation 中继续提问
```

页面 URL 使用服务器返回的真实 ID：

```text
/datasets/{fileId}/analysis?conversationId={conversationId}&runId={runId}
```

没有 `conversationId` 时不会自动创建空会话；只有用户首次提交有效问题时才创建。

## 已连接接口

数据集与历史：

- `GET /health`
- `GET /api/v1/files`
- `POST /api/v1/files/upload`
- `GET /api/v1/files/:fileId`
- `GET /api/v1/files/:fileId/preview?rows=20`
- `DELETE /api/v1/files/:fileId`
- `GET /api/v1/files/:fileId/conversations`
- `GET /api/v1/conversations/:conversationId`

分析闭环：

- `POST /api/v2/conversations`
- `POST /api/v2/conversations/:conversationId/runs`
- `GET /api/v2/runs/:runId`
- `GET /api/v2/runs/:runId/steps`
- `GET /api/v2/runs/:runId/artifacts`
- `GET /api/v2/artifacts/:artifactId`
- `GET /api/v2/runs/:runId/events`
- `POST /api/v2/runs/:runId/cancel`

创建分析任务时，前端会为一次用户提交生成 `Idempotency-Key`。网络失败后重试同一次提交会复用原键；新问题使用新键。创建任务和取消操作不会自动重试。

## 实时更新与恢复

SSE 用于实时展示运行状态、步骤和新增结果。客户端会校验 `run_id`，按 `sequence` 严格递增合并事件，并使用 `event_id` 去重；旧任务、重复事件和心跳不会污染当前执行详情。

REST 持久化状态是最终事实来源。页面刷新、SSE 中断或遗漏终止事件时，前端会查询 Run、Steps、Artifacts 和 Conversation 恢复页面。当前只进行有限恢复尝试，失败后由用户手动重试。

## 当前限制

- Fake 模式返回确定性结果；DeepSeek 模式读取有限历史理解追问，但所有数字仍由本次工具重新计算。
- 图表使用服务端生成的静态图片，不提供交互编辑。
- 只展示服务端实际返回的表格行，不在前端模拟分页。
- 取消为合作式取消；同步分析步骤可能要到下一个取消检查点才会停止。
- 当前只迁移多维分组、月度趋势、高报名低完成组合、柱状图和折线图，不支持任意开放式工具调用。
