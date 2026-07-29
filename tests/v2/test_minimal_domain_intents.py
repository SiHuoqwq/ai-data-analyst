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
                "course_category",
                "course_category",
                "primary_device",
            ],
            "metric_ids": [
                "enrollment_count",
                "completion_rate",
                "completion_rate",
            ],
            "detect_underperforming": True,
        }
    )

    assert intent.dimensions == ["course_category", "primary_device"]
    assert intent.metric_ids == ["enrollment_count", "completion_rate"]


def test_monthly_trend_intent_contains_no_physical_date_or_metric_contract():
    intent = MonthlyTrendIntent.model_validate(
        {
            "workflow": "monthly_trend",
            "series_dimension": "course_category",
            "metric_ids": [
                "enrollment_count",
                "paid_amount",
                "completion_rate",
                "paid_amount",
            ],
        }
    )

    assert intent.workflow == "monthly_trend"
    assert intent.metric_ids == [
        "enrollment_count",
        "paid_amount",
        "completion_rate",
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
        "dimensions": ["course_category"],
        "metric_ids": ["enrollment_count"],
        field: "not-allowed",
    }

    with pytest.raises(ValidationError):
        GroupComparisonIntent.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "workflow": "unsupported",
            "dimensions": ["course_category"],
            "metric_ids": ["enrollment_count"],
        },
        {
            "workflow": "group_comparison",
            "dimensions": [],
            "metric_ids": ["enrollment_count"],
        },
        {
            "workflow": "group_comparison",
            "dimensions": ["course_category"],
            "metric_ids": [],
        },
        {
            "workflow": "monthly_trend",
            "series_dimension": "course_category",
            "metric_ids": [],
        },
    ],
)
def test_minimal_intents_reject_invalid_workflow_or_empty_selections(payload):
    with pytest.raises(ValidationError):
        TypeAdapter(DomainIntent).validate_python(payload)
