# 2026-08-06 dataset-aware recommendation validation addendum (Fake only)

This addendum records a new Fake-only validation. It does not change or
reinterpret the paid DeepSeek acceptance evidence below.

- Explicit Alembic migration reached `0002_dataset_recommendations`; an
  unmigrated disposable database remained unmigrated at FastAPI startup.
- `/health` reported `provider.mode=fake`. Repeated recommendation GET requests
  for two uploaded compatible datasets returned stable cached template data, and
  a selected card question completed a Fake Run with REST artifact recovery and
  a chart download returning `200 image/png`.
- The HTTP check also found that CSV date columns are currently profiled as
  `object`, so the demo upload produces only the group-comparison card. Default
  Fake runs use the generic workflow, so controlled group/monthly chart behavior
  was verified by automated tests rather than this Fake HTTP flow.
- No new paid DeepSeek recommendation acceptance was performed. Any such
  acceptance requires separate, explicit authorization.

# DeepSeek 受控演示验收报告

验收日期：2026-08-06
结论：**有条件通过**

## 1. 验收环境

- 基线 Commit：`f21c8656ed6191d1d4c5d96e3b607b0075a72f9d`
- Provider：`deepseek`
- 页面显示名：`DeepSeek`
- 页面说明：`真实模型模式`
- 模型：`deepseek-chat`
- 最大 Prompt 字符数：`24000`
- 完整产品 Run 预算：最多 6 次；实际 6 次
- 数据库、上传、图表和运行日志均位于仓库外临时运行目录，未提交。
- API Key 只通过进程环境传入；本报告不记录 Key、请求头、Base URL 或环境变量值。

启动后 `/health` 返回 `status=ok`、`database.ready=true`，Provider 三个公开字段与上述配置一致。

## 2. 数据版本

- 文件：`demo/learning_operations_demo.csv`
- 数据性质：完全合成，不对应任何真实个人、机构或业务
- 规模：360 行、9 列
- 日期范围：2025-01 至 2026-06，共 18 个月
- SHA-256：`DBC6235CEA5638348C9CC74D7D7A5A9C4669EFEFE4B499DE654A3EDF7C606DCF`
- 重生成前后哈希一致；数据契约测试 3 项通过。

## 3. 固定问题

### 课程组合比较

> 请分析不同课程类别、课程难度、购买渠道和主要学习设备对课程完成率、退款率及课程评分的影响。找出报名人数较多但完成率偏低的组合，并用表格和图表展示关键结论，再给出运营建议。

### 月度趋势分析

> 请按月份统计各课程类别的报名人数、实付金额和平均完成率趋势，识别增长最快、下滑最明显或波动异常的课程类别，并生成趋势图。

## 4. 调用与失败记录

时间均为 UTC。完整 Run 数为 6；应用层可确认的逻辑模型请求为 15 次：6 次意图识别、5 次初始结论生成、4 次结论修复。没有观察到 429 或 Provider 超时；底层 HTTP 传输重试次数没有作为公共 Run 字段暴露，因此不作猜测。

| # | 问题 | Run ID | 开始 | 完成 | 状态 | 重试 | 结果或原始失败 |
|---|---|---|---|---|---|---|---|
| 1 | 组合比较 | `ea8a3609-5434-46d8-adea-b2ebb87959db` | 09:02:30 | 09:03:55 | failed | 否 | `INVALID_FIELD_TYPE`，退款率分类字段在 PlanCompiler 被错误拒绝 |
| 2 | 组合比较 | `9d2278df-df5d-49d2-aaab-30736c952316` | 09:06:34 | 09:06:44 | failed | 第一次 | `PROMPT_LIMIT_EXCEEDED`，结论修复 Prompt 未重新裁剪 Evidence alias |
| 3 | 组合比较 | `20016f2a-b7d8-4a0d-94d6-705ba9ddfe43` | 09:15:03 | 09:15:22 | completed | 第二次 | 模型意图；确定性结论降级 |
| 4 | 月度趋势 | `147b03fc-0f42-4c0b-965a-43e0f90f00c9` | 09:15:57 | 09:16:14 | completed | 否 | 审计发现缺失月份组合和图表截断，不接受为最终结果 |
| 5 | 月度趋势 | `e67fde62-235e-4f5c-880a-b15b0359d359` | 09:20:16 | 09:20:32 | completed | 第一次 | 审计发现人数波动值与百分比单位不一致，不接受为最终结果 |
| 6 | 月度趋势 | `15953acc-e9b6-423c-b24c-ed43a5548566` | 09:22:29 | 09:22:45 | completed | 第二次 | 模型意图；确定性结论降级 |

