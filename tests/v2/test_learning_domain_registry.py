import pytest

from app.db.models import FileModel
from app.v2.domain.learning_registry import (
    LearningDomainRegistry,
)
from app.v2.schemas.intents import (
    GroupComparisonIntent,
    MonthlyTrendIntent,
)
from app.v2.services.plan_compiler import (
    PlanCompilationError,
    PlanCompiler,
)


def dataset_record(columns=None):
    names = columns or [
        ("课程类别", "object"),
        ("课程难度", "object"),
        ("购买渠道", "object"),
        ("主要学习设备", "object"),
        ("报名日期", "datetime64[ns]"),
        ("实付金额", "float64"),
        ("课程完成率", "float64"),
        ("是否退款", "bool"),
        ("课程评分", "float64"),
    ]
    return FileModel(
        id="dataset-1",
        filename="courses.xlsx",
        filepath="courses.xlsx",
        file_type="xlsx",
        row_count=10,
        col_count=len(names),
        columns_info=[
            {"name": name, "dtype": dtype} for name, dtype in names
        ],
        profile_report="",
    )


def test_registry_owns_dimension_metric_and_date_contracts():
    registry = LearningDomainRegistry()

    assert registry.dimension("course_category").source_field == "课程类别"
    assert registry.dimension("primary_device").source_field == "主要学习设备"
    assert registry.date("enrollment_date").source_field == "报名日期"
    assert registry.metric("enrollment_count").source_field is None
    assert registry.metric("enrollment_count").aggregation == "count"
    assert registry.metric("paid_amount").source_field == "实付金额"
    assert registry.metric("paid_amount").aggregation == "sum"
    assert registry.metric("completion_rate").unit == "percentage"
    assert registry.metric("refund_rate").aggregation == "rate"
    assert registry.metric("rating").unit == "score"


def test_compiler_resolves_group_logical_ids_without_model_aggregation():
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["course_category", "primary_device"],
        metric_ids=["enrollment_count", "completion_rate", "refund_rate"],
        detect_underperforming=True,
    )

    plan = PlanCompiler().compile(intent, dataset_record())
    aggregate = plan.step("group_aggregate")

    assert aggregate.arguments["group_by"] == ["课程类别", "主要学习设备"]
    assert aggregate.arguments["metrics"] == [
        {
            "field": None,
            "aggregation": "count",
            "alias": "sample_count",
        },
        {
            "field": "课程完成率",
            "aggregation": "mean",
            "alias": "completion_rate_mean",
        },
        {
            "field": "是否退款",
            "aggregation": "rate",
            "alias": "refund_rate",
        },
    ]


def test_compiler_uses_backend_owned_monthly_date_and_period_contract():
    intent = MonthlyTrendIntent(
        workflow="monthly_trend",
        series_dimension="course_category",
        metric_ids=["enrollment_count", "paid_amount", "completion_rate"],
    )

    plan = PlanCompiler().compile(intent, dataset_record())
    monthly = plan.step("monthly_aggregate")
    schema = monthly.output_schema

    assert monthly.arguments["date_field"] == "报名日期"
    assert monthly.arguments["category_field"] == "课程类别"
    assert [dimension.id for dimension in schema.dimensions] == [
        "period",
        "series",
    ]
    assert schema.dimensions[0].source_field == "报名日期"


def test_compiler_rejects_missing_registered_physical_field_before_steps():
    intent = MonthlyTrendIntent(
        workflow="monthly_trend",
        series_dimension="course_category",
        metric_ids=["enrollment_count", "paid_amount"],
    )

    with pytest.raises(PlanCompilationError) as exc_info:
        PlanCompiler().compile(
            intent,
            dataset_record(
                [
                    ("课程类别", "object"),
                    ("报名日期", "datetime64[ns]"),
                ]
            ),
        )

    assert exc_info.value.code == "FIELD_NOT_FOUND"
    assert exc_info.value.details == {"field": "实付金额"}
