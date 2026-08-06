import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.models import FileModel
from app.v2.db.models import DatasetRecommendationModel, as_utc, utc_now
from app.v2.domain.learning_registry import LearningDomainRegistry
from app.v2.schemas.recommendations import (
    RecommendationCandidate,
    RecommendationGeneration,
)
from app.v2.services.plan_compiler import PlanCompilationError
from app.v2.services.provider import DeepSeekProvider


@dataclass(frozen=True)
class RecommendationResult:
    dataset_version_id: str
    recommendations: list[dict[str, Any]]
    source: str
    generated_at: Any


class RecommendationServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DatasetRecommendationService:
    def __init__(
        self,
        session_factory: Callable = SessionLocal,
        registry: LearningDomainRegistry | None = None,
    ):
        self.session_factory = session_factory
        self.registry = registry or LearningDomainRegistry()

    def get_or_generate(self, dataset_version_id: str, provider) -> RecommendationResult:
        session = self.session_factory()
        try:
            cached = (
                session.query(DatasetRecommendationModel)
                .filter_by(dataset_version_id=dataset_version_id)
                .first()
            )
            if cached:
                return self._result_from_model(cached)

            file_record = session.get(FileModel, dataset_version_id)
            if not file_record:
                raise RecommendationServiceError(
                    "DATASET_NOT_FOUND", "Dataset does not exist.", 404
                )

            accepted = (
                []
                if getattr(provider, "name", None) == "fake"
                else self._model_recommendations(file_record, provider)
            )
            source = "model" if accepted else "template"
            if not accepted:
                accepted = self._template_recommendations(file_record)

            now = utc_now()
            row = DatasetRecommendationModel(
                id=str(uuid.uuid4()),
                dataset_version_id=dataset_version_id,
                recommendations_json=accepted,
                source=source,
                provider_name=(getattr(provider, "name", None) if source == "model" else None),
                provider_model=(getattr(provider, "model", None) if source == "model" else None),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                winner = (
                    session.query(DatasetRecommendationModel)
                    .filter_by(dataset_version_id=dataset_version_id)
                    .first()
                )
                if winner:
                    return self._result_from_model(winner)
                raise
            session.refresh(row)
            return self._result_from_model(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _model_recommendations(
        self, file_record: FileModel, provider
    ) -> list[dict[str, Any]]:
        try:
            generation = provider.recommend_questions(file_record)
        except Exception:
            return []
        candidates = getattr(generation, "candidates", [])
        accepted: list[dict[str, Any]] = []
        accepted_intents: set[str] = set()
        for candidate in candidates:
            parsed = self._validated_candidate(candidate, file_record)
            if parsed is None or parsed.intent_type in accepted_intents:
                continue
            accepted.append(self._public_candidate(parsed, file_record))
            accepted_intents.add(parsed.intent_type)
        return accepted

    def _template_recommendations(
        self, file_record: FileModel
    ) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        for candidate in self._template_candidates(file_record):
            parsed = self._validated_candidate(candidate, file_record)
            if parsed is None or any(
                item["intent_type"] == parsed.intent_type for item in accepted
            ):
                continue
            accepted.append(self._public_candidate(parsed, file_record))
        return accepted

    def _validated_candidate(
        self, candidate: object, file_record: FileModel
    ) -> RecommendationCandidate | None:
        try:
            parsed = RecommendationCandidate.model_validate(candidate)
            if self._contains_physical_path(parsed, file_record):
                return None
            if any(
                not self._is_public_field(field)
                for field in parsed.referenced_fields
            ):
                return None
            DeepSeekProvider._validate_recommendation_candidates(
                RecommendationGeneration(candidates=[parsed]), file_record
            )
            return parsed
        except (PlanCompilationError, ValidationError, TypeError, ValueError):
            return None

    @staticmethod
    def _contains_physical_path(
        candidate: RecommendationCandidate, file_record: FileModel
    ) -> bool:
        text = f"{candidate.label}\n{candidate.question}"
        if file_record.filepath and file_record.filepath in text:
            return True
        return bool(
            re.search(r"[A-Za-z]:[\\/]", text)
            or re.search(r"(?<!\S)/(?:[^\s/]+/)+[^\s/]+", text)
            or "\\\\" in text
        )

    @staticmethod
    def _is_public_field(field: str) -> bool:
        if any(character in field for character in ("/", "\\", ":")):
            return False
        return not bool(
            re.search(
                r"(?i)(?:^|[_\-\s])(?:api[_-]?key|api|access[_-]?token|token|"
                r"secret|password|passwd|credential|authorization|auth|key)"
                r"(?:$|[_\-\s])",
                field,
            )
        )

    def _template_candidates(
        self, file_record: FileModel
    ) -> list[RecommendationCandidate]:
        field_types = {
            str(item.get("name")): str(item.get("dtype", "")).lower()
            for item in (file_record.columns_info or [])
            if item.get("name") and self._is_public_field(str(item["name"]))
        }
        ordered_fields = self._registry_ordered_fields(field_types)

        def is_metric(field: str) -> bool:
            return any(
                marker in field_types[field]
                for marker in ("float", "decimal", "number", "bool")
            )

        def is_date_hint(field: str) -> bool:
            registry_date_fields = {
                item.source_field for item in self.registry.dates.values()
            }
            return (
                "date" in field_types[field]
                or "time" in field_types[field]
                or field in registry_date_fields
            )

        dimensions = [
            field
            for field in ordered_fields
            if not is_metric(field) and not is_date_hint(field)
        ]
        metrics = [field for field in ordered_fields if is_metric(field)]
        dates = [field for field in ordered_fields if is_date_hint(field)]
        candidates: list[RecommendationCandidate] = []
        if dimensions:
            dimension = dimensions[0]
            referenced_fields = [dimension, *metrics[:1]]
            candidates.append(
                RecommendationCandidate(
                    intent_type="group_comparison",
                    label=f"Compare by {self._field_label(dimension)}",
                    question=f"How do key outcomes compare across {self._field_label(dimension)}?",
                    referenced_fields=referenced_fields,
                )
            )
        if dimensions and dates:
            dimension = dimensions[0]
            date_field = dates[0]
            referenced_fields = [dimension, date_field, *metrics[:1]]
            candidates.append(
                RecommendationCandidate(
                    intent_type="monthly_trend",
                    label=f"Monthly {self._field_label(dimension)} trend",
                    question=(
                        f"How does {self._field_label(dimension)} change by month "
                        f"using {self._field_label(date_field)}?"
                    ),
                    referenced_fields=referenced_fields,
                )
            )
        return candidates

    def _registry_ordered_fields(self, field_types: dict[str, str]) -> list[str]:
        registry_fields = [
            *(item.source_field for item in self.registry.dimensions.values()),
            *(item.source_field for item in self.registry.dates.values()),
            *(
                item.source_field
                for item in self.registry.metrics.values()
                if item.source_field is not None
            ),
        ]
        preferred = [field for field in registry_fields if field in field_types]
        return list(dict.fromkeys([*preferred, *field_types]))

    def _field_label(self, field: str) -> str:
        for definition in self.registry.dimensions.values():
            if definition.source_field == field:
                return definition.label
        for definition in self.registry.dates.values():
            if definition.source_field == field:
                return definition.label
        for definition in self.registry.metrics.values():
            if definition.source_field == field:
                return definition.label
        return field

    def _public_candidate(
        self,
        candidate: RecommendationCandidate,
        file_record: FileModel,
    ) -> dict[str, Any]:
        field_types = {
            str(item.get("name")): str(item.get("dtype", "")).lower()
            for item in (file_record.columns_info or [])
        }

        def is_metric(field: str) -> bool:
            return any(
                marker in field_types.get(field, "")
                for marker in ("float", "decimal", "number", "bool")
            )

        def is_date(field: str) -> bool:
            return "date" in field_types.get(field, "") or "time" in field_types.get(
                field, ""
            )

        dimensions = [
            field
            for field in candidate.referenced_fields
            if not is_metric(field) and not is_date(field)
        ]
        dimension = dimensions[0] if dimensions else None
        if candidate.intent_type == "group_comparison" and dimension:
            label = f"Compare by {self._field_label(dimension)}"
            question = (
                f"How do key outcomes compare across {self._field_label(dimension)}?"
            )
        elif candidate.intent_type == "monthly_trend" and dimension:
            label = f"Monthly {self._field_label(dimension)} trend"
            question = (
                f"How does {self._field_label(dimension)} change by month?"
            )
        else:
            label = "Monthly selected-field trend"
            question = "How do the selected fields change by month?"
        return {
            "id": f"{candidate.intent_type}-1",
            "intent_type": candidate.intent_type,
            "label": label,
            "question": question,
            "referenced_fields": list(candidate.referenced_fields),
        }

    @staticmethod
    def _result_from_model(row: DatasetRecommendationModel) -> RecommendationResult:
        return RecommendationResult(
            dataset_version_id=row.dataset_version_id,
            recommendations=list(row.recommendations_json),
            source=row.source,
            generated_at=as_utc(row.created_at),
        )
