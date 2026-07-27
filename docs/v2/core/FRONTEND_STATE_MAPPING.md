# V2 前端领域状态映射

> 合同状态：V2 设计合同，当前尚未实现。当前前端仍连接 `/api/v1`；本文只定义未来状态边界，不代表 V2 Store、路由或组件已经存在。运行时类型最终以 Pydantic/OpenAPI 生成合同和正式数据库迁移为事实来源。

## 1. 范围

本文是后续 Figma 信息架构和 Frontend V2 的输入，只定义状态边界和页面所需数据，不选择 React 状态库、不写组件、不继承 V1 三栏视觉。

原则：

- 服务端领域状态与本地 UI 状态分离；
- REST snapshot 是最终事实，SSE 事件增量更新 normalized store；
- Step/Artifact 按 ID upsert，避免重放导致重复；
- URL 至少编码 dataset、conversation、run 选择，使刷新可恢复；
- 不在前端推断分析完成、版本归属或 Artifact 文件路径。

## 2. 状态域

### 2.1 `datasetState`

```text
byId
allIds
selectedDatasetId
versionsByDatasetId
versionById
selectedVersionId
listCursor
listStatus
detailStatus
uploadStatus
error
```

服务端字段：

- Dataset：id、name、description、status、default_version_id、version_count、created_at、updated_at；
- DatasetVersion：id、dataset_id、version_number、parent_version_id、source_type、status、original_filename、row_count、column_count、schema、profile、error、created_at、ready_at。

本地字段：上传进度、搜索词、列表过滤、版本选择器是否展开。不能把本地 selectedVersion 写回 Dataset 默认版本，除非用户执行明确修改动作。

### 2.2 `conversationState`

```text
byId
selectedConversationId
messagesById
messageIdsByConversationId
messageCursorByConversationId
runIdsByMessageId
loadStatusByConversationId
draftByConversationId
error
```

服务端字段：Conversation 基本信息、Message id/role/content/status/reply、每条消息关联 RunSummary。

本地字段：输入草稿、引用的 message/artifact、滚动锚点。对话切换不能清除正在服务端运行的 Run，只切换当前视图。

### 2.3 `activeRunState`

```text
runById
selectedRunId
activeRunIdByConversationId
planByRunId
lastEventIdByRunId
lastSequenceByRunId
connectionStatusByRunId
reconcileStatusByRunId
errorByRunId
```

服务端字段：RunSummary/Detail、active plan 摘要、context/version 引用、progress、failure、allowed_actions、last_event_sequence。

第一阶段不维护 token delta 临时答案；收到 `answer.completed` 后按 message ID 获取 committed Message。未来增加 `answer.delta` 时再引入独立临时缓冲区，不能把缓冲区当作服务端事实。

### 2.4 `runStepState`

```text
byId
stepIdsByRunId
progressByStepId
expandedStepIds
loadStatusByRunId
cursorByRunId
```

服务端字段：step_id、plan_step_id、step_sequence、phase、operation、display_name、status、attempt、max_attempts、input_summary、output_summary、warnings、error、artifact_ids、started_at、finished_at。

`expandedStepIds` 是纯 UI 状态。步骤事实不能从工具卡片文本解析。

### 2.5 `artifactState`

```text
byId
artifactIdsByRunId
artifactIdsByStepId
previewPageByArtifactId
selectedArtifactId
loadStatusByArtifactId
downloadStatusByArtifactId
errorByArtifactId
```

服务端字段：ArtifactSummary/Detail、preview、preview_meta、config、download_available、API URLs。

前端不存 storage_key、本地路径或完整大结果。表格分页预览可独立缓存，切换 Run 时不必丢失已加载 metadata。

### 2.6 `uiState`

```text
navigation
panelVisibility
modalState
toastQueue
themePreference
layoutPreference
focusTarget
```

`uiState` 不保存 Run/Step/Artifact 业务状态。视觉重做阶段可重新定义布局，不影响领域 store。

## 3. 页面/视图所需字段

