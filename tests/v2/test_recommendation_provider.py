import json

import httpx
import pytest

from app.db.models import FileModel
from app.v2.services.provider import DeepSeekProvider, FakeAnalysisProvider, ProviderError


def file_record() -> FileModel:
    return FileModel(
        id="dataset-1",
        filename="anonymized-course-data.xlsx",
        filepath="sensitive://private/RAW_ROW_VALUE.xlsx",
        file_type="xlsx",
        row_count=120,
        col_count=3,
        columns_info=[
            {
                "name": "course_category",
                "dtype": "object",
                "null_count": 0,
                "null_rate": 0,
                "unique_count": 4,
                "sample_values": ["SENSITIVE_SAMPLE_VALUE"],
            },
            {
                "name": "enrollment_date",
                "dtype": "datetime64[ns]",
                "null_count": 2,
                "null_rate": 0.0167,
                "unique_count": 80,
                "sample_values": ["2026-01-01"],
            },
            {
                "name": "completion_rate",
                "dtype": "float64",
                "null_count": 0,
                "null_rate": 0,
                "unique_count": 80,
                "sample_values": [0.8],
            },
        ],
        profile_report="RAW_ROW_VALUE",
    )


def response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                }
            ]
        },
    )


def provider_with(handler) -> DeepSeekProvider:
    return DeepSeekProvider(
        api_key="API_KEY_MARKER",
        base_url="https://unit.test",
        model="deepseek-chat",
        timeout_seconds=1,
        max_retries=0,
        max_tool_rounds=4,
        max_prompt_chars=8_000,
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://unit.test",
        ),
    )


def test_deepseek_returns_two_valid_recommendations_from_mocked_json(tmp_path):
    csv_path = tmp_path / "valid-recommendation.csv"
    csv_path.write_text(
        "course_category,enrollment_date,completion_rate\n"
        "A,2026-01-01,0.8\n",
        encoding="utf-8",
    )
    record = file_record()
    record.filepath = str(csv_path)
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "group_comparison",
                            "label": "Compare completion",
                            "question": "Which course categories have the lowest completion rate?",
                            "referenced_fields": [
                                "course_category",
                                "completion_rate",
                            ],
                        },
                        {
                            "intent_type": "monthly_trend",
                            "label": "Monthly enrollments",
                            "question": "How do enrollments change by month and course category?",
                            "referenced_fields": [
                                "course_category",
                                "enrollment_date",
                            ],
                        },
                    ]
                }
            )
        )
    )

    result = provider.recommend_questions(record)

    assert [item.intent_type for item in result.candidates] == [
        "group_comparison",
        "monthly_trend",
    ]
    assert result.candidates[0].referenced_fields == [
        "course_category",
        "completion_rate",
    ]


def test_deepseek_rejects_monthly_recommendation_with_unparseable_date_values(
    tmp_path,
):
    csv_path = tmp_path / "invalid-monthly-date.csv"
    csv_path.write_text(
        "course_category,enrollment_date,completion_rate\n"
        "A,not-a-date,0.8\n",
        encoding="utf-8",
    )
    record = file_record()
    record.filepath = str(csv_path)
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "monthly_trend",
                            "label": "Monthly enrollments",
                            "question": "How do enrollments change by month?",
                            "referenced_fields": [
                                "course_category",
                                "enrollment_date",
                            ],
                        }
                    ]
                }
            )
        )
    )

    with pytest.raises(ProviderError) as raised:
        provider.recommend_questions(record)

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


def test_deepseek_rejects_monthly_recommendation_without_a_category_field():
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "monthly_trend",
                            "label": "Invalid monthly roles",
                            "question": "How do completion rates change by month?",
                            "referenced_fields": [
                                "completion_rate",
                                "enrollment_date",
                            ],
                        }
                    ]
                }
            )
        )
    )

    with pytest.raises(ProviderError) as raised:
        provider.recommend_questions(file_record())

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "intent_type": "group_comparison",
            "label": "Compare completion",
            "question": "Which course categories have the lowest completion rate?",
            "referenced_fields": ["course_category", "completion_rate"],
            "unexpected": True,
        },
        {
            "intent_type": "unsupported_intent",
            "label": "Unsupported",
            "question": "This must not be shown.",
            "referenced_fields": ["course_category"],
        },
    ],
)
def test_deepseek_rejects_recommendations_outside_the_strict_contract(candidate):
    provider = provider_with(
        lambda _request: response(json.dumps({"candidates": [candidate]}))
    )

    with pytest.raises(ProviderError) as raised:
        provider.recommend_questions(file_record())

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


def test_deepseek_rejects_a_recommendation_that_references_missing_fields():
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "group_comparison",
                            "label": "Missing field",
                            "question": "This must not be shown.",
                            "referenced_fields": [
                                "course_category",
                                "missing_field",
                            ],
                        }
                    ]
                }
            )
        )
    )

    with pytest.raises(ProviderError) as raised:
        provider.recommend_questions(file_record())

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


def test_deepseek_recommendation_request_contains_only_safe_field_metadata():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return response('{"candidates":[]}')

    provider_with(handler).recommend_questions(file_record())

    request_text = json.dumps(captured["body"], ensure_ascii=False)
    payload = json.loads(captured["body"]["messages"][1]["content"])
    assert payload["dataset"]["fields"][0] == {
        "name": "course_category",
        "dtype": "object",
        "null_count": 0,
        "null_rate": 0,
        "unique_count": 4,
    }
    assert "filepath" not in request_text
    assert "RAW_ROW_VALUE" not in request_text
    assert "SENSITIVE_SAMPLE_VALUE" not in request_text
    assert "API_KEY_MARKER" not in request_text


def test_fake_provider_returns_deterministic_empty_recommendations_without_http(
    monkeypatch,
):
    calls = []

    def fail_if_called(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("Fake provider must not make HTTP requests")

    monkeypatch.setattr(httpx.Client, "post", fail_if_called)

    result = FakeAnalysisProvider().recommend_questions(file_record())

    assert result.candidates == []
    assert calls == []
