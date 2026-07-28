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
                    "evidence_refs": keys,
                }
            ],
            "recommendations": [
                {
                    "action": "增加分阶段学习提醒。",
                    "reason": "该课程类别需要重点运营。",
                    "evidence_refs": keys[:1],
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

    aliases = registry.create_alias_map(registry.items)
    alias = aliases.alias_for_key(key)
    validated = aliases.validate_conclusion(conclusion_for([alias]))

    assert validated.findings[0].evidence_refs == [alias]


def test_conclusion_rejects_unknown_or_other_run_evidence():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )

    aliases = registry.create_alias_map(registry.items)

    with pytest.raises(ConclusionEvidenceError) as unknown:
        aliases.validate_conclusion(conclusion_for(["e999"]))
    assert unknown.value.code == "UNKNOWN_EVIDENCE_REFERENCE"

    other_registry = EvidenceRegistry.from_tool_evidence(
        "run-other",
        evidence_payload(),
    )
    other_aliases = other_registry.create_alias_map(other_registry.items)
    with pytest.raises(ConclusionEvidenceError) as cross_run:
        registry.validate_alias_map(other_aliases)
    assert cross_run.value.code == "CROSS_RUN_EVIDENCE_REFERENCE"


def test_conclusion_requires_evidence_for_each_finding():
    payload = conclusion_for(["placeholder"]).model_dump()
    payload["findings"][0]["evidence_refs"] = []

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
    aliases = registry.create_alias_map(
        [item for item in registry.items if item.key in keys]
    )
    conclusion = aliases.validate_conclusion(
        conclusion_for([entry.alias for entry in aliases.entries])
    )

    markdown = ConclusionMarkdownRenderer().render(
        conclusion,
        aliases,
    )

    assert "# 课程运营表现" in markdown
    assert "153 人" in markdown
    assert "51.21%" in markdown
    assert "evidence." not in markdown
    assert "e1" not in markdown
    assert "4a405bae-50e7-46ab-a195-9630d03736fb" not in markdown


def test_compact_aliases_are_stable_and_bound_to_the_current_run():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )

    first = registry.create_alias_map(registry.items[:2])
    second = registry.create_alias_map(registry.items[:2])

    assert [entry.alias for entry in first.entries] == ["e1", "e2"]
    assert first.prompt_payload() == second.prompt_payload()
    assert all("key" not in item for item in first.prompt_payload())
    assert all("source_artifact_id" not in item for item in first.prompt_payload())
    assert first.run_id == "run-current"
