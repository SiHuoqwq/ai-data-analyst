import json

import httpx
import pytest

from app.db.models import FileModel
from app.v2.schemas.recommendations import RecommendationCandidate
from app.v2.services.plan_compiler import PlanCompilationError, PlanCompiler
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


def recommendation_record(columns: list[tuple[str, str]]) -> FileModel:
    return FileModel(
        id="recommendation-dataset",
        filename="learning-operations.csv",
        filepath="learning-operations.csv",
        file_type="csv",
        row_count=10,
        col_count=len(columns),
        columns_info=[
            {"name": name, "dtype": dtype} for name, dtype in columns
        ],
        profile_report="",
    )


@pytest.mark.parametrize(
    (
        "intent_type",
        "columns",
        "referenced_fields",
        "expected_semantic",
        "expected_aggregation",
        "expected_result_id",
        "expected_unit",
    ),
    [
        (
            "group_comparison",
            [("获客渠道", "object"), ("成交金额", "float64")],
            ["获客渠道", "成交金额"],
            "成交金额",
            "sum",
            "deal_amount_sum",
            "currency",
        ),
        (
            "group_comparison",
            [("获客渠道", "object"), ("签约日期", "datetime64[ns]")],
            ["获客渠道", "签约日期"],
            "成交套数",
            "count",
            "deal_count",
            "count",
        ),
        (
            "monthly_trend",
            [
                ("获客渠道", "object"),
                ("线索日期", "datetime64[ns]"),
                ("成交金额", "float64"),
            ],
            ["获客渠道", "线索日期", "成交金额"],
            "成交金额",
            "sum",
            "deal_amount_sum",
            "currency",
        ),
        (
            "monthly_trend",
            [
                ("获客渠道", "object"),
                ("线索日期", "datetime64[ns]"),
                ("回款金额", "float64"),
            ],
            ["获客渠道", "线索日期", "回款金额"],
            "回款金额",
            "sum",
            "payment_amount_sum",
            "currency",
        ),
    ],
)
def test_recommendation_validation_uses_registered_metric_contracts(
    intent_type,
    columns,
    referenced_fields,
    expected_semantic,
    expected_aggregation,
    expected_result_id,
    expected_unit,
):
    record = recommendation_record(columns)
    candidate = RecommendationCandidate(
        intent_type=intent_type,
        label="Analyze registered metric",
        question="Analyze the selected registered metric.",
        referenced_fields=referenced_fields,
    )

    intents = DeepSeekProvider._recommendation_validation_intents(
        candidate,
        record,
    )
    assert len(intents) == 1
    intent = intents[0]
    assert [
        (metric.semantic, metric.source_field, metric.aggregation)
        for metric in intent.metrics
    ] == [
        (
            expected_semantic,
            referenced_fields[-1],
            expected_aggregation,
        )
    ]

    plan = PlanCompiler().compile(intent, record)
    aggregate_step = plan.step(
        "monthly_aggregate"
        if intent_type == "monthly_trend"
        else "group_aggregate"
    )
    assert [
        (metric.id, metric.unit) for metric in aggregate_step.output_schema.metrics
    ] == [(expected_result_id, expected_unit)]


