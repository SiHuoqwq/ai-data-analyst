import pandas as pd
import pytest

from app.v2.schemas.results import (
    ResultDimension,
    ResultMetric,
    ResultSchema,
    ToolOutputContract,
)
from app.v2.services.analytics import ToolExecutionResult
from app.v2.services.chart_planner import (
    ChartPlanningError,
    ChartPlanner,
    ChartSpec,
)


def _result(schema: ResultSchema, row_count: int = 2) -> ToolExecutionResult:
    rows = [
        {
            dimension.id: "2026-01" if dimension.role == "time" else "AI 应用"
            for dimension in schema.dimensions
        }
        for _ in range(row_count)
    ]
    for row in rows:
        for metric in schema.metrics:
            row[metric.id] = 1
    frame = pd.DataFrame(rows)
    return ToolExecutionResult(
        status="success",
        summary={},
        preview=rows,
        row_count=len(rows),
        truncated=False,
        warnings=[],
        drafts=[],
        validated_input={},
        dataframe=frame,
        output_contract=ToolOutputContract(
            schema=schema,
            rows=rows,
            full_row_count=len(rows),
            preview_row_count=len(rows),
            source_tool="monthly_trend",
            source_step_id="monthly_aggregate",
        ),
    )


def _metric(metric_id: str, label: str, unit: str):
    aggregation = {
        "count": "count",
        "currency": "sum",
        "percentage": "mean",
        "score": "mean",
    }[unit]
    return ResultMetric(
        id=metric_id,
        label=label,
        unit=unit,
        aggregation=aggregation,
        nullable=unit != "count",
    )


def test_monthly_planner_uses_period_and_creates_three_unit_safe_charts():
    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id="period",
                label="月份",
                role="time",
                data_type="date",
                source_field="报名日期",
            ),
            ResultDimension(
                id="series",
                label="课程类别",
                role="series",
                data_type="string",
                source_field="课程类别",
            ),
        ],
        metrics=[
            _metric("enrollment_count", "报名人数", "count"),
            _metric("paid_amount_sum", "实付金额", "currency"),
            _metric("completion_rate_mean", "平均完成率", "percentage"),
        ],
        grain=["period", "series"],
        time_granularity="month",
    )

    specs = ChartPlanner().plan("monthly_aggregate", _result(schema))

    assert len(specs) == 3
    assert {item.unit for item in specs} == {
        "count",
        "currency",
        "percentage",
    }
    assert all(item.chart_type == "line" for item in specs)
    assert all(item.x_field == "period" for item in specs)
    assert all(item.color_field == "series" for item in specs)
    assert all(item.source_step_id == "monthly_aggregate" for item in specs)
    assert "报名日期" not in {
        item.x_field for item in specs
    }
    assert {tuple(item.y_fields) for item in specs} == {
        ("enrollment_count",),
        ("paid_amount_sum",),
        ("completion_rate_mean",),
    }


def test_monthly_planner_keeps_the_complete_supported_time_range():
    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id="period",
                label="月份",
                role="time",
                data_type="date",
                source_field="报名日期",
            ),
            ResultDimension(
                id="series",
                label="课程类别",
                role="series",
                data_type="string",
                source_field="课程类别",
            ),
        ],
        metrics=[_metric("enrollment_count", "报名人数", "count")],
        grain=["period", "series"],
        time_granularity="month",
    )

    specs = ChartPlanner().plan(
        "monthly_aggregate",
        _result(schema, row_count=90),
    )

    assert specs[0].limit == 90
    assert specs[0].orientation == "vertical"
    assert specs[0].priority_source_step_id is None


def test_chart_spec_preserves_existing_keyword_constructor_defaults():
    spec = ChartSpec(
        source_step_id="aggregate",
        chart_type="bar",
        x_field="dimension_1",
        y_fields=["sample_count"],
        color_field=None,
        title="课程组合",
        limit=20,
        unit="count",
    )

    assert spec.orientation == "vertical"
    assert spec.priority_source_step_id is None
    assert spec.arguments() == {
        "source_step_id": "aggregate",
        "priority_source_step_id": None,
        "chart_type": "bar",
        "orientation": "vertical",
        "x_field": "dimension_1",
        "y_fields": ["sample_count"],
        "color_field": None,
        "title": "课程组合",
        "limit": 20,
    }

def test_group_planner_groups_percentages_but_separates_other_units():
    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id="dimension_1",
                label="课程类别",
                role="category",
                data_type="string",
                source_field="课程类别",
            )
        ],
        metrics=[
            _metric("sample_count", "报名人数", "count"),
            _metric("completion_rate_mean", "平均完成率", "percentage"),
            _metric("refund_rate", "退款率", "percentage"),
            _metric("rating_mean", "平均评分", "score"),
        ],
        grain=["dimension_1"],
    )

    specs = ChartPlanner().plan(
        "group_aggregate",
        _result(schema, row_count=20),
        priority_source_step_id="underperforming",
    )

    assert len(specs) == 3
    by_unit = {item.unit: item for item in specs}
    assert by_unit["percentage"].y_fields == [
        "completion_rate_mean",
        "refund_rate",
    ]
    assert by_unit["count"].y_fields == ["sample_count"]
    assert by_unit["score"].y_fields == ["rating_mean"]
    assert all(item.chart_type == "bar" for item in specs)
    assert all(item.x_field == "dimension_1" for item in specs)
    assert all(item.color_field is None for item in specs)
    assert all(item.orientation == "horizontal" for item in specs)
    assert all(item.limit == 10 for item in specs)
    assert all(item.title == "重点 Top 10" for item in specs)
    assert all(
        item.priority_source_step_id == "underperforming" for item in specs
    )


def test_group_planner_keeps_all_rows_when_fewer_than_top_ten():
    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id="dimension_1",
                label="课程类别",
                role="category",
                data_type="string",
                source_field="课程类别",
            ),
            ResultDimension(
                id="dimension_2",
                label="课程难度",
                role="category",
                data_type="string",
                source_field="课程难度",
            ),
        ],
        metrics=[_metric("sample_count", "报名人数", "count")],
        grain=["dimension_1", "dimension_2"],
    )

    specs = ChartPlanner().plan(
        "group_aggregate", _result(schema, row_count=3)
    )

    assert specs[0].orientation == "horizontal"
    assert specs[0].limit == 3


def test_planner_rejects_missing_output_contract():
    result = ToolExecutionResult(
        "success",
        {},
        [],
        0,
        False,
        [],
        [],
        {},
        pd.DataFrame(),
    )

    with pytest.raises(ChartPlanningError) as error:
        ChartPlanner().plan("source", result)

    assert error.value.code == "RESULT_SCHEMA_REQUIRED"


def test_planner_rejects_schema_without_renderable_dimension():
    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id="series",
                label="课程类别",
                role="series",
                data_type="string",
                source_field="课程类别",
            )
        ],
        metrics=[_metric("sample_count", "报名人数", "count")],
        grain=["series"],
    )

    with pytest.raises(ChartPlanningError) as error:
        ChartPlanner().plan("source", _result(schema))

    assert error.value.code == "CHART_DIMENSION_NOT_FOUND"
