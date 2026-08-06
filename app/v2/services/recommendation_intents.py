from app.db.models import FileModel
from app.services.parser import parse_file
from app.v2.domain.learning_registry import LearningDomainRegistry
from app.v2.schemas.intents import AnalysisIntent, IntentMetric
from app.v2.schemas.recommendations import RecommendationCandidate
from app.v2.services.plan_compiler import (
    PlanCompilationError,
    PlanCompiler,
    PlanValidator,
)


def validated_recommendation_intent(
    candidate: RecommendationCandidate,
    file_record: FileModel,
    *,
    parsed_frame=None,
) -> AnalysisIntent:
    if candidate.intent_type == "monthly_trend" and parsed_frame is None:
        try:
            parsed_frame = parse_file(file_record.filepath)
        except Exception as exc:
            raise PlanCompilationError(
                "RECOMMENDATION_VALIDATION_FAILED",
                "Recommended question could not be validated.",
            ) from exc
    compiler = (
        PlanCompiler(
            validator=PlanValidator(dataframe_loader=lambda _path: parsed_frame)
        )
        if candidate.intent_type == "monthly_trend"
        else PlanCompiler()
    )
    for intent in recommendation_validation_intents(candidate, file_record):
        try:
            plan = compiler.compile(intent, file_record)
            compiler.validator.validate(plan, file_record)
        except PlanCompilationError:
            continue
        return intent
    raise PlanCompilationError(
        "INVALID_RECOMMENDATION_FIELDS",
        "Recommended question does not map to an executable workflow.",
    )


def recommendation_validation_intents(
    candidate: RecommendationCandidate,
    file_record: FileModel,
) -> list[AnalysisIntent]:
    field_types = {
        str(item.get("name")): str(item.get("dtype", "")).lower()
        for item in (file_record.columns_info or [])
    }
    fields = candidate.referenced_fields
    registry = LearningDomainRegistry()
    metric_definitions = {
        field: definition
        for metric_id, definition in registry.metrics.items()
        for field in (metric_id, definition.source_field)
        if field is not None
    }

    def registered_metric(field: str):
        return metric_definitions.get(field)

    def is_metric_field(field: str) -> bool:
        return registered_metric(field) is not None or any(
            marker in field_types[field]
            for marker in ("float", "decimal", "number", "bool")
        )

    def is_numeric_code(field: str) -> bool:
        return "int" in field_types[field]

    def is_date_hint(field: str) -> bool:
        return "date" in field_types[field] or "time" in field_types[field]

    def registered_metrics(
        metric_fields: list[str],
        allowed_semantics: set[str],
    ) -> list[IntentMetric]:
        metrics: list[IntentMetric] = []
        seen_semantics: set[str] = set()
        for field in metric_fields:
            definition = registered_metric(field)
            if definition is not None and definition.semantic not in allowed_semantics:
                raise PlanCompilationError(
                    "UNSUPPORTED_RECOMMENDATION_METRIC",
                    "Recommended metric is not supported by this workflow.",
                    {"field": field},
                )
            if definition is None or definition.semantic in seen_semantics:
                continue
            metrics.append(
                IntentMetric(
                    semantic=definition.semantic,
                    source_field=field,
                    aggregation=definition.aggregation,
                )
            )
            seen_semantics.add(definition.semantic)
        return metrics or [
            IntentMetric(
                semantic="报名人数",
                source_field=None,
                aggregation="count",
            )
        ]

    if candidate.intent_type == "monthly_trend":
        intents = []
        for date_field in fields:
            if is_metric_field(date_field) or is_numeric_code(date_field):
                continue
            for dimension_field in fields:
                if (
                    dimension_field == date_field
                    or is_metric_field(dimension_field)
                    or is_date_hint(dimension_field)
                ):
                    continue
                metric_fields = [
                    field
                    for field in fields
                    if field not in {date_field, dimension_field}
                ]
                if len(metric_fields) > 3 or any(
                    not (is_metric_field(field) or is_numeric_code(field))
                    for field in metric_fields
                ):
                    continue
                intents.append(
                    AnalysisIntent(
                        analysis_type="monthly_trend",
                        dimensions=[dimension_field],
                        date_field=date_field,
                        metrics=registered_metrics(
                            metric_fields,
                            {"实付金额", "平均完成率"},
                        ),
                    )
                )
        return intents

    dimension_candidates = [
        field
        for field in fields
        if not is_metric_field(field) and not is_date_hint(field)
    ]
    categorical_fields = [
        field for field in dimension_candidates if not is_numeric_code(field)
    ]
    dimension_fields = categorical_fields or dimension_candidates
    metric_fields = [
        field
        for field in fields
        if is_metric_field(field)
        or (is_numeric_code(field) and field not in dimension_fields)
    ]
    if not dimension_fields or len(dimension_fields) > 4:
        raise PlanCompilationError(
            "INVALID_RECOMMENDATION_FIELDS",
            "Group recommendations require up to four category fields.",
        )
    return [
        AnalysisIntent(
            analysis_type="group_comparison",
            dimensions=dimension_fields,
            metrics=registered_metrics(
                metric_fields,
                {"平均完成率", "退款率", "平均评分"},
            ),
        )
    ]
