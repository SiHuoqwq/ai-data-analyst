from collections import defaultdict

from app.v2.services.evidence import EvidenceItem, EvidenceRegistry


class DeterministicGroundedAnswerRenderer:
    """Render a useful answer using verified evidence only."""

    def render(
        self,
        registry: EvidenceRegistry,
        artifact_types: set[str],
    ) -> str:
        if not registry.items:
            raise ValueError("deterministic answer requires evidence")

        sources = sorted(
            {
                item.source_tool
                for item in registry.items
                if item.source_tool != "unknown"
            }
        )
        dimensions = self._unique(
            field for item in registry.items for field in item.dimensions
        )
        metrics = self._metric_names(registry.items)
        overview = []
        if sources:
            overview.append(f"已完成{'、'.join(sources)}分析")
        if dimensions:
            overview.append(f"分析维度包括{'、'.join(dimensions[:8])}")
        if metrics:
            overview.append(f"分析指标包括{'、'.join(metrics[:8])}")

        lines = [
            "# 数据分析结论",
            "",
            "## 分析概览",
            "",
            "；".join(overview) + "。",
            "",
            "## 关键结果",
            "",
        ]
        lines.extend(
            f"- {item.label}：{item.display_value}"
            for item in self._representative_items(registry.items)
        )
        lines.extend(self._trend_findings(registry.items))
        lines.extend(self._underperforming_findings(registry.items))

        generated = [
            label
            for artifact_type, label in (
                ("table", "结构化结果表"),
                ("chart", "对应图表"),
            )
            if artifact_type in artifact_types
        ]
        if generated:
            lines.extend(
                [
                    "",
                    f"{'和'.join(generated)}已经生成，完整明细请查看对应结果。",
                ]
            )

        lines.extend(["", "## 运营建议", ""])
        lines.extend(
            f"- {text}\n  - 依据：{item.label}：{item.display_value}"
            for text, item in self._recommendations(registry.items)
        )

        lines.extend(
            [
                "",
                "## 数据限制",
                "",
                "- 缺失值沿用分析工具的既定处理规则。",
                "- 成交金额等汇总值只使用非空记录计算。",
                "- 当前结果反映数据关联，不代表因果关系。",
                "- 表格或图表可能仅展示重点结果；趋势判断使用本次工具返回的完整聚合数据。",
            ]
        )
        return "\n".join(lines).strip()

    @staticmethod
    def _unique(values) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @classmethod
    def _metric_names(
        cls, items: tuple[EvidenceItem, ...]
    ) -> list[str]:
        return cls._unique(
            item.label.rsplit(" · ", 1)[-1] for item in items
        )

    @staticmethod
    def _representative_items(
        items: tuple[EvidenceItem, ...],
    ) -> list[EvidenceItem]:
        selected: list[EvidenceItem] = []
        selected_keys: set[str] = set()

        # Always cover the principal semantic units before filling by source.
        for unit in ("count", "percentage", "currency", "number"):
            item = next((item for item in items if item.unit == unit), None)
            if item is not None:
                selected.append(item)
                selected_keys.add(item.key)

        grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in items:
            grouped[item.source_artifact_id].append(item)
        index = 0
        while len(selected) < 16:
            added = False
            for group in grouped.values():
                if index >= len(group):
                    continue
                candidate = group[index]
                if candidate.key in selected_keys:
                    continue
                selected.append(candidate)
                selected_keys.add(candidate.key)
                added = True
                if len(selected) == 16:
                    break
            if not added and all(index >= len(group) - 1 for group in grouped.values()):
                break
            index += 1
        return selected

    @staticmethod
    def _trend_findings(
        items: tuple[EvidenceItem, ...],
    ) -> list[str]:
        monthly = [
            item for item in items if item.source_tool == "monthly_trend"
        ]
        if not monthly:
            return []

        months = sorted(
            {
                value
                for item in monthly
                for field, value in item.dimensions.items()
                if "月" in field or "month" in field.lower()
            }
        )
        lines = []
        signal_labels = {
            "fastest_growth.change_rate": "增长最快的类别",
            "largest_decline.change_rate": "下降最大的类别",
            "most_volatile.change_rate_stddev": "波动最大的类别",
        }
        for item in monthly:
            marker = ".by_metric."
            if marker not in item.label:
                continue
            tail = item.label.split(marker, 1)[1]
            metric, _, signal_path = tail.partition(".")
            description = signal_labels.get(signal_path)
            category = item.dimensions.get("category")
            if not description or not category:
                continue
            lines.append(
                f"- {metric}{description}为{category}："
                f"{item.display_value}。"
            )

        if months:
            lines.extend(
                [
                    "",
                    f"- 趋势分析覆盖 {months[0]} 至 {months[-1]}；"
                    "增长、下降和波动判断基于完整月度聚合结果。",
                ]
            )

        by_metric: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in monthly:
            by_metric[item.label.rsplit(" · ", 1)[-1]].append(item)
        for metric, values in list(by_metric.items())[:3]:
            numeric = [
                item
                for item in values
                if isinstance(item.value, (int, float))
                and not isinstance(item.value, bool)
            ]
            if len(numeric) < 2:
                continue
            low = min(numeric, key=lambda item: float(item.value))
            high = max(numeric, key=lambda item: float(item.value))
            lines.append(
                f"- {metric}的完整趋势中，较低值为"
                f"{low.label}：{low.display_value}；较高值为"
                f"{high.label}：{high.display_value}。"
            )
        return lines

    @staticmethod
    def _recommendations(
        items: tuple[EvidenceItem, ...],
    ) -> list[tuple[str, EvidenceItem]]:
        recommendations: list[tuple[str, EvidenceItem]] = []
        underperforming = next(
            (
                item
                for item in items
                if item.source_tool == "identify_underperforming"
                and item.unit == "percentage"
            ),
            None,
        )
        monthly = next(
            (
                item
                for item in items
                if item.source_tool == "monthly_trend"
            ),
            None,
        )
        if underperforming:
            recommendations.append(
                (
                    "针对高线索量、低成交转化的组合，重点排查到访与认购环节"
                    "的转化瓶颈并优化跟进节奏。",
                    underperforming,
                )
            )
        if monthly:
            recommendations.append(
                (
                    "结合月度变化检查同期获客渠道投放节奏与推盘安排。",
                    monthly,
                )
            )
        if not recommendations:
            recommendations.append(
                (
                    "持续跟踪重点分组，并结合结构化结果安排后续销售跟进动作。",
                    items[0],
                )
            )
        return recommendations[:4]

    @staticmethod
    def _underperforming_findings(
        items: tuple[EvidenceItem, ...],
    ) -> list[str]:
        underperforming = [
            item
            for item in items
            if item.source_tool == "identify_underperforming"
        ]
        if not underperforming:
            return []

        matched_groups = next(
            (
                item
                for item in underperforming
                if item.label == "matched_groups"
            ),
            None,
        )
        count = 0
        if (
            matched_groups is not None
            and isinstance(matched_groups.value, (int, float))
            and not isinstance(matched_groups.value, bool)
        ):
            count = int(matched_groups.value)

        lines = ["", "## 低表现组合", ""]
        if count == 0:
            lines.append("未检测到符合条件的低表现组合。")
            return lines

        lines.append(f"检测到 {count} 个高线索、低成交转化组合。")
        lines.append("")

        grouped: dict[tuple[tuple[str, str], ...], dict[str, str]] = defaultdict(dict)
        dimension_text: dict[tuple[tuple[str, str], ...], str] = {}
        for item in underperforming:
            if not item.dimensions:
                continue
            key = tuple(sorted(item.dimensions.items()))
            dimension_text[key] = " / ".join(item.dimensions.values())
            field = item.label.rsplit(" · ", 1)[-1]
            grouped[key][field] = item.display_value

        for key, fields in grouped.items():
            dim = dimension_text.get(key, "")
            lead = fields.get("lead_count", "—")
            deal = fields.get("deal_count", "—")
            rate = fields.get("deal_rate", "—")
            prefix = f"{dim}：" if dim else ""
            lines.append(
                f"- {prefix}线索数 {lead}，成交套数 {deal}，成交转化率 {rate}。"
            )
        return lines
