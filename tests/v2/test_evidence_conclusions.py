import pytest
from pydantic import ValidationError

from app.v2.schemas.conclusions import StructuredConclusion
from app.v2.services.evidence import (
    ConclusionEvidenceError,
    EvidenceRegistry,
)
from app.v2.services.markdown_renderer import ConclusionMarkdownRenderer


def evidence_payload():
    return [
        {
            "artifact_id": "4a405bae-50e7-46ab-a195-9630d03736fb",
            "artifact_type": "table",
            "source_tool": "group_aggregate",
            "title": "课程汇总",
            "summary": {"scanned_rows": 321},
            "preview": [
                {
                    "课程类别": "AI 应用",
                    "报名人数": 153,
                    "平均完成率": 0.5121,
                    "实付金额": 12345.6,
                    "平均课程评分": 4.25,
                }
            ],
            "warnings": [],
        }
    ]


def conclusion_for(keys: list[str]) -> StructuredConclusion:
    return StructuredConclusion.model_validate(
        {
            "headline": "课程运营表现",
            "overview": "AI 应用课程仍有提升空间。",
            "findings": [
                {
                    "title": "主要发现",
                    "statement": "AI 应用课程完成表现偏弱。",
                    "evidence_keys": keys,
                }
            ],
            "recommendations": [
                {
                    "action": "增加分阶段学习提醒。",
                    "reason": "该课程类别需要重点运营。",
                    "evidence_keys": keys[:1],
                }
            ],
            "limitations": ["评分均值仅基于非空记录计算。"],
        }
    )


def test_registry_formats_structured_business_units():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )

    by_label = {item.label: item for item in registry.items}
    assert by_label["AI 应用 · 报名人数"].unit == "count"
    assert by_label["AI 应用 · 报名人数"].display_value == "153 人"
    assert by_label["AI 应用 · 平均完成率"].unit == "percentage"
    assert by_label["AI 应用 · 平均完成率"].display_value == "51.21%"
    assert by_label["AI 应用 · 实付金额"].unit == "currency"
    assert by_label["AI 应用 · 实付金额"].display_value == "¥12,345.60"
    assert by_label["AI 应用 · 平均课程评分"].unit == "score"
    assert by_label["AI 应用 · 平均课程评分"].display_value == "4.25 分"
    assert len({item.key for item in registry.items}) == len(registry.items)


def test_conclusion_references_only_current_registry():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )
    key = next(
        item.key for item in registry.items if item.unit == "percentage"
    )

    validated = registry.validate_conclusion(conclusion_for([key]))

    assert validated.findings[0].evidence_keys == [key]


def test_conclusion_rejects_unknown_or_other_run_evidence():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )

    with pytest.raises(ConclusionEvidenceError):
        registry.validate_conclusion(
            conclusion_for(["evidence.run-other.a0.r0.f0"])
        )


def test_conclusion_requires_evidence_for_each_finding():
    payload = conclusion_for(["placeholder"]).model_dump()
    payload["findings"][0]["evidence_keys"] = []

    with pytest.raises(ValidationError):
        StructuredConclusion.model_validate(payload)


def test_conclusion_rejects_model_authored_business_numbers():
    payload = conclusion_for(["placeholder"]).model_dump()
    payload["findings"][0]["statement"] = "完成率为 51.21%。"

    with pytest.raises(ValidationError):
        StructuredConclusion.model_validate(payload)


def test_renderer_injects_values_without_internal_keys_or_uuids():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )
    keys = [
        item.key
        for item in registry.items
        if item.unit in {"count", "percentage"}
    ]
    conclusion = registry.validate_conclusion(conclusion_for(keys))

    markdown = ConclusionMarkdownRenderer().render(
        conclusion,
        registry,
    )

    assert "# 课程运营表现" in markdown
    assert "153 人" in markdown
    assert "51.21%" in markdown
    assert "evidence." not in markdown
    assert "4a405bae-50e7-46ab-a195-9630d03736fb" not in markdown
