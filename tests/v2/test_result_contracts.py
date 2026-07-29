import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.analytics import StructuredAnalysisTools
from app.v2.services.plan_compiler import PlanCompiler


@pytest.fixture
def course_file(tmp_path):
    source = tmp_path / "courses.xlsx"
    pd.DataFrame(
        [
            {
                "课程类别": "AI 应用",
                "课程难度": "入门",
                "购买渠道": "官网",
                "主要学习设备": "Windows",
                "实付金额": 100,
                "课程完成率": 0.5,
                "是否退款": False,
                "课程评分": 4.5,
                "报名日期": "2026-01-10",
            },
            {
                "课程类别": "AI 应用",
                "课程难度": "进阶",
                "购买渠道": "短视频",
                "主要学习设备": "Android",
                "实付金额": 200,
                "课程完成率": 0.8,
                "是否退款": True,
                "课程评分": 4.0,
                "报名日期": "2026-02-10",
            },
        ]
    ).to_excel(source, index=False)
    return FileModel(
        id="dataset-1",
        filename="courses.xlsx",
        filepath=str(source),
        file_type="xlsx",
        row_count=2,
        col_count=9,
        columns_info=[
            {"name": "课程类别", "dtype": "object"},
            {"name": "课程难度", "dtype": "object"},
            {"name": "购买渠道", "dtype": "object"},
            {"name": "主要学习设备", "dtype": "object"},
            {"name": "实付金额", "dtype": "float64"},
            {"name": "课程完成率", "dtype": "float64"},
            {"name": "是否退款", "dtype": "bool"},
            {"name": "课程评分", "dtype": "float64"},
            {"name": "报名日期", "dtype": "datetime64[ns]"},
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
        }
    )


def test_monthly_tool_returns_stable_contract_and_separate_preview(course_file):
    step = PlanCompiler().compile(
        monthly_intent(),
        course_file,
    ).step("monthly_aggregate")

    result = StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        course_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    assert list(result.dataframe.columns) == [
        "period",
        "series",
        "enrollment_count",
        "paid_amount_sum",
        "completion_rate_mean",
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
        "enrollment_count",
        "paid_amount_sum",
        "completion_rate_mean",
    ]
    assert [column["label"] for column in table["columns"]] == [
        "月份",
        "课程类别",
        "报名人数",
        "实付金额",
        "平均完成率",
    ]


def test_monthly_trend_signals_use_stable_metric_ids(course_file):
    step = PlanCompiler().compile(
        monthly_intent(),
        course_file,
    ).step("monthly_aggregate")

    result = StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        course_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    assert set(result.summary["trend_signals"]["by_metric"]) == {
        "enrollment_count",
        "paid_amount_sum",
        "completion_rate_mean",
    }
    assert result.summary["metric_labels"] == {
        "enrollment_count": "报名人数",
        "paid_amount_sum": "实付金额",
        "completion_rate_mean": "平均完成率",
    }


def test_group_contract_keeps_full_result_separate_from_artifact_preview(
    course_file,
):
    intent = AnalysisIntent.model_validate(
        {
            "analysis_type": "group_comparison",
            "dimensions": ["课程难度"],
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
            ],
        }
    )
    step = PlanCompiler().compile(
        intent,
        course_file,
    ).step("group_aggregate")
    arguments = {**step.arguments, "limit": 1}

    result = StructuredAnalysisTools().execute(
        step.operation,
        arguments,
        course_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    assert list(result.dataframe.columns) == [
        "dimension_1",
        "sample_count",
        "completion_rate_mean",
    ]
    assert len(result.dataframe) == 2
    assert result.output_contract.full_row_count == 2
    assert result.output_contract.preview_row_count == 1
    assert len(result.output_contract.rows) == 2
    assert len(result.drafts[0].payload["rows"]) == 1
    assert result.truncated is True
