import hashlib
import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Iterator, Protocol

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
from app.v2.services.recommendation_renderer import (
    DeterministicRecommendationRenderer,
)
from app.v2.services.recommendation_safety import (
    is_public_field_name,
    public_column_metadata,
)


@dataclass
class _DatasetLockEntry:
    lock: Lock
    references: int = 0


_PROCESS_SINGLE_FLIGHT_GUARD = Lock()
_PROCESS_DATASET_LOCKS: dict[str, _DatasetLockEntry] = {}
_CACHE_CONFLICT_RECOVERY_ATTEMPTS = 2


@dataclass(frozen=True)
class RecommendationResult:
    dataset_version_id: str
    recommendations: list[dict[str, Any]]
    source: str
    generated_at: Any


@dataclass(frozen=True)
class _ValidatedRecommendation:
    candidate: RecommendationCandidate
    intent: AnalysisIntent


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
        renderer: DeterministicRecommendationRenderer | None = None,
    ):
        self.session_factory = session_factory
        self.registry = registry or LearningDomainRegistry()
        self.renderer = renderer or DeterministicRecommendationRenderer(
            self.registry
        )

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
            file_record = session.get(FileModel, dataset_version_id)
            if not file_record:
                raise RecommendationServiceError(
                    "DATASET_NOT_FOUND", "Dataset does not exist.", 404
                )
            if cached and self._cache_matches(
                cached, provider_name, provider_model
            ):
                canonical = self._canonical_cached_recommendations(
                    cached,
                    file_record,
                )
                if canonical is not None:
                    if cached.recommendations_json != canonical:
                        cached.recommendations_json = canonical
                        cached.updated_at = utc_now()
                        session.commit()
                        session.refresh(cached)
                    return self._result_from_model(cached, canonical)

            now = utc_now()
            row = cached or DatasetRecommendationModel(
                id=str(uuid.uuid4()),
                dataset_version_id=dataset_version_id,
            )
            row.provider_name = provider_name
            row.provider_model = provider_model
            row.created_at = now
            row.updated_at = now
            accepted = (
                []
                if provider_name == "fake"
                else self._model_recommendations(file_record, provider, row)
            )
            source = "model" if accepted else "template"
            if not accepted:
                accepted = self._template_recommendations(file_record, row)

            row.recommendations_json = accepted
            row.source = source
            if cached is None:
                session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return self._reconcile_cache_conflict(
                    session=session,
                    dataset_version_id=dataset_version_id,
                    file_record=file_record,
                    provider_name=provider_name,
                    provider_model=provider_model,
                    accepted=accepted,
                    source=source,
                )
            session.refresh(row)
            return self._result_from_model(row, accepted)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _reconcile_cache_conflict(
        self,
        *,
        session,
        dataset_version_id: str,
        file_record: FileModel,
        provider_name: str,
        provider_model: str | None,
        accepted: list[dict[str, Any]],
        source: str,
    ) -> RecommendationResult:
        for _attempt in range(_CACHE_CONFLICT_RECOVERY_ATTEMPTS):
            winner = (
                session.query(DatasetRecommendationModel)
                .filter_by(dataset_version_id=dataset_version_id)
                .first()
            )
            if winner is None:
                continue
            if not self._cache_matches(winner, provider_name, provider_model):
                break

            canonical = self._canonical_cached_recommendations(
                winner,
                file_record,
            )
            if canonical is not None:
                return self._result_from_model(winner, canonical)

            # The database winner is unusable, but this request already paid
            # (if applicable) and produced a validated controlled selection.
            # Replace the invalid generation in place and re-render it against
            # the winner's new cache generation instead of calling the provider
            # again. A second conflict is reread only within the fixed bound.
            now = utc_now()
            winner.provider_name = provider_name
            winner.provider_model = provider_model
            winner.source = source
            winner.created_at = now
            winner.updated_at = now
            winner.recommendations_json = accepted
            replacement = self._canonical_cached_recommendations(
                winner,
                file_record,
            )
            if replacement is None:
                break
            winner.recommendations_json = replacement
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                continue
            session.refresh(winner)
            return self._result_from_model(winner, replacement)

        raise RecommendationServiceError(
            "RECOMMENDATION_CACHE_CONFLICT",
            "Recommendation cache could not be reconciled safely.",
            503,
        )

    @staticmethod
    @contextmanager
    def _dataset_lock(dataset_version_id: str) -> Iterator[None]:
        with _PROCESS_SINGLE_FLIGHT_GUARD:
            entry = _PROCESS_DATASET_LOCKS.setdefault(
                dataset_version_id,
                _DatasetLockEntry(lock=Lock()),
            )
            entry.references += 1
        entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            with _PROCESS_SINGLE_FLIGHT_GUARD:
                entry.references -= 1
                if (
                    entry.references == 0
                    and _PROCESS_DATASET_LOCKS.get(dataset_version_id) is entry
                ):
                    del _PROCESS_DATASET_LOCKS[dataset_version_id]

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
        self,
        file_record: FileModel,
        provider,
        row: DatasetRecommendationModel,
    ) -> list[dict[str, Any]]:
        try:
            generation = provider.recommend_questions(file_record)
        except Exception:
            return []
        candidates = getattr(generation, "candidates", [])
        accepted: list[dict[str, Any]] = []
        accepted_intents: set[str] = set()
        for candidate in candidates:
            validated = self._validated_candidate(candidate, file_record)
            if (
                validated is None
                or validated.candidate.intent_type in accepted_intents
            ):
                continue
            accepted.append(self._public_candidate(validated, file_record, row))
            accepted_intents.add(validated.candidate.intent_type)
        return accepted

    def _canonical_cached_recommendations(
        self,
        row: DatasetRecommendationModel,
        file_record: FileModel,
    ) -> list[dict[str, Any]] | None:
        if row.source == "template":
            return self._template_recommendations(file_record, row)
        if row.source != "model" or not isinstance(row.recommendations_json, list):
            return None

        accepted: list[dict[str, Any]] = []
        accepted_intents: set[str] = set()
        for cached_item in row.recommendations_json:
            validated = self._validated_candidate(cached_item, file_record)
            if (
                validated is None
                or validated.candidate.intent_type in accepted_intents
            ):
                continue
            accepted.append(self._public_candidate(validated, file_record, row))
            accepted_intents.add(validated.candidate.intent_type)
        return accepted or None

    def resolve_recommendation_intent(
        self,
        dataset_version_id: str,
        provider: RecommendationProvider,
        recommendation_id: str,
        question: str,
    ) -> AnalysisIntent:
        provider_name, provider_model = self._provider_identity(provider)
        with self._dataset_lock(dataset_version_id):
            session = self.session_factory()
            try:
                file_record = session.get(FileModel, dataset_version_id)
                row = (
                    session.query(DatasetRecommendationModel)
                    .filter_by(dataset_version_id=dataset_version_id)
                    .first()
                )
                if (
                    file_record is None
                    or row is None
                    or not self._cache_matches(
                        row,
                        provider_name,
                        provider_model,
                    )
                ):
                    raise self._invalid_selection()
                canonical = self._canonical_cached_recommendations(
                    row,
                    file_record,
                )
                selected = next(
                    (
                        item
                        for item in canonical or []
                        if item["id"] == recommendation_id
                    ),
                    None,
                )
                if selected is None or selected["question"] != question:
                    raise self._invalid_selection()
                validated = self._validated_candidate(selected, file_record)
                if validated is None:
                    raise self._invalid_selection()
                return validated.intent
            finally:
                session.close()

    @staticmethod
    def _invalid_selection() -> RecommendationServiceError:
        return RecommendationServiceError(
            "RECOMMENDATION_SELECTION_INVALID",
            "Recommendation selection is no longer valid for this dataset.",
            409,
        )

    def _template_recommendations(
        self,
        file_record: FileModel,
        row: DatasetRecommendationModel,
    ) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        for candidate in self._template_candidates(file_record):
            validated = self._validated_candidate(candidate, file_record)
            if validated is None or any(
                item["intent_type"] == validated.candidate.intent_type
                for item in accepted
            ):
                continue
            accepted.append(self._public_candidate(validated, file_record, row))
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
    ) -> _ValidatedRecommendation | None:
        try:
            controlled = {
                "intent_type": (
                    candidate.get("intent_type")
                    if isinstance(candidate, dict)
                    else getattr(candidate, "intent_type", None)
                ),
                "referenced_fields": (
                    candidate.get("referenced_fields")
                    if isinstance(candidate, dict)
                    else getattr(candidate, "referenced_fields", None)
                ),
            }
            parsed = RecommendationCandidate.model_validate(controlled)
            if len(set(parsed.referenced_fields)) != len(parsed.referenced_fields):
                return None
            available_fields = {
                str(item.get("name"))
                for item in public_column_metadata(file_record.columns_info or [])
            }
            if any(
                field not in available_fields or not is_public_field_name(field)
                for field in parsed.referenced_fields
            ):
                return None
            intent = validated_recommendation_intent(parsed, file_record)
            return _ValidatedRecommendation(parsed, intent)
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

    def _public_candidate(
        self,
        validated: _ValidatedRecommendation,
        file_record: FileModel,
        row: DatasetRecommendationModel,
    ) -> dict[str, Any]:
        candidate = validated.candidate
        label, question = self.renderer.render(
            candidate,
            validated.intent,
            file_record,
        )
        return {
            "id": self._recommendation_id(candidate, row),
            "intent_type": candidate.intent_type,
            "label": label,
            "question": question,
            "referenced_fields": list(candidate.referenced_fields),
        }

    @staticmethod
    def _recommendation_id(
        candidate: RecommendationCandidate,
        row: DatasetRecommendationModel,
    ) -> str:
        generation = as_utc(row.created_at).isoformat()
        identity = json.dumps(
            {
                "dataset_version_id": row.dataset_version_id,
                "cache_id": row.id,
                "cache_generation": generation,
                "provider_name": row.provider_name,
                "provider_model": row.provider_model,
                "intent_type": candidate.intent_type,
                "referenced_fields": list(candidate.referenced_fields),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return f"{candidate.intent_type}-{digest}"

    @staticmethod
    def _result_from_model(
        row: DatasetRecommendationModel,
        recommendations: list[dict[str, Any]],
    ) -> RecommendationResult:
        return RecommendationResult(
            dataset_version_id=row.dataset_version_id,
            recommendations=list(recommendations),
            source=row.source,
            generated_at=as_utc(row.created_at),
        )
