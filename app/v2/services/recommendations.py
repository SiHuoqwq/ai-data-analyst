import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Protocol

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
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.plan_compiler import PlanCompilationError
from app.v2.services.recommendation_intents import validated_recommendation_intent
from app.v2.services.recommendation_safety import (
    contains_unsafe_recommendation_content,
    is_public_field_name,
    public_column_metadata,
)


_PROCESS_SINGLE_FLIGHT_GUARD = Lock()
_PROCESS_DATASET_LOCKS: dict[str, Lock] = {}


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


class RecommendationProvider(Protocol):
    name: str
    model: str

    def recommend_questions(
        self, file_record: FileModel
    ) -> RecommendationGeneration: ...


class DatasetRecommendationService:
    def __init__(
        self,
        session_factory: Callable = SessionLocal,
        registry: LearningDomainRegistry | None = None,
    ):
        self.session_factory = session_factory
        self.registry = registry or LearningDomainRegistry()

    def get_or_generate(
        self,
        dataset_version_id: str,
        provider: RecommendationProvider,
    ) -> RecommendationResult:
        """Coalesce first misses for a dataset inside this service process.

        Database uniqueness remains a conflict guard across processes; this
        lock intentionally does not claim cross-process single-flight.
        """
        provider_name, provider_model = self._provider_identity(provider)
        with self._dataset_lock(dataset_version_id):
            return self._get_or_generate_locked(
                dataset_version_id,
                provider,
                provider_name,
                provider_model,
            )

    def _get_or_generate_locked(
        self,
        dataset_version_id: str,
        provider: RecommendationProvider,
        provider_name: str,
        provider_model: str | None,
    ) -> RecommendationResult:
        session = self.session_factory()
        try:
            cached = (
                session.query(DatasetRecommendationModel)
                .filter_by(dataset_version_id=dataset_version_id)
                .first()
            )
            if cached and self._cache_matches(
                cached, provider_name, provider_model
            ):
                return self._result_from_model(cached)

            file_record = session.get(FileModel, dataset_version_id)
            if not file_record:
                raise RecommendationServiceError(
                    "DATASET_NOT_FOUND", "Dataset does not exist.", 404
                )

            accepted = (
                []
                if provider_name == "fake"
                else self._model_recommendations(file_record, provider)
            )
            source = "model" if accepted else "template"
            if not accepted:
                accepted = self._template_recommendations(file_record)

            now = utc_now()
            row = cached or DatasetRecommendationModel(
                id=str(uuid.uuid4()),
                dataset_version_id=dataset_version_id,
            )
            row.recommendations_json = accepted
            row.source = source
            row.provider_name = provider_name
            row.provider_model = provider_model
            row.created_at = now
            row.updated_at = now
            if cached is None:
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
                if winner and self._cache_matches(
                    winner, provider_name, provider_model
                ):
                    return self._result_from_model(winner)
                raise RecommendationServiceError(
                    "RECOMMENDATION_CACHE_CONFLICT",
                    "Recommendation cache was updated by another provider.",
                    503,
                )
            session.refresh(row)
            return self._result_from_model(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _dataset_lock(dataset_version_id: str) -> Lock:
        with _PROCESS_SINGLE_FLIGHT_GUARD:
            return _PROCESS_DATASET_LOCKS.setdefault(dataset_version_id, Lock())

    @staticmethod
    def _provider_identity(
        provider: RecommendationProvider,
    ) -> tuple[str, str | None]:
        name = str(getattr(provider, "name", "") or "").strip()
        model_value = getattr(provider, "model", None)
        model = str(model_value).strip() if model_value is not None else None
        if not name:
            raise RecommendationServiceError(
                "PROVIDER_IDENTITY_REQUIRED",
                "Recommendation provider identity is required.",
                503,
            )
        return name, model or None

    @staticmethod
    def _cache_matches(
        row: DatasetRecommendationModel,
        provider_name: str,
        provider_model: str | None,
    ) -> bool:
        return (
            row.provider_name == provider_name
            and row.provider_model == provider_model
        )

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
            accepted.append(self._public_candidate(parsed))
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
            accepted.append(self._public_candidate(parsed))
        return accepted

    def resolve_template_intent(
        self,
        file_record: FileModel,
        intent_type: str,
    ) -> AnalysisIntent | None:
        for candidate in self._template_candidates(file_record):
            if candidate.intent_type != intent_type:
                continue
            try:
                return validated_recommendation_intent(
                    candidate,
                    file_record,
                )
            except (PlanCompilationError, ValueError):
                return None
        return None

    def _validated_candidate(
        self, candidate: object, file_record: FileModel
    ) -> RecommendationCandidate | None:
        try:
            parsed = RecommendationCandidate.model_validate(candidate)
            available_fields = {
                str(item.get("name"))
                for item in public_column_metadata(file_record.columns_info or [])
            }
            if contains_unsafe_recommendation_content(parsed, file_record):
                return None
            if any(
                field not in available_fields or not is_public_field_name(field)
                for field in parsed.referenced_fields
            ):
                return None
            validated_recommendation_intent(parsed, file_record)
            return parsed
        except (PlanCompilationError, ValidationError, TypeError, ValueError):
            return None

    def _template_candidates(
        self, file_record: FileModel
    ) -> list[RecommendationCandidate]:
        field_types = {
            str(item.get("name")): str(item.get("dtype", "")).lower()
            for item in public_column_metadata(file_record.columns_info or [])
            if item.get("name")
        }
        ordered_fields = self._registry_ordered_fields(field_types)
        metric_definitions = {
            field: definition
            for metric_id, definition in self.registry.metrics.items()
            for field in (metric_id, definition.source_field)
            if field is not None
        }

        def is_metric(field: str) -> bool:
            return field in metric_definitions or any(
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
        metric_semantics = {
            field: definition.semantic
            for field, definition in metric_definitions.items()
        }
        group_metrics = [
            field
            for field in metrics
            if metric_semantics.get(field)
            in {"平均完成率", "退款率", "平均评分"}
        ]
        monthly_metrics = [
            field
            for field in metrics
            if metric_semantics.get(field) in {"实付金额", "平均完成率"}
        ]
        dates = [field for field in ordered_fields if is_date_hint(field)]
        candidates: list[RecommendationCandidate] = []
        if dimensions:
            dimension = dimensions[0]
            referenced_fields = [dimension, *group_metrics[:1]]
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
            referenced_fields = [
                dimension,
                date_field,
                *monthly_metrics[:1],
            ]
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
    ) -> dict[str, Any]:
        return {
            "id": f"{candidate.intent_type}-1",
            "intent_type": candidate.intent_type,
            "label": candidate.label,
            "question": candidate.question,
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
