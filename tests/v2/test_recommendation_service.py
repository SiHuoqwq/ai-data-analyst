from dataclasses import dataclass

from app.db import database
from app.db.models import FileModel
from app.v2.db.models import DatasetRecommendationModel
from app.v2.schemas.recommendations import (
    RecommendationCandidate,
    RecommendationGeneration,
)
from app.v2.services.recommendations import DatasetRecommendationService


@dataclass
class StubProvider:
    generation: object | Exception
    name: str = "stub-model"
    model: str = "stub-v1"
    calls: int = 0
    prompt: str = "PROMPT_MARKER"
    raw_response: str = "RAW_RESPONSE_MARKER"
    private_path: str = "C:/private/rows.csv"

    def recommend_questions(self, _file_record):
        self.calls += 1
        if isinstance(self.generation, Exception):
            raise self.generation
        return self.generation


@dataclass
class RawGeneration:
    candidates: list[RecommendationCandidate]


def add_dataset(tmp_path, *, dataset_id: str, columns: list[dict], content: str):
    csv_path = tmp_path / f"{dataset_id}.csv"
    csv_path.write_text(content, encoding="utf-8")
    session = database.SessionLocal()
    try:
        session.add(
            FileModel(
                id=dataset_id,
                filename=f"{dataset_id}.csv",
                filepath=str(csv_path),
                file_type="csv",
                row_count=2,
                col_count=len(columns),
                columns_info=columns,
                profile_report="RAW_ROW_MARKER",
            )
        )
        session.commit()
    finally:
        session.close()


def compatible_columns():
    return [
        {"name": "category", "dtype": "object"},
        {"name": "enrolled_at", "dtype": "datetime64[ns]"},
        {"name": "completion_rate", "dtype": "float64"},
    ]


def valid_generation() -> RawGeneration:
    return RawGeneration(
        candidates=[
            RecommendationCandidate(
                intent_type="group_comparison",
                label="Completion by category",
                question="Which categories have the lowest completion rate?",
                referenced_fields=["category", "completion_rate"],
            ),
            RecommendationCandidate(
                intent_type="group_comparison",
                label="Duplicate group candidate",
                question="This duplicate must not be stored.",
                referenced_fields=["category"],
            ),
            RecommendationCandidate(
                intent_type="monthly_trend",
                label="Monthly category trend",
                question="How do categories change by month?",
                referenced_fields=["category", "enrolled_at"],
            ),
        ]
    )


def test_cache_miss_validates_and_persists_one_model_candidate_per_intent(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-model",
        columns=compatible_columns(),
        content=(
            "category,enrolled_at,completion_rate\n"
            "A,2026-01-01,0.8\nB,2026-02-01,0.6\n"
        ),
    )
    provider = StubProvider(valid_generation())

    result = DatasetRecommendationService().get_or_generate(
        "dataset-model", provider
    )

    assert result.source == "model"
    assert [item["intent_type"] for item in result.recommendations] == [
        "group_comparison",
        "monthly_trend",
    ]
    assert provider.calls == 1
    session = database.SessionLocal()
    try:
        stored = session.query(DatasetRecommendationModel).filter_by(
            dataset_version_id="dataset-model"
        ).one()
        assert stored.source == "model"
        assert stored.provider_name == "stub-model"
        assert stored.provider_model == "stub-v1"
        assert all(set(item) == {"id", "intent_type", "label", "question", "referenced_fields"} for item in stored.recommendations_json)
        stored_text = str(stored.recommendations_json)
        assert "PROMPT_MARKER" not in stored_text
        assert "RAW_RESPONSE_MARKER" not in stored_text
        assert "RAW_ROW_MARKER" not in stored_text
        assert "private/rows.csv" not in stored_text
    finally:
        session.close()


def test_cache_hit_returns_persisted_recommendations_without_calling_provider(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-cache",
        columns=compatible_columns(),
        content="category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
    )
    provider = StubProvider(valid_generation())
    service = DatasetRecommendationService()

    first = service.get_or_generate("dataset-cache", provider)
    second = service.get_or_generate("dataset-cache", provider)

    assert provider.calls == 1
    assert second.recommendations == first.recommendations
    assert second.generated_at == first.generated_at


def test_rejects_missing_and_nonexecutable_model_candidates_before_caching(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-invalid",
        columns=compatible_columns(),
        content="category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
    )
    provider = StubProvider(
        RecommendationGeneration(
            candidates=[
                RecommendationCandidate(
                    intent_type="group_comparison",
                    label="Missing field",
                    question="Do not keep this question.",
                    referenced_fields=["category", "missing_field"],
                ),
                RecommendationCandidate(
                    intent_type="monthly_trend",
                    label="No category dimension",
                    question="Do not keep this trend.",
                    referenced_fields=["enrolled_at", "completion_rate"],
                ),
            ]
        )
    )

    result = DatasetRecommendationService().get_or_generate(
        "dataset-invalid", provider
    )

    assert result.source == "template"
    assert provider.calls == 1
    assert all(
        "missing_field" not in item["referenced_fields"]
        for item in result.recommendations
    )
    assert all(
        item["question"] not in {"Do not keep this question.", "Do not keep this trend."}
        for item in result.recommendations
    )


def test_rejects_model_candidates_that_include_physical_paths(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-path",
        columns=compatible_columns(),
        content="category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
    )
    provider = StubProvider(
        RecommendationGeneration(
            candidates=[
                RecommendationCandidate(
                    intent_type="group_comparison",
                    label="Private file comparison",
                    question="Compare C:/private/rows.csv by category.",
                    referenced_fields=["category"],
                )
            ]
        )
    )

    result = DatasetRecommendationService().get_or_generate("dataset-path", provider)

    assert result.source == "template"
    assert all("C:/private/rows.csv" not in item["question"] for item in result.recommendations)


def test_provider_failure_and_fake_empty_generation_use_deterministic_templates(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-template-failure",
        columns=compatible_columns(),
        content="category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
    )
    add_dataset(
        tmp_path,
        dataset_id="dataset-template-fake",
        columns=compatible_columns(),
        content="category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
    )
    failing = StubProvider(RuntimeError("provider unavailable"))
    fake = StubProvider(RecommendationGeneration(candidates=[]), name="fake")
    service = DatasetRecommendationService()

    fallback = service.get_or_generate("dataset-template-failure", failing)
    fake_result = service.get_or_generate("dataset-template-fake", fake)

    assert fallback.source == fake_result.source == "template"
    assert fallback.recommendations == fake_result.recommendations
    assert failing.calls == fake.calls == 1
    assert {item["intent_type"] for item in fallback.recommendations} == {
        "group_comparison",
        "monthly_trend",
    }


def test_incompatible_dataset_caches_only_executable_template_questions(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-incompatible",
        columns=[{"name": "value", "dtype": "float64"}],
        content="value\n1.0\n2.0\n",
    )
    provider = StubProvider(RecommendationGeneration(candidates=[]), name="fake")

    result = DatasetRecommendationService().get_or_generate(
        "dataset-incompatible", provider
    )

    assert result.source == "template"
    assert result.recommendations == []
