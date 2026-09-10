import pytest
from pydantic import TypeAdapter, ValidationError

from app.v2.schemas.intents import (
    DomainIntent,
    GroupComparisonIntent,
    MonthlyTrendIntent,
)


def test_group_comparison_intent_accepts_only_logical_ids_and_deduplicates():
    intent = GroupComparisonIntent.model_validate(
        {
            "workflow": "group_comparison",
            "dimensions": [
                "project_name",
                "project_name",
                "city",
            ],
            "metric_ids": [
                "deal_count",
                "deal_amount",
                "deal_amount",
            ],
            "detect_underperforming": True,
        }
    )

    assert intent.dimensions == ["project_name", "city"]
    assert intent.metric_ids == ["deal_count", "deal_amount"]


def test_monthly_trend_intent_contains_no_physical_date_or_metric_contract():
    intent = MonthlyTrendIntent.model_validate(
        {
            "workflow": "monthly_trend",
            "series_dimension": "lead_channel",
            "metric_ids": [
                "deal_count",
                "deal_amount",
                "payment_amount",
                "deal_amount",
            ],
        }
    )

    assert intent.workflow == "monthly_trend"
    assert intent.metric_ids == [
        "deal_count",
        "deal_amount",
        "payment_amount",
    ]
    assert not hasattr(intent, "date_field")


@pytest.mark.parametrize(
    "field",
    [
        "source_field",
        "aggregation",
        "date_field",
        "filters",
        "steps",
        "x_field",
        "explanation",
    ],
)
def test_minimal_intents_reject_model_controlled_fields(field):
    payload = {
        "workflow": "group_comparison",
        "dimensions": ["project_name"],
        "metric_ids": ["deal_count"],
        field: "not-allowed",
    }

    with pytest.raises(ValidationError):
        GroupComparisonIntent.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "workflow": "unsupported",
            "dimensions": ["project_name"],
            "metric_ids": ["deal_count"],
        },
        {
            "workflow": "group_comparison",
            "dimensions": [],
            "metric_ids": ["deal_count"],
        },
        {
            "workflow": "group_comparison",
            "dimensions": ["project_name"],
            "metric_ids": [],
        },
        {
            "workflow": "monthly_trend",
            "series_dimension": "lead_channel",
            "metric_ids": [],
        },
    ],
)
def test_minimal_intents_reject_invalid_workflow_or_empty_selections(payload):
    with pytest.raises(ValidationError):
        TypeAdapter(DomainIntent).validate_python(payload)
