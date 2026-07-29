from dataclasses import replace

import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.plan_compiler import (
    CompiledStep,
    PlanCompilationError,
    PlanCompiler,
    PlanValidator,
)


def dataset_record():
    return FileModel(
        id="dataset-1",
        filename="courses.xlsx",
        filepath="courses.xlsx",
        file_type="xlsx",
        row_count=4,
        col_count=8,
        columns_info=[
            {"name": "报名日期", "dtype": "datetime64[ns]"},
            {"name": "课程类别", "dtype": "object"},
            {"name": "课程难度", "dtype": "object"},
            {"name": "购买渠道", "dtype": "object"},
            {"name": "主要学习设备", "dtype": "object"},
            {"name": "实付金额", "dtype": "float64"},
            {"name": "课程完成率", "dtype": "float64"},
            {"name": "是否退款", "dtype": "bool"},
            {"name": "课程评分", "dtype": "float64"},
        ],
        profile_report="",
    )


def monthly_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "monthly_trend",
            "dimensions": ["课程类别"],
            "date_field": "报名日期",
            "metrics": [
                {
                    "semantic": "报名人数",
                    "source_field": None,
                    "aggregation": "count",
                },
                {
                    "semantic": "实付金额",
                    "source_field": "实付金额",
                    "aggregation": "sum",
                },
                {
                    "semantic": "平均完成率",
                    "source_field": "课程完成率",
                    "aggregation": "mean",
                },
            ],
            "needs_visualization": True,
        }
    )


def group_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "group_comparison",
            "dimensions": [
                "课程类别",
                "课程难度",
                "购买渠道",
                "主要学习设备",
            ],
            "metrics": [
                {
                    "semantic": "报名人数",
                    "source_field": None,
                    "aggregation": "count",
                },
                {
                    "semantic": "平均完成率",
                    "source_field": "课程完成率",
                    "aggregation": "mean",
                },
                {
                    "semantic": "退款率",
                    "source_field": "是否退款",
                    "aggregation": "rate",
                },
                {
                    "semantic": "平均评分",
                    "source_field": "课程评分",
                    "aggregation": "mean",
                },
            ],
            "needs_visualization": True,
            "include_underperforming": True,
        }
    )


def test_monthly_compiler_generates_fixed_server_owned_workflow():
    plan = PlanCompiler().compile(monthly_intent(), dataset_record())

    assert plan.workflow == "monthly_trend"
    assert [step.operation for step in plan.steps] == [
        "inspect_dataset",
        "monthly_trend",
        "calculate_trend_signals",
        "chart_planning",
    ]
    assert [step.step_id for step in plan.steps] == [
        "inspect",
        "monthly_aggregate",
        "trend_signals",
        "charts",
    ]
    assert plan.steps[-1].arguments == {
        "source_step_ids": ["monthly_aggregate"]
    }
    assert all(step.operation != "create_chart" for step in plan.steps)


def test_group_compiler_generates_aggregate_underperforming_and_charts():
    plan = PlanCompiler().compile(group_intent(), dataset_record())

    assert [step.operation for step in plan.steps] == [
        "inspect_dataset",
        "group_aggregate",
        "identify_underperforming",
        "chart_planning",
    ]
    assert plan.steps[-1].arguments == {
        "source_step_ids": ["group_aggregate", "underperforming"]
    }


def test_monthly_schema_uses_stable_ids_and_units():
    plan = PlanCompiler().compile(monthly_intent(), dataset_record())
    schema = plan.step("monthly_aggregate").output_schema

    assert [(item.id, item.label, item.role) for item in schema.dimensions] == [
        ("period", "月份", "time"),
        ("series", "课程类别", "series"),
    ]
    assert [(item.id, item.label, item.unit) for item in schema.metrics] == [
        ("enrollment_count", "报名人数", "count"),
        ("paid_amount_sum", "实付金额", "currency"),
        ("completion_rate_mean", "平均完成率", "percentage"),
    ]
    assert schema.time_granularity == "month"


def test_group_schema_uses_stable_dimension_and_metric_ids():
    plan = PlanCompiler().compile(group_intent(), dataset_record())
    schema = plan.step("group_aggregate").output_schema

    assert [item.id for item in schema.dimensions] == [
        "dimension_1",
        "dimension_2",
        "dimension_3",
        "dimension_4",
    ]
    assert [item.id for item in schema.metrics] == [
        "sample_count",
        "completion_rate_mean",
        "refund_rate",
        "rating_mean",
    ]


def test_validator_rejects_missing_fields_and_wrong_data_types():
    missing = monthly_intent().model_copy(
        update={"date_field": "不存在日期"}
    )
    with pytest.raises(PlanCompilationError) as missing_error:
        PlanCompiler().compile(missing, dataset_record())
    assert missing_error.value.code == "FIELD_NOT_FOUND"

    invalid = monthly_intent().model_copy(
        update={
            "metrics": [
                monthly_intent().metrics[0],
                monthly_intent().metrics[1].model_copy(
                    update={"source_field": "课程类别"}
                ),
            ]
        }
    )
    with pytest.raises(PlanCompilationError) as type_error:
        PlanCompiler().compile(invalid, dataset_record())
    assert type_error.value.code == "INVALID_FIELD_TYPE"


def test_validator_rejects_raw_date_as_aggregated_chart_axis_before_execution():
    plan = PlanCompiler().compile(monthly_intent(), dataset_record())
    chart_step = plan.step("charts")
    invalid_chart_step = replace(
        chart_step,
        arguments={
            "source_step_ids": ["monthly_aggregate"],
            "x_field": "报名日期",
        },
    )
    invalid_plan = replace(
        plan,
        steps=tuple(
            invalid_chart_step if step.step_id == "charts" else step
            for step in plan.steps
        ),
    )

    with pytest.raises(PlanCompilationError) as exc_info:
        PlanValidator().validate(invalid_plan, dataset_record())

    assert exc_info.value.code == "INVALID_FIELD_LINEAGE"


def test_validator_rejects_unparseable_monthly_date_values():
    frame = pd.DataFrame(
        {
            "报名日期": ["not-a-date", "still-not-a-date"],
            "课程类别": ["A", "B"],
            "实付金额": [10, 20],
            "课程完成率": [0.5, 0.6],
        }
    )
    validator = PlanValidator(dataframe_loader=lambda _path: frame)
    plan = PlanCompiler(validator=validator).compile(
        monthly_intent(),
        dataset_record(),
    )

    with pytest.raises(PlanCompilationError) as exc_info:
        validator.validate(plan, dataset_record())

    assert exc_info.value.code == "UNPARSABLE_DATE_FIELD"