没有超过每个问题两次修复性重试或总计六次完整 Run 的预算。

## 5. 课程组合比较验收

最终 Run：`20016f2a-b7d8-4a0d-94d6-705ba9ddfe43`
结论：**有条件通过**

### 意图与计划

- `intent_mode=model`，实际编译为 `group_comparison`。
- 固定步骤顺序：`inspect_dataset` → `group_aggregate` → `identify_underperforming` → `chart_planning` → `validate_results` → `generate_answer`。
- 六个 Step 均为 `completed`，每个执行尝试次数为 1。
- PlanCompiler 只产生上述受控工具，没有任意 Python、SQL、文件路径或未注册工具。

### Artifact 与图表

- 共 10 个 Artifact：text 2、metric 1、table 2、chart 5。
- 分组表完整结果为 192 个组合，页面按既定预览上限展示 100 行。
- 低表现表完整展示 1 个组合。
- 五张柱状图按 count、percentage、score 拆分；完成率与退款率共用百分比量纲，人数和评分分别绘制。
- 五个图表接口均返回 HTTP 200、`image/png`。

### 独立 pandas 对账

页面公开的 100 行分组表包含 400 个数值单元格：

- 完全一致：322
- 仅十位小数序列化舍入：78
- 不一致：0

低表现规则独立结果：

- 最小样本量：5
- 高报名分位阈值：8
- 低完成率分位阈值：0.666501875
- 唯一匹配组合：前端开发 / 进阶 / 官网 / Windows
- 报名人数：8
- 平均完成率：0.6519875（页面结论显示 65.20%）
- 退款率：0.125（页面结论显示 12.50%）
- 平均评分：独立值与页面 4.33 的展示舍入一致

### Evidence 与结论

- 全部 Artifact 的 `run_id` 均等于最终 Run ID。
- Evidence alias 由当前 Run 的完整工具结果建立；跨 Run alias 校验未被放宽。
- 页面结论中的 65.20%、12.50% 和 4.33 均能由独立结果复核。
- 运营建议引用了当前低表现组合，并明确写出“当前结果反映数据关联，不代表因果关系”。
- 模型初始结论和一次修复均违反“叙述字段不得直接包含数字”约束，诊断类型为 `NUMBER_IN_NARRATIVE`；系统未接受模型文本，最终使用 `deterministic_fallback`。

## 6. 月度趋势验收

最终 Run：`15953acc-e9b6-423c-b24c-ed43a5548566`
结论：**有条件通过**

### 意图与计划

- `intent_mode=model`，实际编译为 `monthly_trend`。
- 固定步骤顺序：`inspect_dataset` → `monthly_trend` → `calculate_trend_signals` → `chart_planning` → `validate_results` → `generate_answer`。
- 六个 Step 均为 `completed`，每个执行尝试次数为 1。
- 月份使用内部稳定字段 `period`，系列维度使用 `series`。

### Artifact 与图表

- 共 7 个 Artifact：text 2、metric 1、table 1、chart 3。
- 月度表为完整的 18 个月 × 5 类课程，共 90 行。
- 缺少报名记录的月份/类别组合中：人数与金额为 0，平均完成率保持缺失，不伪造均值。
- 三张折线图分别为报名人数、实付金额、平均完成率，没有混用量纲。
- 横轴均为 `period`，系列均为课程类别，表格时间范围为 2025-01 至 2026-06。
- 图表没有“展示前 50 项”截断标识；三个接口均返回 HTTP 200、`image/png`。

### 独立 pandas 对账

页面完整月度表包含 270 个数值单元格：

