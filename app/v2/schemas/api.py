import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunContextRequest(APIModel):
    include_message_ids: list[str] = Field(default_factory=list, max_length=50)
    include_artifact_ids: list[str] = Field(default_factory=list, max_length=50)


class CreateRunRequest(APIModel):
    message: str = Field(min_length=1, max_length=4000)
    dataset_version_id: str | None = None
    confirm_version_switch: bool = False
    reply_to_message_id: str | None = None
    parent_run_id: str | None = None
    retry_of_run_id: str | None = None
    context: RunContextRequest = Field(default_factory=RunContextRequest)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "message": "分析销售数据的主要特征",
                    "dataset_version_id": "file-uuid",
                    "confirm_version_switch": False,
                    "context": {
                        "include_message_ids": [],
                        "include_artifact_ids": [],
                    },
                }
            ]
        },
    )


class CancelRunRequest(APIModel):
    reason: str = Field(default="user_requested", min_length=1, max_length=200)


class APIMeta(APIModel):
    request_id: str
    schema_version: str = "1.0"
    next_cursor: str | None = None
    has_more: bool | None = None


class RunSummary(APIModel):
    id: str
    conversation_id: str
    dataset_version_id: str
    trigger_message_id: str
    answer_message_id: str | None
    status: str
    current_phase: str | None
    progress: dict[str, Any]
    failure: dict[str, Any] | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    cancelled_at: datetime.datetime | None
    last_event_sequence: int
    allowed_actions: dict[str, bool]


class CreatedMessage(APIModel):
    id: str
    role: str
    content_text: str
    status: str


class CreatedRun(APIModel):
    id: str
    status: str
    dataset_version_id: str


class CreateRunData(APIModel):
    message: CreatedMessage
    run: CreatedRun
    events_url: str


class CreateRunResponse(APIModel):
    data: CreateRunData
    meta: APIMeta


class RunResponse(APIModel):
    data: RunSummary
    meta: APIMeta


class RunStepSummary(APIModel):
    id: str
    plan_step_id: str | None
    sequence: int
    phase: str
    operation: str
    display_name: str
    status: str
    attempt: int
    max_attempts: int
    output_summary: dict[str, Any] | None
    error: dict[str, Any] | None
    artifact_ids: list[str]
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None


class ArtifactSummary(APIModel):
    id: str
    dataset_version_id: str
    run_id: str
    run_step_id: str
    artifact_type: str
    status: str
    title: str
    content_format: str
    payload: dict[str, Any]
    size_bytes: int
    row_count: int | None
    download_available: bool
    created_at: datetime.datetime


class StepListResponse(APIModel):
    data: list[RunStepSummary]
    meta: APIMeta


class ArtifactListResponse(APIModel):
    data: list[ArtifactSummary]
    meta: APIMeta


class ArtifactResponse(APIModel):
    data: ArtifactSummary
    meta: APIMeta
