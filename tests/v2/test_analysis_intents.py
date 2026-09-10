import json

import httpx
import pytest
from pydantic import ValidationError

from app.db.models import FileModel
from app.v2.schemas.intents import MonthlyTrendIntent
from app.v2.services.provider import DeepSeekProvider, ProviderError


def monthly_intent_payload():
    return {
        "workflow": "monthly_trend",
        "series_dimension": "lead_channel",
        "metric_ids": [
            "deal_count",
            "deal_amount",
            "payment_amount",
        ],
    }


def file_record():
    return FileModel(
        id="dataset-1",
        filename="real-estate.csv",
        filepath="real-estate.csv",
        file_type="csv",
        row_count=10,
        col_count=4,
        columns_info=[
            {"name": "签约日期", "dtype": "datetime"},
            {"name": "获客渠道", "dtype": "object"},
            {"name": "成交金额", "dtype": "float64"},
            {"name": "回款金额", "dtype": "float64"},
        ],
        profile_report="",
    )


def provider_with(handler):
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


def test_monthly_intent_accepts_only_high_level_fields():
    intent = MonthlyTrendIntent.model_validate(monthly_intent_payload())

    assert intent.workflow == "monthly_trend"
    assert intent.series_dimension == "lead_channel"
    assert intent.metric_ids == [
        "deal_count",
        "deal_amount",
        "payment_amount",
    ]

    for forbidden in (
        "source_field",
        "aggregation",
        "date_field",
        "filters",
        "source_step_id",
        "x_field",
        "tool",
        "steps",
    ):
        payload = monthly_intent_payload()
        payload[forbidden] = "model-controlled"
        with pytest.raises(ValidationError):
            MonthlyTrendIntent.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow", "free_form"),
        ("metric_ids", ["profit_rate"]),
    ],
)
def test_intent_rejects_unsupported_domain_values(field, value):
    payload = monthly_intent_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        MonthlyTrendIntent.model_validate(payload)


def test_deepseek_generates_intent_without_low_level_plan_fields():
    captured = {}

    def handler(request):
        body = json.loads(request.content)
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                monthly_intent_payload(),
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    intent = provider_with(handler).generate_intent(
        "按月份分析成交金额趋势",
        file_record(),
    )

    assert intent.workflow == "monthly_trend"
    body = captured["body"]
    prompt = json.dumps(body["messages"], ensure_ascii=False)
    prompt_payload = json.loads(body["messages"][1]["content"])
    assert "房地产销售经营分析" in prompt
    assert [
        item["workflow"]
        for item in prompt_payload["valid_json_examples"]
    ] == ["group_comparison", "monthly_trend"]
    assert "allowed_tools" not in prompt
    assert "create_chart" not in prompt
    assert "source_step_id" not in prompt
    assert "source_field" not in prompt
    assert "aggregation" not in prompt
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 1000


def test_deepseek_repairs_invalid_intent_at_most_once():
    responses = [
        {"analysis_type": "unsupported"},
        monthly_intent_payload(),
    ]
    calls = 0
    request_bodies = []

    def handler(request):
        nonlocal calls
        request_bodies.append(json.loads(request.content))
        payload = responses[calls]
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(payload)}}
                ]
            },
        )

    intent = provider_with(handler).generate_intent(
        "按月份分析成交金额趋势",
        file_record(),
    )

    assert intent.workflow == "monthly_trend"
    assert calls == 2
    assert all(
        body["response_format"] == {"type": "json_object"}
        for body in request_bodies
    )
    assert all(body["max_tokens"] == 1000 for body in request_bodies)
    repair_prompt = json.dumps(
        request_bodies[1]["messages"],
        ensure_ascii=False,
    )
    repair_payload = json.loads(
        request_bodies[1]["messages"][1]["content"]
    )
    assert [
        item["workflow"]
        for item in repair_payload["valid_json_examples"]
    ] == ["group_comparison", "monthly_trend"]
    assert "validation_issues" in repair_prompt
    assert "unsupported" not in repair_prompt


def test_deepseek_fails_after_single_intent_repair():
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"workflow": "unsupported"}
                            )
                        }
                    }
                ]
            },
        )

    with pytest.raises(ProviderError) as exc_info:
        provider_with(handler).generate_intent(
            "按月份分析成交金额趋势",
            file_record(),
        )

    assert exc_info.value.code == "INTENT_REPAIR_FAILED"
    assert calls == 2
