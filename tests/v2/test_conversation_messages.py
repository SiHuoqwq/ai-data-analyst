import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.db.models import FileModel, MessageModel
from app.main import app
from app.v2.api.dependencies import get_provider
from app.v2.db.models import AnalysisRunModel
from app.v2.services.provider import FakeAnalysisProvider
from app.v2.services.runs import AnalysisRunService


def wait_for_status(client: TestClient, run_id: str, expected: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v2/runs/{run_id}")
        if response.status_code == 200 and response.json()["data"]["status"] == expected:
            return response.json()["data"]
        time.sleep(0.02)
    raise AssertionError(f"run did not reach {expected}")


def create_conversation(
    client: TestClient,
    *,
    title: str | None = None,
    file_id: str = "file-1",
) -> dict:
    payload = {"file_id": file_id}
    if title is not None:
        payload["title"] = title
    response = client.post("/api/v2/conversations", json=payload)
    assert response.status_code == 201
    return response.json()["data"]


def create_run(
    client: TestClient,
    conversation_id: str,
    key: str,
    message: str,
    dataset_version_id: str = "file-1",
) -> dict:
    response = client.post(
        f"/api/v2/conversations/{conversation_id}/runs",
        headers={"Idempotency-Key": key},
        json={
            "message": message,
            "dataset_version_id": dataset_version_id,
        },
    )
    assert response.status_code == 202
    return response.json()["data"]


@pytest.fixture
def fake_client(v2_runtime):
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_create_conversation_uses_default_title_and_creates_no_messages(fake_client):
    conversation = create_conversation(fake_client)

    assert conversation["file_id"] == "file-1"
    assert conversation["title"] == "新分析"
    assert conversation["mode"] == "agent"
    assert conversation["created_at"].endswith("Z")

    history = fake_client.get(
        f"/api/v1/conversations/{conversation['id']}"
    )
    assert history.status_code == 200
    assert history.json()["messages"] == []


def test_create_conversation_accepts_custom_title(fake_client):
    conversation = create_conversation(fake_client, title="季度销售复盘")
    assert conversation["title"] == "季度销售复盘"


def test_conversation_list_returns_ordered_user_questions_only(fake_client):
    conversation = create_conversation(fake_client, title="多轮课程分析")
    started_at = datetime(2026, 8, 13, 9, 0, 0)
    session = database.SessionLocal()
    session.add_all([
        MessageModel(
            id="question-2",
            conv_id=conversation["id"],
            role="user",
            content="第二个问题",
            created_at=started_at + timedelta(minutes=2),
        ),
        MessageModel(
            id="answer-1",
            conv_id=conversation["id"],
            role="assistant",
            content="不应出现在问题列表中的回答",
            created_at=started_at + timedelta(minutes=1),
        ),
        MessageModel(
            id="question-1",
            conv_id=conversation["id"],
            role="user",
            content="第一个问题",
            created_at=started_at,
        ),
    ])
    session.commit()
    session.close()

    response = fake_client.get(
        f"/api/v1/files/file-1/conversations"
    )

    assert response.status_code == 200
    listed = next(
        item for item in response.json() if item["id"] == conversation["id"]
    )
    assert listed["message_count"] == 3
    assert listed["user_questions"] == ["第一个问题", "第二个问题"]


def test_create_conversation_rejects_missing_file_with_uniform_error(fake_client):
    response = fake_client.post(
        "/api/v2/conversations",
        json={"file_id": "missing", "title": "无效会话"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


def test_run_persists_ordered_user_and_assistant_messages(fake_client):
    conversation = create_conversation(fake_client)
    created = create_run(
        fake_client,
        conversation["id"],
        "message-success",
        "汇总销售数据",
    )
    run_id = created["run"]["id"]

    assert created["run"]["conversation_id"] == conversation["id"]
    assert created["run"]["input_message_id"] == created["message"]["id"]
    assert created["run"]["output_message_id"] is None

    completed = wait_for_status(fake_client, run_id, "completed")
    assert completed["input_message_id"] == created["message"]["id"]
    assert completed["output_message_id"]
    assert completed["finished_at"]
    assert completed["error"] is None

    history = fake_client.get(
        f"/api/v1/conversations/{conversation['id']}"
    ).json()
    assert [message["role"] for message in history["messages"]] == [
        "user",
        "assistant",
    ]
    assert history["messages"][0]["content"] == "汇总销售数据"
    assert "renderer" not in history["messages"][1]["content"]
    assert '"columns"' not in history["messages"][1]["content"]

    session = database.SessionLocal()
    messages = (
        session.query(MessageModel)
        .filter_by(conv_id=conversation["id"])
        .order_by(MessageModel.created_at, MessageModel.id)
        .all()
    )
    assert messages[1].created_at > messages[0].created_at
    session.close()


def test_run_creation_rolls_back_user_message_when_event_creation_fails(v2_runtime):
    class FailingEventEmitter:
        def emit(self, *_args, **_kwargs):
            raise RuntimeError("event persistence failed")

    service = AnalysisRunService(event_emitter=FailingEventEmitter())

    with pytest.raises(RuntimeError, match="event persistence failed"):
        service.create_run(
            conversation_id="conversation-1",
            dataset_version_id="file-1",
            message="不会留下孤儿消息",
            idempotency_key="transaction-rollback",
        )

    session = database.SessionLocal()
    assert (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1")
        .count()
        == 0
    )
    assert (
        session.query(AnalysisRunModel)
        .filter_by(conversation_id="conversation-1")
        .count()
        == 0
    )
    session.close()


def test_run_service_marks_idempotent_replay_as_existing_work(v2_runtime):
    service = AnalysisRunService()

    first = service.create_run_result(
        conversation_id="conversation-1",
        dataset_version_id="file-1",
        message="只执行一次",
        idempotency_key="service-idempotency",
    )
    replay = service.create_run_result(
        conversation_id="conversation-1",
        dataset_version_id="file-1",
        message="只执行一次",
        idempotency_key="service-idempotency",
    )

    assert first.created is True
    assert replay.created is False
    assert replay.run.id == first.run.id

    session = database.SessionLocal()
    assert (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1", role="user")
        .count()
        == 1
    )
    session.close()


def test_idempotent_retry_and_conflict_do_not_duplicate_messages(v2_runtime):
    provider = FakeAnalysisProvider(step_delay_seconds=0.1)
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            conversation = create_conversation(client)
            first = create_run(
                client,
                conversation["id"],
                "same-message-key",
                "第一次分析",
            )
            replay = create_run(
                client,
                conversation["id"],
                "same-message-key",
                "第一次分析",
            )
            assert replay["run"]["id"] == first["run"]["id"]
            assert (
                replay["run"]["input_message_id"]
                == first["run"]["input_message_id"]
            )

            wait_for_status(client, first["run"]["id"], "completed")
            replay_after_completion = create_run(
                client,
                conversation["id"],
                "same-message-key",
                "第一次分析",
            )
            assert replay_after_completion["run"]["id"] == first["run"]["id"]

            history = client.get(
                f"/api/v1/conversations/{conversation['id']}"
            ).json()
            assert [message["role"] for message in history["messages"]] == [
                "user",
                "assistant",
            ]

            conflict = client.post(
                f"/api/v2/conversations/{conversation['id']}/runs",
                headers={"Idempotency-Key": "same-message-key"},
                json={
                    "message": "冲突请求",
                    "dataset_version_id": "file-1",
                },
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            assert len(
                client.get(
                    f"/api/v1/conversations/{conversation['id']}"
                ).json()["messages"]
            ) == 2
    finally:
        app.dependency_overrides.clear()


def test_failed_and_cancelled_runs_keep_only_user_messages(v2_runtime):
    app.dependency_overrides[get_provider] = lambda: FakeAnalysisProvider(
        step_delay_seconds=0.2
    )
    try:
        with TestClient(app) as client:
            conversation = create_conversation(client)

            failed_created = create_run(
                client,
                conversation["id"],
                "failed-message",
                "[fake:fail]",
            )
            failed = wait_for_status(
                client, failed_created["run"]["id"], "failed"
            )
            assert failed["output_message_id"] is None

            cancelled_created = create_run(
                client,
                conversation["id"],
                "cancelled-message",
                "取消这次分析",
            )
            cancelled_id = cancelled_created["run"]["id"]
            wait_for_status(client, cancelled_id, "running")
            cancel = client.post(
                f"/api/v2/runs/{cancelled_id}/cancel",
                json={"reason": "user_requested"},
            )
            assert cancel.status_code == 202
            cancelled = wait_for_status(client, cancelled_id, "cancelled")
            assert cancelled["output_message_id"] is None

            repeated = client.post(
                f"/api/v2/runs/{cancelled_id}/cancel",
                json={"reason": "user_requested"},
            )
            assert repeated.status_code == 202

            history = client.get(
                f"/api/v1/conversations/{conversation['id']}"
            ).json()
            assert [message["role"] for message in history["messages"]] == [
                "user",
                "user",
            ]
    finally:
        app.dependency_overrides.clear()


def test_same_conversation_supports_two_isolated_analysis_rounds(fake_client):
    conversation = create_conversation(fake_client, title="连续分析")

    first = create_run(
        fake_client,
        conversation["id"],
        "round-1",
        "第一轮问题",
    )
    first_run = wait_for_status(fake_client, first["run"]["id"], "completed")
    second = create_run(
        fake_client,
        conversation["id"],
        "round-2",
        "第二轮问题",
    )
    second_run = wait_for_status(fake_client, second["run"]["id"], "completed")

    history = fake_client.get(
        f"/api/v1/conversations/{conversation['id']}"
    ).json()
    assert [message["role"] for message in history["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert first_run["input_message_id"] != second_run["input_message_id"]
    assert first_run["output_message_id"] != second_run["output_message_id"]

    first_artifacts = {
        artifact["id"]
        for artifact in fake_client.get(
            f"/api/v2/runs/{first_run['id']}/artifacts"
        ).json()["data"]
    }
    second_artifacts = {
        artifact["id"]
        for artifact in fake_client.get(
            f"/api/v2/runs/{second_run['id']}/artifacts"
        ).json()["data"]
    }
    assert len(first_artifacts) == 5
    assert len(second_artifacts) == 5
    assert first_artifacts.isdisjoint(second_artifacts)


def test_run_rejects_conversation_dataset_mismatch_without_message(v2_runtime):
    session = database.SessionLocal()
    source = session.get(FileModel, "file-1")
    session.add(
        FileModel(
            id="file-2",
            filename="other.csv",
            filepath=source.filepath,
            file_type="csv",
            row_count=1,
            col_count=1,
            columns_info=[],
            profile_report="",
        )
    )
    session.commit()
    session.close()

    with TestClient(app) as client:
        mismatch = client.post(
            "/api/v2/conversations/conversation-1/runs",
            headers={"Idempotency-Key": "dataset-mismatch"},
            json={"message": "错误数据集", "dataset_version_id": "file-2"},
        )
        assert mismatch.status_code == 409
        assert (
            mismatch.json()["error"]["code"]
            == "CONVERSATION_DATASET_MISMATCH"
        )

        missing = client.post(
            "/api/v2/conversations/conversation-1/runs",
            headers={"Idempotency-Key": "dataset-missing"},
            json={"message": "不存在的数据集", "dataset_version_id": "missing"},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "DATASET_NOT_FOUND"

    session = database.SessionLocal()
    assert (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1")
        .count()
        == 0
    )
    session.close()
