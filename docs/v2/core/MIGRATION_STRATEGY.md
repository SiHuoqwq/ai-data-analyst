# V1 到 V2 迁移策略

> 合同状态：V2 设计合同，当前尚未执行迁移。当前可运行系统仍使用 `/api/v1`、V1 `app.db` 和现有 storage；实现阶段以迁移工具、正式数据库迁移及验证报告为最终事实来源。

## 1. 推荐结论

采用并行新库迁移，不原地修改 V1：

```text
V1 app.db + V1 storage（只读）
→ 可重复 migration tool（dry-run 优先）
→ V2 app_v2.db + V2 managed storage
→ 校验报告
→ 人工确认切换
```

理由：

- V1 四表不能表达 DatasetVersion、AnalysisRun、RunStep 和 Artifact；原地 ALTER 容易形成半迁移状态。
- V1 存在历史孤儿图表，不能在强制外键的新 schema 中直接复制。
- 新库允许随时回退到 `v1-stable-baseline` 和原始 app.db。
- V2 从第一天使用 Alembic，避免继续依赖 `create_all`。
- V1 `/api/v1` 与未来 V2 `/api/v2` 在迁移期并存；V2 未通过验证前，V1 始终保持可启动和可回滚。
- 本合同整理阶段不清理 30 条历史孤儿图表，也不修改 `app.db` 或 storage。

## 2. 基线事实

Phase 0 审计时 V1 数据库：

- `files`: 8；
- `conversations`: 6；
- `messages`: 14；
- `charts`: 30；
- SQLite 旧连接外键未启用；
- 30 条 ChartModel.message_id 均未匹配真实 Message；
- 通过 `charts.filepath == messages.chart_ids[]` 可唯一匹配 10 条；
- 20 条没有可靠消息归属；无歧义多匹配。

这些数字是 Phase 0 快照，正式迁移前必须重新执行只读审计并把新计数写入 migration manifest，不能假设仍然相同。

## 3. 安全边界

### 3.1 禁止

- 不对用户当前 `app.db` 执行 ALTER、UPDATE、DELETE 或 VACUUM。
- 不移动/重命名 V1 uploads/charts；迁移使用 copy 或受控引用。
- 不把无法确定归属的 chart 猜测性绑定到最近消息。
- 不把 V1 对话内容伪造为已验证 AnalysisRun 证据。
- 不在未生成 backup/hash/manifest 前切换应用配置。

### 3.2 迁移前快照

创建新的迁移工作目录，建议位于 `<backup-directory>` 或项目外的受控目录：

```text
migration/{timestamp}/
├── source_app.db.copy
├── source_manifest.json
├── dry_run_report.json
├── id_map.csv
├── quarantine.jsonl
└── verification_report.json
```

Manifest 至少包含：

- 源 DB 绝对路径（仅本地报告，不提交 Git）；
- DB sha256、大小、mtime；
- 四表 row count；
- 每个 storage 文件的相对路径、sha256、大小；
- orphan/missing file/重复 path 数量；
- V1 commit/tag `v1-stable-baseline`；
- migration tool 版本和 V2 Alembic revision。

## 4. V2 数据库与 Alembic

- 新建 `app_v2.db`，不复用 `app.db` 文件。
- V2 schema 的初始 revision 由 Alembic 创建；所有后续 schema 修改都经 Alembic。
- migration tool 首先把空库升级到目标 Alembic revision，再写数据。
- 每批写入后运行 foreign key check、unique check 和业务不变量校验。
- V1 应用继续指向 app.db；只有验证和人工确认后才切换 V2 配置。

## 5. 表映射

### 5.1 files → Dataset + DatasetVersion

每条 V1 files：

1. 创建 Dataset：
   - name = filename；
   - description = “从 V1 迁移”；
   - status = active；
   - metadata_json 保存 `legacy_file_id`、迁移时间和 V1 row/col count。
2. 创建 DatasetVersion：
   - version_number = 1；
   - source_type = migrated；
   - original_filename/file_type 从 V1 读取；
   - storage object 从 V1 filepath 复制到 V2 managed storage；
   - 重新计算 sha256/size；
   - V1 columns_info 转换为 schema_json v1；
   - V1 Markdown profile_report 不能直接冒充结构化画像：保存为 legacy markdown metadata，并用 V2 profiler 重新生成 profile_json；
   - 重新解析成功后 status=ready，失败则 status=failed 并隔离。
