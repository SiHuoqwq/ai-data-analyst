import hashlib
import unicodedata

from app.db.models import FileModel
from app.v2.domain.learning_registry import LearningDomainRegistry
from app.v2.schemas.intents import AnalysisIntent
from app.v2.schemas.recommendations import RecommendationCandidate


class DeterministicRecommendationRenderer:
    """Render public copy from validated intent structure, never model prose."""

    def __init__(self, registry: LearningDomainRegistry | None = None):
        self.registry = registry or LearningDomainRegistry()

    def render(
        self,
        candidate: RecommendationCandidate,
        intent: AnalysisIntent,
        file_record: FileModel,
    ) -> tuple[str, str]:
        dimensions = [
            self._field_slot(field, file_record)
            for field in intent.dimensions
        ]
        dimension = ", ".join(dimensions) or "selected field"
        if candidate.intent_type == "monthly_trend":
            date = self._field_slot(intent.date_field or "date", file_record)
            return (
                f"{dimension}月度趋势",
                f"按{date}月份查看{dimension}的变化趋势",
            )
        return (
            f"按{dimension}比较",
            f"不同{dimension}的关键指标表现有何差异？",
        )

    def _field_slot(self, field: str, file_record: FileModel) -> str:
        trusted_label = self._registry_label(field)
        if trusted_label is not None:
            return trusted_label

        normalized = unicodedata.normalize("NFKC", str(field or "")).strip()
        field_names = [
            str(item.get("name"))
            for item in (file_record.columns_info or [])
        ]
        position = field_names.index(field) + 1 if field in field_names else 0
        digest = hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()
        return f"field-{position}-{digest[:8]}"

    def _registry_label(self, field: str) -> str | None:
        definitions = (
            *self.registry.dimensions.values(),
            *self.registry.dates.values(),
            *self.registry.metrics.values(),
        )
        for definition in definitions:
            if definition.source_field == field:
                return definition.label
        return None
