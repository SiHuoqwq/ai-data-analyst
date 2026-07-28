# 析数 Frontend V2

面向数据集理解与分析结果展示的 AI 数据分析工作区。当前版本已接入 V1 数据集能力和最小 V2 分析闭环，默认使用后端的确定性测试分析模式，不需要模型密钥，也不会调用真实 LLM。

## 环境要求

- Node.js 20 或更高版本
- npm 10 或更高版本
- Python 后端默认运行在 `http://127.0.0.1:8000`
- 后端必须设置 `V2_PROVIDER=fake`

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
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再启动前端：

```bash
cd frontend-v2
npm run dev
```

前端默认地址为 `http://localhost:5174`。Vite 会将 `/api` 和 `/health` 代理到后端。

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

- 当前分析结果由确定性测试流程生成，不读取历史消息进行上下文推理。
- 同一 Conversation 支持多轮记录和继续提问，但界面不会暗示模型理解了历史上下文。
- 图表使用服务端生成的静态图片，不提供交互编辑。
- 只展示服务端实际返回的表格行，不在前端模拟分页。
- 取消为合作式取消；同步分析步骤可能要到下一个取消检查点才会停止。
- 尚未接入真实 DeepSeek，也未迁移更多旧版分析工具。