@pytest.mark.parametrize(
    (
        "intent_type",
        "columns",
        "referenced_fields",
        "expected_dimensions",
        "aggregate_step_id",
        "result_id",
    ),
    [
        (
            "group_comparison",
            [("segment", "object"), ("score", "float64")],
            ["segment", "score"],
            ["segment"],
            "group_aggregate",
            "lead_count",
        ),
        (
            "monthly_trend",
            [
                ("segment", "object"),
                ("observed_at", "datetime64[ns]"),
                ("score", "float64"),
            ],
            ["segment", "observed_at", "score"],
            ["segment"],
            "monthly_aggregate",
            "lead_count",
        ),
        (
            "group_comparison",
            [("segment", "object"), ("score", "int64")],
            ["segment", "score"],
            ["segment"],
            "group_aggregate",
            "lead_count",
        ),
        (
            "monthly_trend",
            [
                ("segment", "object"),
                ("observed_at", "datetime64[ns]"),
                ("score", "int64"),
            ],
            ["segment", "observed_at", "score"],
            ["segment"],
            "monthly_aggregate",
            "lead_count",
        ),
    ],
)
def test_recommendation_validation_does_not_guess_unknown_numeric_semantics(
    intent_type,
    columns,
    referenced_fields,
    expected_dimensions,
    aggregate_step_id,
    result_id,
):
    record = recommendation_record(columns)
    candidate = RecommendationCandidate(
        intent_type=intent_type,
        label="Analyze unknown metric",
        question="Analyze the selected fields.",
        referenced_fields=referenced_fields,
    )

    intents = DeepSeekProvider._recommendation_validation_intents(
        candidate,
        record,
    )
    assert len(intents) == 1
    intent = intents[0]
    assert intent.dimensions == expected_dimensions
    assert [
        (metric.semantic, metric.source_field, metric.aggregation)
        for metric in intent.metrics
    ] == [("线索数", None, "count")]

    plan = PlanCompiler().compile(intent, record)
    assert [
        (metric.id, metric.unit)
        for metric in plan.step(aggregate_step_id).output_schema.metrics
    ] == [(result_id, "count")]


@pytest.mark.parametrize(
    ("intent_type", "columns", "referenced_fields"),
    [
        (
            "monthly_trend",
            [
                ("获客渠道", "object"),
                ("线索日期", "datetime64[ns]"),
                ("到访日期", "datetime64[ns]"),
            ],
            ["获客渠道", "线索日期", "到访日期"],
        ),
        (
            "monthly_trend",
            [
                ("获客渠道", "object"),
                ("线索日期", "datetime64[ns]"),
                ("签约日期", "datetime64[ns]"),
            ],
            ["获客渠道", "线索日期", "签约日期"],
        ),
    ],
)
def test_recommendation_validation_rejects_registered_metric_in_wrong_workflow(
    intent_type,
    columns,
    referenced_fields,
):
    record = recommendation_record(columns)
    candidate = RecommendationCandidate(
        intent_type=intent_type,
        label="Analyze unsupported registered metric",
        question="Analyze the selected registered metric.",
        referenced_fields=referenced_fields,
    )

    with pytest.raises(PlanCompilationError) as raised:
        DeepSeekProvider._recommendation_validation_intents(candidate, record)

    assert raised.value.code == "UNSUPPORTED_RECOMMENDATION_METRIC"


def test_deepseek_returns_two_valid_recommendations_from_mocked_json(tmp_path):
    captured = {}
    csv_path = tmp_path / "valid-recommendation.csv"
    csv_path.write_text(
        "course_category,enrollment_date,completion_rate\n"
        "A,2026-01-01,0.8\n",
        encoding="utf-8",
    )
    record = file_record()
    record.filepath = str(csv_path)
    record.columns_info[1]["dtype"] = "object"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "group_comparison",
                            "referenced_fields": [
                                "course_category",
                                "completion_rate",
                            ],
                        },
                        {
                            "intent_type": "monthly_trend",
                            "referenced_fields": [
                                "course_category",
                                "enrollment_date",
                            ],
                        },
                    ]
                }
            )
        )

    provider = provider_with(handler)

    result = provider.recommend_questions(record)

    assert [item.intent_type for item in result.candidates] == [
        "group_comparison",
        "monthly_trend",
    ]
    assert result.candidates[0].referenced_fields == [
        "course_category",
        "completion_rate",
    ]
    assert result.candidates[0].label is None
    assert result.candidates[0].question is None
    assert "only intent_type and referenced_fields" in (
        captured["body"]["messages"][0]["content"]
    )
    user_payload = json.loads(captured["body"]["messages"][1]["content"])
    candidate_schema = user_payload["selection_schema"]["properties"][
        "candidates"
    ]["items"]
    assert candidate_schema["additionalProperties"] is False
    assert set(candidate_schema["properties"]) == {
        "intent_type",
        "referenced_fields",
    }