3. 设置 Dataset.default_version_id。
4. 写 legacy_id_map：`files/{id} → Dataset` 和 `files/{id} → DatasetVersion`。

如果 V1 filepath 缺失：仍可创建 archived/failed DatasetVersion 记录，但不能标 ready；写 quarantine reason `SOURCE_FILE_MISSING`。

### 5.2 conversations → Conversation

- 只有 file_id 能映射到 Dataset 的 Conversation 才进入正常表。
- dataset_id 使用 legacy file 映射；default_version_id 使用 v1 版本 1。
- title、mode、created_at 保留；mode 写 metadata，不直接变成 V2 执行策略。
- created_at 保留原时间并标记 legacy timezone assumption；updated_at 可取最后消息时间。
- 无效 file_id 的 Conversation 进入 quarantine，不猜测数据集。

### 5.3 messages → Message

- 保留 conversation、role、content、created_at 和原 ID 映射。
- V1 tool_calls/chart_ids 原样保存到 `metadata_json.legacy`，不放入 V2 正式工具执行字段。
- role 只接受 user/assistant；未知 role 进入 quarantine 或映射为 system 前必须人工规则确认。
- Message status=committed，content_format 根据 role/content 检测为 plain_text/markdown。
- 历史消息不自动创建 AnalysisRun、RunStep 或“已验证” Artifact 证据，因为 V1 没有足够执行事实。

为什么不合成 AnalysisRun：

- 无法可靠重建计划、工具结果、步骤顺序和结果校验；
- 把助手文本包装成 completed Run 会错误暗示它已通过 V2 证据验证；
- V2 Conversation 允许 Message 不关联 Run，因此可安全保留历史展示。

前端对这些消息显示“V1 历史记录，未经 V2 证据链验证”。

## 6. 旧图表迁移

### 6.1 分类规则

按以下顺序进行只读分类：

1. `charts.message_id` 是否真实匹配 V1 Message；
2. 否则用规范化 `charts.filepath` 与每个 Message.chart_ids[] 精确匹配；
3. 关联 Message 的 Conversation.file_id 是否有效；
4. 物理文件是否存在、是否可读取、hash 是否唯一；
5. 匹配是否唯一。

### 6.2 可唯一匹配的图表

Phase 0 快照中有 10 条路径唯一匹配，正式迁移重新计算。

处理方式：

- 复制物理图片到 V2 managed storage；
- 创建 `artifact_type=chart`、`status=ready` 的 legacy Artifact；
- dataset_version_id 来自匹配 Message 的 Conversation → Dataset Version；
- `run_id`、`run_step_id` 为空，因为无法证明属于某个 V2 Run；
- config_json 标记 `spec_available=false`，不能假装有结构化图表规范；
- metadata 记录 legacy chart id、legacy message id、匹配方法、source hash；
- Message.metadata 可引用 legacy artifact_id，前端标记“V1 静态图表”。

### 6.3 20 条无法匹配的孤儿图表

不得进入正常 Artifact 表。写入 `migration_quarantine_records`：

- source_table=charts；
- source_id；
- reason_code=`ORPHAN_CHART_UNRESOLVED`；
- source payload（脱敏）；
- 原 storage path、存在性、sha256；
- review_status=pending。

物理文件：

- 默认不移动、不删除；manifest 保存只读引用；
- 若需要长期封存，可复制到 V2 quarantine storage，但不能出现在正常产品结果列表；
- 后续只有人工提供可靠归属证据后，运行单独的 reviewed migration，不在主迁移中自动处理。

### 6.4 文件存在性分支

| DB 行 | 文件 | 处理 |
|---|---|---|
| 可匹配 | 存在 | 复制并创建 legacy Artifact |
| 可匹配 | 缺失 | quarantine `ARTIFACT_FILE_MISSING`，Message 保留 metadata |
| 不可匹配 | 存在 | quarantine，保留 hash/路径，不正常展示 |
| 不可匹配 | 缺失 | quarantine，仅保留 DB payload 和原因 |

## 7. 迁移阶段

