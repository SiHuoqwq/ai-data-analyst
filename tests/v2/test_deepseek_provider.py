import json

import httpx
import pytest

from app.db.models import FileModel
from app.v2.services.evidence import EvidenceRegistry
from app.v2.services.provider import DeepSeekProvider, ProviderError


def file_record() -> FileModel:
    return FileModel(
        id="dataset-1",
        filename="匿名课程数据.xlsx",
        filepath="sensitive://private/SENSITIVE_ROW_VALUE.xlsx",
        file_type="xlsx",
        row_count=120,
        col_count=7,
        columns_info=[
            {
                "name": "课程类别",
                "dtype": "object",
                "null_count": 0,
                "null_rate": 0,
                "unique_count": 4,
                "sample_values": ["SENSITIVE_ROW_VALUE"],
            },
            {
                "name": "完成率",
                "dtype": "float64",
                "null_count": 2,
                "null_rate": 0.0167,
                "unique_count": 80,
                "sample_values": [0.8],
            },
        ],
        profile_report="SENSITIVE_ROW_VALUE",
    )


def response(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        },
    )


def provider_with(handler, **overrides) -> DeepSeekProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://unit.test",
    )
    return DeepSeekProvider(
        api_key="test-key",
        base_url="https://unit.test",
        model="deepseek-chat",
        timeout_seconds=1,
        max_retries=overrides.pop("max_retries", 0),
        max_tool_rounds=overrides.pop("max_tool_rounds", 4),
        max_prompt_chars=overrides.pop("max_prompt_chars", 8_000),
        client=client,
        **overrides,
    )


def valid_inspect_plan() -> str:
    return json.dumps(
        {
            "goal": "inspect the dataset",
            "steps": [
                {
                    "id": "inspect",
                    "tool": "inspect_dataset",
                    "purpose": "inspect fields",
                    "arguments": {},
                }
            ],
        }
    )


def conclusion_registry() -> EvidenceRegistry:
    return EvidenceRegistry.from_tool_evidence(
        "run-1",
        [
            {
                "artifact_id": "artifact-private-id",
                "artifact_type": "table",
                "source_tool": "group_aggregate",
                "title": "课程汇总",
                "summary": {},
                "preview": [{"课程类别": "AI 应用", "报名人数": 12}],
            }
        ],
    )


def valid_conclusion(key: str) -> str:
    return json.dumps(
        {
            "headline": "课程运营结论",
            "overview": "课程表现需要持续观察。",
            "findings": [
                {
                    "title": "主要发现",
                    "statement": "该课程类别报名表现值得关注。",
                    "evidence_keys": [key],
                }
            ],
            "recommendations": [
                {
                    "action": "持续跟踪课程运营表现。",
                    "reason": "当前结构化结果提供了可靠依据。",
                    "evidence_keys": [key],
                }
            ],
            "limitations": ["结论仅基于当前数据集。"],
        },
        ensure_ascii=False,
    )


def test_deepseek_builds_grounded_conclusion_and_repairs_once():
    registry = conclusion_registry()
    key = registry.items[0].key
    requests = []
    responses = iter(("not-json", valid_conclusion(key)))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return response(next(responses))

    conclusion = provider_with(handler).build_conclusion(
        "分析课程表现",
        file_record(),
        registry,
    )

    assert conclusion.findings[0].evidence_keys == [key]
    assert len(requests) == 2
    repair_payload = requests[1]["messages"][1]["content"]
    assert "artifact-private-id" not in repair_payload
    assert "SENSITIVE_ROW_VALUE" not in repair_payload


def test_deepseek_rejects_conclusion_after_single_failed_repair():
    registry = conclusion_registry()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return response("not-json")

    with pytest.raises(ProviderError) as error:
        provider_with(handler).build_conclusion(
            "分析课程表现",
            file_record(),
            registry,
        )

    assert error.value.code == "UNGROUNDED_ANSWER"
    assert len(requests) == 2


def test_deepseek_repairs_an_invalid_plan_at_most_once():
    requests = []
    responses = iter(("not-json", valid_inspect_plan()))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return response(next(responses))

    plan = provider_with(handler).build_plan(
        "inspect the dataset",
        file_record(),
        history=[],
    )

    assert [step.operation for step in plan.steps] == ["inspect_dataset"]
    assert len(requests) == 2
    repair_payload = json.loads(requests[1]["messages"][1]["content"])
    assert repair_payload["invalid_response_excerpt"] == "not-json"
    assert "plan_schema" in repair_payload
    assert "allowed_tools" in repair_payload
    assert "SENSITIVE_ROW_VALUE" not in json.dumps(repair_payload)


