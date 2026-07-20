# V2 重构边界

> 状态：Phase 0 完成后的设计边界
> 目的：为 V2 提供可信起点，不在本文中启动 V2 实现或网页视觉重做。

## 1. Phase 0 修改前基线

基线建立于 `master` 的 `3d44bae`，随后创建分支 `chore/v1-stabilization`。

### Git 工作区

- 已跟踪文件没有未提交修改。
- 工作区存在用户未跟踪文件，包括 `PROJECT_SUMMARY.md`、测试 CSV、简历生成脚本和简历文件；Phase 0 没有删除、移动或覆盖这些文件。
- `PROJECT_SUMMARY.md` 仅按本次任务要求修正端口、文件格式和流式能力描述。

### 可复现基线

- 后端：`python -m pytest -q`，15 passed，0 failed。
- 前端依赖：`npm install` 成功，181 packages，0 vulnerabilities。
- 前端构建：失败，共 4 个 TypeScript 错误：未使用的 `useRef`、工具状态类型不兼容、状态 setter 类型错误、函数式更新参数隐式 `any`。
- 端口：README 和 `start.bat` 使用 8000，Vite proxy 使用 8001。
- CORS：FastAPI 未配置 CORS，但项目总结声称已配置。
- SQLite：表为 `files`、`conversations`、`messages`、`charts`；连接的 `PRAGMA foreign_keys=0`。
- 旧数据库中有 30 条 `charts` 记录，审计时 30 条均没有对应的真实 `messages.id`。
- 上传接口声称支持 `.xls`，但环境没有 `xlrd`，实际不能稳定解析旧版 Excel。
- SSE 能推送 Agent/工具/图表过程事件，但最终答案不是模型 token 级逐字流式。

## 2. Phase 0 稳定化决定

- 默认后端地址统一为 `127.0.0.1:8000`；`app.run`、CORS 和 Vite proxy 读取根目录 `.env` 的同一套配置。
- SQLite 每个连接启用外键约束；测试可把共享 session factory 绑定到临时数据库。
- 助手消息和图表在一个事务中保存：先 flush 真实消息 ID，再创建图表记录，持久化完成后才发送 `done`。
- 删除文件时先删除数据库关系，再尽力清理上传文件和关联图表物理文件；物理文件清理失败时允许留下无数据库引用的文件，不能留下指向缺失文件的数据库关系。
- 不自动删除旧 `app.db` 中的 30 条孤儿图表，避免破坏用户数据。旧数据需要单独备份、审计和迁移；新代码不再制造同类孤儿。
- 报告必须传入属于当前文件的 `conversation_id`，且对话中必须已有助手分析结果。报告输入包含画像、消息、工具调用和图表，并明确禁止补造证据中不存在的结论。
- V1 正式支持 CSV 和 XLSX；`.xls` 暂停支持。
- SSE 文档使用“分析过程事件推送”，不宣称 token 级逐字流式。

## 3. V1 能力复用判断

| V1 能力 | 判断 | 边界与理由 |
|---|---|---|
| CSV/XLSX 基础解析 | 需要重构后复用 | `pandas` 解析行为和现有测试可保留；需要加入编码、分隔符、Sheet、类型识别、大小限制和数据版本边界。 |
| 数据画像 | 需要重构后复用 | 行列数、缺失、重复、描述统计可复用；V2 必须输出结构化画像，不能只依赖 Markdown 字符串。 |
| 分析工具中的纯函数 | 只保留行为和测试 | 基础统计逻辑有价值，但当前工具直接依赖全局 DataFrame 缓存，输入/输出主要是字符串，不能原样进入 V2。 |
| 图表引擎 | 需要重构后复用 | matplotlib 生成静态图的能力可作为导出/兼容路径；V2 主路径需要结构化图表规范和 Artifact 关联。 |
| FastAPI 路由 | 只保留行为和测试 | URL 和用户流程可作为兼容参考；路由当前直接操作 session、文件系统和 Agent，V2 应改为应用服务边界。 |
| 数据库模型 | 建议重写 | V1 四表不足以表达数据版本、分析运行、步骤和产物；`chart_ids` 语义也不清晰。迁移时保留已有数据读取能力。 |
| React 三栏交互思路 | 只保留行为和测试 | 文件、分析过程、结果上下文三个概念可保留；当前视觉、布局和 props 状态链不作为 V2 UI 约束。 |
| SSE | 需要重构后复用 | 传输方式可保留；事件命名、错误、顺序、run/step/artifact ID 和断线语义必须统一。 |
| 测试样例 | 可直接复用 | parser、profiler、工具单测和 Phase 0 主链路测试应成为 V2 回归基线；实现替换时保持行为或明确迁移断言。 |

“可直接复用”仅表示测试资产可以直接进入下一阶段，不表示所有测试覆盖已经充分。

## 4. V2 必须重做的核心

### 数据与会话模型

