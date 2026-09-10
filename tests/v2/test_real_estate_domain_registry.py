import pytest

from app.db.models import FileModel
from app.v2.domain.real_estate_registry import (
    RealEstateDomainRegistry,
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
        ("项目", "object"),
        ("城市", "object"),
        ("区域", "object"),
        ("置业顾问", "object"),
        ("获客渠道", "object"),
        ("户型", "object"),
        ("客户等级", "object"),
        ("线索日期", "datetime64[ns]"),
        ("到访日期", "datetime64[ns]"),
        ("认购日期", "datetime64[ns]"),
        ("签约日期", "datetime64[ns]"),
        ("成交金额", "float64"),
        ("回款金额", "float64"),
    ]
    return FileModel(
        id="dataset-1",
        filename="real-estate.xlsx",
        filepath="real-estate.xlsx",
        file_type="xlsx",
        row_count=10,
        col_count=len(names),
        columns_info=[
            {"name": name, "dtype": dtype} for name, dtype in names
        ],
        profile_report="",
    )


def test_registry_owns_dimension_metric_and_date_contracts():
    registry = RealEstateDomainRegistry()

    assert registry.dimension("project_name").source_field == "项目"
    assert registry.dimension("sales_consultant").source_field == "置业顾问"
    assert registry.date("contract_date").source_field == "签约日期"
    assert registry.metric("deal_count").source_field == "签约日期"
    assert registry.metric("deal_count").aggregation == "count"
    assert registry.metric("deal_amount").source_field == "成交金额"
    assert registry.metric("deal_amount").aggregation == "sum"
    assert registry.metric("avg_deal_amount").unit == "currency"
    assert registry.metric("visit_rate").aggregation == "ratio"
    assert registry.metric("visit_rate").numerator_metric_id == "visit_count"
    assert registry.metric("visit_rate").denominator_metric_id == "lead_count"
    assert registry.metric("avg_deal_amount").numerator_metric_id == "deal_amount"
    assert registry.metric("avg_deal_amount").denominator_metric_id == "deal_count"
    assert registry.metric("avg_deal_amount").is_derived is True
    assert registry.metric("lead_count").is_derived is False


def test_compiler_resolves_group_logical_ids_without_model_aggregation():
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["project_name", "city"],
        metric_ids=["deal_count", "deal_amount", "payment_amount"],
        detect_underperforming=False,
    )

    plan = PlanCompiler().compile(intent, dataset_record())
    aggregate = plan.step("group_aggregate")

    assert aggregate.arguments["group_by"] == ["项目", "城市"]
    assert aggregate.arguments["metrics"] == [
        {
            "kind": "base",
            "field": "签约日期",
            "aggregation": "count",
            "alias": "deal_count",
        },
        {
            "kind": "base",
            "field": "成交金额",
            "aggregation": "sum",
            "alias": "deal_amount_sum",
        },
        {
            "kind": "base",
            "field": "回款金额",
            "aggregation": "sum",
            "alias": "payment_amount_sum",
        },
    ]


def test_compiler_uses_backend_owned_monthly_date_and_period_contract():
    intent = MonthlyTrendIntent(
        workflow="monthly_trend",
        series_dimension="lead_channel",
        metric_ids=["deal_count", "deal_amount", "payment_amount"],
    )

    plan = PlanCompiler().compile(intent, dataset_record())
    monthly = plan.step("monthly_aggregate")
    schema = monthly.output_schema

    assert monthly.arguments["date_field"] == "签约日期"
    assert monthly.arguments["category_field"] == "获客渠道"
    assert [dimension.id for dimension in schema.dimensions] == [
        "period",
        "series",
    ]
    assert schema.dimensions[0].source_field == "签约日期"


def test_compiler_rejects_missing_registered_physical_field_before_steps():
    intent = MonthlyTrendIntent(
        workflow="monthly_trend",
        series_dimension="lead_channel",
        metric_ids=["deal_count", "deal_amount"],
    )

    with pytest.raises(PlanCompilationError) as exc_info:
        PlanCompiler().compile(
            intent,
            dataset_record(
                [
                    ("获客渠道", "object"),
                    ("签约日期", "datetime64[ns]"),
                ]
            ),
        )

    assert exc_info.value.code == "FIELD_NOT_FOUND"
    assert exc_info.value.details == {"field": "成交金额"}
