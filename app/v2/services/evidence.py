from dataclasses import dataclass
from typing import Any, Literal

from app.v2.schemas.conclusions import StructuredConclusion


EvidenceUnit = Literal[
    "count",
    "percentage",
    "currency",
    "score",
    "number",
    "text",
]


class ConclusionEvidenceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        unknown_count: int = 0,
    ):
        super().__init__(message)
        self.code = code
        self.unknown_count = unknown_count


@dataclass(frozen=True)
class EvidenceItem:
    key: str
    run_id: str
    source_artifact_id: str
    source_tool: str
    label: str
    value: Any
    display_value: str
    unit: EvidenceUnit
    dimensions: dict[str, str]
    sample_size: int | None = None

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "display_value": self.display_value,
            "unit": self.unit,
            "dimensions": self.dimensions,
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class EvidenceAliasEntry:
    alias: str
    item: EvidenceItem

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "label": self.item.label,
            "display_value": self.item.display_value,
            "unit": self.item.unit,
            "dimensions": self.item.dimensions,
            "sample_size": self.item.sample_size,
        }


class EvidenceAliasMap:
    def __init__(self, run_id: str, entries: list[EvidenceAliasEntry]):
        self.run_id = run_id
        self.entries = tuple(entries)
        self._by_alias = {entry.alias: entry.item for entry in entries}
        self._alias_by_key = {
            entry.item.key: entry.alias for entry in entries
        }
        if len(self._by_alias) != len(entries):
            raise ValueError("evidence aliases must be unique")

    def prompt_payload(self) -> list[dict[str, Any]]:
        return [entry.prompt_payload() for entry in self.entries]

    def alias_for_key(self, key: str) -> str:
        try:
            return self._alias_by_key[key]
        except KeyError as exc:
            raise ConclusionEvidenceError(
                "UNKNOWN_EVIDENCE_REFERENCE",
                "evidence key is not part of the current conclusion request",
                unknown_count=1,
            ) from exc

    def validate_conclusion(
        self,
        conclusion: StructuredConclusion,
    ) -> StructuredConclusion:
        referenced = [
            alias
            for finding in conclusion.findings
            for alias in finding.evidence_refs
        ]
        referenced.extend(
            alias
            for recommendation in conclusion.recommendations
            for alias in recommendation.evidence_refs
        )
        unknown = sorted(
            {alias for alias in referenced if alias not in self._by_alias}
        )
        if unknown:
            raise ConclusionEvidenceError(
                "UNKNOWN_EVIDENCE_REFERENCE",
                "conclusion references evidence outside the current alias map",
                unknown_count=len(unknown),
            )
        return conclusion

    def get(self, alias: str) -> EvidenceItem:
        try:
            return self._by_alias[alias]
        except KeyError as exc:
            raise ConclusionEvidenceError(
                "UNKNOWN_EVIDENCE_REFERENCE",
                "evidence alias is not part of the current conclusion request",
                unknown_count=1,
            ) from exc


