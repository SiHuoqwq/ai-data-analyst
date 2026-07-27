# 析数 Frontend V2

AI 数据分析助手的新前端第一阶段。该工程与旧 `frontend/` 完全隔离，只连接当前真实 `/api/v1` 数据集接口和 `/health`。

## 环境

- Node.js 20 或更高版本（本轮使用 Node.js 22）
- npm 10 或更高版本
- 后端默认运行在 `http://127.0.0.1:8000`

## 安装

```bash
cd frontend-v2
npm install
```

## 开发启动

先在仓库根目录启动后端：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再启动新前端：

```bash
cd frontend-v2
npm run dev
```

新前端默认使用 `http://localhost:5174`，Vite 将 `/api` 和 `/health` 代理到后端。

如后端地址不同，在仓库根目录 `.env` 中设置 `BACKEND_HOST` 和 `BACKEND_PORT`。生产部署可为前端设置 `VITE_API_BASE_URL`；不设置时使用同源请求。

## 验证命令

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

## 已连接接口

- `GET /health`
- `GET /api/v1/files`
- `POST /api/v1/files/upload`
- `GET /api/v1/files/:fileId`
- `GET /api/v1/files/:fileId/preview?rows=20`
- `DELETE /api/v1/files/:fileId`
- `GET /api/v1/files/:fileId/conversations`

分析工作台页面目前只是明确的结构占位，不调用 `/api/v2`、LLM、AnalysisRun、Artifact 或 SSE。
