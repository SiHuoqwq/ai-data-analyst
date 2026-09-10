from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from app.db.models import FileModel
from app.services.parser import parse_file
from app.v2.domain.real_estate_registry import RealEstateDomainRegistry
from app.v2.schemas.intents import (
    AnalysisIntent,
    DomainIntent,
    GroupComparisonIntent,
    IntentMetric,
    MonthlyTrendIntent,
)
from app.v2.schemas.results import (
    ResultDimension,
    ResultMetric,
    ResultSchema,
)


class PlanCompilationError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class CompiledStep:
    step_id: str
    operation: str
    display_name: str
    arguments: dict[str, Any]
    output_schema: ResultSchema | None = None


@dataclass(frozen=True)
class CompiledPlan:
    workflow: str
    goal: str
    steps: tuple[CompiledStep, ...]
    intent: AnalysisIntent

    def step(self, step_id: str) -> CompiledStep:
        for item in self.steps:
            if item.step_id == step_id:
                return item
        raise KeyError(step_id)


SEMANTIC_FIELDS = {
    "线索数": ("lead_count", "count"),
    "到访数": ("visit_count", "count"),
    "认购数": ("subscription_count", "count"),
    "成交套数": ("deal_count", "count"),
    "成交金额": ("deal_amount_sum", "currency"),
    "回款金额": ("payment_amount_sum", "currency"),
    "到访率": ("visit_rate", "percentage"),
    "认购转化率": ("subscription_rate", "percentage"),
    "成交转化率": ("deal_rate", "percentage"),
    "平均成交金额": ("avg_deal_amount", "currency"),
}

MONTHLY_FIELDS = {
    "线索数": ("lead_count", "count"),
    "到访数": ("visit_count", "count"),
    "认购数": ("subscription_count", "count"),
    "成交套数": ("deal_count", "count"),
    "成交金额": ("deal_amount_sum", "currency"),
    "回款金额": ("payment_amount_sum", "currency"),
}

# 房地产月度趋势中，各指标对应各自的业务日期阶段。
MONTHLY_METRIC_DATES = {
    "lead_count": "lead_date",
    "visit_count": "visit_date",
    "subscription_count": "subscription_date",
    "deal_count": "contract_date",
    "deal_amount": "contract_date",
    "payment_amount": "contract_date",
}


def _metric_schema(
    metric: IntentMetric,
    monthly: bool,
) -> ResultMetric:
    metric_id, unit = (
        MONTHLY_FIELDS if monthly else SEMANTIC_FIELDS
    )[metric.semantic]
    return ResultMetric(
        id=metric_id,
        label=metric.semantic,
        unit=unit,
        aggregation=metric.aggregation,
        nullable=metric.aggregation != "count",
        source_field=metric.source_field,
    )


class PlanValidator:
    def __init__(
        self,
        dataframe_loader: Callable[[str], pd.DataFrame] | None = None,
    ):
        self.dataframe_loader = dataframe_loader

    def validate_intent_fields(
        self,
        intent: AnalysisIntent,
        file_record: FileModel,
    ) -> None:
        fields = {
            str(item.get("name")): str(item.get("dtype", ""))
            for item in (file_record.columns_info or [])
        }
        referenced = [
            *intent.dimensions,
            *[item.field for item in intent.filters],
            *[
                item.source_field
                for item in intent.metrics
                if item.source_field is not None
            ],
        ]
        if intent.date_field:
            referenced.append(intent.date_field)
        for field in referenced:
            if field not in fields:
                raise PlanCompilationError(
                    "FIELD_NOT_FOUND",
                    "分析字段不存在",
                    {"field": field},
                )
        for metric in intent.metrics:
            if metric.source_field is None:
                continue
            dtype = fields[metric.source_field].lower()
            numeric = any(
                marker in dtype
                for marker in ("int", "float", "decimal", "number", "bool")
            )
            if metric.aggregation in {"sum", "mean"} and not numeric:
                raise PlanCompilationError(
                    "INVALID_FIELD_TYPE",
                    "指标字段类型不支持所选聚合",
                    {
                        "field": metric.source_field,
                        "aggregation": metric.aggregation,
                    },
                )

    def validate(
        self,
        plan: CompiledPlan,
        file_record: FileModel,
    ) -> None:
        self.validate_intent_fields(plan.intent, file_record)
        seen: set[str] = set()
        for step in plan.steps:
            if step.step_id in seen:
                raise PlanCompilationError(
                    "DUPLICATE_STEP_ID",
                    "编译后的步骤 ID 重复",
                )
            if step.operation == "chart_planning":
                if set(step.arguments) != {"source_step_ids"}:
                    raise PlanCompilationError(
                        "INVALID_FIELD_LINEAGE",
                        "图表规划只能引用上游结构化结果",
                    )
                for source_id in step.arguments["source_step_ids"]:
                    if source_id not in seen:
                        raise PlanCompilationError(
                            "INVALID_FIELD_LINEAGE",
                            "图表规划引用了不存在的上游步骤",
                            {"source_step_id": source_id},
                        )
                    source = plan.step(source_id)
                    if source.output_schema is None:
                        raise PlanCompilationError(
                            "INVALID_FIELD_LINEAGE",
                            "图表规划引用的步骤没有输出 Schema",
                        )
            seen.add(step.step_id)

        if plan.workflow == "monthly_trend":
            schema = plan.step("monthly_aggregate").output_schema
            time_dimensions = [
                item for item in schema.dimensions if item.role == "time"
            ]
            if [item.id for item in time_dimensions] != ["period"]:
                raise PlanCompilationError(
                    "INVALID_FIELD_LINEAGE",
                    "月度趋势必须使用 period 时间维度",
                )
            loader = self.dataframe_loader
            if loader is not None:
                frame = loader(file_record.filepath)
                parsed = pd.to_datetime(
                    frame[plan.intent.date_field],
                    errors="coerce",
                    format="mixed",
                )
                if parsed.notna().sum() == 0:
                    raise PlanCompilationError(
                        "UNPARSABLE_DATE_FIELD",
                        "日期字段没有可解析值",
                        {"field": plan.intent.date_field},
                    )


