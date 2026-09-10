import json

import httpx
import pytest
from pydantic import ValidationError

from app.db.models import FileModel
from app.v2.schemas.intents import GroupComparisonIntent
from app.v2.services.provider import DeepSeekProvider, ProviderError
from app.v2.services.structured_diagnostics import (
    diagnose_structured_response,
)
from app.v2.services.structured_response import StructuredResponseError


def test_empty_and_invalid_json_have_distinct_redacted_classifications():
    empty = diagnose_structured_response(
        "",
        finish_reason="stop",
        request_stage="initial",
        error=StructuredResponseError("invalid"),
    )
    invalid = diagnose_structured_response(
        "not-json",
        finish_reason="length",
        request_stage="repair",
        error=StructuredResponseError("invalid"),
    )

    assert empty["error_code"] == "EMPTY_STRUCTURED_RESPONSE"
    assert empty["content_empty"] is True
    assert empty["content_length"] == 0
    assert invalid["error_code"] == "INVALID_JSON"
    assert invalid["finish_reason"] == "length"
    assert invalid["json_parse_success"] is False


def test_schema_mismatch_records_only_types_locations_and_hash():
    content = json.dumps(
        {
            "workflow": "group_comparison",
            "dimensions": ["lead_channel"],
            "metric_ids": ["deal_count"],
            "secret_explanation": "private-response-text",
        }
    )
    with pytest.raises(ValidationError) as exc_info:
        GroupComparisonIntent.model_validate_json(content)

    diagnostic = diagnose_structured_response(
        content,
        finish_reason="stop",
        request_stage="initial",
        error=exc_info.value,
    )

    assert diagnostic["error_code"] == "INTENT_SCHEMA_MISMATCH"
    assert diagnostic["top_level_keys"] == [
        "dimensions",
        "metric_ids",
        "secret_explanation",
        "workflow",
    ]
    assert diagnostic["top_level_value_types"] == {
        "workflow": "string",
        "dimensions": "array",
        "metric_ids": "array",
        "secret_explanation": "string",
    }
    assert diagnostic["validation_error_types"] == ["extra_forbidden"]
    assert diagnostic["validation_error_locations"] == [
        ["secret_explanation"]
    ]
    assert diagnostic["extra_field_names"] == ["secret_explanation"]
    assert diagnostic["missing_field_names"] == []
    assert diagnostic["invalid_enum_field_names"] == []
    serialized = json.dumps(diagnostic)
    assert "private-response-text" not in serialized
    assert len(diagnostic["response_sha256"]) == 64


def _provider(handler):
    return DeepSeekProvider(
        api_key="test-key",
        base_url="https://example.test",
        model="deepseek-chat",
        timeout_seconds=1,
        max_retries=0,
        max_tool_rounds=5,
        max_prompt_chars=24_000,
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://example.test",
        ),
    )


def _file_record():
    return FileModel(
        id="dataset-1",
        filename="real-estate.csv",
        filepath="real-estate.csv",
        file_type="csv",
        row_count=1,
        col_count=1,
        columns_info=[{"name": "获客渠道", "dtype": "object"}],
        profile_report="",
    )


def test_provider_records_two_redacted_diagnostics_without_response_text():
    responses = [
        ("", "stop"),
        ('{"workflow":"unsupported","private":"do-not-store"}', "stop"),
    ]
    calls = 0

    def handler(_request):
        nonlocal calls
        content, finish_reason = responses[calls]
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": finish_reason,
                        "message": {"content": content},
                    }
                ]
            },
        )

    provider = _provider(handler)
    with pytest.raises(ProviderError) as exc_info:
        provider.generate_intent("比较不同渠道", _file_record())

    assert exc_info.value.code == "INTENT_REPAIR_FAILED"
    assert [
        item["error_code"] for item in provider.last_intent_diagnostics
    ] == ["EMPTY_STRUCTURED_RESPONSE", "INTENT_SCHEMA_MISMATCH"]
    assert [
        item["request_stage"] for item in provider.last_intent_diagnostics
    ] == ["initial", "repair"]
    serialized = json.dumps(provider.last_intent_diagnostics)
    assert "do-not-store" not in serialized
    assert "比较不同渠道" not in serialized
