from pathlib import Path

import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.schemas.analysis import (
    GroupAggregateInput,
    MonthlyTrendInput,
)
from app.v2.schemas.results import (
    ResultDimension,
    ResultMetric,
    ResultSchema,
    ToolOutputContract,
)
from app.v2.services.analytics import (
    StructuredAnalysisTools,
    ToolExecutionError,
    ToolExecutionResult,
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


def test_group_aggregate_computes_count_sum_mean_and_field_count(course_file):
    result = StructuredAnalysisTools().execute(
        "group_aggregate",
        {
            "group_by": ["课程类别"],
            "metrics": [
                {"field": None, "aggregation": "count", "alias": "报名人数"},
                {"field": "实付金额", "aggregation": "sum", "alias": "实付金额"},
                {"field": "完成率", "aggregation": "mean", "alias": "平均完成率"},
                {"field": "课程评分", "aggregation": "count", "alias": "评分记录数"},
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
            "评分记录数": 1,
            "平均评分": 4.5,
        },
        {
            "课程类别": "B",
            "报名人数": 2,
            "实付金额": 420.0,
            "平均完成率": 0.8,
            "评分记录数": 2,
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
        "by_metric": {
            "报名人数": {
                "fastest_growth": {"category": "A", "change_rate": 0.0},
                "largest_decline": {"category": "A", "change_rate": 0.0},
                "most_volatile": {
                    "category": "A",
                    "change_rate_stddev": 0.0,
                },
            },
            "实付金额": {
                "fastest_growth": {"category": "B", "change_rate": 0.1},
                "largest_decline": {"category": "A", "change_rate": -0.2},
                "most_volatile": {
                    "category": "A",
                    "change_rate_stddev": 0.0,
                },
            },
            "平均完成率": {
                "fastest_growth": {
                    "category": "B",
                    "change_rate": -0.222222,
                },
                "largest_decline": {
                    "category": "A",
                    "change_rate": -0.5,
                },
                "most_volatile": {
                    "category": "A",
                    "change_rate_stddev": 0.0,
                },
            },
        },
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
    assert len(result.dataframe) == 4
    assert result.truncated is True
    assert result.summary["trend_signals"] == {
        "primary_metric": "实付金额",
        "fastest_growth": {"category": "B", "change_rate": 0.1},
        "largest_decline": {"category": "A", "change_rate": -0.2},
        "most_volatile": {"category": "A", "change_rate_stddev": 0.0},
        "by_metric": {
            "实付金额": {
                "fastest_growth": {"category": "B", "change_rate": 0.1},
                "largest_decline": {"category": "A", "change_rate": -0.2},
                "most_volatile": {
                    "category": "A",
                    "change_rate_stddev": 0.0,
                },
            }
        },
    }
    assert result.summary["trend_signals"]["by_metric"]["实付金额"] == {
        "fastest_growth": {"category": "B", "change_rate": 0.1},
        "largest_decline": {"category": "A", "change_rate": -0.2},
        "most_volatile": {"category": "A", "change_rate_stddev": 0.0},
    }


def test_monthly_trend_fills_missing_month_category_combinations(tmp_path):
    source = tmp_path / "monthly-gaps.xlsx"
    pd.DataFrame(
        [
            {"报名日期": "2026-01-05", "课程类别": "A", "实付金额": 10, "完成率": 0.8},
            {"报名日期": "2026-01-06", "课程类别": "B", "实付金额": 20, "完成率": 0.6},
            {"报名日期": "2026-02-05", "课程类别": "A", "实付金额": 11, "完成率": 0.7},
            {"报名日期": "2026-03-05", "课程类别": "A", "实付金额": 12, "完成率": 0.9},
            {"报名日期": "2026-03-06", "课程类别": "B", "实付金额": 22, "完成率": 0.5},
        ]
    ).to_excel(source, index=False)
    record = FileModel(
        id="monthly-gaps",
        filename=source.name,
        filepath=str(source),
        file_type="xlsx",
        row_count=5,
        col_count=4,
        columns_info=[],
        profile_report="",
    )

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
        record,
        {},
    )

    assert len(result.dataframe) == 6
    missing = result.dataframe[
        (result.dataframe["月份"] == "2026-02")
        & (result.dataframe["课程类别"] == "B")
    ].iloc[0]
    assert missing["报名人数"] == 0
    assert missing["实付金额"] == 0
    assert pd.isna(missing["平均完成率"])
    assert result.summary["trend_signals"]["most_volatile"] == {
        "category": "B",
        "change_rate_stddev": 0.707107,
    }


def test_underperforming_combinations_records_deterministic_rule(course_file):
    result = StructuredAnalysisTools().execute(
        "identify_underperforming",
        {
            "group_by": ["课程类别", "课程难度"],
            "conversion_field": "课程评分",
            "min_sample_size": 2,
            "high_volume_quantile": 0.5,
            "low_conversion_quantile": 0.5,
            "limit": 20,
        },
        course_file,
        {},
    )

    assert result.summary["rule"]["min_sample_size"] == 2
    assert result.summary["rule"]["high_volume_quantile"] == 0.5
    assert result.summary["rule"]["low_conversion_quantile"] == 0.5
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


def test_chart_splits_mixed_units_and_keeps_multidimensional_labels(
    course_file, tmp_path, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "chart_dir", str(tmp_path / "charts"))
    tools = StructuredAnalysisTools()
    source = tools.execute(
        "group_aggregate",
        {
            "group_by": ["课程类别", "课程难度"],
            "metrics": [
                {"field": None, "aggregation": "count", "alias": "报名人数"},
                {
                    "field": "完成率",
                    "aggregation": "mean",
                    "alias": "平均完成率",
                },
                {
                    "field": "实付金额",
                    "aggregation": "mean",
                    "alias": "平均实付金额",
                },
            ],
            "filters": [],
            "sort": [],
            "limit": 20,
        },
        course_file,
        {},
    )

    result = tools.execute(
        "create_chart",
        {
            "source_step_id": "aggregate",
            "chart_type": "bar",
            "x_field": "课程类别",
            "y_fields": ["报名人数", "平均完成率", "平均实付金额"],
            "color_field": None,
            "title": "课程组合表现",
            "limit": 20,
        },
        course_file,
        {"aggregate": source},
    )

    assert len(result.drafts) == 3
    assert result.summary["unit_groups"] == {
        "count": ["报名人数"],
        "percentage": ["平均完成率"],
        "currency": ["平均实付金额"],
    }
    assert all(Path(item.chart_filepath).is_file() for item in result.drafts)
    assert all(" / " in item.alt_text for item in result.drafts)


def test_horizontal_chart_prioritizes_underperforming_groups_without_mutating_source(
    course_file, tmp_path, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "chart_dir", str(tmp_path / "charts"))
    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id=f"dimension_{index}",
                label=label,
                role="category",
                data_type="string",
                source_field=label,
            )
            for index, label in enumerate(
                ["课程类别", "课程难度", "购买渠道", "主要学习设备"], start=1
            )
        ],
        metrics=[
            ResultMetric(
                id="enrollment_count",
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
            ),
        ],
        grain=["dimension_1", "dimension_2", "dimension_3", "dimension_4"],
    )
    rows = [
        {
            "dimension_1": f"类别 {index}",
            "dimension_2": f"难度 {index}",
            "dimension_3": f"渠道 {index}",
            "dimension_4": f"设备 {index}",
            "enrollment_count": 12 - index,
            "completion_rate_mean": 0.5,
        }
        for index in range(12)
    ]
    source_frame = pd.DataFrame(rows)
    source_before = source_frame.copy(deep=True)
    source = ToolExecutionResult(
        "success", {}, rows, len(rows), False, [], [], {}, source_frame,
        ToolOutputContract(
            schema=schema,
            rows=rows,
            full_row_count=len(rows),
            preview_row_count=len(rows),
            source_tool="group_aggregate",
            source_step_id="aggregate",
        ),
    )
    priority_rows = [rows[11], rows[7]]
    priority = ToolExecutionResult(
        "success", {}, priority_rows, len(priority_rows), False, [], [], {},
        pd.DataFrame(priority_rows),
        ToolOutputContract(
            schema=schema,
            rows=priority_rows,
            full_row_count=len(priority_rows),
            preview_row_count=len(priority_rows),
            source_tool="identify_underperforming",
            source_step_id="underperforming",
        ),
    )

    result = StructuredAnalysisTools().execute(
        "create_chart",
        {
            "source_step_id": "aggregate",
            "priority_source_step_id": "underperforming",
            "chart_type": "bar",
            "orientation": "horizontal",
            "x_field": "dimension_1",
            "y_fields": ["enrollment_count", "completion_rate_mean"],
            "color_field": None,
            "title": "重点 Top 10",
            "limit": 10,
        },
        course_file,
        {"aggregate": source, "underperforming": priority},
    )

    assert result.summary["plotted_rows"] == 10
    assert len(result.drafts) == 2
    assert source.dataframe.equals(source_before)
    for chart in result.drafts:
        assert Path(chart.chart_filepath).is_file()
        assert chart.alt_text.index(
            "类别 11 / 难度 11 / 渠道 11 / 设备 11"
        ) < chart.alt_text.index("类别 0 / 难度 0 / 渠道 0 / 设备 0")


