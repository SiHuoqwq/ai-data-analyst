import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.v2.api.dependencies import get_provider
from app.v2.api.errors import V2APIError
from app.v2.services.provider import FakeAnalysisProvider


def wait_for_status(client: TestClient, run_id: str, expected: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v2/runs/{run_id}")
        if response.status_code == 200 and response.json()["data"]["status"] == expected:
            return response.json()["data"]
        time.sleep(0.02)
    raise AssertionError(f"run did not reach {expected}")


def create_run(client: TestClient, key: str, message: str = "分析销售数据") -> dict:
    response = client.post(
        "/api/v2/conversations/conversation-1/runs",
        headers={"Idempotency-Key": key},
        json={"message": message, "dataset_version_id": "file-1"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["meta"]["schema_version"] == "1.0"
    assert body["data"]["run"]["status"] == "queued"
    assert body["data"]["events_url"].startswith("/api/v2/runs/")
    return body["data"]


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, value = line.split(": ", 1)
            fields[key] = value
        payload = json.loads(fields["data"])
        assert fields["id"] == payload["event_id"]
        assert fields["event"] == payload["event_type"]
        events.append(payload)
    return events


def test_provider_configuration_is_fake_only(monkeypatch):
    if settings.deepseek_api_key:
        assert settings.deepseek_api_key not in repr(settings)
    monkeypatch.setattr(settings, "v2_provider", "fake")
    monkeypatch.setattr(settings, "v2_fake_step_delay_seconds", 0.25)
    provider = get_provider()
    assert isinstance(provider, FakeAnalysisProvider)
    assert provider.step_delay_seconds == 0.25

    monkeypatch.setattr(settings, "v2_provider", "deepseek")
    with pytest.raises(V2APIError) as error:
        get_provider()
    assert error.value.code == "PROVIDER_NOT_AVAILABLE"


def test_v2_success_api_and_sse_vertical_flow(v2_runtime):
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            created = create_run(client, "api-success")
            run_id = created["run"]["id"]
            completed = wait_for_status(client, run_id, "completed")

            assert completed["answer_message_id"]
            assert completed["created_at"].endswith("Z")
            assert completed["allowed_actions"]["cancel"] is False

            steps_response = client.get(f"/api/v2/runs/{run_id}/steps")
            assert steps_response.status_code == 200
            assert all(
                step["status"] == "completed"
                for step in steps_response.json()["data"]
            )

            artifacts_response = client.get(f"/api/v2/runs/{run_id}/artifacts")
            assert artifacts_response.status_code == 200
            artifacts = artifacts_response.json()["data"]
            assert {artifact["artifact_type"] for artifact in artifacts} == {
                "text",
                "metric",
                "table",
                "chart",
            }
            chart = next(
                artifact
                for artifact in artifacts
                if artifact["artifact_type"] == "chart"
            )
            assert chart["payload"]["image_url"].startswith("/api/v2/")
            assert "storage_key" not in chart
            image = client.get(chart["payload"]["image_url"])
            assert image.status_code == 200
            assert image.headers["content-type"] == "image/png"
            artifact_detail = client.get(f"/api/v2/artifacts/{chart['id']}")
            assert artifact_detail.status_code == 200
            assert artifact_detail.json()["data"]["payload"] == chart["payload"]

            stream = client.get(f"/api/v2/runs/{run_id}/events")
            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            events = parse_sse(stream.text)
            assert events[0]["event_type"] == "run.started"
            assert events[-1]["event_type"] == "run.completed"
            assert all(event["timestamp"].endswith("Z") for event in events)
            assert [event["sequence"] for event in events] == list(
                range(1, len(events) + 1)
            )
            artifact_events = [
                event for event in events if event["event_type"] == "artifact.created"
            ]
            assert {
                event["payload"]["artifact_type"] for event in artifact_events
            } == {"text", "metric", "table", "chart"}
            assert "answer.delta" not in stream.text
            assert str(v2_runtime["chart_dir"]) not in stream.text

            last_only = parse_sse(
                client.get(
                    f"/api/v2/runs/{run_id}/events",
                    params={"after_sequence": events[-2]["sequence"]},
                ).text
            )
            assert [event["event_type"] for event in last_only] == ["run.completed"]
            resumed = parse_sse(
                client.get(
                    f"/api/v2/runs/{run_id}/events",
                    headers={"Last-Event-ID": events[0]["event_id"]},
                ).text
            )
            assert resumed[0]["sequence"] == 2
            assert resumed[-1]["event_type"] == "run.completed"

            terminal_cancel = client.post(
                f"/api/v2/runs/{run_id}/cancel",
                json={"reason": "user_requested"},
            )
            assert terminal_cancel.status_code == 409
            assert terminal_cancel.json()["error"]["code"] == "RUN_NOT_CANCELLABLE"

            v1 = client.get("/api/v1/files")
            assert v1.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_create_run_is_idempotent_and_conflicts_on_different_request(v2_runtime):
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            first = create_run(client, "same-key", "第一次请求")
            replay = client.post(
                "/api/v2/conversations/conversation-1/runs",
                headers={"Idempotency-Key": "same-key"},
                json={"message": "第一次请求", "dataset_version_id": "file-1"},
            )
            assert replay.status_code == 202
            assert replay.json()["data"]["run"]["id"] == first["run"]["id"]
            wait_for_status(client, first["run"]["id"], "completed")

            conflict = client.post(
                "/api/v2/conversations/conversation-1/runs",
                headers={"Idempotency-Key": "same-key"},
                json={"message": "不同请求", "dataset_version_id": "file-1"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    finally:
        app.dependency_overrides.clear()


def test_v2_errors_use_uniform_envelope(v2_runtime):
    with TestClient(app) as client:
        missing = client.get("/api/v2/runs/missing")
        assert missing.status_code == 404
        assert missing.json() == {
            "error": {
                "code": "RUN_NOT_FOUND",
                "message": "分析任务不存在",
                "details": {},
                "retryable": False,
                "request_id": missing.json()["error"]["request_id"],
            }
        }

        invalid = client.post(
            "/api/v2/conversations/conversation-1/runs",
            json={"message": "", "dataset_version_id": "file-1"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
        assert invalid.json()["error"]["retryable"] is False

        missing_conversation = client.post(
            "/api/v2/conversations/missing/runs",
            headers={"Idempotency-Key": "missing-conversation"},
            json={"message": "分析数据", "dataset_version_id": "file-1"},
        )
        assert missing_conversation.status_code == 404
        assert (
            missing_conversation.json()["error"]["code"]
            == "CONVERSATION_NOT_FOUND"
        )

        missing_dataset = client.post(
            "/api/v2/conversations/conversation-1/runs",
            headers={"Idempotency-Key": "missing-dataset"},
            json={"message": "分析数据", "dataset_version_id": "missing"},
        )
        assert missing_dataset.status_code == 404
        assert missing_dataset.json()["error"]["code"] == "DATASET_VERSION_NOT_FOUND"


def test_api_can_cancel_running_run(v2_runtime):
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider(
        step_delay_seconds=0.2
    )
    try:
        with TestClient(app) as client:
            created = create_run(client, "api-cancel")
            run_id = created["run"]["id"]
            wait_for_status(client, run_id, "running")

            cancelled = client.post(
                f"/api/v2/runs/{run_id}/cancel",
                json={"reason": "user_requested"},
            )
            assert cancelled.status_code == 202
            wait_for_status(client, run_id, "cancelled")
            events = parse_sse(client.get(f"/api/v2/runs/{run_id}/events").text)
            assert events[-1]["event_type"] == "run.cancelled"
    finally:
        app.dependency_overrides.clear()


def test_api_exposes_failed_run_and_terminal_event(v2_runtime):
    class FailingProvider(FakeAnalysisProvider):
        def build_plan(self, question, file_record):
            raise RuntimeError("controlled provider failure")

    app.dependency_overrides[get_provider] = lambda: FailingProvider()
    try:
        with TestClient(app) as client:
            created = create_run(client, "api-failure")
            run_id = created["run"]["id"]
            failed = wait_for_status(client, run_id, "failed")
            assert failed["failure"]["code"] == "EXECUTION_FAILED"
            events = parse_sse(client.get(f"/api/v2/runs/{run_id}/events").text)
            assert events[-1]["event_type"] == "run.failed"
    finally:
        app.dependency_overrides.clear()