| 视图 | 最小服务端字段 | 数据来源 |
|---|---|---|
| 数据集列表 | id、name、status、default version summary、updated_at | GET datasets |
| 数据集概览 | Dataset detail、Version schema/profile | GET dataset/version |
| 对话列表/历史 | Conversation、Message page、RunSummary | GET conversation（后续可增加 list endpoint） |
| 分析输入区 | selected dataset/version、conversation、显式引用项 | normalized state + local draft |
| 运行状态区 | run status/current_phase/progress/failure | GET run + SSE |
| 计划摘要 | goal、revision、step_count、warnings、validation state | run detail + plan events |
| 步骤详情 | phase、operation、status、attempt、summary、error、artifact ids | GET steps + SSE |
| 主结果区域 | ready Artifact metadata/config/preview | GET run artifacts + GET artifact |
| 最终回答 | committed assistant Message、引用 artifacts | GET conversation/run |
| 下载/导出 | artifact id/type/title/download_available | GET artifact/download |

后续正式 UI 设计不能依赖 V1 的 `chartPaths: string[]` 或工具调用字符串；所有结果以 Artifact 和 RunStep ID 组织。

## 4. Run 状态到 UI 的映射

| Run status | 用户文案含义 | 主 UI 行为 | 可用操作 |
|---|---|---|---|
| `queued` | 请求已接收 | 显示等待，禁用重复提交同幂等请求 | cancel |
| `running` | 正在分析 | 根据 current_phase 展示计划生成、校验、执行、结果校验或回答生成；Artifact 到达即可展示 | cancel |
| `completed` | 分析完成 | 展示 committed answer 和主 Artifact | retry/new follow-up/download |
| `cancelled` | 已停止 | 保留已完成步骤和可用 Artifact，明确非完整结果 | retry |
| `failed` | 分析失败 | 展示结构化错误与已保留证据 | retry（仅 allowed）/edit question |

前端不根据“所有可见 Step 看起来完成”自行把 Run 设为 completed。

`current_phase` 仅在 running 下使用：plan_generation、plan_validation、execution、result_validation、answer_generation。取消请求已接收但服务端尚未确认停止时，Run 仍为 queued/running，前端根据 allowed_actions 或取消请求本地状态禁用重复取消。

## 5. 步骤折叠策略

默认展开：

- 当前 running/failed Step；
- 有 warning 或 error 的 Step；
- 用户主动打开的 Step。

默认折叠：

- 已成功的 plan_generation、plan_validation；
- 已成功且没有警告的中间 query/retrieve Step；
- answer_generation（最终答案已经在主区展示）。

计划整体显示为简洁摘要，不把模型原始 Prompt、内部 JSON 或 tool schema 暴露给普通用户。高级“查看分析过程”可展示：operation、字段/指标摘要、行数、耗时、警告和 Artifact，不显示 storage/worker/secret。

## 6. Artifact 展示优先级

### 主区域

- `chart`：结构化 spec 可渲染且 ready；
- `table`：核心查询/分析结果的分页预览；
- `metric`：关键指标卡或证据摘要；
- `text`：明确标记为分析结论或方法说明。

### 次级/详情区域

- `report`、`dataset_preview`、`cleaned_dataset`、`error_log` 是后续扩展类型；第一阶段不要求主工作台实现；
- 中间 table/metric：步骤详情内折叠；
- `error_log`：普通界面不展示内容，只显示脱敏错误摘要；本地诊断模式单独处理。

Artifact 排序建议：最终回答显式引用顺序 → required expected outputs → 创建时间。不能仅按 SSE 到达顺序决定主次。

## 7. SSE reducer

通用处理：

1. 校验 envelope schema major、run_id、sequence；
2. event_id/sequence 去重；
3. sequence gap 时暂停增量应用并触发 reconcile；
4. 对 normalized entity 执行 ID upsert；
5. 更新 last_event_id/sequence；
6. terminal event 后请求 canonical Run/Steps/Artifacts/Conversation。

