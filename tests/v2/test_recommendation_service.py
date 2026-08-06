from dataclasses import dataclass

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.db.models import FileModel
from app.v2.db.models import DatasetRecommendationModel, utc_now
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


@pytest.mark.parametrize(
    ("columns", "group_fields", "monthly_fields"),
    [
        (
            [
                {"name": "课程类别", "dtype": "object"},
                {"name": "报名日期", "dtype": "datetime64[ns]"},
                {"name": "实付金额", "dtype": "int64"},
                {"name": "课程完成率", "dtype": "int64"},
                {"name": "课程评分", "dtype": "int64"},
            ],
            ["课程类别", "课程完成率"],
            ["课程类别", "报名日期", "实付金额"],
        ),
        (
            [
                {"name": "category", "dtype": "object"},
                {"name": "enrollment_date", "dtype": "datetime64[ns]"},
                {"name": "paid_amount", "dtype": "int64"},
                {"name": "completion_rate", "dtype": "int64"},
                {"name": "rating", "dtype": "int64"},
            ],
            ["category", "completion_rate"],
            ["category", "enrollment_date", "paid_amount"],
        ),
    ],
)
def test_template_candidates_use_registered_integer_metric_contracts(
    columns,
    group_fields,
    monthly_fields,
):
    record = FileModel(
        id="registered-integer-metrics",
        filename="registered-integer-metrics.csv",
        filepath="registered-integer-metrics.csv",
        file_type="csv",
        row_count=2,
        col_count=len(columns),
        columns_info=columns,
        profile_report="",
    )

    candidates = DatasetRecommendationService()._template_candidates(record)

    assert [candidate.intent_type for candidate in candidates] == [
        "group_comparison",
        "monthly_trend",
    ]
    assert candidates[0].referenced_fields == group_fields
    assert candidates[1].referenced_fields == monthly_fields


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


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "C:/private/rows.csv",
        "/private/raw/rows.csv",
        "\\\\server\\share\\rows.csv",
    ],
)
def test_rejects_model_candidates_that_include_physical_paths(
    v2_runtime, tmp_path, unsafe_path
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
                    question=f"Compare {unsafe_path} by category.",
                    referenced_fields=["category"],
                )
            ]
        )
    )

    result = DatasetRecommendationService().get_or_generate("dataset-path", provider)

    assert result.source == "template"
    assert all(unsafe_path not in item["question"] for item in result.recommendations)


def test_model_recommendations_cache_only_derived_public_text(
    v2_runtime, tmp_path
):
    columns = [
        *compatible_columns(),
        {"name": "notes", "dtype": "object", "sample_values": ["SAMPLE_VALUE_MARKER"]},
    ]
    add_dataset(
        tmp_path,
        dataset_id="dataset-redacted",
        columns=columns,
        content="category,enrolled_at,completion_rate,notes\nA,2026-01-01,0.8,private\n",
    )
    provider = StubProvider(
        RecommendationGeneration(
            candidates=[
                RecommendationCandidate(
                    intent_type="group_comparison",
                    label="SAMPLE_VALUE_MARKER",
                    question=(
                        "Authorization: Bearer API_TOKEN_MARKER at "
                        "the selected category."
                    ),
                    referenced_fields=["category", "completion_rate"],
                )
            ]
        )
    )

    result = DatasetRecommendationService().get_or_generate(
        "dataset-redacted", provider
    )

    assert result.source == "model"
    assert result.recommendations == [
        {
            "id": "group_comparison-1",
            "intent_type": "group_comparison",
            "label": "Compare by category",
            "question": "How do key outcomes compare across category?",
            "referenced_fields": ["category", "completion_rate"],
        }
    ]


def test_fake_provider_skips_model_candidates_and_uses_templates(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-fake-candidates",
        columns=compatible_columns(),
        content="category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
    )
    fake = StubProvider(valid_generation(), name="fake")

    result = DatasetRecommendationService().get_or_generate(
        "dataset-fake-candidates", fake
    )

    assert result.source == "template"
    assert fake.calls == 0
    assert result.recommendations[0]["question"] == (
        "How do key outcomes compare across category?"
    )


def test_sensitive_field_names_are_not_available_to_model_or_templates(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-sensitive-field",
        columns=[{"name": "api_key", "dtype": "object"}],
        content="api_key\nsecret\n",
    )
    fake = StubProvider(RecommendationGeneration(candidates=[]), name="fake")

    result = DatasetRecommendationService().get_or_generate(
        "dataset-sensitive-field", fake
    )

    assert result.source == "template"
    assert result.recommendations == []
    assert fake.calls == 0


class RaceSession:
    def __init__(self, file_record):
        self.file_record = file_record
        self.winner = None

    def query(self, _model):
        return self

    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return self.winner

    def get(self, _model, _dataset_version_id):
        return self.file_record

    def add(self, _row):
        pass

    def commit(self):
        self.winner = DatasetRecommendationModel(
            id="race-winner",
            dataset_version_id=self.file_record.id,
            recommendations_json=[
                {
                    "id": "group_comparison-1",
                    "intent_type": "group_comparison",
                    "label": "Winner",
                    "question": "Winner question",
                    "referenced_fields": ["category"],
                }
            ],
            source="template",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        raise IntegrityError("INSERT", {}, RuntimeError("unique conflict"))

    def rollback(self):
        pass

    def refresh(self, _row):
        pass

    def close(self):
        pass


def test_unique_cache_conflict_returns_existing_winner(tmp_path):
    csv_path = tmp_path / "race.csv"
    csv_path.write_text(
        "category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
        encoding="utf-8",
    )
    session = RaceSession(
        FileModel(
            id="dataset-race",
            filename="race.csv",
            filepath=str(csv_path),
            file_type="csv",
            row_count=1,
            col_count=3,
            columns_info=compatible_columns(),
            profile_report="",
        )
    )
    provider = StubProvider(valid_generation())

    result = DatasetRecommendationService(
        session_factory=lambda: session
    ).get_or_generate("dataset-race", provider)

    assert result.source == "template"
    assert result.recommendations == session.winner.recommendations_json


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
    assert failing.calls == 1
    assert fake.calls == 0
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


def test_object_category_fields_do_not_create_monthly_template(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-object-categories",
        columns=[
            {"name": "category", "dtype": "object"},
            {"name": "region", "dtype": "object"},
        ],
        content="category,region\nA,North\nB,South\n",
    )
    fake = StubProvider(RecommendationGeneration(candidates=[]), name="fake")

    result = DatasetRecommendationService().get_or_generate(
        "dataset-object-categories", fake
    )

    assert [
        item["intent_type"] for item in result.recommendations
    ] == ["group_comparison"]


def test_object_registry_date_requires_locally_parseable_values(
    v2_runtime, tmp_path
):
    add_dataset(
        tmp_path,
        dataset_id="dataset-unparseable-date",
        columns=[
            {"name": "课程类别", "dtype": "object"},
            {"name": "报名日期", "dtype": "object"},
            {"name": "课程完成率", "dtype": "float64"},
        ],
        content=(
            "课程类别,报名日期,课程完成率\n"
            "数据分析,not-a-date,0.82\n"
            "产品设计,still-not-a-date,0.74\n"
        ),
    )
    fake = StubProvider(RecommendationGeneration(candidates=[]), name="fake")

    result = DatasetRecommendationService().get_or_generate(
        "dataset-unparseable-date", fake
    )

    assert [
        item["intent_type"] for item in result.recommendations
    ] == ["group_comparison"]