def test_chart_alt_text_is_bounded_for_many_multidimensional_groups(
    tmp_path, monkeypatch
):
    from app.config import settings

    source_path = tmp_path / "many-groups.xlsx"
    rows = [
        {
            "课程类别": f"人工智能应用与行业实践课程类别{i:02d}",
            "课程难度": "高级综合实践",
            "购买渠道": "短视频内容营销推广渠道",
            "主要学习设备": "Android 平板与移动设备",
            "课程完成率": 0.3 + i / 100,
            "是否退款": i % 2 == 0,
            "课程评分": 4 + i / 100,
        }
        for i in range(20)
    ]
    pd.DataFrame(rows).to_excel(source_path, index=False)
    file_model = FileModel(
        id="many-groups",
        filename="many-groups.xlsx",
        filepath=str(source_path),
        file_type="xlsx",
        row_count=20,
        col_count=7,
        columns_info=[],
        profile_report="",
    )
    monkeypatch.setattr(settings, "chart_dir", str(tmp_path / "charts"))
    tools = StructuredAnalysisTools()
    source = tools.execute(
        "group_aggregate",
        {
            "group_by": [
                "课程类别",
                "课程难度",
                "购买渠道",
                "主要学习设备",
            ],
            "metrics": [
                {
                    "field": "课程完成率",
                    "aggregation": "mean",
                    "alias": "平均完成率",
                },
                {
                    "field": "课程评分",
                    "aggregation": "mean",
                    "alias": "平均课程评分",
                },
            ],
            "filters": [],
            "sort": [],
            "limit": 100,
        },
        file_model,
        {},
    )

    result = tools.execute(
        "create_chart",
        {
            "source_step_id": "aggregate",
            "chart_type": "bar",
            "x_field": "课程类别",
            "y_fields": ["平均完成率", "平均课程评分"],
            "color_field": None,
            "title": "多维课程组合表现",
            "limit": 20,
        },
        file_model,
        {"aggregate": source},
    )

    first_full_label = (
        "人工智能应用与行业实践课程类别00 / 高级综合实践 / "
        "短视频内容营销推广渠道 / Android 平板与移动设备"
    )
    first_row = source.drafts[0].payload["rows"][0]
    assert " / ".join(
        [
            first_row["课程类别"],
            first_row["课程难度"],
            first_row["购买渠道"],
            first_row["主要学习设备"],
        ]
    ) == first_full_label
    assert all(len(item.alt_text) <= 500 for item in result.drafts)
    assert all(first_full_label in item.alt_text for item in result.drafts)


def test_table_payload_attaches_metric_units_to_metric_columns():
    from app.v2.services.analytics import _table_payload

    schema = ResultSchema(
        dimensions=[
            ResultDimension(
                id="channel",
                label="获客渠道",
                role="category",
                data_type="string",
                source_field="lead_channel",
            )
        ],
        metrics=[
            ResultMetric(
                id="lead_count",
                label="线索数",
                unit="count",
                aggregation="count",
                nullable=False,
            ),
            ResultMetric(
                id="deal_rate",
                label="成交转化率",
                unit="percentage",
                aggregation="ratio",
                nullable=False,
            ),
        ],
        grain=["channel"],
    )
    frame = pd.DataFrame(
        [{"channel": "短视频平台", "lead_count": 150, "deal_rate": 0.0533}]
    )
    payload = _table_payload(frame, schema)

    by_key = {column["key"]: column for column in payload["columns"]}
    assert by_key["lead_count"]["unit"] == "count"
    assert by_key["deal_rate"]["unit"] == "percentage"
    assert "unit" not in by_key["channel"]
