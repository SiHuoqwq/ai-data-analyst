from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.v2.schemas.analysis import (
    Aggregation,
    FilterSpec,
    StrictAnalysisModel,
)


AnalysisType = Literal["group_comparison", "monthly_trend"]
DimensionId = Literal[
    "course_category",
    "course_difficulty",
    "purchase_channel",
    "primary_device",
]
GroupMetricId = Literal[
    "enrollment_count",
    "completion_rate",
    "refund_rate",
    "rating",
]
MonthlyMetricId = Literal[
    "enrollment_count",
    "paid_amount",
    "completion_rate",
]
MetricSemantic = Literal[
    "报名人数",
    "实付金额",
    "平均完成率",
    "退款率",
    "平均评分",
]

SEMANTIC_AGGREGATIONS: dict[str, set[str]] = {
    "报名人数": {"count"},
    "实付金额": {"sum"},
    "平均完成率": {"mean"},
    "退款率": {"rate", "mean"},
    "平均评分": {"mean"},
}


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class GroupComparisonIntent(StrictAnalysisModel):
    workflow: Literal["group_comparison"]
    dimensions: list[DimensionId] = Field(min_length=1, max_length=4)
    metric_ids: list[GroupMetricId] = Field(min_length=1, max_length=4)
    detect_underperforming: bool = False

    @field_validator("dimensions", "metric_ids", mode="before")
    @classmethod
    def deduplicate_ids(cls, values):
        return _deduplicate(values)


class MonthlyTrendIntent(StrictAnalysisModel):
    workflow: Literal["monthly_trend"]
    series_dimension: DimensionId
    metric_ids: list[MonthlyMetricId] = Field(min_length=1, max_length=3)

    @field_validator("metric_ids", mode="before")
    @classmethod
    def deduplicate_ids(cls, values):
        return _deduplicate(values)


DomainIntent = Annotated[
    GroupComparisonIntent | MonthlyTrendIntent,
    Field(discriminator="workflow"),
]


class IntentMetric(StrictAnalysisModel):
    semantic: MetricSemantic
    source_field: str | None = Field(default=None, max_length=256)
    aggregation: Aggregation

    @model_validator(mode="after")
    def validate_semantic_contract(self):
        if self.aggregation not in SEMANTIC_AGGREGATIONS[self.semantic]:
            raise ValueError("aggregation is not supported for this metric")
        if self.semantic == "报名人数":
            if self.source_field is not None:
                raise ValueError("count metric must not define source_field")
        elif not self.source_field:
            raise ValueError("source_field is required for this metric")
        return self


class AnalysisIntent(StrictAnalysisModel):
    analysis_type: AnalysisType
    dimensions: list[str] = Field(min_length=1, max_length=4)
    date_field: str | None = Field(default=None, max_length=256)
    metrics: list[IntentMetric] = Field(min_length=1, max_length=5)
    filters: list[FilterSpec] = Field(default_factory=list, max_length=20)
    needs_visualization: bool = True
    include_underperforming: bool = False

    @model_validator(mode="after")
    def validate_workflow_scope(self):
        semantics = {metric.semantic for metric in self.metrics}
        if self.analysis_type == "monthly_trend":
            if not self.date_field:
                raise ValueError("date_field is required for monthly_trend")
            allowed = {"报名人数", "实付金额", "平均完成率"}
            if not semantics.issubset(allowed):
                raise ValueError("monthly_trend contains unsupported metrics")
            if len(self.dimensions) != 1:
                raise ValueError("monthly_trend requires one series dimension")
            if self.include_underperforming:
                raise ValueError(
                    "monthly_trend does not support underperforming groups"
                )
        else:
            allowed = {"报名人数", "平均完成率", "退款率", "平均评分"}
            if not semantics.issubset(allowed):
                raise ValueError(
                    "group_comparison contains unsupported metrics"
                )
            if self.date_field is not None:
                raise ValueError(
                    "group_comparison must not define a date_field"
                )
        return self
