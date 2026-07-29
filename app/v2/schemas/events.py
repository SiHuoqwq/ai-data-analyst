import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorPayload(StrictEventModel):
    code: str
    message: str
    retryable: bool
    failed_step_id: str | None = None


class ProgressPayload(StrictEventModel):
    completed_steps: int = Field(ge=0)
    total_steps: int | None = Field(default=None, ge=0)


class RunStartedPayload(StrictEventModel):
    status: Literal["queued"]
    conversation_id: str
    dataset_version_id: str
    trigger_message_id: str
    parent_run_id: str | None = None
    retry_of_run_id: str | None = None


class RunStatusPayload(StrictEventModel):
    status: Literal["queued", "running"]
    current_phase: str | None
    progress: ProgressPayload
    summary: str
    intent_mode: Literal[
        "model",
        "repaired_model",
        "controlled_fallback",
    ] | None = None


class StepStartedPayload(StrictEventModel):
    step_id: str
    plan_step_id: str | None
    step_sequence: int = Field(ge=1)
    phase: str
    operation: str
    display_name: str
    status: Literal["running"]
    attempt: int = Field(ge=1)


class StepCompletedPayload(StrictEventModel):
    step_id: str
    status: Literal["completed"]
    summary: str
    row_count: int | None = Field(default=None, ge=0)
    artifact_ids: list[str]
    warnings: list[str]
    duration_ms: int = Field(ge=0)


class ArtifactCreatedPayload(StrictEventModel):
    artifact_id: str
    step_id: str
    artifact_type: Literal["text", "metric", "table", "chart"]
    title: str
    status: Literal["ready"]
    summary: dict[str, Any]
    preview_url: str


class AnswerCompletedPayload(StrictEventModel):
    answer_message_id: str
    content_format: Literal["markdown", "plain_text"]
    artifact_ids: list[str]


class RunCompletedPayload(StrictEventModel):
    status: Literal["completed"]
    answer_message_id: str
    artifact_ids: list[str]
    completed_at: str


class RunFailedPayload(StrictEventModel):
    status: Literal["failed"]
    error: ErrorPayload
    partial_artifact_ids: list[str]
    retry_of_run_id: str | None = None


class RunCancelledPayload(StrictEventModel):
    status: Literal["cancelled"]
    reason: str
    cancelled_at: str
    partial_artifact_ids: list[str]


class HeartbeatPayload(StrictEventModel):
    server_time: str
    last_event_sequence: int = Field(ge=0)


class EventEnvelope(StrictEventModel):
    event_id: str
    event_type: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime.datetime
    schema_version: Literal["1.0"] = "1.0"
    payload: dict[str, Any]


EVENT_PAYLOAD_MODELS = {
    "run.started": RunStartedPayload,
    "run.status": RunStatusPayload,
    "step.started": StepStartedPayload,
    "step.completed": StepCompletedPayload,
    "artifact.created": ArtifactCreatedPayload,
    "answer.completed": AnswerCompletedPayload,
    "run.completed": RunCompletedPayload,
    "run.failed": RunFailedPayload,
    "run.cancelled": RunCancelledPayload,
    "heartbeat": HeartbeatPayload,
}