- `Dataset`：稳定的数据集身份、所有者和生命周期。
- `DatasetVersion`：原始文件、清洗版本、schema、profile、hash 和创建来源。
- `Conversation` 与 `Message`：明确归属 Dataset，消息内容和工具/运行引用使用结构化字段。
- 数据集必须由服务端会话或请求上下文绑定，模型不能自由选择或伪造 `file_id`。

### 分析运行模型

- `AnalysisRun`：一次用户问题从创建、规划、执行、验证到完成/失败的状态容器。
- `RunStep`：计划步骤、输入、确定性执行结果、状态、耗时和错误。
- `Artifact`：表格、图表、文件、统计结果等统一产物，关联 DatasetVersion、AnalysisRun 和 RunStep。
- 报告基于已完成的 AnalysisRun、RunStep 和 Artifact 生成，不再从零散聊天字符串猜测分析过程。

### Agent 与分析执行

- Agent 输出结构化分析计划，并在执行前校验指标、维度、筛选条件和步骤依赖。
- 工具 Schema 从真实类型模型自动生成，禁止维护第二份手写且不一致的 Schema。
- LLM 负责意图理解、规划和解释；聚合、筛选、指标、统计和图表数据准备由确定性分析引擎执行。
- 结果验证器检查空结果、字段、口径、数值边界、证据是否支持结论，以及是否回答原问题。
- 工具调用必须由服务端注入 DatasetVersion 上下文，不能依赖进程级全局 DataFrame 缓存。

### API、SSE 与前端状态

- 统一 SSE 事件协议，至少表达 `run_started`、`plan_created`、`step_started`、`step_completed`、`artifact_created`、`message_delta`、`run_completed`、`run_failed`。
- 每个事件包含稳定的 `run_id`、必要时包含 `step_id`/`artifact_id`、序号和可版本化 payload。
- 明确 token 流式是否支持；如果不支持，不能把完整回答事件描述成 token delta。
- 前端按文件领域、会话领域、运行领域和 Artifact 领域管理状态，避免当前根组件 props 链和隐式状态耦合。
- V2 网页需要在数据模型、API 和 SSE 协议稳定后单独设计；当前三栏深色视觉不是必须继承的设计约束。

## 5. 建议的 V2 核心链路

```text
上传 CSV
→ 创建 Dataset 和 DatasetVersion
→ 生成结构化数据画像
→ 用户提出问题
→ 创建 AnalysisRun
→ 生成结构化分析计划
→ 校验计划
→ 执行确定性分析
→ 保存 RunStep 和 Artifact
→ 校验结果
→ 生成最终回答
→ 完成 AnalysisRun
```

第一条 V2 纵向切片应只覆盖一份 CSV、一个问题、一组确定性结果和一个可追溯 Artifact。CSV/XLSX 扩展、交互图表和更复杂分析应在该链路稳定后逐步加入。

## 6. 暂时不做

- 多 Agent 或 Agent 互相讨论。
- 大规模模型 Provider 切换。
- 微服务拆分。
- Kubernetes。
- 高级权限系统。
- 大量新增分析工具。
- 完整 Artifact 平台在 Phase 0 的提前实现。
- 真正 token 流式作为 Phase 0 强制项。
- V2 网页正式重做或当前页面的大规模视觉调整。

## 7. Phase 0 后仍存在的 V1 限制

- Agent 的流式入口仍未读取历史消息，多轮历史目前主要用于展示和报告；应由 V2 的 Conversation/AnalysisRun 模型解决。
- Agent 工具 Schema 仍是手工生成，存在参数类型和 required 信息失真；V2 必须改为自动生成。
- 分析工具仍依赖进程内全局 DataFrame 缓存，不适合并发、多实例和数据版本。
- 上传仍一次性读入内存，缺少文件大小、CSV 编码/分隔符和复杂 XLSX 处理。
- 当前 `messages.chart_ids` 保存的是路径，命名和语义不准确；Phase 0 保持兼容，V2 由 Artifact 替代。
- SQLite 使用 `create_all`，没有正式迁移机制。Phase 0 未改变现有四表结构。
- 旧数据库的 30 条孤儿图表记录没有自动删除或猜测性重绑。
- 最终回答仍非 token 级流式。
- LLM 分析正确性尚无固定问题集和期望答案评测；Phase 0 测试验证的是主链路和关系，不验证模型聪明程度。
- 现有 UI 只修复构建和阻断问题，视觉与信息架构留待 V2 协议稳定后单独设计。

## 8. 下一阶段建议（不在 Phase 0 执行）

下一阶段应先完成 V2 的领域模型与协议设计稿：定义 Dataset/DatasetVersion、AnalysisRun/RunStep/Artifact、结构化分析计划、统一 SSE 事件和迁移策略，并用 Phase 0 集成测试抽取第一组 V2 验收场景。设计确认后，再实现最小纵向切片。