| Event | Store action |
|---|---|
| `run.started` | upsert queued Run，设置 conversation activeRun |
| `run.status` | 更新 status/current_phase/progress |
| `step.started` | upsert Step running |
| `step.completed` | Step completed，写 summary/artifact refs |
| `artifact.created` | Artifact ready upsert，关联 run/step |
| `answer.completed` | 保存 answer message 引用并拉取 committed Message |
| `run.completed` | Run completed，触发 canonical reconcile |
| `run.failed` | Run failed，写 error，触发 allowed_actions reconcile |
| `run.cancelled` | Run cancelled，保留可用部分产物 |
| `heartbeat` | 只更新连接健康状态 |

## 8. 错误与重试

| 错误类型 | 自动重试 | UI 建议 |
|---|---:|---|
| SSE 网络断开 | 是 | 静默指数退避；超过阈值显示“重新连接” |
| sequence gap | 是 | replay；失败后 REST reconcile |
| 5xx/503 临时服务错误 | 有限 | 保留用户输入，显示重试 |
| EXECUTION_TIMEOUT 且 retryable | 不自动新建 Run | 提供“重新运行”，明确会产生新 Run |
| 字段/schema/计划无效 | 否 | 展示可理解字段问题，允许修改问题/版本 |
| EMPTY_RESULT | 否 | 展示筛选后无结果，建议调整条件 |
| Artifact preview 加载失败 | 是 | 不影响 completed Run，单独重试 Artifact |
| 资源不存在 | 否 | 清理本地失效选择，返回安全页面 |
| cancelled | 否 | 显示已完成的部分结果不是完整结论 |

“重试 Run”调用创建 Run API 并带 retry_of_run_id；前端不能把 failed Run 本地改回 running。

## 9. 刷新和恢复

推荐 URL：

```text
/datasets/{dataset_id}/conversations/{conversation_id}?run={run_id}&artifact={artifact_id}
```

恢复顺序：

1. 解析 URL，但不立即信任本地缓存；
2. GET Dataset 和 selected Version；
3. GET Conversation message page；
4. 确定 URL run 或 Conversation 最近 active Run；
5. GET Run、Steps、Artifacts 并重建 normalized state；
6. active/non-terminal Run 使用保存的 Last-Event-ID 重连 SSE；
7. terminal Run 只加载 REST canonical state；
8. URL 中 Artifact 存在且属于当前 Run 时打开详情，否则移除无效参数。

LocalStorage 可保存：主题、面板偏好、最近 ID、last event ID。不能把 LocalStorage 中的 Run status、版本归属或 Artifact 路径当成事实。

## 10. 多运行和导航

- 一个 Conversation 可以存在多个历史 Run，但同一时间默认只突出一个 activeRun。
- 如果允许同会话并发运行，store 必须按 run_id 隔离 SSE、steps 和 artifacts；是否允许属于 OPEN_QUESTIONS。
- 切换 Conversation 不取消后台 Run；全局运行指示可以提示其他会话仍在分析。
- selectedRunId 是查看对象，activeRunId 是服务端仍运行对象，二者不能混为一个字段。

## 11. Figma 与 UI 重设计输入

正式 UI 设计前需要稳定以下合同：

- Dataset/Version 选择与固定版本提示；
- Run 状态和阶段文案；
- Plan/Step 的默认折叠层级；
- Artifact 主次与支持的结构化 chart spec；
- Error.retryable/allowed_actions；
- 刷新恢复和跨 Conversation 运行提示。

视觉设计可以完全重做 V1 三栏布局，但不能删除这些信息职责：

1. 当前数据集和固定版本始终可辨识；
2. 用户问题、运行过程、证据 Artifact 和最终答案有明确层次；
3. 失败/中断/部分结果不会伪装成完整成功；
4. 每个重要结论能够打开对应 Artifact 证据；
5. 页面刷新后不丢失正在运行的事实状态。

## 12. 前端合同测试建议

- REST snapshot hydration；
- SSE 正常顺序、重复、gap、replay、terminal reconcile；
- Run/Step/Artifact normalized upsert 不重复；
- streaming_mode=none 和 delta 两种回答路径；
- 刷新 active Run 后恢复；
- failed/cancelled 以及 failure code=EXECUTION_INTERRUPTED 的按钮和文案；
- Artifact preview 分页与下载失败不污染 Run 状态；
- 切换 Conversation 不取消运行、不串流事件。
