import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.db.database import SessionLocal
from app.db.models import MessageModel
from app.v2.api.dependencies import get_provider
from app.v2.api.errors import V2APIError
from app.v2.schemas.api import (
    APIMeta,
    ArtifactListResponse,
    ArtifactResponse,
    CancelRunRequest,
    CreateRunRequest,
    CreateRunResponse,
    RunResponse,
    StepListResponse,
)
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.queries import AnalysisQueryService
from app.v2.services.runs import AnalysisRunService, RunServiceError
from app.v2.services.streaming import RunEventStream


router = APIRouter(prefix="/api/v2", tags=["v2-analysis"])
workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="v2-analysis")
queries = AnalysisQueryService()
run_service = AnalysisRunService()
event_stream = RunEventStream()


def _meta(page: bool = False) -> APIMeta:
    return APIMeta(
        request_id=str(uuid.uuid4()),
        next_cursor=None if page else None,
        has_more=False if page else None,
    )


def _raise_service_error(exc: RunServiceError):
    raise V2APIError(exc.status_code, exc.code, exc.message) from exc


@router.post(
    "/conversations/{conversation_id}/runs",
    status_code=202,
    response_model=CreateRunResponse,
    response_model_exclude_none=True,
)
def create_run(
    conversation_id: str,
    body: CreateRunRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="同一对话范围内的幂等键",
    ),
    provider=Depends(get_provider),
):
    if not idempotency_key:
        raise V2APIError(
            422,
            "VALIDATION_ERROR",
            "缺少 Idempotency-Key",
            {"header": "Idempotency-Key"},
        )
    try:
        run = run_service.create_run(
            conversation_id=conversation_id,
            dataset_version_id=body.dataset_version_id,
            message=body.message,
            idempotency_key=idempotency_key,
            parent_run_id=body.parent_run_id,
            retry_of_run_id=body.retry_of_run_id,
        )
    except RunServiceError as exc:
        _raise_service_error(exc)

    session = SessionLocal()
    try:
        message = session.get(MessageModel, run.trigger_message_id)
        response = {
            "data": {
                "message": {
                    "id": message.id,
                    "role": message.role,
                    "content_text": message.content,
                    "status": "committed",
                },
                "run": {
                    "id": run.id,
                    "status": run.status,
                    "dataset_version_id": run.dataset_version_id,
                },
                "events_url": f"/api/v2/runs/{run.id}/events",
            },
            "meta": _meta(),
        }
    finally:
        session.close()

    workers.submit(AnalysisExecutor(provider).execute, run.id)
    return response


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    response_model_exclude_none=True,
)
def get_run(run_id: str):
    try:
        return {"data": queries.get_run(run_id), "meta": _meta()}
    except RunServiceError as exc:
        _raise_service_error(exc)


@router.get("/runs/{run_id}/steps", response_model=StepListResponse)
def list_steps(run_id: str):
    try:
        return {"data": queries.list_steps(run_id), "meta": _meta(page=True)}
    except RunServiceError as exc:
        _raise_service_error(exc)


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactListResponse)
def list_artifacts(run_id: str):
    try:
        return {
            "data": queries.list_artifacts(run_id),
            "meta": _meta(page=True),
        }
    except RunServiceError as exc:
        _raise_service_error(exc)


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
    response_model_exclude_none=True,
)
def get_artifact(artifact_id: str):
    try:
        return {"data": queries.get_artifact(artifact_id), "meta": _meta()}
    except RunServiceError as exc:
        _raise_service_error(exc)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str):
    try:
        path = queries.artifact_file(artifact_id)
        return FileResponse(path, media_type="image/png", filename=f"{artifact_id}.png")
    except RunServiceError as exc:
        _raise_service_error(exc)


@router.post(
    "/runs/{run_id}/cancel",
    status_code=202,
    response_model=RunResponse,
    response_model_exclude_none=True,
)
def cancel_run(run_id: str, body: CancelRunRequest):
    try:
        run_service.request_cancel(run_id, body.reason)
        return {"data": queries.get_run(run_id), "meta": _meta()}
    except RunServiceError as exc:
        _raise_service_error(exc)


@router.get("/runs/{run_id}/events")
async def stream_events(
    request: Request,
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    try:
        queries.get_run(run_id)
        if last_event_id:
            after_sequence = max(
                after_sequence,
                event_stream.sequence_for_event(run_id, last_event_id),
            )
    except RunServiceError as exc:
        _raise_service_error(exc)
    return StreamingResponse(
        event_stream.stream(request, run_id, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
