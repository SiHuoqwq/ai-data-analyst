import pytest
from pydantic import ValidationError

from app.v2.schemas.conclusions import StructuredConclusion
from app.v2.services.evidence import (
    ConclusionEvidenceError,
    EvidenceRegistry,
)
from app.v2.services.markdown_renderer import ConclusionMarkdownRenderer
from app.v2.services.deterministic_renderer import (
    DeterministicGroundedAnswerRenderer,
)
from app.v2.services.provider import FakeAnalysisProvider


def evidence_payload():
    return [
        {
            "artifact_id": "4a405bae-50e7-46ab-a195-9630d03736fb",
            "artifact_type": "table",
            "source_tool": "group_aggregate",
            "title": "渠道汇总",
            "summary": {"scanned_rows": 321},
            "preview": [
                {
                    "lead_channel": "线上投放",
                    "lead_count": 153,
                    "deal_rate": 0.5121,
                    "deal_amount_sum": 12345.6,
                    "avg_deal_amount": 425000.0,
                }
            ],
            "warnings": [],
        }
    ]


def conclusion_for(keys: list[str]) -> StructuredConclusion:
    return StructuredConclusion.model_validate(
        {
            "headline": "渠道成交表现",
            "overview": "线上投放渠道成交转化仍有提升空间。",
            "findings": [
                {
                    "title": "主要发现",
                    "statement": "线上投放渠道成交转化表现偏弱。",
                    "evidence_refs": keys,
                }
            ],
            "recommendations": [
                {
                    "action": "进一步检查该渠道的到访与认购环节。",
                    "reason": "该渠道线索量较高但成交转化偏低。",
                    "evidence_refs": keys[:1],
                }
            ],
            "limitations": ["转化率均值仅基于非空记录计算。"],
        }
    )


def test_registry_formats_structured_business_units():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-current",
        evidence_payload(),
    )

    by_label = {item.label: item for item in registry.items}
    assert by_label["线上投放 · lead_count"].unit == "count"
    assert by_label["线上投放 · lead_count"].display_value == "153"
    assert by_label["线上投放 · deal_rate"].unit == "percentage"
    assert by_label["线上投放 · deal_rate"].display_value == "51.21%"
    assert by_label["线上投放 · deal_amount_sum"].unit == "currency"
    assert by_label["线上投放 · deal_amount_sum"].display_value == "¥12,345.60"
    # avg_deal_amount 虽为派生指标，但单位必须是货币，不能显示成百分比。
    assert by_label["线上投放 · avg_deal_amount"].unit == "currency"
    assert by_label["线上投放 · avg_deal_amount"].display_value == "¥425,000.00"
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
    payload["findings"][0]["statement"] = "成交转化率为 51.21%。"

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

    assert "# 渠道成交表现" in markdown
    assert "153" in markdown
    assert "51.21%" in markdown
    assert "evidence." not in markdown
    assert "e1" not in markdown
    assert "4a405bae-50e7-46ab-a195-9630d03736fb" not in markdown


def test_deterministic_renderer_uses_complete_monthly_trend_signals():
    evidence = [
        {
            "artifact_id": "monthly-table",
            "artifact_type": "table",
            "source_tool": "monthly_trend",
            "title": "月度趋势",
            "summary": {
                "trend_signals": {
                    "by_metric": {
                        "线索数": {
                            "fastest_growth": {
                                "category": "线上投放",
                                "change_rate": 1.0,
                            },
                            "largest_decline": {
                                "category": "渠道分销",
                                "change_rate": -0.6,
                            },
                            "most_volatile": {
                                "category": "自然到访",
                                "change_rate_stddev": 1.466112,
                            },
                        }
                    }
                }
            },
            "preview": [
                {
                    "月份": "2025-01",
                    "lead_channel": "线上投放",
                    "lead_count": 10,
                },
                {
                    "月份": "2026-06",
                    "lead_channel": "线上投放",
                    "lead_count": 4,
                },
            ],
            "warnings": [],
        }
    ]
    registry = EvidenceRegistry.from_tool_evidence("run-monthly", evidence)

    markdown = DeterministicGroundedAnswerRenderer().render(
        registry,
        {"table", "chart"},
    )

    assert "线索数增长最快的类别为线上投放：100.00%" in markdown
    assert "线索数下降最大的类别为渠道分销：-60.00%" in markdown
    assert "线索数波动最大的类别为自然到访：146.61%" in markdown


def test_deterministic_renderer_expresses_underperforming_groups():
    evidence = [
        {
            "artifact_id": "underperforming-table",
            "artifact_type": "table",
            "source_tool": "identify_underperforming",
            "title": "高线索量低成交转化率组合",
            "summary": {"matched_groups": 2},
            "preview": [
                {
                    "dimension_1": "线上投放",
                    "lead_count": 153,
                    "deal_count": 32,
                    "deal_rate": 0.209,
                },
                {
                    "dimension_1": "渠道分销",
                    "lead_count": 120,
                    "deal_count": 18,
                    "deal_rate": 0.15,
                },
            ],
            "warnings": [],
        }
    ]
    registry = EvidenceRegistry.from_tool_evidence("run-underperforming", evidence)

    markdown = DeterministicGroundedAnswerRenderer().render(
        registry,
        {"table"},
    )

    assert "检测到 2 个高线索、低成交转化组合。" in markdown
    assert "线上投放" in markdown
    assert "线索数 153" in markdown
    assert "成交套数 32" in markdown
    assert "成交转化率 20.90%" in markdown
    assert "渠道分销" in markdown


