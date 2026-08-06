# 部署与数据库迁移

## 发布原则

1. FastAPI 启动生命周期不执行 Alembic。
2. 数据库迁移是启动前的显式发布步骤。
3. 迁移失败必须阻止后端启动。
4. 真实 `app.db` 不用于试验 downgrade。
5. 发布验证默认使用 `V2_PROVIDER=fake`。

## 配置

从示例创建本地配置：

```powershell
Copy-Item .env.example .env
```

最低配置：

```dotenv
V2_PROVIDER=fake
DATABASE_URL=sqlite:///./app.db
UPLOAD_DIR=./storage/uploads
CHART_DIR=./storage/charts
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_ORIGIN=http://localhost:5174
```

`.env`、数据库、上传文件和生成图表不得提交到 Git。

## Windows 启动

完整演示环境推荐使用：

```powershell
.\start-demo.ps1
```

它检查 Python、npm 和前端依赖，默认强制使用 Fake Provider，显式执行
数据库迁移，然后启动 8000 后端和 5174 正式前端。运行数据库、上传文件、
图表、日志和进程状态均位于 `$env:TEMP\xishu-demo-runtime`，不会写入 Git。

停止脚本只处理由当前项目状态文件记录的进程树：

```powershell
.\stop-demo.ps1
```

检查环境但不迁移、不启动服务：

```powershell
.\start-demo.ps1 -CheckOnly
```

未来受控真实模型验收必须显式选择 Provider，并预先设置本地环境变量：

```powershell
$env:DEEPSEEK_API_KEY = "<local-secret>"
.\start-demo.ps1 -Provider DeepSeek
```

脚本不会写入或输出 API Key。缺失 Key 时会在迁移和启动前停止。

现有后端单独启动脚本仍可使用：

```powershell
.\start.bat
```

执行顺序：

```text
python -m app.migrate
→ 检查退出码
→ 成功后 python -m app.run
→ 失败则停止
```

`app.migrate` 使用与应用相同的 `DATABASE_URL`，并显式执行 Alembic
`upgrade head`。它不会执行 downgrade。

仅验证迁移、不启动后端：

```powershell
$env:AI_DATA_ANALYST_MIGRATE_ONLY = "1"
.\start.bat
Remove-Item Env:AI_DATA_ANALYST_MIGRATE_ONLY
```

## Revision 就绪检查

FastAPI 启动时读取数据库当前 revision 和仓库 Alembic head，但不修改
数据库。未迁移时：

- `GET /health` 返回 HTTP 503；
- `/api/v2/*` 返回 HTTP 503；
- 错误码为 `DATABASE_MIGRATION_REQUIRED`；
- V1 表不会被删除；
- 完成迁移后需要重启后端重新检查 revision。

## 新建临时数据库

以下数据库必须是新建、可丢弃的：

```powershell
$tempRoot = Join-Path $env:TEMP "ai-data-analyst-migration-check"
New-Item -ItemType Directory -Force $tempRoot
$freshDatabase = (Join-Path $tempRoot "fresh.db").Replace("\", "/")
$env:ALEMBIC_DATABASE_URL = "sqlite:///$freshDatabase"

python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

只有这种新建临时库可以执行 `downgrade base`。

## 真实数据库副本验证

对真实 `app.db` 只读取时间戳、大小和 SHA-256：

```powershell
Get-Item .\app.db | Select-Object Length, LastWriteTimeUtc
Get-FileHash .\app.db -Algorithm SHA256
```

随后复制到仓库外目录：

```powershell
$copyRoot = Join-Path $env:TEMP "ai-data-analyst-db-copy"
New-Item -ItemType Directory -Force $copyRoot
Copy-Item .\app.db "$copyRoot\app-copy.db"
$copyDatabase = (Join-Path $copyRoot "app-copy.db").Replace("\", "/")
$env:ALEMBIC_DATABASE_URL = "sqlite:///$copyDatabase"
```

只对副本执行：

```powershell
python -m alembic upgrade head
python -m alembic upgrade head
```

必须核对：

- V1 `files`、`conversations`、`messages`、`charts` 行数不变；
- V2 四表存在；
- `alembic_version` 为当前 head；
- `PRAGMA foreign_key_check` 返回空结果；
- 原始 `app.db` 的时间戳和 SHA-256 未改变。

不得对真实库或真实库副本执行 `downgrade base`。

## 前端构建

```powershell
Set-Location frontend-v2
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

开发模式由 Vite 将 `/api` 和 `/health` 代理到后端。前后端分开部署时，
通过 `VITE_API_BASE_URL` 指向公开后端地址，并相应设置
`FRONTEND_ORIGIN`。

## 发布验证

```powershell
$env:V2_PROVIDER = "fake"
python -m pytest -q
python -m compileall -q app tests alembic
```

验证期间不设置真实 DeepSeek Key，不调用收费模型。发布完成前还应检查：

```powershell
git diff --check
git status --short --branch
```

### 前端依赖审计说明

当前 `npm audit --omit=dev` 会报告 React Router
`GHSA-qwww-vcr4-c8h2`。官方说明该问题只影响使用不稳定 RSC API 的应用；
本项目前端是 `BrowserRouter` SPA，源码没有 RSC 或 Server Action 路径，
因此当前部署方式不进入该漏洞路径。正式升级 React Router 主版本前仍应
重新运行完整前端测试，不使用 `npm audit fix --force` 自动进行破坏性升级。

参考：
[GitHub Advisory GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2)。

## 故障处理

| 现象 | 检查 |
|---|---|
| `DATABASE_MIGRATION_REQUIRED` | 运行 `python -m app.migrate`，成功后重启后端 |
| 迁移脚本退出非零 | 不启动后端；检查 `DATABASE_URL`、目录权限和磁盘空间 |
| 前端显示后端离线 | 检查 `/health` 状态码、8000 端口和 `FRONTEND_ORIGIN` |
| V2 分析失败 | 查询 Run、Steps、Artifacts；不要只依赖 SSE |
| 图表无法加载 | 检查 Artifact 下载接口，不使用本地物理路径访问 |