class PlanCompiler:
    def __init__(
        self,
        validator: PlanValidator | None = None,
        registry: RealEstateDomainRegistry | None = None,
    ):
        self.validator = validator or PlanValidator(
            dataframe_loader=parse_file
        )
        self.registry = registry or RealEstateDomainRegistry()

    def compile(
        self,
        intent: DomainIntent | AnalysisIntent,
        file_record: FileModel,
    ) -> CompiledPlan:
        if isinstance(intent, (GroupComparisonIntent, MonthlyTrendIntent)):
            intent = self._resolve_domain_intent(intent)
        self.validator.validate_intent_fields(intent, file_record)
        if intent.analysis_type == "monthly_trend":
            return self._compile_monthly(intent)
        if intent.analysis_type == "group_comparison":
            return self._compile_group(intent)
        raise PlanCompilationError(
            "UNSUPPORTED_ANALYSIS_INTENT",
            "当前分析类型不在支持范围内",
        )

    def _resolve_domain_intent(
        self,
        intent: GroupComparisonIntent | MonthlyTrendIntent,
    ) -> AnalysisIntent:
        if isinstance(intent, GroupComparisonIntent):
            return AnalysisIntent(
                analysis_type="group_comparison",
                dimensions=[
                    self.registry.dimension(item).source_field
                    for item in intent.dimensions
                ],
                metrics=[
                    self._resolved_metric(item)
                    for item in intent.metric_ids
                ],
                include_underperforming=intent.detect_underperforming,
            )
        date_ids = {
            MONTHLY_METRIC_DATES[item] for item in intent.metric_ids
        }
        if len(date_ids) != 1:
            raise PlanCompilationError(
                "MIXED_MONTHLY_DATE_SCOPE",
                "月度趋势中各指标对应不同业务日期，暂不支持混合日期聚合",
                {
                    "metric_ids": intent.metric_ids,
                    "date_ids": sorted(date_ids),
                },
            )
        return AnalysisIntent(
            analysis_type="monthly_trend",
            dimensions=[
                self.registry.dimension(
                    intent.series_dimension
                ).source_field
            ],
            date_field=self.registry.date(date_ids.pop()).source_field,
            metrics=[
                self._resolved_metric(item)
                for item in intent.metric_ids
            ],
        )

    def _resolved_metric(self, metric_id: str) -> IntentMetric:
        definition = self.registry.metric(metric_id)
        return IntentMetric(
            semantic=definition.semantic,
            source_field=definition.source_field,
            aggregation=definition.aggregation,
        )

    def _compile_metric_specs(
        self,
        metrics: list[IntentMetric],
        monthly: bool,
    ) -> list[dict[str, Any]]:
        field_map = MONTHLY_FIELDS if monthly else SEMANTIC_FIELDS
        base_specs: dict[str, dict[str, Any]] = {}
        derived_specs: list[dict[str, Any]] = []

        def ensure_base(definition) -> str:
            result_id = field_map[definition.semantic][0]
            if result_id not in base_specs:
                base_specs[result_id] = {
                    "kind": "base",
                    "field": definition.source_field,
                    "aggregation": definition.aggregation,
                    "alias": result_id,
                }
            return result_id

        for metric in metrics:
            definition = self.registry.metric_by_semantic(metric.semantic)
            result_id = field_map[metric.semantic][0]
            if definition.is_derived:
                numerator_id = ensure_base(
                    self.registry.metric(definition.numerator_metric_id)
                )
                denominator_id = ensure_base(
                    self.registry.metric(definition.denominator_metric_id)
                )
                derived_specs.append(
                    {
                        "kind": "derived",
                        "numerator_metric_id": numerator_id,
                        "denominator_metric_id": denominator_id,
                        "alias": result_id,
                    }
                )
            else:
                ensure_base(definition)

        return list(base_specs.values()) + derived_specs

    def _compile_monthly(self, intent: AnalysisIntent) -> CompiledPlan:
        dimensions = [
            ResultDimension(
                id="period",
                label="月份",
                role="time",
                data_type="date",
                source_field=intent.date_field,
            ),
            ResultDimension(
                id="series",
                label=intent.dimensions[0],
                role="series",
                data_type="string",
                source_field=intent.dimensions[0],
            ),
        ]
        metrics = [
            _metric_schema(metric, monthly=True)
            for metric in intent.metrics
        ]
        schema = ResultSchema(
            dimensions=dimensions,
            metrics=metrics,
            grain=["period", "series"],
            time_granularity="month",
        )
        steps = (
            CompiledStep(
                "inspect",
                "inspect_dataset",
                "检查数据字段",
                {},
            ),
            CompiledStep(
                "monthly_aggregate",
                "monthly_trend",
                "计算月度趋势",
                {
                    "date_field": intent.date_field,
                    "category_field": intent.dimensions[0],
                    "metrics": [
                        {
                            "field": item.source_field,
                            "aggregation": item.aggregation,
                            "alias": result.id,
                        }
                        for item, result in zip(intent.metrics, metrics)
                    ],
                    "filters": [
                        item.model_dump(mode="json")
                        for item in intent.filters
                    ],
                    "limit": 100,
                },
                schema,
            ),
            CompiledStep(
                "trend_signals",
                "calculate_trend_signals",
                "识别增长、下降和波动",
                {"source_step_id": "monthly_aggregate"},
                schema,
            ),
            CompiledStep(
                "charts",
                "chart_planning",
                "根据结果元数据生成趋势图",
                {"source_step_ids": ["monthly_aggregate"]},
            ),
        )
        return CompiledPlan(
            workflow="monthly_trend",
            goal="按月份分析房地产销售趋势",
            steps=steps,
            intent=intent,
        )

    def _compile_group(self, intent: AnalysisIntent) -> CompiledPlan:
        dimensions = [
            ResultDimension(
                id=f"dimension_{index}",
                label=field,
                role="category",
                data_type="string",
                source_field=field,
            )
            for index, field in enumerate(intent.dimensions, start=1)
        ]
        metrics = [
            _metric_schema(metric, monthly=False)
            for metric in intent.metrics
        ]
        aggregate_schema = ResultSchema(
            dimensions=dimensions,
            metrics=metrics,
            grain=[item.id for item in dimensions],
        )
        aggregate_step = CompiledStep(
            "group_aggregate",
            "group_aggregate",
            "比较房地产销售指标",
            {
                "group_by": intent.dimensions,
                "metrics": self._compile_metric_specs(
                    intent.metrics, monthly=False
                ),
                "filters": [
                    item.model_dump(mode="json") for item in intent.filters
                ],
                "sort": [
                    {"field": metrics[0].id, "direction": "desc"}
                ],
                "limit": 100,
            },
            aggregate_schema,
        )
        steps: list[CompiledStep] = [
            CompiledStep(
                "inspect",
                "inspect_dataset",
                "检查数据字段",
                {},
            ),
            aggregate_step,
        ]
        if intent.include_underperforming:
            steps.append(
                self._underperforming_step(intent, dimensions)
            )
        steps.append(
            CompiledStep(
                "charts",
                "chart_planning",
                "根据结果元数据生成对比图",
                {"source_step_ids": ["group_aggregate"]},
            )
        )
        return CompiledPlan(
            workflow="group_comparison",
            goal="比较房地产销售维度表现",
            steps=tuple(steps),
            intent=intent,
        )

    def _underperforming_step(
        self,
        intent: AnalysisIntent,
        dimensions: list[ResultDimension],
    ) -> CompiledStep:
        lead = self.registry.metric("lead_count")
        deal_count = self.registry.metric("deal_count")
        deal_rate = self.registry.metric("deal_rate")
        schema = ResultSchema(
            dimensions=dimensions,
            metrics=[
                ResultMetric(
                    id="lead_count",
                    label=lead.label,
                    unit="count",
                    aggregation="count",
                    nullable=False,
                    source_field=None,
                ),
                ResultMetric(
                    id="deal_count",
                    label=deal_count.label,
                    unit="count",
                    aggregation="count",
                    nullable=True,
                    source_field=deal_count.source_field,
                ),
                ResultMetric(
                    id="deal_rate",
                    label=deal_rate.label,
                    unit="percentage",
                    aggregation="ratio",
                    nullable=True,
                    source_field=None,
                ),
            ],
            grain=[item.id for item in dimensions],
        )
        return CompiledStep(
            "underperforming",
            "identify_underperforming",
            "识别高线索量低成交转化率组合",
            {
                "group_by": intent.dimensions,
                "conversion_field": self.registry.date(
                    "contract_date"
                ).source_field,
                "min_sample_size": 5,
                "high_volume_quantile": 0.75,
                "low_conversion_quantile": 0.25,
                "limit": 20,
            },
            schema,
        )
