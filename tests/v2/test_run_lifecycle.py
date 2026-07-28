import threading
import time
from pathlib import Path

import pytest

from app.db import database
from app.db.models import FileModel, MessageModel
from app.v2.db.models import (
    AnalysisRunModel,
    ArtifactModel,
    RunEventModel,
    RunStepModel,
)
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.provider import FakeAnalysisProvider
from app.v2.services.runs import AnalysisRunService


def create_run(service: AnalysisRunService, key: str = "request-1"):
    return service.create_run(
        conversation_id="conversation-1",
        dataset_version_id="file-1",
        message="请分析这份销售数据",
        idempotency_key=key,
    )


def test_fake_provider_has_deterministic_failure_trigger(v2_runtime):
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    with pytest.raises(RuntimeError, match="controlled fake provider failure"):
        FakeAnalysisProvider().build_plan("[fake:fail]", file_record)
    session.close()


def test_fake_provider_completes_persisted_vertical_run(v2_runtime):
    service = AnalysisRunService()
    run = create_run(service)

    AnalysisExecutor(FakeAnalysisProvider()).execute(run.id)

    session = database.SessionLocal()
    completed = session.get(AnalysisRunModel, run.id)
    steps = (
        session.query(RunStepModel)
        .filter_by(run_id=run.id)
        .order_by(RunStepModel.sequence)
        .all()
    )
    artifacts = session.query(ArtifactModel).filter_by(run_id=run.id).all()
    events = (
        session.query(RunEventModel)
        .filter_by(run_id=run.id)
        .order_by(RunEventModel.sequence)
        .all()
    )

    assert completed.status == "completed"
    assert completed.answer_message_id
    assert session.get(MessageModel, completed.answer_message_id).role == "assistant"
    assert steps
    assert all(step.status == "completed" for step in steps)
    assert {artifact.artifact_type for artifact in artifacts} == {
        "text",
        "metric",
        "table",
        "chart",
    }
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert events[0].event_type == "run.started"
    assert events[-1].event_type == "run.completed"
    assert "answer.completed" in [event.event_type for event in events]

    chart = next(item for item in artifacts if item.artifact_type == "chart")
    assert chart.payload_json["image_url"] == f"/api/v2/artifacts/{chart.id}/download"
    assert not chart.payload_json["image_url"].startswith("./")
    assert "\\" not in chart.payload_json["image_url"]
    assert Path(v2_runtime["chart_dir"], chart.storage_key).is_file()
    session.close()

    database.configure_database(v2_runtime["database_url"])
    restored = database.SessionLocal().get(AnalysisRunModel, run.id)
    assert restored.status == "completed"


def test_executor_persists_sanitized_failure(v2_runtime):
    class FailingProvider(FakeAnalysisProvider):
        def build_plan(self, question, file_record):
            raise RuntimeError(r"secret failed at D:\private\data.csv")

    run = create_run(AnalysisRunService(), "failure-1")
    AnalysisExecutor(FailingProvider()).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    events = session.query(RunEventModel).filter_by(run_id=run.id).all()
    assert failed.status == "failed"
    assert failed.failure_json == {
        "code": "EXECUTION_FAILED",
        "message": "分析执行失败",
        "retryable": False,
        "failed_step_id": None,
    }
    assert events[-1].event_type == "run.failed"
    assert "private" not in str(events[-1].payload_json)
    session.close()


def test_queued_cancel_is_idempotent(v2_runtime):
    service = AnalysisRunService()
    run = create_run(service, "cancel-queued")

    first = service.request_cancel(run.id, "user_requested")
    second = service.request_cancel(run.id, "user_requested")

    assert first.status == "cancelled"
    assert second.status == "cancelled"
    session = database.SessionLocal()
    event_types = [
        event.event_type
        for event in session.query(RunEventModel)
        .filter_by(run_id=run.id)
        .order_by(RunEventModel.sequence)
    ]
    assert event_types.count("run.cancelled") == 1
    session.close()


def test_running_cancel_is_cooperative(v2_runtime):
    service = AnalysisRunService()
    run = create_run(service, "cancel-running")
    executor = AnalysisExecutor(FakeAnalysisProvider(step_delay_seconds=0.15))
    thread = threading.Thread(target=executor.execute, args=(run.id,))
    thread.start()

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        session = database.SessionLocal()
        status = session.get(AnalysisRunModel, run.id).status
        session.close()
        if status == "running":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("run did not enter running")

    requested = service.request_cancel(run.id, "user_requested")
    assert requested.status == "running"
    thread.join(timeout=3)
    assert not thread.is_alive()

    session = database.SessionLocal()
    cancelled = session.get(AnalysisRunModel, run.id)
    assert cancelled.status == "cancelled"
    assert (
        session.query(RunEventModel)
        .filter_by(run_id=run.id, event_type="run.cancelled")
        .count()
        == 1
    )
    session.close()
