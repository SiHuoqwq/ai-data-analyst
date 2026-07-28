from pathlib import Path

import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.schemas.analysis import (
    GroupAggregateInput,
    MonthlyTrendInput,
)
from app.v2.services.analytics import (
    StructuredAnalysisTools,
    ToolExecutionError,
)


@pytest.fixture
def course_file(tmp_path) -> FileModel:
    source = tmp_path / "courses.xlsx"
    pd.DataFrame(
        [
            {
                "课程类别": "A",
                "课程难度": "入门",
                "退款": "否",
                "完成率": 0.8,
                "课程评分": 4.5,
                "实付金额": 100,
                "报名日期": "2026-01-10",
            },
            {
                "课程类别": "A",
                "课程难度": "入门",
                "退款": "是",
                "完成率": 0.4,
                "课程评分": None,
                "实付金额": 80,
                "报名日期": "2026-02-11",
            },
            {
                "课程类别": "B",
                "课程难度": "进阶",
                "退款": "否",
                "完成率": 0.9,
                "课程评分": 4.8,
                "实付金额": 200,
                "报名日期": "2026-01-12",
            },
            {
                "课程类别": "B",
                "课程难度": "进阶",
                "退款": "否",
                "完成率": 0.7,
                "课程评分": 4.2,
                "实付金额": 220,
                "报名日期": "2026-02-14",
            },
        ]
    ).to_excel(source, index=False)
    return FileModel(
        id="course-file",
        filename="courses.xlsx",
        filepath=str(source),
        file_type="xlsx",
        row_count=4,
        col_count=7,
        columns_info=[],
        profile_report="",
    )


def table_rows(result):
    table = next(
        draft for draft in result.drafts if draft.artifact_type == "table"
    )
    return table.payload["rows"]


def test_tool_schemas_reject_unknown_or_unsafe_parameters():
    with pytest.raises(ValueError):
        GroupAggregateInput.model_validate(
            {
                "group_by": ["课程类别"],
                "metrics": [
                    {
                        "field": None,
                        "aggregation": "count",
                        "alias": "报名人数",
                    }
                ],
                "filters": [],
                "sort": [],
                "limit": 20,
                "python_code": "open('.env').read()",
            }
        )


def test_inspect_dataset_classifies_chinese_fields(course_file):
    result = StructuredAnalysisTools().execute(
        "inspect_dataset", {}, course_file, {}
    )

    assert result.status == "success"
    assert result.summary["row_count"] == 4
    assert "实付金额" in result.summary["numeric_fields"]
    assert "课程类别" in result.summary["categorical_fields"]
    assert "报名日期" in result.summary["date_fields"]
    assert {draft.artifact_type for draft in result.drafts} == {
        "text",
        "metric",
    }


def test_group_aggregate_computes_count_sum_mean_and_boolean_rate(course_file):
    result = StructuredAnalysisTools().execute(
        "group_aggregate",
        {
            "group_by": ["课程类别"],
            "metrics": [
                {"field": None, "aggregation": "count", "alias": "报名人数"},
                {"field": "实付金额", "aggregation": "sum", "alias": "实付金额"},
                {"field": "完成率", "aggregation": "mean", "alias": "平均完成率"},
                {"field": "退款", "aggregation": "rate", "alias": "退款率"},
                {"field": "课程评分", "aggregation": "mean", "alias": "平均评分"},
            ],
            "filters": [],
            "sort": [{"field": "课程类别", "direction": "asc"}],
            "limit": 20,
        },
        course_file,
        {},
    )

    assert result.status == "success"
    assert table_rows(result) == [
        {
            "课程类别": "A",
            "报名人数": 2,
            "实付金额": 180.0,
            "平均完成率": 0.6,
            "退款率": 0.5,
            "平均评分": 4.5,
        },
        {
            "课程类别": "B",
            "报名人数": 2,
            "实付金额": 420.0,
            "平均完成率": 0.8,
            "退款率": 0.0,
            "平均评分": 4.5,
        },
    ]


def test_group_aggregate_returns_structured_field_suggestions(course_file):
    with pytest.raises(ToolExecutionError) as raised:
        StructuredAnalysisTools().execute(
            "group_aggregate",
            {
                "group_by": ["不存在字段"],
                "metrics": [
                    {
                        "field": None,
                        "aggregation": "count",
                        "alias": "报名人数",
                    }
                ],
                "filters": [],
                "sort": [],
                "limit": 20,
            },
            course_file,
            {},
        )

    assert raised.value.code == "SCHEMA_FIELD_NOT_FOUND"
    assert "课程类别" in raised.value.details["available_fields"]
    assert str(course_file.filepath) not in raised.value.message


def test_group_aggregate_parses_percent_and_currency_strings(tmp_path):
    source = tmp_path / "formatted.xlsx"
    pd.DataFrame(
        [
            {"类别": "A", "完成率": "75%", "金额": "￥1,200"},
            {"类别": "A", "完成率": "50%", "金额": "800元"},
        ]
    ).to_excel(source, index=False)
    record = FileModel(
        id="formatted",
        filename="formatted.xlsx",
        filepath=str(source),
        file_type="xlsx",
        row_count=2,
        col_count=3,
        columns_info=[],
        profile_report="",
    )

    result = StructuredAnalysisTools().execute(
        "group_aggregate",
        {
            "group_by": ["类别"],
            "metrics": [
                {"field": "完成率", "aggregation": "mean", "alias": "平均完成率"},
                {"field": "金额", "aggregation": "sum", "alias": "实付金额"},
            ],
            "filters": [],
            "sort": [],
            "limit": 20,
        },
        record,
        {},
    )

    assert table_rows(result) == [
        {"类别": "A", "平均完成率": 0.625, "实付金额": 2000.0}
    ]