- 完全一致：225
- 仅浮点或十位小数序列化舍入：45
- 不一致：0

独立趋势信号与当前 Run Evidence 完全一致：

| 指标 | 增长最快 | 变化 | 下滑最大 | 变化 | 波动最大 | 相对波动 |
|---|---|---:|---|---:|---|---:|
| 报名人数 | 数据分析 | 166.6667% | 前端开发 | -62.5% | 商业分析 | 100% |
| 实付金额 | 数据分析 | 153.7193% | 前端开发 | -63.3124% | 数据分析 | 11.3506% |
| 平均完成率 | 商业分析 | 12.4525% | 数据分析 | -2.8050% | AI 应用 | 12.1694% |

其中商业分析月度人数按 0 和 6 交替，独立绝对标准差为 3；页面趋势合同使用相对标准差，值为 100%，类别判断一致。

### Evidence 与结论

- 全部 Artifact 的 `run_id` 均等于最终 Run ID。
- 页面结论中的 166.67%、-62.50% 和 100.00% 与独立结果一致。
- 结论明确写出相关性不代表因果关系。
- 模型初始结论和一次修复仍未通过无数字叙述 Schema，系统拒绝模型结论并使用 `deterministic_fallback`。

## 7. 恢复、页面与敏感信息检查

两个最终 Run 均满足：

- 最终状态为 `completed`。
- REST 重读可恢复 Run、6 个 Step 和全部 Artifact。
- 从 `after_sequence=0` 重连 SSE 时，事件 sequence 严格递增并到达 `run.completed`。
- Provider 运行时状态由 `/health` 提供，值为 DeepSeek 真实模型模式。
- 所有表格 Artifact 均可通过公开 API 重新获取。
- 图表只暴露 `/api/v2/artifacts/{id}/download`，不暴露物理文件路径。
- 对公开 Run、Step、Artifact 和 SSE 验收记录扫描，未发现 `API Key`、认证头、Bearer、`sk-` 形式字符串或 Windows 绝对路径。
- 临时验收 JSON、数据库、日志和 PNG 均位于仓库外，没有加入 Git。

## 8. 本轮最小修复

1. 允许受控退款率工具读取工具已支持的“是/否”分类字段，同时继续要求 sum/mean 使用数值字段。
2. 结论修复阶段根据同一 Run 的 EvidenceRegistry 重新生成受 Prompt 上限约束的 alias 映射；未降低 Evidence 校验。
3. 月度聚合补齐完整月份×类别组合，保留均值缺失语义。
4. 人数波动改用相对标准差，使数值与既有 percentage Evidence 单位一致。
5. 月度图在工具上限 100 行内绘制完整 90 行时间序列；非月度组合图仍保持既有 50 行限制。

所有生产改动均有先失败、后通过的回归测试。

## 9. 已知边界

- 两个最终 Run 的意图识别、计划、pandas、图表和 Evidence 均通过，但模型结论未通过严格结构化结论 Schema，最终均使用确定性降级，因此不能表述为“模型生成的最终结论通过”。
- 确定性降级文本仍包含 `group_aggregate`、`period`、`sample_count` 等内部稳定字段名，且通用摘要的个别单位文案不够自然；数字本身已通过 Evidence 和 pandas 复核。
- 组合结果共有 192 组；页面表格展示前 100 行，组合图展示前 50 项，并在标题中明确披露。
- 验收使用固定合成数据，没有真实用户数据、生产负载或性能结论。

## 10. 最终结论

两条受控意图均完成了“真实模型识别 → 服务端确定性计划 → pandas 计算 → 量纲安全图表 → 当前 Run Evidence → Artifact/Step 持久化 → SSE/REST 恢复”的真实闭环，所有页面业务数字与独立计算一致或仅存在可解释的序列化舍入差异。

由于最终结论均触发严格 Evidence 保护下的确定性降级，本次验收结论为 **有条件通过**。可以展示系统如何拒绝不合规模型回答并保持数字可信；若录制面向 HR 的最终成片，建议先在不改变计算和 Evidence 的前提下单独收敛确定性降级文案中的内部字段名和单位表达。
