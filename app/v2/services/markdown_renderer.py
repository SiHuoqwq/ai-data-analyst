from app.v2.schemas.conclusions import StructuredConclusion
from app.v2.services.evidence import EvidenceAliasMap


class ConclusionMarkdownRenderer:
    def render(
        self,
        conclusion: StructuredConclusion,
        aliases: EvidenceAliasMap,
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
            lines.extend(self._evidence_lines(finding.evidence_refs, aliases))
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
                        recommendation.evidence_refs,
                        aliases,
                    )
                )
        if conclusion.limitations:
            lines.extend(["", "## 限制与说明", ""])
            lines.extend(f"- {item}" for item in conclusion.limitations)
        return "\n".join(lines).strip()

    @staticmethod
    def _evidence_lines(
        references: list[str],
        aliases: EvidenceAliasMap,
    ) -> list[str]:
        result = []
        seen = set()
        for reference in references:
            if reference in seen:
                continue
            seen.add(reference)
            item = aliases.get(reference)
            result.append(f"- {item.label}：{item.display_value}")
        return result
