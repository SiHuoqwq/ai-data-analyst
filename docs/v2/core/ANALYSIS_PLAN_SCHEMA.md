# AnalysisPlan 结构化计划合同

> 合同状态：V2 设计合同，当前尚未实现。当前可运行系统仍使用 `/api/v1`。文中的 JSON Schema 是目标合同基准；实现阶段必须由 Pydantic Schema 导出并通过合同测试，生成结果才是运行时事实来源。

## 1. 核心决定

V2 区分两个对象：

1. `ModelPlanDraft`：发给模型生成的草稿结构，不包含可自由填写的 `dataset_version_id`。
2. `AnalysisPlan`：服务端将 Run 已绑定的 `dataset_version_id` 注入草稿后形成的持久化计划。

因此，持久化 AnalysisPlan 必须包含 `dataset_version_id`，但该字段是 `readOnly` 服务端字段。任何模型输出中的同名字段都被 `extra="forbid"` 拒绝，而不是覆盖服务端上下文。

## 2. JSON Schema

Schema 使用 JSON Schema Draft 2020-12。实现时由 Pydantic model 自动导出此合同，不维护独立手写 Tool Schema；本文是设计基准，代码生成结果必须通过合同测试与本文保持兼容。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai-data-analyst.local/schemas/analysis-plan/1.0.json",
  "title": "AnalysisPlan",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "goal",
    "dataset_version_id",
    "steps",
    "expected_outputs",
    "assumptions",
    "warnings"
  ],
  "properties": {
    "schema_version": {
      "const": "1.0"
    },
    "goal": {
      "type": "string",
      "minLength": 1,
      "maxLength": 1000
    },
    "dataset_version_id": {
      "type": "string",
      "minLength": 1,
      "readOnly": true,
      "description": "由服务端从 AnalysisRun 注入，模型不可选择或切换"
    },
    "steps": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {
        "$ref": "#/$defs/PlanStep"
      }
    },
    "expected_outputs": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {
        "$ref": "#/$defs/ExpectedOutput"
      }
    },
    "assumptions": {
      "type": "array",
      "maxItems": 20,
      "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": 500
      }
    },
    "warnings": {
      "type": "array",
      "maxItems": 20,
      "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": 500
      }
    }
  },
  "$defs": {
    "ArtifactType": {
      "type": "string",
      "enum": [
        "text",
        "metric",
        "table",
        "chart"
      ]
    },
    "MetricSpec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["field", "aggregation", "alias"],
      "properties": {
        "field": {
          "type": "string",
          "minLength": 1,
          "maxLength": 256
        },
        "aggregation": {
          "type": "string",
          "enum": [
            "none",
            "count",
            "count_distinct",
            "sum",
            "mean",
            "min",
            "max",
            "median",
            "stddev"
          ]
        },
        "alias": {
          "type": ["string", "null"],
          "maxLength": 256
        }
      }
    },
    "DimensionSpec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["field", "time_grain"],
      "properties": {
        "field": {
          "type": "string",
          "minLength": 1,
          "maxLength": 256
        },
        "time_grain": {
          "type": ["string", "null"],
          "enum": [null, "day", "week", "month", "quarter", "year"]
        }
      }
    },
    "FilterSpec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["field", "operator", "value"],
      "properties": {
        "field": {
          "type": "string",
          "minLength": 1,
          "maxLength": 256
        },
        "operator": {
          "type": "string",
          "enum": [
            "eq",
            "ne",
            "gt",
            "gte",
            "lt",
            "lte",
            "in",
            "not_in",
            "between",
            "contains",
            "is_null",
            "not_null"
          ]
        },
        "value": {
          "oneOf": [
            {"type": "string"},
            {"type": "number"},
            {"type": "boolean"},
            {"type": "null"},
            {
              "type": "array",
              "minItems": 1,
              "maxItems": 100,
              "items": {
                "type": ["string", "number", "boolean", "null"]
              }
            }
          ]
        }
      }
    },
    "AggregationSpec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["mode", "drop_null_groups"],
      "properties": {
        "mode": {
          "type": "string",
          "enum": ["none", "global", "grouped"]
        },
        "drop_null_groups": {
          "type": "boolean"
        }
      }
    },
    "SortSpec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["field_or_alias", "direction", "nulls"],
      "properties": {
        "field_or_alias": {
          "type": "string",
          "minLength": 1,
          "maxLength": 256
        },
        "direction": {
          "type": "string",
          "enum": ["asc", "desc"]
        },
        "nulls": {
          "type": "string",
          "enum": ["first", "last"]
        }
      }
    },
    "OperationConfig": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "columns": {
          "type": "array",
          "maxItems": 100,
          "items": {"type": "string", "minLength": 1}
        },
        "include_profile": {"type": "boolean"},
        "method": {
          "type": ["string", "null"],
          "enum": [null, "iqr", "zscore", "mad", "seasonal"]
        },
        "sensitivity": {
          "type": ["number", "null"],
          "minimum": 0,
          "maximum": 10
        },
        "time_grain": {
          "type": ["string", "null"],
          "enum": [null, "day", "week", "month", "quarter", "year"]
        },
        "chart_type": {
          "type": ["string", "null"],
          "enum": [null, "bar", "line", "scatter", "heatmap", "table"]
        },
        "source_artifact_id": {
          "type": ["string", "null"]
        },
        "sampling": {
          "type": ["string", "null"],
          "enum": [null, "head", "random", "stratified"]
        }
      }
    },
    "PlanStep": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "step_id",
        "operation",
        "metrics",
        "dimensions",
        "filters",
        "aggregation",
        "sort",
        "limit",
        "dependencies",
        "expected_artifact_type",
        "parameters"
      ],
      "properties": {
        "step_id": {
          "type": "string",
          "pattern": "^[a-z][a-z0-9_]{0,63}$"
        },
        "operation": {
          "type": "string",
          "enum": [
            "inspect_dataset",
            "query_dataset",
            "analyze_distribution",
            "analyze_time_series",
            "detect_anomalies",
            "create_visualization",
            "retrieve_artifact"
          ]
        },
        "metrics": {
          "type": "array",
          "maxItems": 20,
          "items": {"$ref": "#/$defs/MetricSpec"}
        },
        "dimensions": {
          "type": "array",
          "maxItems": 20,
          "items": {"$ref": "#/$defs/DimensionSpec"}
        },
        "filters": {
          "type": "array",
          "maxItems": 50,
          "items": {"$ref": "#/$defs/FilterSpec"}
        },
        "aggregation": {
          "$ref": "#/$defs/AggregationSpec"
        },
        "sort": {
          "type": "array",
          "maxItems": 10,
          "items": {"$ref": "#/$defs/SortSpec"}
        },
        "limit": {
          "type": ["integer", "null"],
          "minimum": 1,
          "maximum": 1000
        },
        "dependencies": {
          "type": "array",
          "maxItems": 20,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]{0,63}$"
          }
        },
        "expected_artifact_type": {
          "$ref": "#/$defs/ArtifactType"
        },
        "parameters": {
          "$ref": "#/$defs/OperationConfig"
        }
      }
    },
    "ExpectedOutput": {
      "type": "object",
      "additionalProperties": false,
      "required": ["from_step_id", "artifact_type", "description", "required"],
      "properties": {
        "from_step_id": {
          "type": "string",
          "pattern": "^[a-z][a-z0-9_]{0,63}$"
        },
        "artifact_type": {
          "$ref": "#/$defs/ArtifactType"
        },
        "description": {
          "type": "string",
          "minLength": 1,
          "maxLength": 500
        },
        "required": {
          "type": "boolean"
        }
      }
    }
  }
}
```

## 3. Pydantic 模型边界

实现应由一组 `BaseModel` 组合而成，全部使用：

```python
model_config = ConfigDict(extra="forbid", strict=True)
```

服务端构建顺序：

```text
模型 JSON
→ ModelPlanDraft.model_validate_json
→ 注入 run.dataset_version_id
→ AnalysisPlan.model_validate
→ 数据集 schema 语义校验
→ DAG 和 operation 规则校验
→ 保存 valid/invalid plan revision
```

禁止做法：

- 手工把 Pydantic 字段重新映射成一份工具 Schema；
- `extra="ignore"` 静默吞掉模型生成的未知字段；
- 用类型强制转换掩盖错误，例如把任意字符串转数字；
- 接受模型传入的 `file_id`、storage path、SQL、run_id 或 dataset_version_id。

## 4. 语义校验规则

JSON Schema 只能验证形状，以下规则必须由 `PlanValidator` 在执行前验证。

### 4.1 绑定与版本

- `plan.dataset_version_id == run.dataset_version_id`。
- DatasetVersion 必须为 ready，且属于 Conversation 的 Dataset。
- 所有 source artifact 必须属于同一 DatasetVersion，除非 operation 明确支持跨版本比较；V2 第一版不支持跨版本操作。

### 4.2 字段与类型

- metrics、dimensions、filters、columns 中的字段必须精确存在于 `DatasetVersion.schema_json`。
- 数值聚合只允许数值字段；count/count_distinct 可用于其他类型。
- time_grain 只允许可安全转换为日期/时间的字段。
- contains 只允许文本/分类字段。
- between 必须传两个同类型值；in/not_in 必须传数组；is_null/not_null 的 value 必须为 null。
- sort 只能引用结果字段、dimension 或 metric alias。

### 4.3 聚合与结果大小

- aggregation=grouped 时 dimensions 不能为空。
- aggregation=none 时 metric aggregation 必须全部为 none，除非 operation 自身定义统计输出。
- `limit` 缺失仅允许 inspect/统计类操作；可能产生明细行的 query 必须有 limit。
- 预估分组基数或结果大小超过阈值时拒绝或要求先缩小维度，不让模型无限查询。

### 4.4 步骤依赖

- step_id 唯一。
- 每个 dependency 必须引用同计划中的 step_id。
- 依赖图必须是 DAG，不能自依赖。
- `create_visualization.parameters.source_artifact_id` 可引用运行前已有 Artifact；若来源由当前计划产生，应通过 dependency 和执行时解析的 artifact 角色引用，不允许模型猜测未来 artifact_id。
- expected_outputs.from_step_id 必须存在，且类型与步骤 expected_artifact_type 一致。

### 4.5 Operation 专属规则

| Operation | 必要规则 |
|---|---|
| `inspect_dataset` | metrics/dimensions/filters 为空；columns 可选；第一阶段输出 text/metric/table 摘要。 |
| `query_dataset` | 至少一个 metric 或 dimension；明细查询必须 limit；不接受原始 SQL。 |
| `analyze_distribution` | 至少一个目标字段；不接受 chart_type；结果为 metric/table。 |
| `analyze_time_series` | 必须有一个时间 dimension 和至少一个数值 metric；需要 time_grain。 |
| `detect_anomalies` | 必须有数值 metric；method 必须与数据类型和时间维度兼容。 |
| `create_visualization` | 必须依赖表格/metric Artifact 或确定性查询步骤；chart_type 必填；不直接把原始全量数据发送给前端。 |
| `retrieve_artifact` | source_artifact_id 必填；只返回受限 preview，不改变 Artifact。 |

## 5. 示例计划

用户问题：“按月份比较销售额趋势，并画折线图。”服务端已经把 Run 固定到 `dver_sales_2026_01`。

```json
{
  "schema_version": "1.0",
  "goal": "按月份汇总销售额，识别整体变化并生成趋势图",
  "dataset_version_id": "dver_sales_2026_01",
  "steps": [
    {
      "step_id": "monthly_sales",
      "operation": "analyze_time_series",
      "metrics": [
        {
          "field": "sales",
          "aggregation": "sum",
          "alias": "monthly_sales"
        }
      ],
      "dimensions": [
        {
          "field": "order_date",
          "time_grain": "month"
        }
      ],
      "filters": [],
      "aggregation": {
        "mode": "grouped",
        "drop_null_groups": true
      },
      "sort": [
        {
          "field_or_alias": "order_date",
          "direction": "asc",
          "nulls": "last"
        }
      ],
      "limit": 120,
      "dependencies": [],
      "expected_artifact_type": "table",
      "parameters": {
        "time_grain": "month"
      }
    },
    {
      "step_id": "sales_chart",
      "operation": "create_visualization",
      "metrics": [],
      "dimensions": [],
      "filters": [],
      "aggregation": {
        "mode": "none",
        "drop_null_groups": true
      },
      "sort": [],
      "limit": null,
      "dependencies": ["monthly_sales"],
      "expected_artifact_type": "chart",
      "parameters": {
        "chart_type": "line"
      }
    }
  ],
  "expected_outputs": [
    {
      "from_step_id": "monthly_sales",
      "artifact_type": "table",
      "description": "月度销售额时间序列",
      "required": true
    },
    {
      "from_step_id": "sales_chart",
      "artifact_type": "chart",
      "description": "月度销售额折线图",
      "required": true
    }
  ],
  "assumptions": [
    "sales 字段代表可直接汇总的销售额口径"
  ],
  "warnings": [
    "计划执行前需要确认 order_date 的日期解析成功率"
  ]
}
```

## 6. 计划修订和失败

- 首次草稿 revision=1。
- schema/DAG/字段错误写入 invalid plan 的 validation_errors，不创建执行步骤。
- 可修正错误允许在 Run 保持 running 时重新进入 plan_generation 阶段，创建 revision+1；默认最多 2 次模型修订，避免无限循环。
- valid plan 不原地修改。需要调整时创建新 revision，并把旧计划标记 superseded。
- 用户在执行开始后改变目标，应创建新 AnalysisRun，不修改当前计划。

## 7. 合同测试要求

后续实现至少测试：

- 模型草稿包含 dataset_version_id/file_id 时被拒绝；
- 未知字段被拒绝；
- 列不存在、类型不兼容、聚合非法时执行前失败；
- 循环依赖、缺失依赖和 future artifact ID 被拒绝；
- 服务端注入版本与 Run 不一致时失败；
- JSON Schema 从 Pydantic 自动生成并与 API OpenAPI 中的 schema 一致；
- 固定计划样例能稳定通过校验，非法样例产生结构化错误路径。
