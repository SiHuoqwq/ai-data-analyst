from dataclasses import replace

import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.plan_compiler import (
    PlanCompilationError,
    PlanCompiler,
    PlanValidator,
)


def dataset_record():
    return FileModel(
        id="dataset-1",
        filename="real-estate.xlsx",
        filepath="real-estate.xlsx",
        file_type="xlsx",
        row_count=4,
        col_count=13,
        columns_info=[
            {"name": "项目", "dtype": "object"},
            {"name": "城市", "dtype": "object"},
            {"name": "区域", "dtype": "object"},
            {"name": "置业顾问", "dtype": "object"},
            {"name": "获客渠道", "dtype": "object"},
            {"name": "户型", "dtype": "object"},
            {"name": "客户等级", "dtype": "object"},
            {"name": "线索日期", "dtype": "datetime64[ns]"},
            {"name": "到访日期", "dtype": "datetime64[ns]"},
            {"name": "认购日期", "dtype": "datetime64[ns]"},
            {"name": "签约日期", "dtype": "datetime64[ns]"},
            {"name": "成交金额", "dtype": "float64"},
            {"name": "回款金额", "dtype": "float64"},
        ],
        profile_report="",
    )


def monthly_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "monthly_trend",
            "dimensions": ["获客渠道"],
            "date_field": "签约日期",
            "metrics": [
                {
                    "semantic": "线索数",
                    "source_field": None,
                    "aggregation": "count",
                },
                {
                    "semantic": "成交金额",
                    "source_field": "成交金额",
                    "aggregation": "sum",
                },
                {
                    "semantic": "回款金额",
                    "source_field": "回款金额",
                    "aggregation": "sum",
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
                "项目",
                "城市",
                "区域",
                "获客渠道",
            ],
            "metrics": [
                {
                    "semantic": "线索数",
                    "source_field": None,
                    "aggregation": "count",
                },
                {
                    "semantic": "成交金额",
                    "source_field": "成交金额",
                    "aggregation": "sum",
                },
                {
                    "semantic": "回款金额",
                    "source_field": "回款金额",
                    "aggregation": "sum",
                },
                {
                    "semantic": "平均成交金额",
                    "source_field": None,
                    "aggregation": "ratio",
                },
            ],
            "needs_visualization": True,
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


def test_group_compiler_generates_aggregate_and_charts():
    plan = PlanCompiler().compile(group_intent(), dataset_record())

    assert [step.operation for step in plan.steps] == [
        "inspect_dataset",
        "group_aggregate",
        "chart_planning",
    ]
    assert plan.steps[-1].arguments == {
        "source_step_ids": ["group_aggregate"]
    }


def test_group_compiler_includes_underperforming_step():
    intent = group_intent().model_copy(
        update={"include_underperforming": True}
    )

    plan = PlanCompiler().compile(intent, dataset_record())

    assert [step.operation for step in plan.steps] == [
        "inspect_dataset",
        "group_aggregate",
        "identify_underperforming",
        "chart_planning",
    ]
    underperforming = plan.step("underperforming")
    assert underperforming.arguments["conversion_field"] == "签约日期"
    assert underperforming.arguments["group_by"] == [
        "项目",
        "城市",
        "区域",
        "获客渠道",
    ]
    assert [item.id for item in underperforming.output_schema.metrics] == [
        "lead_count",
        "deal_count",
        "deal_rate",
    ]


def test_monthly_schema_uses_stable_ids_and_units():
    plan = PlanCompiler().compile(monthly_intent(), dataset_record())
    schema = plan.step("monthly_aggregate").output_schema

    assert [(item.id, item.label, item.role) for item in schema.dimensions] == [
        ("period", "月份", "time"),
        ("series", "获客渠道", "series"),
    ]
    assert [(item.id, item.label, item.unit) for item in schema.metrics] == [
        ("lead_count", "线索数", "count"),
        ("deal_amount_sum", "成交金额", "currency"),
        ("payment_amount_sum", "回款金额", "currency"),
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
        "lead_count",
        "deal_amount_sum",
        "payment_amount_sum",
        "avg_deal_amount",
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
                    update={"source_field": "获客渠道"}
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
            "x_field": "签约日期",
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
            "签约日期": ["not-a-date", "still-not-a-date"],
            "获客渠道": ["自然到访", "渠道分销"],
            "成交金额": [1000000, 2000000],
            "回款金额": [500000, 1200000],
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
