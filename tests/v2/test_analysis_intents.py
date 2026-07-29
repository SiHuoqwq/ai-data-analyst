import json

import httpx
import pytest
from pydantic import ValidationError

from app.db.models import FileModel
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.provider import DeepSeekProvider, ProviderError


def monthly_intent_payload():
    return {
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
        "filters": [],
        "needs_visualization": True,
        "include_underperforming": False,
    }


def file_record():
    return FileModel(
        id="dataset-1",
        filename="courses.csv",
        filepath="courses.csv",
        file_type="csv",
        row_count=10,
        col_count=4,
        columns_info=[
            {"name": "报名日期", "dtype": "datetime"},
            {"name": "课程类别", "dtype": "object"},
            {"name": "实付金额", "dtype": "float64"},
            {"name": "课程完成率", "dtype": "float64"},
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
    intent = AnalysisIntent.model_validate(monthly_intent_payload())

    assert intent.analysis_type == "monthly_trend"
    assert intent.date_field == "报名日期"
    assert [metric.semantic for metric in intent.metrics] == [
        "报名人数",
        "实付金额",
        "平均完成率",
    ]

    for forbidden in ("source_step_id", "x_field", "tool", "steps"):
        payload = monthly_intent_payload()
        payload[forbidden] = "model-controlled"
        with pytest.raises(ValidationError):
            AnalysisIntent.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("analysis_type", "free_form"),
        (
            "metrics",
            [
                {
                    "semantic": "利润率",
                    "source_field": "利润",
                    "aggregation": "mean",
                }
            ],
        ),
    ],
)
def test_intent_rejects_unsupported_domain_values(field, value):
    payload = monthly_intent_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        AnalysisIntent.model_validate(payload)


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
        "按月份分析课程趋势",
        file_record(),
    )

    assert intent.analysis_type == "monthly_trend"
    prompt = json.dumps(captured["body"], ensure_ascii=False)
    assert "在线学习运营" in prompt
    assert "不得生成 source_step_id" in prompt
    assert "不得生成 x_field" in prompt
    assert "allowed_tools" not in prompt
    assert "create_chart" not in prompt
    assert captured["body"]["response_format"] == {
        "type": "json_object"
    }


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
        "按月份分析课程趋势",
        file_record(),
    )

    assert intent.analysis_type == "monthly_trend"
    assert calls == 2
    assert all(
        body["response_format"] == {"type": "json_object"}
        for body in request_bodies
    )


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
                                {"analysis_type": "unsupported"}
                            )
                        }
                    }
                ]
            },
        )

    with pytest.raises(ProviderError) as exc_info:
        provider_with(handler).generate_intent(
            "按月份分析课程趋势",
            file_record(),
        )

    assert exc_info.value.code == "PROVIDER_INVALID_RESPONSE"
    assert calls == 2
