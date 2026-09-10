from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.v2.schemas.analysis import (
    Aggregation,
    FilterSpec,
    StrictAnalysisModel,
)


AnalysisType = Literal["group_comparison", "monthly_trend"]
DimensionId = Literal[
    "project_name",
    "city",
    "district",
    "sales_consultant",
    "lead_channel",
    "property_type",
    "customer_level",
]
GroupMetricId = Literal[
    "lead_count",
    "visit_count",
    "subscription_count",
    "deal_count",
    "deal_amount",
    "payment_amount",
    "visit_rate",
    "subscription_rate",
    "deal_rate",
    "avg_deal_amount",
]
MonthlyMetricId = Literal[
    "lead_count",
    "visit_count",
    "subscription_count",
    "deal_count",
    "deal_amount",
    "payment_amount",
]
MetricSemantic = Literal[
    "线索数",
    "到访数",
    "认购数",
    "成交套数",
    "成交金额",
    "回款金额",
    "到访率",
    "认购转化率",
    "成交转化率",
    "平均成交金额",
]

SEMANTIC_AGGREGATIONS: dict[str, set[str]] = {
    "线索数": {"count"},
    "到访数": {"count"},
    "认购数": {"count"},
    "成交套数": {"count"},
    "成交金额": {"sum"},
    "回款金额": {"sum"},
    "到访率": {"ratio"},
    "认购转化率": {"ratio"},
    "成交转化率": {"ratio"},
    "平均成交金额": {"ratio"},
}

# 到访率 / 认购转化率 / 成交转化率 / 平均成交金额均为派生指标，
# 由注册表定义分子与分母指标，跨指标相除计算。
_COUNT_SEMANTICS = {"线索数", "到访数", "认购数", "成交套数"}
_DERIVED_SEMANTICS = {"到访率", "认购转化率", "成交转化率", "平均成交金额"}
_MONTHLY_SEMANTICS = {
    "线索数",
    "到访数",
    "认购数",
    "成交套数",
    "成交金额",
    "回款金额",
}
_GROUP_SEMANTICS = _MONTHLY_SEMANTICS | _DERIVED_SEMANTICS


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
        if self.semantic in _DERIVED_SEMANTICS:
            if self.source_field is not None:
                raise ValueError("derived metric must not define source_field")
        elif self.semantic in _COUNT_SEMANTICS:
            # 计数指标可引用字段（到访/认购/签约日期）以统计非空记录，
            # 线索数不引用字段，直接统计行数。
            return self
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
            if not semantics.issubset(_MONTHLY_SEMANTICS):
                raise ValueError("monthly_trend contains unsupported metrics")
            if len(self.dimensions) != 1:
                raise ValueError("monthly_trend requires one series dimension")
            if self.include_underperforming:
                raise ValueError(
                    "monthly_trend does not support underperforming groups"
                )
        else:
            if not semantics.issubset(_GROUP_SEMANTICS):
                raise ValueError(
                    "group_comparison contains unsupported metrics"
                )
            if self.date_field is not None:
                raise ValueError(
                    "group_comparison must not define a date_field"
                )
        return self