def test_monthly_trend_is_chronological_and_keeps_category_series(course_file):
    result = StructuredAnalysisTools().execute(
        "monthly_trend",
        {
            "date_field": "报名日期",
            "category_field": "课程类别",
            "metrics": [
                {"field": None, "aggregation": "count", "alias": "报名人数"},
                {"field": "实付金额", "aggregation": "sum", "alias": "实付金额"},
                {"field": "完成率", "aggregation": "mean", "alias": "平均完成率"},
            ],
            "filters": [],
            "limit": 100,
        },
        course_file,
        {},
    )

    assert MonthlyTrendInput.model_validate(result.validated_input)
    assert result.summary["trend_signals"] == {
        "primary_metric": "报名人数",
        "fastest_growth": {"category": "A", "change_rate": 0.0},
        "largest_decline": {"category": "A", "change_rate": 0.0},
        "most_volatile": {"category": "A", "change_rate_stddev": 0.0},
    }
    assert table_rows(result) == [
        {
            "月份": "2026-01",
            "课程类别": "A",
            "报名人数": 1,
            "实付金额": 100.0,
            "平均完成率": 0.8,
        },
        {
            "月份": "2026-01",
            "课程类别": "B",
            "报名人数": 1,
            "实付金额": 200.0,
            "平均完成率": 0.9,
        },
        {
            "月份": "2026-02",
            "课程类别": "A",
            "报名人数": 1,
            "实付金额": 80.0,
            "平均完成率": 0.4,
        },
        {
            "月份": "2026-02",
            "课程类别": "B",
            "报名人数": 1,
            "实付金额": 220.0,
            "平均完成率": 0.7,
        },
    ]


def test_monthly_trend_signals_use_full_result_before_preview_limit(course_file):
    result = StructuredAnalysisTools().execute(
        "monthly_trend",
        {
            "date_field": "报名日期",
            "category_field": "课程类别",
            "metrics": [
                {"field": "实付金额", "aggregation": "sum", "alias": "实付金额"}
            ],
            "filters": [],
            "limit": 2,
        },
        course_file,
        {},
    )

    assert len(table_rows(result)) == 2
    assert result.truncated is True
    assert result.summary["trend_signals"] == {
        "primary_metric": "实付金额",
        "fastest_growth": {"category": "B", "change_rate": 0.1},
        "largest_decline": {"category": "A", "change_rate": -0.2},
        "most_volatile": {"category": "A", "change_rate_stddev": 0.0},
    }


def test_underperforming_combinations_records_deterministic_rule(course_file):
    result = StructuredAnalysisTools().execute(
        "identify_underperforming",
        {
            "group_by": ["课程类别", "课程难度"],
            "completion_field": "完成率",
            "min_sample_size": 2,
            "high_volume_quantile": 0.5,
            "low_completion_quantile": 0.5,
            "limit": 20,
        },
        course_file,
        {},
    )

    assert result.summary["rule"]["min_sample_size"] == 2
    assert result.summary["rule"]["high_volume_quantile"] == 0.5
    assert result.summary["rule"]["low_completion_quantile"] == 0.5
    assert table_rows(result)[0]["课程类别"] == "A"


@pytest.mark.parametrize(
    ("chart_type", "source_step_id"),
    [("bar", "group-step"), ("line", "trend-step")],
)
def test_chart_tool_generates_managed_static_png(
    course_file, tmp_path, monkeypatch, chart_type, source_step_id
):
    from app.config import settings

    monkeypatch.setattr(settings, "chart_dir", str(tmp_path / "charts"))
    Path(settings.chart_dir).mkdir()
    tools = StructuredAnalysisTools()
    operation = "group_aggregate" if chart_type == "bar" else "monthly_trend"
    arguments = (
        {
            "group_by": ["课程类别"],
            "metrics": [
                {"field": None, "aggregation": "count", "alias": "报名人数"}
            ],
            "filters": [],
            "sort": [],
            "limit": 20,
        }
        if chart_type == "bar"
        else {
            "date_field": "报名日期",
            "category_field": "课程类别",
            "metrics": [
                {"field": None, "aggregation": "count", "alias": "报名人数"}
            ],
            "filters": [],
            "limit": 100,
        }
    )
    source = tools.execute(operation, arguments, course_file, {})

    result = tools.execute(
        "create_chart",
        {
            "source_step_id": source_step_id,
            "chart_type": chart_type,
            "x_field": "课程类别" if chart_type == "bar" else "月份",
            "y_fields": ["报名人数"],
            "color_field": None if chart_type == "bar" else "课程类别",
            "title": "匿名课程趋势",
            "limit": 20,
        },
        course_file,
        {source_step_id: source},
    )

    chart = result.drafts[0]
    assert chart.artifact_type == "chart"
    assert chart.chart_type == chart_type
    assert Path(chart.chart_filepath).is_file()
    assert Path(chart.chart_filepath).parent == Path(settings.chart_dir)