def test_deterministic_renderer_reports_no_underperforming_groups():
    evidence = [
        {
            "artifact_id": "underperforming-table",
            "artifact_type": "table",
            "source_tool": "identify_underperforming",
            "title": "高线索量低成交转化率组合",
            "summary": {"matched_groups": 0},
            "preview": [],
            "warnings": [],
        }
    ]
    registry = EvidenceRegistry.from_tool_evidence("run-underperforming", evidence)

    markdown = DeterministicGroundedAnswerRenderer().render(
        registry,
        {"table"},
    )

    assert "未检测到符合条件的低表现组合。" in markdown


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


def inspect_evidence_payload():
    return [
        {
            "artifact_id": "inspect-artifact",
            "artifact_type": "metric",
            "source_tool": "inspect_dataset",
            "title": "数据记录数",
            "summary": {
                "row_count": 520,
                "column_count": 14,
                "missing_counts": {"到访日期": 236, "认购日期": 300},
            },
            "preview": [],
            "warnings": [],
        }
    ]


def test_registry_humanizes_inspect_metadata_labels():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-demo",
        inspect_evidence_payload(),
    )

    labels = {item.label for item in registry.items}
    assert "数据行数" in labels
    assert "数据列数" in labels
    assert "到访日期 空值数" in labels
    assert not any(
        raw in item.label
        for item in registry.items
        for raw in ("row_count", "column_count", "missing_counts")
    )


def test_fake_conclusion_uses_business_language_without_raw_keys():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-demo",
        inspect_evidence_payload(),
    )
    provider = FakeAnalysisProvider()
    conclusion = provider.build_conclusion("分析销售数据", None, registry)

    markdown = ConclusionMarkdownRenderer().render(
        conclusion,
        provider.last_conclusion_aliases,
    )

    assert "销售经营分析结论" in markdown
    for raw in ("row_count", "column_count", "missing_counts"):
        assert raw not in markdown
    assert "测试分析模式" not in markdown
    assert "确定性分析步骤生成" not in markdown


def test_deterministic_renderer_hides_inspect_metadata_keys():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-demo",
        inspect_evidence_payload(),
    )

    markdown = DeterministicGroundedAnswerRenderer().render(
        registry,
        {"metric"},
    )

    for raw in ("row_count", "column_count", "missing_counts"):
        assert raw not in markdown


def underperforming_evidence_payload():
    return [
        {
            "artifact_id": "inspect-artifact",
            "artifact_type": "metric",
            "source_tool": "inspect_dataset",
            "title": "数据记录数",
            "summary": {
                "row_count": 520,
                "column_count": 14,
                "missing_counts": {"到访日期": 236},
            },
            "preview": [],
            "warnings": [],
        },
        {
            "artifact_id": "underperforming-table",
            "artifact_type": "table",
            "source_tool": "identify_underperforming",
            "title": "高线索量低成交转化率组合",
            "summary": {"matched_groups": 1},
            "preview": [
                {
                    "lead_channel": "短视频平台",
                    "lead_count": 150,
                    "deal_count": 8,
                    "deal_rate": 0.0533,
                }
            ],
            "warnings": [],
        },
    ]


def group_comparison_evidence_payload():
    return [
        {
            "artifact_id": "inspect-artifact",
            "artifact_type": "metric",
            "source_tool": "inspect_dataset",
            "title": "数据记录数",
            "summary": {"row_count": 520, "column_count": 14},
            "preview": [],
            "warnings": [],
        },
        {
            "artifact_id": "group-table",
            "artifact_type": "table",
            "source_tool": "group_aggregate",
            "title": "分组统计结果",
            "summary": {"scanned_rows": 321},
            "preview": [
                {"lead_channel": "线上投放", "lead_count": 153, "deal_count": 32},
                {"lead_channel": "渠道分销", "lead_count": 120, "deal_count": 18},
            ],
            "warnings": [],
        },
    ]


def test_fake_conclusion_prioritizes_underperforming_over_inspection():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-demo",
        underperforming_evidence_payload(),
    )
    provider = FakeAnalysisProvider()
    conclusion = provider.build_conclusion(
        "哪些获客渠道线索多但成交转化率偏低？",
        None,
        registry,
    )

    markdown = ConclusionMarkdownRenderer().render(
        conclusion,
        provider.last_conclusion_aliases,
    )

    assert "高线索低成交转化渠道识别" in markdown
    assert "短视频平台" in markdown
    assert "150" in markdown
    assert "8" in markdown
    assert "5.33%" in markdown
    assert "数据行数" not in markdown
    assert "数据列数" not in markdown


def test_fake_conclusion_prioritizes_group_comparison_over_inspection():
    registry = EvidenceRegistry.from_tool_evidence(
        "run-demo",
        group_comparison_evidence_payload(),
    )
    provider = FakeAnalysisProvider()
    conclusion = provider.build_conclusion(
        "各获客渠道的线索和成交情况如何？",
        None,
        registry,
    )

    markdown = ConclusionMarkdownRenderer().render(
        conclusion,
        provider.last_conclusion_aliases,
    )

    assert "获客渠道对比结论" in markdown
    assert "线上投放" in markdown
    assert "153" in markdown
    assert "数据行数" not in markdown
    assert "数据列数" not in markdown
