# 作品集演示指南

## 演示目标

在 5～8 分钟内说明三个核心价值：

1. 上传数据后，用户能够快速理解字段和数据质量；
2. 分析过程是可观察、可恢复、可取消的；
3. 模型只选择高层意图，业务数字由确定性工具计算并接受证据校验。

演示数据必须匿名，不提交用户真实 Excel、数据库、图表或密钥。

仓库内的推荐数据为 `demo/learning_operations_demo.csv`。该文件完全由
`demo/generate_learning_operations_demo.py` 生成，不对应任何真实个人、
机构或业务，允许随项目公开。需要重建时运行：

```powershell
python demo/generate_learning_operations_demo.py
```

## 无密钥演示

配置：

```dotenv
V2_PROVIDER=fake
```

流程：

1. 运行 `.\start-demo.ps1`，确认输出 Provider 为 Fake。
2. 打开 `http://localhost:5174`，确认顶部显示“Fake / 确定性演示/测试模式”。
3. 上传 `demo/learning_operations_demo.csv`。
4. 查看数据集行列数、字段信息、缺失值和前 20 行预览。
5. 进入分析工作台并提交“请生成数据预览表和概览图”。
6. 打开执行详情，展示真实 RunStep。
7. 展示 metric、table、chart 和 text Artifact。
8. 刷新页面，说明 Run、Artifact 和消息来自持久化恢复。
9. 在同一 Conversation 中提交第二个问题，展示消息顺序。

Fake Provider 的作用是稳定验证产品闭环。它不会真正理解任意业务问题，
演示时不要把固定测试结果描述成模型分析结论。

页面提供的“课程组合比较”和“月度趋势分析”快捷问题只填入输入框，不会
自动提交。Fake 模式下提交它们仍执行固定概览链路；它们主要用于后续受控
DeepSeek 验收。

推荐来源显示“模型选题”时，只表示模型选择了受控意图和引用字段；卡片标题
与问题始终由服务端确定性生成，并不是模型自由文案。“字段模板”表示选题也
由服务端生成。

点击推荐卡片只会填入输入框；确认提交时页面会附带数据集绑定的推荐 ID，
后端重新校验缓存、字段和意图后直接执行同一个受控 AnalysisIntent。手工编辑
问题会清除该选择并回到普通问题识别流程。

## 可选的真实领域分析

只有明确配置 DeepSeek 且接受真实请求费用时使用：

```dotenv
V2_PROVIDER=deepseek
DEEPSEEK_API_KEY=<local-secret>
```

支持的第一类问题：

> 请分析不同课程类别、课程难度、购买渠道和主要学习设备对课程完成率、
> 退款率及课程评分的影响。找出报名人数较多但完成率偏低的组合，并用
> 表格和图表展示关键结论，再给出运营建议。

支持的第二类问题：

> 请按月份统计各课程类别的报名人数、实付金额和平均完成率趋势，识别
> 增长最快、下滑最明显或波动异常的课程类别，并生成趋势图。

演示时说明：

- DeepSeek 只输出 `group_comparison` 或 `monthly_trend` 高层意图；
- PlanCompiler 负责编译固定步骤；
- pandas 负责计算；
- ChartPlanner 自动选择时间轴并按量纲拆图；
- Evidence Registry 约束最终结论；
- `deterministic_fallback` 表示服务端基于可信证据生成回答，不代表模型
  成功生成了结构化结论。

## 页面讲解顺序

### 工作区首页

- 上传支持 CSV、XLSX；
- 展示最近数据集；
- 后端健康状态来自 `/health`。

### 数据集概览

- 行列规模、缺失值、字段类型；
- 字段表和数据预览仅在自身容器横向滚动；
- 最近会话可以继续已有分析。

### 分析工作台

- 用户问题作为本轮分析标题；
- 主画布展示结论、指标、表格和图表；
- 执行详情抽屉只显示服务端真实步骤；
- SSE 中断后通过 REST 恢复；
- queued/running Run 可以合作式取消。

## 工程亮点回答

**为什么不让模型直接写 pandas？**

为了让字段、聚合方式、单位和结果血缘可校验。模型只选择受限意图，
服务端编译固定工作流。

**为什么同时使用 SSE 和 REST？**

SSE 提供实时体验；REST 与数据库提供刷新、断线和进程重启后的最终事实。

**如何避免模型编造数字？**

所有数字来自 pandas Artifact 和 Evidence。结构化结论必须引用当前 Run
的证据别名；失败后最多修复一次，再使用确定性降级。

**当前最大的限制是什么？**

领域和工作流有意收窄；V2 仍通过适配层复用 V1 文件和消息表；图表是静态
PNG；取消不能强制中断同步函数。

## 演示前检查

```powershell
python -m pytest -q
Set-Location frontend-v2
npm run typecheck
npm run lint
npm test
npm run build
```

- 确认 `.env` 未被 Git 跟踪；
- 确认使用匿名数据；
- 确认 `V2_PROVIDER=fake`，除非明确进行受控真实演示；
- 确认页面顶部 Provider 标识与 `/health` 一致；
- 确认页面没有显示绝对路径、Prompt、堆栈或密钥；
- 确认图表 URL 通过 HTTP 访问；
- 确认 390×844 和 1440×900 无页面级横向溢出。