### Phase A：只读审计

- 打开 V1 DB 为只读 URI；
- 计算表计数、foreign_key_check、路径匹配、物理文件清单；
- 输出 dry_run_report；
- 不创建 V2 正常数据。

验收：报告可重复，两次对同一 source hash 结果一致。

### Phase B：建立空 V2

- 创建新 app_v2.db；
- `alembic upgrade head`；
- 验证空库 FK 与 schema revision；
- 写 migration run metadata。

### Phase C：迁移 Dataset/Version

- 按 V1 file id 稳定顺序；
- copy 文件、hash、重新解析/profile；
- 每个 Dataset 独立事务；
- 写 legacy_id_map 和失败 quarantine。

### Phase D：迁移 Conversation/Message

- 只迁移存在有效 Dataset 映射的数据；
- 保持 Conversation 内时间顺序，时间相同用 legacy id 稳定排序；
- 不生成 AnalysisRun。

### Phase E：迁移可验证 Artifact

- 按唯一匹配规则导入；
- 其他全部 quarantine；
- 对复制文件二次 hash 验证。

### Phase F：校验

- V1 与 V2 映射计数；
- 所有 V2 FK、unique、领域不变量；
- storage hash/size；
- 随机抽查 Dataset profile、Conversation 消息顺序和可匹配图表；
- 生成 verification_report，列出所有丢弃为 0、隔离数量和原因。

### Phase G：人工切换

- 保留 V1 tag、应用和 app.db；
- 在副本环境启动 V2，执行 smoke/integration 测试；
- 人工签署迁移报告后修改配置指向 app_v2.db；
- V1 app.db 设置操作系统只读并归档，不删除。

## 8. 幂等和可重跑

- 每次 migration 有 `migration_run_id`、source DB hash 和 tool version。
- legacy_id_map 唯一约束防止重复创建。
- 目标对象 ID 可以由 `(source_hash, source_table, source_id, target_type)` 确定性生成，或使用映射表保存首次 ID。
- 如果 source DB hash 变化，必须创建新的 migration run；不能继续复用旧报告。
- 文件 copy 使用内容寻址的临时路径，完成 hash 校验后原子落位。
- dry-run 永远不写正常 V2 表。

## 9. 回退策略

切换前：删除失败的 app_v2.db/managed storage 副本即可，V1 不受影响。

切换后回退：

1. 停止 V2 写入；
2. 保存 V2 DB/storage 供诊断；
3. 恢复配置到 V1 app.db 和 `v1-stable-baseline`；
4. 明确 V2 切换后新创建的数据不会自动回写 V1；如果已开放真实使用，需要单独导出或限定试运行窗口。

因此建议首次切换为只读/试用窗口，确认后再让 V2 接收不可替代的新数据。

## 10. 保留策略

- V1 app.db 和 storage 至少保留到 V2 迁移验收后一个明确保留期；建议 90 天，最终由产品/运维决定。
- source backup、manifest、verification report 保留更久并限制访问。
- quarantine 不进入正常 UI，不自动删除；人工复核或保留期结束后单独审批。
- migration 报告不能记录 API key、原始敏感字段样例或完整用户数据。

## 11. 迁移验收标准

- V1 原 DB hash 在迁移前后不变；
- V2 Alembic revision 正确，foreign key check 无错误；
- 每条已迁移 V1 file 有 Dataset 和 v1 DatasetVersion 映射，或明确 quarantine 原因；
- 有效 Conversation/Message 计数与映射报告一致，顺序稳定；
- 没有凭猜测生成 AnalysisRun；
- 正常 Artifact 全部有 DatasetVersion、hash、存在的物理对象；
- 所有无法归属 chart 只在 quarantine；
- migration 可对同一 source 重跑而不重复；
- V1 应用仍能从原 app.db 启动；
- 回退演练成功。

## 12. 实现前仍需确认

- V1 历史消息是否全部迁移，还是只迁移有价值的 Conversation；
- quarantine/backup 的保留期；
- V2 managed storage 使用本地目录还是对象存储；
- 用户是否接受 V1 历史图表标记为“静态、无结构化 spec”；
- V2 试运行期间是否禁止新 V1/V2 双写（推荐禁止双写，使用明确切换窗口）。
