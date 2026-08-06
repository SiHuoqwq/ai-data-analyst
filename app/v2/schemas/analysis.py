from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictAnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Aggregation = Literal["count", "sum", "mean", "min", "max", "rate"]
FilterOperator = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "contains",
    "is_null",
    "not_null",
]


class MetricSpec(StrictAnalysisModel):
    field: str | None = Field(default=None, max_length=256)
    aggregation: Aggregation
    alias: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def require_field_for_value_aggregations(self):
        if self.aggregation != "count" and not self.field:
            raise ValueError("field is required for this aggregation")
        return self


class FilterSpec(StrictAnalysisModel):
    field: str = Field(min_length=1, max_length=256)
    operator: FilterOperator
    value: Any = None


class SortSpec(StrictAnalysisModel):
    field: str = Field(min_length=1, max_length=256)
    direction: Literal["asc", "desc"] = "asc"


class InspectDatasetInput(StrictAnalysisModel):
    pass


class GroupAggregateInput(StrictAnalysisModel):
    group_by: list[str] = Field(min_length=1, max_length=4)
    metrics: list[MetricSpec] = Field(min_length=1, max_length=10)
    filters: list[FilterSpec] = Field(default_factory=list, max_length=20)
    sort: list[SortSpec] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=50, ge=1, le=100)


class MonthlyTrendInput(StrictAnalysisModel):
    date_field: str = Field(min_length=1, max_length=256)
    category_field: str = Field(min_length=1, max_length=256)
    metrics: list[MetricSpec] = Field(min_length=1, max_length=10)
    filters: list[FilterSpec] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=100, ge=1, le=100)


class UnderperformingInput(StrictAnalysisModel):
    group_by: list[str] = Field(min_length=1, max_length=4)
    completion_field: str = Field(min_length=1, max_length=256)
    min_sample_size: int = Field(default=5, ge=1, le=100_000)
    high_volume_quantile: float = Field(default=0.75, ge=0, le=1)
    low_completion_quantile: float = Field(default=0.25, ge=0, le=1)
    limit: int = Field(default=20, ge=1, le=100)


class CreateChartInput(StrictAnalysisModel):
    source_step_id: str = Field(min_length=1, max_length=100)
    chart_type: Literal["bar", "line"]
    x_field: str = Field(min_length=1, max_length=256)
    y_fields: list[str] = Field(min_length=1, max_length=4)
    color_field: str | None = Field(default=None, max_length=256)
    title: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


TOOL_INPUT_MODELS = {
    "inspect_dataset": InspectDatasetInput,
    "group_aggregate": GroupAggregateInput,
    "monthly_trend": MonthlyTrendInput,
    "identify_underperforming": UnderperformingInput,
    "create_chart": CreateChartInput,
}


class PlanStepDraft(StrictAnalysisModel):
    id: str = Field(min_length=1, max_length=100)
    tool: Literal[
        "inspect_dataset",
        "group_aggregate",
        "monthly_trend",
        "identify_underperforming",
        "create_chart",
    ]
    purpose: str = Field(min_length=1, max_length=300)
    arguments: dict[str, Any]

    @model_validator(mode="after")
    def validate_tool_arguments(self):
        model = TOOL_INPUT_MODELS[self.tool]
        self.arguments = model.model_validate(self.arguments).model_dump(
            mode="json"
        )
        return self


class ModelPlanDraft(StrictAnalysisModel):
    goal: str = Field(min_length=1, max_length=1000)
    steps: list[PlanStepDraft] = Field(min_length=1, max_length=6)


def model_tool_catalog() -> list[dict[str, Any]]:
    descriptions = {
        "inspect_dataset": "检查字段、类型和缺失情况，不读取原始样例值。",
        "group_aggregate": "按一个或多个维度计算计数、金额、均值或布尔比例。",
        "monthly_trend": "按月份和类别计算多个聚合指标。",
        "identify_underperforming": "用分位数和最小样本量识别高报名低完成组合。",
        "create_chart": "基于本次运行已有步骤结果生成柱状图或折线图。",
    }
    return [
        {
            "name": name,
            "description": descriptions[name],
            "read_only": True,
            "output_types": (
                ["chart"]
                if name == "create_chart"
                else ["text", "metric"]
                if name == "inspect_dataset"
                else ["table"]
            ),
            "input_schema": model.model_json_schema(),
        }
        for name, model in TOOL_INPUT_MODELS.items()
    ]
