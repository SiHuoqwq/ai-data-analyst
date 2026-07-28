from app.v2.schemas.conclusions import StructuredConclusion
from app.v2.services.evidence import EvidenceRegistry


class ConclusionMarkdownRenderer:
    def render(
        self,
        conclusion: StructuredConclusion,
        registry: EvidenceRegistry,
    ) -> str:
        lines = [f"# {conclusion.headline}", "", conclusion.overview]
        lines.extend(["", "## 关键发现"])
        for finding in conclusion.findings:
            lines.extend(
                [
                    "",
                    f"### {finding.title}",
                    "",
                    finding.statement,
                    "",
                    "数据依据：",
                    "",
                ]
            )
            lines.extend(self._evidence_lines(finding.evidence_keys, registry))
        if conclusion.recommendations:
            lines.extend(["", "## 运营建议"])
            for recommendation in conclusion.recommendations:
                lines.extend(
                    [
                        "",
                        f"- {recommendation.action}",
                        f"  - 原因：{recommendation.reason}",
                    ]
                )
                lines.extend(
                    f"  - 依据：{line[2:]}"
                    for line in self._evidence_lines(
                        recommendation.evidence_keys,
                        registry,
                    )
                )
        if conclusion.limitations:
            lines.extend(["", "## 限制与说明", ""])
            lines.extend(f"- {item}" for item in conclusion.limitations)
        return "\n".join(lines).strip()

    @staticmethod
    def _evidence_lines(
        keys: list[str],
        registry: EvidenceRegistry,
    ) -> list[str]:
        result = []
        seen = set()
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            item = registry.get(key)
            result.append(f"- {item.label}：{item.display_value}")
        return result
