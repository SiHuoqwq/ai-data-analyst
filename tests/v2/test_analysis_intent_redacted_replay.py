import json

import pytest
from pydantic import ValidationError

from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.structured_response import (
    StructuredResponseError,
    StructuredResponseParser,
)


def validation_signature(payload):
    with pytest.raises(ValidationError) as exc_info:
        AnalysisIntent.model_validate(payload)
    return {
        (tuple(item["loc"]), item["type"])
        for item in exc_info.value.errors(
            include_url=False,
            include_input=False,
            include_context=False,
        )
    }


def test_redacted_replay_rejects_empty_content_before_schema_validation():
    parser = StructuredResponseParser()

    with pytest.raises(
        StructuredResponseError,
        match="exactly one JSON object",
    ):
        parser.parse_object("")


def test_redacted_replay_classifies_legacy_plan_shape():
    synthetic_payload = {
        "analysis_type": "group_comparison",
        "dimensions": ["dimension_a"],
        "metrics": ["metric_a", "metric_b"],
        "steps": [],
    }
    parsed = StructuredResponseParser().parse_object(
        json.dumps(synthetic_payload)
    )

    assert validation_signature(parsed) == {
        (("metrics", 0), "model_type"),
        (("metrics", 1), "model_type"),
        (("steps",), "extra_forbidden"),
    }


def test_redacted_replay_classifies_wrong_types_enums_and_chart_fields():
    synthetic_payload = {
        "analysis_type": "monthly_trend",
        "dimensions": "dimension_a",
        "date_field": "date_a",
        "metrics": [
            {
                "semantic": "metric_a",
                "source_field": "source_a",
                "aggregation": "average",
            }
        ],
        "x_field": "date_a",
    }
    parsed = StructuredResponseParser().parse_object(
        json.dumps(synthetic_payload)
    )

    assert validation_signature(parsed) == {
        (("dimensions",), "list_type"),
        (("metrics", 0, "semantic"), "literal_error"),
        (("metrics", 0, "aggregation"), "literal_error"),
        (("x_field",), "extra_forbidden"),
    }
