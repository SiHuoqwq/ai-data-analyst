import json

from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.models import FileModel
from app.main import app
from app.v2.api.dependencies import get_provider
from app.v2.api import routes
from app.v2.services.provider import FakeAnalysisProvider
from app.v2.services.recommendations import RecommendationServiceError


def _configure_recommendation_dataset(tmp_path) -> None:
    csv_path = tmp_path / "recommendations.csv"
    csv_path.write_text(
        "category,enrolled_at,completion_rate\nA,2026-01-01,0.8\n",
        encoding="utf-8",
    )
    session = database.SessionLocal()
    try:
        dataset = session.get(FileModel, "file-1")
        dataset.filepath = str(csv_path)
        dataset.columns_info = [
            {"name": "category", "dtype": "object", "sample_values": ["RAW_ROW_MARKER"]},
            {"name": "enrolled_at", "dtype": "datetime64[ns]"},
            {"name": "completion_rate", "dtype": "float64"},
        ]
        dataset.profile_report = "PROMPT_MARKER API_KEY_MARKER RAW_RESPONSE_MARKER"
        session.commit()
    finally:
        session.close()


def test_get_recommendations_returns_strict_fake_templates_and_cached_result(
    v2_runtime, tmp_path
):
    _configure_recommendation_dataset(tmp_path)
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            first = client.get("/api/v2/datasets/file-1/recommendations")
            second = client.get("/api/v2/datasets/file-1/recommendations")

        assert first.status_code == second.status_code == 200
        assert first.json()["data"] == second.json()["data"]
        body = first.json()
        assert set(body) == {"data", "meta"}
        assert set(body["data"]) == {
            "dataset_version_id",
            "recommendations",
            "source",
            "generated_at",
        }
        assert body["data"]["dataset_version_id"] == "file-1"
        assert body["data"]["source"] == "template"
        assert body["data"]["generated_at"]
        assert {item["intent_type"] for item in body["data"]["recommendations"]} == {
            "group_comparison",
            "monthly_trend",
        }
        assert all(
            set(item)
            == {"id", "intent_type", "label", "question", "referenced_fields"}
            for item in body["data"]["recommendations"]
        )
        assert set(body["meta"]) == {
            "request_id",
            "schema_version",
            "next_cursor",
            "has_more",
        }
        rendered = json.dumps(body)
        for marker in (
            "PROMPT_MARKER",
            "RAW_RESPONSE_MARKER",
            "RAW_ROW_MARKER",
            "API_KEY_MARKER",
            "C:/",
            str(v2_runtime["database_path"]),
        ):
            assert marker not in rendered
    finally:
        app.dependency_overrides.clear()


def test_uploaded_csv_with_object_iso_date_gets_monthly_template(
    v2_runtime, tmp_path, monkeypatch
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            uploaded = client.post(
                "/api/v1/files/upload",
                files={
                    "file": (
                        "learning-operations.csv",
                        (
                            "课程类别,报名日期,课程完成率\n"
                            "数据分析,2026-01-05,0.82\n"
                            "产品设计,2026-02-12,0.74\n"
                        ).encode("utf-8"),
                        "text/csv",
                    )
                },
            )
            assert uploaded.status_code == 200
            dataset_id = uploaded.json()["id"]

            session = database.SessionLocal()
            try:
                record = session.get(FileModel, dataset_id)
                date_column = next(
                    item
                    for item in record.columns_info
                    if item["name"] == "报名日期"
                )
                assert date_column["dtype"] == "object"
            finally:
                session.close()

            response = client.get(
                f"/api/v2/datasets/{dataset_id}/recommendations"
            )

        assert response.status_code == 200
        assert {
            item["intent_type"]
            for item in response.json()["data"]["recommendations"]
        } == {"group_comparison", "monthly_trend"}
    finally:
        app.dependency_overrides.clear()


def test_get_recommendations_returns_not_found_for_unknown_dataset(v2_runtime):
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v2/datasets/missing/recommendations")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_get_recommendations_converts_service_errors_to_safe_v2_error(
    v2_runtime, monkeypatch
):
    def fail(_dataset_version_id, _provider):
        raise RecommendationServiceError(
            "INTERNAL_DETAIL", "C:/private/API_KEY_MARKER.txt", 500
        )

    monkeypatch.setattr(routes.recommendation_service, "get_or_generate", fail)
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v2/datasets/file-1/recommendations")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "RECOMMENDATIONS_UNAVAILABLE"
        assert "C:/private" not in json.dumps(response.json())
        assert "API_KEY_MARKER" not in json.dumps(response.json())
    finally:
        app.dependency_overrides.clear()
