from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from app.db.models import FileModel
from app.services.parser import parse_file
from app.v2.domain.learning_registry import LearningDomainRegistry
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
    "报名人数": ("sample_count", "count"),
    "实付金额": ("paid_amount_sum", "currency"),
    "平均完成率": ("completion_rate_mean", "percentage"),
    "退款率": ("refund_rate", "percentage"),
    "平均评分": ("rating_mean", "score"),
}

MONTHLY_FIELDS = {
    "报名人数": ("enrollment_count", "count"),
    "实付金额": ("paid_amount_sum", "currency"),
    "平均完成率": ("completion_rate_mean", "percentage"),
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
        registry: LearningDomainRegistry | None = None,
    ):
        self.validator = validator or PlanValidator(
            dataframe_loader=parse_file
        )
        self.registry = registry or LearningDomainRegistry()

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
        return AnalysisIntent(
            analysis_type="monthly_trend",
            dimensions=[
                self.registry.dimension(
                    intent.series_dimension
                ).source_field
            ],
            date_field=self.registry.date("enrollment_date").source_field,
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
            goal="按月份和课程类别分析运营趋势",
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
            "比较课程运营指标",
            {
                "group_by": intent.dimensions,
                "metrics": [
                    {
                        "field": item.source_field,
                        "aggregation": item.aggregation,
                        "alias": result.id,
                    }
                    for item, result in zip(intent.metrics, metrics)
                ],
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
        chart_sources = ["group_aggregate"]
        if intent.include_underperforming:
            completion = next(
                (
                    item
                    for item in intent.metrics
                    if item.semantic == "平均完成率"
                ),
                None,
            )
            if completion is None:
                raise PlanCompilationError(
                    "MISSING_REQUIRED_METRIC",
                    "识别低完成组合需要平均完成率指标",
                )
            under_schema = ResultSchema(
                dimensions=dimensions,
                metrics=[
                    ResultMetric(
                        id="sample_count",
                        label="报名人数",
                        unit="count",
                        aggregation="count",
                        nullable=False,
                    ),
                    ResultMetric(
                        id="completion_rate_mean",
                        label="平均完成率",
                        unit="percentage",
                        aggregation="mean",
                        nullable=True,
                        source_field=completion.source_field,
                    ),
                ],
                grain=[item.id for item in dimensions],
                metadata={"result_kind": "underperforming"},
            )
            steps.append(
                CompiledStep(
                    "underperforming",
                    "identify_underperforming",
                    "识别高报名低完成组合",
                    {
                        "group_by": intent.dimensions,
                        "completion_field": completion.source_field,
                        "min_sample_size": 5,
                        "high_volume_quantile": 0.75,
                        "low_completion_quantile": 0.25,
                        "limit": 20,
                    },
                    under_schema,
                )
            )
            chart_sources.append("underperforming")
        steps.append(
            CompiledStep(
                "charts",
                "chart_planning",
                "根据结果元数据生成对比图",
                {"source_step_ids": chart_sources},
            )
        )
        return CompiledPlan(
            workflow="group_comparison",
            goal="比较课程运营维度并识别低表现组合",
            steps=tuple(steps),
            intent=intent,
        )