def test_deepseek_accepts_monthly_recommendation_with_integer_category_code(
    tmp_path,
):
    csv_path = tmp_path / "encoded-category.csv"
    csv_path.write_text(
        "course_category_code,enrollment_date\n"
        "1,2026-01-01\n"
        "2,2026-02-01\n",
        encoding="utf-8",
    )
    record = file_record()
    record.filepath = str(csv_path)
    record.col_count = 2
    record.columns_info = [
        {
            "name": "course_category_code",
            "dtype": "int64",
            "null_count": 0,
            "null_rate": 0,
            "unique_count": 2,
        },
        {
            "name": "enrollment_date",
            "dtype": "object",
            "null_count": 0,
            "null_rate": 0,
            "unique_count": 2,
        },
    ]
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "monthly_trend",
                            "label": "Monthly category trend",
                            "question": "How do encoded course categories change by month?",
                            "referenced_fields": [
                                "course_category_code",
                                "enrollment_date",
                            ],
                        }
                    ]
                }
            )
        )
    )

    result = provider.recommend_questions(record)

    assert result.candidates[0].referenced_fields == [
        "course_category_code",
        "enrollment_date",
    ]


def test_deepseek_leaves_monthly_executability_validation_to_the_service(
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

    result = provider.recommend_questions(record)

    assert result.candidates[0].intent_type == "monthly_trend"


def test_deepseek_leaves_monthly_field_role_validation_to_the_service():
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

    result = provider.recommend_questions(file_record())

    assert result.candidates[0].referenced_fields == [
        "completion_rate",
        "enrollment_date",
    ]


def test_deepseek_drops_invalid_candidate_item_without_losing_valid_sibling():
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "unsupported_intent",
                            "referenced_fields": ["course_category"],
                        },
                        {
                            "intent_type": "group_comparison",
                            "referenced_fields": [
                                "course_category",
                                "completion_rate",
                            ],
                        },
                    ]
                }
            )
        )
    )

    result = provider.recommend_questions(file_record())

    assert [item.intent_type for item in result.candidates] == [
        "group_comparison"
    ]