class EvidenceRegistry:
    def __init__(self, run_id: str, items: list[EvidenceItem]):
        self.run_id = run_id
        self.items = tuple(items)
        self._by_key = {item.key: item for item in items}
        if len(self._by_key) != len(items):
            raise ValueError("evidence keys must be unique")

    @classmethod
    def from_tool_evidence(
        cls,
        run_id: str,
        evidence: list[dict[str, Any]],
    ) -> "EvidenceRegistry":
        items: list[EvidenceItem] = []
        for artifact_index, artifact in enumerate(evidence):
            if artifact.get("artifact_type") == "chart":
                continue
            source_artifact_id = str(artifact.get("artifact_id") or "")
            source_tool = str(artifact.get("source_tool") or "unknown")
            preview = artifact.get("preview") or []
            for row_index, row in enumerate(preview):
                if not isinstance(row, dict):
                    continue
                dimensions = {
                    str(field): str(value)
                    for field, value in row.items()
                    if isinstance(value, str)
                }
                sample_size = cls._sample_size(row)
                for field_index, (field, value) in enumerate(row.items()):
                    if value is None or isinstance(value, str):
                        continue
                    unit = cls._infer_unit(str(field), value)
                    label_prefix = " / ".join(dimensions.values())
                    label = (
                        f"{label_prefix} · {field}"
                        if label_prefix
                        else str(field)
                    )
                    items.append(
                        EvidenceItem(
                            key=(
                                f"evidence.a{artifact_index}."
                                f"r{row_index}.f{field_index}"
                            ),
                            run_id=run_id,
                            source_artifact_id=source_artifact_id,
                            source_tool=source_tool,
                            label=label,
                            value=value,
                            display_value=cls._format_value(value, unit),
                            unit=unit,
                            dimensions=dimensions,
                            sample_size=sample_size,
                        )
                    )
            summary = artifact.get("summary") or {}
            for summary_index, (path, value) in enumerate(
                cls._numeric_summary_values(summary)
            ):
                unit = cls._infer_unit(path, value)
                items.append(
                    EvidenceItem(
                        key=(
                            f"evidence.a{artifact_index}."
                            f"summary.f{summary_index}"
                        ),
                        run_id=run_id,
                        source_artifact_id=source_artifact_id,
                        source_tool=source_tool,
                        label=path,
                        value=value,
                        display_value=cls._format_value(value, unit),
                        unit=unit,
                        dimensions={},
                    )
                )
        return cls(run_id, items)

    def validate_conclusion(
        self,
        conclusion: StructuredConclusion,
    ) -> StructuredConclusion:
        referenced = [
            key
            for finding in conclusion.findings
            for key in finding.evidence_refs
        ]
        referenced.extend(
            key
            for recommendation in conclusion.recommendations
            for key in recommendation.evidence_refs
        )
        unknown = sorted({key for key in referenced if key not in self._by_key})
        if unknown:
            raise ConclusionEvidenceError(
                "UNKNOWN_EVIDENCE_REFERENCE",
                "conclusion references evidence outside the current run",
                unknown_count=len(unknown),
            )
        return conclusion

    def create_alias_map(
        self,
        items: tuple[EvidenceItem, ...] | list[EvidenceItem],
    ) -> EvidenceAliasMap:
        selected = list(items)
        if any(item.run_id != self.run_id for item in selected):
            raise ConclusionEvidenceError(
                "CROSS_RUN_EVIDENCE_REFERENCE",
                "evidence belongs to a different run",
            )
        return EvidenceAliasMap(
            self.run_id,
            [
                EvidenceAliasEntry(alias=f"e{index}", item=item)
                for index, item in enumerate(selected, start=1)
            ],
        )

    def validate_alias_map(self, aliases: EvidenceAliasMap) -> None:
        if aliases.run_id != self.run_id:
            raise ConclusionEvidenceError(
                "CROSS_RUN_EVIDENCE_REFERENCE",
                "evidence aliases belong to a different run",
            )

    def get(self, key: str) -> EvidenceItem:
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise ConclusionEvidenceError(
                "UNKNOWN_EVIDENCE_REFERENCE",
                "evidence does not belong to the current run",
                unknown_count=1,
            ) from exc

    def prompt_payload(self) -> list[dict[str, Any]]:
        return [item.prompt_payload() for item in self.items]

    @staticmethod
    def _sample_size(row: dict[str, Any]) -> int | None:
        for field, value in row.items():
            if EvidenceRegistry._infer_unit(str(field), value) == "count":
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _infer_unit(field: str, value: Any) -> EvidenceUnit:
        normalized = field.lower()
        if any(
            marker in normalized
            for marker in (
                "完成率",
                "退款率",
                "折扣率",
                "比例",
                "百分比",
                "quantile",
                "rate",
                "percentage",
                "completion",
                "refund",
            )
        ):
            return "percentage"
        if any(
            marker in normalized
            for marker in (
                "金额",
                "收入",
                "销售额",
                "成本",
                "价格",
                "amount",
                "revenue",
                "sales",
                "cost",
                "price",
            )
        ):
            return "currency"
        if any(
            marker in normalized
            for marker in ("评分", "得分", "score", "rating")
        ):
            return "score"
        if any(
            marker in normalized
            for marker in (
                "人数",
                "数量",
                "记录数",
                "样本量",
                "row_count",
                "count",
                "matched_groups",
                "scanned_rows",
            )
        ):
            return "count"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "number"
        return "text"

    @staticmethod
    def _format_value(value: Any, unit: EvidenceUnit) -> str:
        number = float(value) if isinstance(value, (int, float)) else None
        if unit == "percentage" and number is not None:
            percentage = number * 100 if -1 <= number <= 1 else number
            return f"{percentage:.2f}%"
        if unit == "currency" and number is not None:
            return f"¥{number:,.2f}"
        if unit == "count" and number is not None:
            return f"{int(number):,} 人"
        if unit == "score" and number is not None:
            return f"{number:.2f} 分"
        if unit == "number" and number is not None:
            return f"{number:,.2f}".rstrip("0").rstrip(".")
        return str(value)

    @classmethod
    def _numeric_summary_values(
        cls,
        value: Any,
        path: str = "",
    ):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            yield path or "value", value
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                nested_path = f"{path}.{key}" if path else str(key)
                yield from cls._numeric_summary_values(nested, nested_path)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                nested_path = f"{path}.{index}" if path else str(index)
                yield from cls._numeric_summary_values(nested, nested_path)