def test_deepseek_fails_after_one_invalid_plan_repair():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response("still-not-json")

    with pytest.raises(ProviderError) as raised:
        provider_with(handler).build_plan(
            "inspect the dataset",
            file_record(),
            history=[],
        )

    assert calls == 2
    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
    assert "still-not-json" not in raised.value.user_message
    assert "still-not-json" not in json.dumps(raised.value.details)


def test_deepseek_does_not_repair_plan_after_cancellation():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response("not-json")

    provider = provider_with(handler)
    provider.set_cancel_check(lambda: True)

    with pytest.raises(ProviderError) as raised:
        provider.build_plan("inspect the dataset", file_record(), history=[])

    assert calls == 1
    assert raised.value.code == "RUN_CANCELLED"


def test_deepseek_build_plan_uses_strict_whitelisted_tools_and_minimized_schema():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return response(
            json.dumps(
                {
                    "goal": "按类别比较完成情况",
                    "steps": [
                        {
                            "id": "inspect",
                            "tool": "inspect_dataset",
                            "purpose": "确认字段",
                            "arguments": {},
                        },
                        {
                            "id": "aggregate",
                            "tool": "group_aggregate",
                            "purpose": "计算类别指标",
                            "arguments": {
                                "group_by": ["课程类别"],
                                "metrics": [
                                    {
                                        "field": None,
                                        "aggregation": "count",
                                        "alias": "报名人数",
                                    },
                                    {
                                        "field": "完成率",
                                        "aggregation": "mean",
                                        "alias": "平均完成率",
                                    },
                                ],
                                "filters": [],
                                "sort": [],
                                "limit": 20,
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            )
        )

    provider = provider_with(handler)
    plan = provider.build_plan(
        "比较课程类别",
        file_record(),
        history=[{"role": "assistant", "content": "上一轮已比较课程类别"}],
    )

    assert [step.operation for step in plan.steps] == [
        "inspect_dataset",
        "group_aggregate",
    ]
    assert plan.steps[1].arguments["metrics"][1]["field"] == "完成率"
    request_text = json.dumps(captured["body"], ensure_ascii=False)
    assert "课程类别" in request_text
    assert "完成率" in request_text
    assert "SENSITIVE_ROW_VALUE" not in request_text
    assert "sensitive://private" not in request_text


def test_deepseek_build_answer_only_receives_user_facing_structured_evidence():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return response("A 类平均完成率为 75%，建议优化课程引导。")

    provider = provider_with(handler)
    answer = provider.build_answer(
        "哪个类别完成率低？",
        file_record(),
        evidence=[
            {
                "artifact_id": "artifact-1",
                "artifact_type": "table",
                "title": "类别汇总",
                "summary": {"row_count": 2},
                "preview": [
                    {"课程类别": "A", "平均完成率": 0.75},
                    {"课程类别": "B", "平均完成率": 0.9},
                ],
            }
        ],
        history=[],
    )

    assert "75%" in answer
    request_body = captured["body"]
    request_text = json.dumps(request_body, ensure_ascii=False)
    user_payload = json.loads(request_body["messages"][1]["content"])
    assert "artifact_id" not in user_payload["evidence"][0]
    assert "artifact-1" not in request_text
    assert any(
        "不要自行计算" in rule
        for rule in user_payload["answer_rules"]
    )
    assert any(
        "每个比例数值" in rule
        for rule in user_payload["answer_rules"]
    )
    assert "SENSITIVE_ROW_VALUE" not in request_text
    assert "sensitive://private" not in request_text


def test_deepseek_rejects_answer_with_number_missing_from_evidence():
    provider = provider_with(
        lambda _request: response("A 类平均完成率为 88%。")
    )

    with pytest.raises(ProviderError) as raised:
        provider.build_answer(
            "哪个类别完成率低？",
            file_record(),
            evidence=[
                {
                    "artifact_id": "artifact-1",
                    "artifact_type": "table",
                    "title": "类别汇总",
                    "summary": {"row_count": 1},
                    "preview": [{"课程类别": "A", "平均完成率": 0.75}],
                }
            ],
            history=[],
        )

    assert raised.value.code == "UNGROUNDED_ANSWER"
    assert "88" not in raised.value.user_message
    assert raised.value.details == {
        "unsupported_numbers": [
            {
                "token": "88",
                "semantic_category": "rate",
            }
        ]
    }


def test_deepseek_rejects_rate_claim_using_unrelated_row_count():
    provider = provider_with(
        lambda _request: response("A 类平均完成率为 88%。")
    )

    with pytest.raises(ProviderError) as raised:
        provider.build_answer(
            "哪个类别完成率低？",
            file_record(),
            evidence=[
                {
                    "artifact_id": "artifact-88",
                    "artifact_type": "table",
                    "title": "2026 年类别汇总",
                    "summary": {"row_count": 88},
                    "preview": [{"课程类别": "A", "平均完成率": 0.75}],
                }
            ],
            history=[],
        )

    assert raised.value.code == "UNGROUNDED_ANSWER"


def test_deepseek_accepts_reasonably_rounded_rate_and_amount_claims():
    provider = provider_with(
        lambda _request: response(
            "平均完成率为 63.1%，平均实付金额为 ￥1,157.34。"
        )
    )

    answer = provider.build_answer(
        "汇总完成率和实付金额",
        file_record(),
        evidence=[
            {
                "artifact_id": "artifact-1",
                "artifact_type": "table",
                "title": "课程汇总",
                "summary": {"row_count": 1},
                "preview": [
                    {
                        "平均完成率": 0.6308301115,
                        "平均实付金额": 1157.3406315789,
                    }
                ],
            }
        ],
        history=[],
    )

    assert "63.1%" in answer
    assert "1,157.34" in answer


def test_deepseek_accepts_grounded_decimals_directly_after_chinese_text():
    provider = provider_with(
        lambda _request: response("完成率91.78%，评分4.64。")
    )

    answer = provider.build_answer(
        "说明完成率和评分",
        file_record(),
        evidence=[
            {
                "artifact_id": "internal-artifact-id",
                "artifact_type": "table",
                "title": "课程汇总",
                "summary": {"row_count": 1},
                "preview": [
                    {
                        "平均完成率": 0.9178,
                        "平均课程评分": 4.64,
                    }
                ],
            }
        ],
        history=[],
    )

    assert "完成率91.78%" in answer
    assert "评分4.64" in answer


def test_deepseek_keeps_numeric_semantics_within_structured_segments():
    provider = provider_with(
        lambda _request: response(
            "完成率91.78% / 评分4.64 / 报名人数6。"
        )
    )

    answer = provider.build_answer(
        "说明完成率、评分和报名人数",
        file_record(),
        evidence=[
            {
                "artifact_id": "internal-artifact-id",
                "artifact_type": "table",
                "title": "课程汇总",
                "summary": {"row_count": 1},
                "preview": [
                    {
                        "平均完成率": 0.9178,
                        "平均课程评分": 4.64,
                        "报名人数": 6,
                    }
                ],
            }
        ],
        history=[],
    )

    assert "完成率91.78% / 评分4.64 / 报名人数6" in answer


def test_deepseek_accepts_numbers_from_the_safe_dataset_profile():
    provider = provider_with(
        lambda _request: response("当前数据集共 120 行、7 列。")
    )

    answer = provider.build_answer(
        "说明数据规模",
        file_record(),
        evidence=[],
        history=[],
    )

    assert "120" in answer
    assert "7" in answer


def test_deepseek_accepts_quantile_evidence_displayed_as_percentage():
    provider = provider_with(
        lambda _request: response("筛选采用 75% 的报名量分位数。")
    )

    answer = provider.build_answer(
        "说明筛选规则",
        file_record(),
        evidence=[
            {
                "artifact_id": "artifact-rule",
                "artifact_type": "table",
                "title": "低表现组合",
                "summary": {
                    "rule": {
                        "high_volume_quantile": 0.75,
                    }
                },
                "preview": [],
            }
        ],
        history=[],
    )

    assert "75%" in answer


def test_deepseek_ignores_markdown_ordinal():
    provider = provider_with(
        lambda _request: response(
            "完成率为 50%。\n"
            "2. 样本数为 6。"
        )
    )

    answer = provider.build_answer(
        "说明结论和证据",
        file_record(),
        evidence=[
            {
                "artifact_id": "internal-artifact-id",
                "artifact_type": "table",
                "title": "课程汇总",
                "summary": {
                    "matched_groups": 6,
                },
                "preview": [
                    {
                        "平均完成率": 0.5,
                        "报名人数": 6,
                    }
                ],
            }
        ],
        history=[],
    )

    assert "2. 样本数为 6" in answer


def test_deepseek_retries_one_server_error_then_succeeds():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": {"message": "temporary"}})
        return response(
            '{"goal":"检查字段","steps":[{"id":"inspect","tool":'
            '"inspect_dataset","purpose":"确认字段","arguments":{}}]}'
        )

    plan = provider_with(handler, max_retries=1).build_plan(
        "检查字段", file_record(), history=[]
    )

    assert calls == 2
    assert plan.steps[0].operation == "inspect_dataset"


def test_deepseek_maps_network_timeout_without_leaking_details():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout at sensitive://private/dataset.xlsx")

    provider = provider_with(handler)

    with pytest.raises(ProviderError) as raised:
        provider.build_plan("检查字段", file_record(), history=[])

    assert raised.value.code == "PROVIDER_TIMEOUT"
    assert raised.value.retryable is True
    assert "private" not in raised.value.user_message


def test_deepseek_rejects_plan_over_tool_round_limit():
    steps = [
        {
            "id": f"inspect-{index}",
            "tool": "inspect_dataset",
            "purpose": "检查字段",
            "arguments": {},
        }
        for index in range(5)
    ]
    provider = provider_with(
        lambda _request: response(
            json.dumps({"goal": "重复检查", "steps": steps}, ensure_ascii=False)
        ),
        max_tool_rounds=4,
    )

    with pytest.raises(ProviderError) as raised:
        provider.build_plan("检查字段", file_record(), history=[])

    assert raised.value.code == "TOOL_ROUND_LIMIT_EXCEEDED"


def test_deepseek_can_repair_one_invalid_tool_step():
    provider = provider_with(
        lambda _request: response(
            json.dumps(
                {
                    "id": "aggregate-repaired",
                    "tool": "group_aggregate",
                    "purpose": "使用可用字段重新汇总",
                    "arguments": {
                        "group_by": ["课程类别"],
                        "metrics": [
                            {
                                "field": None,
                                "aggregation": "count",
                                "alias": "报名人数",
                            }
                        ],
                        "filters": [],
                        "sort": [],
                        "limit": 20,
                    },
                },
                ensure_ascii=False,
            )
        )
    )

    repaired = provider.repair_step(
        "按类别统计",
        file_record(),
        {
            "step_id": "aggregate",
            "operation": "group_aggregate",
            "arguments": {"group_by": ["错误字段"]},
        },
        {
            "code": "SCHEMA_FIELD_NOT_FOUND",
            "message": "字段不存在",
            "details": {"available_fields": ["课程类别", "完成率"]},
        },
        [],
    )

    assert repaired.operation == "group_aggregate"
    assert repaired.arguments["group_by"] == ["课程类别"]


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, "PROVIDER_AUTH_FAILED", False),
        (429, "PROVIDER_RATE_LIMITED", True),
        (500, "PROVIDER_UNAVAILABLE", True),
    ],
)
def test_deepseek_maps_http_errors(status_code, expected_code, retryable):
    provider = provider_with(
        lambda _request: httpx.Response(
            status_code, json={"error": {"message": "secret upstream detail"}}
        )
    )

    with pytest.raises(ProviderError) as raised:
        provider.build_plan("检查字段", file_record(), history=[])

    assert raised.value.code == expected_code
    assert raised.value.retryable is retryable
    assert "secret upstream detail" not in raised.value.user_message


def test_deepseek_rejects_missing_api_key_without_network():
    provider = DeepSeekProvider(
        api_key="",
        base_url="https://unit.test",
        model="deepseek-chat",
        timeout_seconds=1,
        max_retries=0,
        max_tool_rounds=4,
        max_prompt_chars=8_000,
    )

    with pytest.raises(ProviderError) as raised:
        provider.build_plan("检查字段", file_record(), history=[])

    assert raised.value.code == "PROVIDER_NOT_CONFIGURED"
    assert raised.value.retryable is False


@pytest.mark.parametrize("content", ["", "not-json", "{}", '{"goal":"x","steps":[]}'])
def test_deepseek_rejects_invalid_or_empty_plan(content):
    provider = provider_with(lambda _request: response(content))

    with pytest.raises(ProviderError) as raised:
        provider.build_plan("检查字段", file_record(), history=[])

    assert raised.value.code == "PROVIDER_INVALID_RESPONSE"