def test_deepseek_drops_extra_key_candidate_item_without_losing_valid_sibling():
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "intent_type": "group_comparison",
                            "referenced_fields": ["course_category"],
                            "unexpected": True,
                        },
                        {
                            "intent_type": "monthly_trend",
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

    result = provider.recommend_questions(file_record())

    assert [item.intent_type for item in result.candidates] == ["monthly_trend"]


@pytest.mark.parametrize(
    "payload",
    [
        {"candidates": [], "unexpected": True},
        {"candidates": "not-an-array"},
        {
            "candidates": [
                {"intent_type": "group_comparison", "referenced_fields": ["a"]},
                {"intent_type": "group_comparison", "referenced_fields": ["b"]},
                {"intent_type": "group_comparison", "referenced_fields": ["c"]},
            ]
        },
    ],
)
def test_deepseek_keeps_recommendation_outer_envelope_strict(payload):
    provider = provider_with(
        lambda _request: response(json.dumps(payload))
    )

    with pytest.raises(ProviderError) as raised:
        provider.recommend_questions(file_record())

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"


def test_deepseek_leaves_referenced_field_validation_to_the_service():
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

    result = provider.recommend_questions(file_record())

    assert result.candidates[0].referenced_fields == [
        "course_category",
        "missing_field",
    ]


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


def test_deepseek_profile_excludes_sensitive_and_path_like_field_names():
    captured = {}
    record = file_record()
    record.filename = "..\\private\\leaked\r\nname.csv"
    record.columns_info.extend(
        [
            {"name": "customer_segment", "dtype": "object"},
            {"name": "课程类别", "dtype": "object"},
            {"name": "learning_path", "dtype": "object"},
            {"name": "location", "dtype": "object"},
            {"name": "customer_location", "dtype": "object"},
            {"name": "product_uri", "dtype": "object"},
            {"name": "access_channel", "dtype": "object"},
            {"name": "client_keyboard_layout", "dtype": "object"},
            {"name": "source_pathway", "dtype": "object"},
            {"name": "storage_keynote", "dtype": "object"},
            {"name": "api_key", "dtype": "object"},
            {"name": "API Key", "dtype": "object"},
            {"name": "api.key", "dtype": "object"},
            {"name": "refresh_token", "dtype": "object"},
            {"name": "accessToken", "dtype": "object"},
            {"name": "accesstoken", "dtype": "object"},
            {"name": "accessKey", "dtype": "object"},
            {"name": "access.key", "dtype": "object"},
            {"name": "bearer", "dtype": "object"},
            {"name": "to.ken", "dtype": "object"},
            {"name": "user_password_hash", "dtype": "object"},
            {"name": "userpassword", "dtype": "object"},
            {"name": "pass.word", "dtype": "object"},
            {"name": "clientsecret", "dtype": "object"},
            {"name": "credential", "dtype": "object"},
            {"name": "authorization", "dtype": "object"},
            {"name": "storagePath", "dtype": "object"},
            {"name": "sourcePath", "dtype": "object"},
            {"name": "sourcepathValue", "dtype": "object"},
            {"name": "filepath_hash", "dtype": "object"},
            {"name": "dirname", "dtype": "object"},
            {"name": "fileURI", "dtype": "object"},
            {"name": "sourceURI", "dtype": "object"},
            {"name": "source.uri", "dtype": "object"},
            {"name": "storageLocation", "dtype": "object"},
            {"name": "file.location", "dtype": "object"},
            {"name": "storageFolder", "dtype": "object"},
            {"name": "sourceFolder", "dtype": "object"},
            {"name": "localFolder", "dtype": "object"},
            {"name": "sessionCookie", "dtype": "object"},
            {"name": "clientCertificate", "dtype": "object"},
            {"name": "a.pi.key", "dtype": "object"},
            {"name": "ac.cess.key", "dtype": "object"},
            {"name": "sto.rage.folder", "dtype": "object"},
            {"name": "file.u.r.i", "dtype": "object"},
            {"name": "prefix.a.pi.key.hash", "dtype": "object"},
            {"name": "meta.ac.cess.key.version", "dtype": "object"},
            {"name": "snapshot.sto.rage.folder.count", "dtype": "object"},
            {"name": "normalized.file.u.r.i.value", "dtype": "object"},
            {"name": "ＦｉｌｅＰａｔｈ", "dtype": "object"},
            {"name": "C:\\private\\value", "dtype": "object"},
            {"name": "../private/value", "dtype": "object"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return response('{"candidates":[]}')

    provider_with(handler).recommend_questions(record)

    payload = json.loads(captured["body"]["messages"][1]["content"])
    assert payload["dataset"]["filename"] == "leakedname.csv"
    assert [field["name"] for field in payload["dataset"]["fields"]] == [
        "course_category",
        "enrollment_date",
        "completion_rate",
        "customer_segment",
        "课程类别",
        "learning_path",
        "location",
        "customer_location",
        "product_uri",
        "access_channel",
        "client_keyboard_layout",
        "source_pathway",
        "storage_keynote",
    ]
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "api_key",
        "API Key",
        "api.key",
        "refresh_token",
        "accessToken",
        "accesstoken",
        "accessKey",
        "access.key",
        "bearer",
        "to.ken",
        "user_password_hash",
        "userpassword",
        "pass.word",
        "clientsecret",
        "credential",
        "authorization",
        "storagePath",
        "sourcePath",
        "sourcepathValue",
        "filepath_hash",
        "dirname",
        "fileURI",
        "sourceURI",
        "source.uri",
        "storageLocation",
        "file.location",
        "storageFolder",
        "sourceFolder",
        "localFolder",
        "sessionCookie",
        "clientCertificate",
        "a.pi.key",
        "ac.cess.key",
        "sto.rage.folder",
        "file.u.r.i",
        "prefix.a.pi.key.hash",
        "meta.ac.cess.key.version",
        "snapshot.sto.rage.folder.count",
        "normalized.file.u.r.i.value",
        "ＦｉｌｅＰａｔｈ",
        "C:\\private\\value",
        "../private/value",
        "SENSITIVE_SAMPLE_VALUE",
    ):
        assert forbidden not in serialized


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
