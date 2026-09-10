import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.analytics import StructuredAnalysisTools
from app.v2.services.plan_compiler import PlanCompiler


@pytest.fixture
def real_estate_file(tmp_path):
    source = tmp_path / "real-estate.xlsx"
    pd.DataFrame(
        [
            {
                "项目": "云顶壹号",
                "获客渠道": "自然到访",
                "签约日期": "2026-01-15",
                "成交金额": 1000000,
                "回款金额": 500000,
            },
            {
                "项目": "滨江府",
                "获客渠道": "自然到访",
                "签约日期": "2026-02-20",
                "成交金额": 2000000,
                "回款金额": 1200000,
            },
        ]
    ).to_excel(source, index=False)
    return FileModel(
        id="dataset-1",
        filename="real-estate.xlsx",
        filepath=str(source),
        file_type="xlsx",
        row_count=2,
        col_count=5,
        columns_info=[
            {"name": "项目", "dtype": "object"},
            {"name": "获客渠道", "dtype": "object"},
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
        }
    )


def test_monthly_tool_returns_stable_contract_and_separate_preview(
    real_estate_file,
):
    step = PlanCompiler().compile(
        monthly_intent(),
        real_estate_file,
    ).step("monthly_aggregate")

    result = StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        real_estate_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    assert list(result.dataframe.columns) == [
        "period",
        "series",
        "lead_count",
        "deal_amount_sum",
        "payment_amount_sum",
    ]
    assert result.output_contract.source_tool == "monthly_trend"
    assert result.output_contract.source_step_id == "monthly_aggregate"
    assert result.output_contract.full_row_count == 2
    assert result.output_contract.preview_row_count == 2
    assert result.output_contract.result_schema.dimensions[0].role == "time"
    table = result.drafts[0].payload
    assert [column["key"] for column in table["columns"]] == [
        "period",
        "series",
        "lead_count",
        "deal_amount_sum",
        "payment_amount_sum",
    ]
    assert [column["label"] for column in table["columns"]] == [
        "月份",
        "获客渠道",
        "线索数",
        "成交金额",
        "回款金额",
    ]


def test_monthly_trend_signals_use_stable_metric_ids(real_estate_file):
    step = PlanCompiler().compile(
        monthly_intent(),
        real_estate_file,
    ).step("monthly_aggregate")

    result = StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        real_estate_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    assert set(result.summary["trend_signals"]["by_metric"]) == {
        "lead_count",
        "deal_amount_sum",
        "payment_amount_sum",
    }
    assert result.summary["metric_labels"] == {
        "lead_count": "线索数",
        "deal_amount_sum": "成交金额",
        "payment_amount_sum": "回款金额",
    }


def test_group_contract_keeps_full_result_separate_from_artifact_preview(
    real_estate_file,
):
    intent = AnalysisIntent.model_validate(
        {
            "analysis_type": "group_comparison",
            "dimensions": ["项目"],
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
            ],
        }
    )
    step = PlanCompiler().compile(
        intent,
        real_estate_file,
    ).step("group_aggregate")
    arguments = {**step.arguments, "limit": 1}

    result = StructuredAnalysisTools().execute(
        step.operation,
        arguments,
        real_estate_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    assert list(result.dataframe.columns) == [
        "dimension_1",
        "lead_count",
        "deal_amount_sum",
    ]
    assert len(result.dataframe) == 2
    assert result.output_contract.full_row_count == 2
    assert result.output_contract.preview_row_count == 1
    assert len(result.output_contract.rows) == 2
    assert len(result.drafts[0].payload["rows"]) == 1
    assert result.truncated is True
