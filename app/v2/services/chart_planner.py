from dataclasses import dataclass
from typing import Literal

from app.v2.schemas.results import MetricUnit, ResultSchema
from app.v2.services.analytics import ToolExecutionResult


class ChartPlanningError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class ChartSpec:
    source_step_id: str
    chart_type: Literal["bar", "line"]
    x_field: str
    y_fields: list[str]
    color_field: str | None
    title: str
    limit: int
    unit: MetricUnit

    def arguments(self) -> dict:
        return {
            "source_step_id": self.source_step_id,
            "chart_type": self.chart_type,
            "x_field": self.x_field,
            "y_fields": self.y_fields,
            "color_field": self.color_field,
            "title": self.title,
            "limit": self.limit,
        }


class ChartPlanner:
    def plan(
        self,
        source_step_id: str,
        result: ToolExecutionResult,
    ) -> list[ChartSpec]:
        contract = result.output_contract
        if contract is None:
            raise ChartPlanningError(
                "RESULT_SCHEMA_REQUIRED",
                "图表规划需要结构化结果契约",
                {"source_step_id": source_step_id},
            )
        schema = contract.result_schema
        time_dimension = next(
            (
                item
                for item in schema.dimensions
                if item.role == "time"
            ),
            None,
        )
        category_dimension = next(
            (
                item
                for item in schema.dimensions
                if item.role == "category"
            ),
            None,
        )
        series_dimension = next(
            (
                item
                for item in schema.dimensions
                if item.role == "series"
            ),
            None,
        )
        x_dimension = time_dimension or category_dimension
        if x_dimension is None:
            raise ChartPlanningError(
                "CHART_DIMENSION_NOT_FOUND",
                "分析结果没有可用于图表横轴的维度",
                {"source_step_id": source_step_id},
            )

        metrics_by_unit: dict[MetricUnit, list] = {}
        for metric in schema.metrics:
            metrics_by_unit.setdefault(metric.unit, []).append(metric)

        chart_type: Literal["bar", "line"] = (
            "line" if time_dimension is not None else "bar"
        )
        color_field = (
            series_dimension.id
            if time_dimension is not None and series_dimension is not None
            else None
        )
        return [
            ChartSpec(
                source_step_id=source_step_id,
                chart_type=chart_type,
                x_field=x_dimension.id,
                y_fields=[item.id for item in metrics],
                color_field=color_field,
                title=self._title(schema, metrics),
                limit=50,
                unit=unit,
            )
            for unit, metrics in metrics_by_unit.items()
        ]

    @staticmethod
    def _title(schema: ResultSchema, metrics: list) -> str:
        dimension_labels = " / ".join(
            item.label
            for item in schema.dimensions
            if item.role in {"time", "category"}
        )
        metric_labels = "、".join(item.label for item in metrics)
        return f"{dimension_labels}：{metric_labels}"
