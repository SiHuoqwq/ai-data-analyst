import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.db.database import SessionLocal
from app.db.models import MessageModel
from app.v2.api.dependencies import get_provider, get_recommendation_provider
from app.v2.api.errors import V2APIError
from app.v2.schemas.api import (
    APIMeta,
    ArtifactListResponse,
    ArtifactResponse,
    CancelRunRequest,
    CreateConversationRequest,
    CreateConversationResponse,
    CreateRunRequest,
    CreateRunResponse,
    DatasetRecommendationsResponse,
    RunResponse,
    StepListResponse,
)
from app.v2.services.conversations import (
    ConversationService,
    ConversationServiceError,
)
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.queries import AnalysisQueryService
from app.v2.services.runs import AnalysisRunService, RunServiceError
from app.v2.services.recommendations import (
    DatasetRecommendationService,
    RecommendationServiceError,
)
from app.v2.services.streaming import RunEventStream


router = APIRouter(prefix="/api/v2", tags=["v2-analysis"])
workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="v2-analysis")
queries = AnalysisQueryService()
run_service = AnalysisRunService()
conversation_service = ConversationService()
recommendation_service = DatasetRecommendationService()
event_stream = RunEventStream()


def _meta(page: bool = False) -> APIMeta:
    return APIMeta(
        request_id=str(uuid.uuid4()),
        next_cursor=None if page else None,
        has_more=False if page else None,
    )


def _raise_service_error(exc: RunServiceError):
    raise V2APIError(exc.status_code, exc.code, exc.message) from exc


def _raise_recommendation_service_error(exc: RecommendationServiceError):
    if exc.code == "DATASET_NOT_FOUND":
        raise V2APIError(404, "DATASET_NOT_FOUND", "Dataset does not exist.") from exc
    raise V2APIError(
        503,
        "RECOMMENDATIONS_UNAVAILABLE",
        "Dataset recommendations are temporarily unavailable.",
    ) from exc


def _close_owned_provider(provider) -> None:
    if not getattr(provider, "_owned_by_provider_dependency", False):
        return
    close = getattr(provider, "close", None)
    if callable(close):
        close()


@router.post(
    "/conversations",
    status_code=201,
    response_model=CreateConversationResponse,
)
def create_conversation(body: CreateConversationRequest):
    try:
        return {
            "data": conversation_service.create(body.file_id, body.title),
            "meta": _meta(),
        }
    except ConversationServiceError as exc:
        _raise_service_error(exc)


@router.get(
    "/datasets/{dataset_version_id}/recommendations",
    response_model=DatasetRecommendationsResponse,
)
def get_dataset_recommendations(
    dataset_version_id: str,
    provider=Depends(get_recommendation_provider),
):
    try:
        result = recommendation_service.get_or_generate(dataset_version_id, provider)
        return {
            "data": {
                "dataset_version_id": result.dataset_version_id,
                "recommendations": result.recommendations,
                "source": result.source,
                "generated_at": result.generated_at,
            },
            "meta": _meta(),
        }
    except RecommendationServiceError as exc:
        _raise_recommendation_service_error(exc)
    except Exception as exc:
        raise V2APIError(
            503,
            "RECOMMENDATIONS_UNAVAILABLE",
            "Dataset recommendations are temporarily unavailable.",
        ) from exc


@router.post(
    "/conversations/{conversation_id}/runs",
    status_code=202,
    response_model=CreateRunResponse,
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
    provider_handed_to_executor = False
    try:
        if not idempotency_key:
            raise V2APIError(
                422,
                "VALIDATION_ERROR",
                "缺少 Idempotency-Key",
                {"header": "Idempotency-Key"},
            )
        try:
            run = run_service.find_idempotent_run(
                conversation_id=conversation_id,
                dataset_version_id=body.dataset_version_id,
                message=body.message,
                idempotency_key=idempotency_key,
                parent_run_id=body.parent_run_id,
                retry_of_run_id=body.retry_of_run_id,
                provider_name=provider.name,
                provider_model=provider.model,
                recommendation_id=body.recommendation_id,
            )
        except RunServiceError as exc:
            _raise_service_error(exc)
        trusted_intent = None
        created = False
        if run is None:
            if body.recommendation_id is not None:
                if body.dataset_version_id is None:
                    raise V2APIError(
                        422,
                        "VALIDATION_ERROR",
                        "推荐选择必须包含数据集版本",
                        {"field": "dataset_version_id"},
                    )
                try:
                    trusted_intent = (
                        recommendation_service.resolve_recommendation_intent(
                            body.dataset_version_id,
                            provider,
                            body.recommendation_id,
                            body.message,
                        )
                    )
                except RecommendationServiceError as exc:
                    raise V2APIError(
                        409,
                        "RECOMMENDATION_SELECTION_INVALID",
                        "推荐问题已失效，请刷新后重试。",
                        retryable=False,
                    ) from exc
            try:
                result = run_service.create_run_result(
                    conversation_id=conversation_id,
                    dataset_version_id=body.dataset_version_id,
                    message=body.message,
                    idempotency_key=idempotency_key,
                    parent_run_id=body.parent_run_id,
                    retry_of_run_id=body.retry_of_run_id,
                    provider_name=provider.name,
                    provider_model=provider.model,
                    recommendation_id=body.recommendation_id,
                )
                run = result.run
                created = result.created
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
                        "conversation_id": run.conversation_id,
                        "status": run.status,
                        "dataset_version_id": run.dataset_version_id,
                        "input_message_id": run.trigger_message_id,
                        "output_message_id": run.answer_message_id,
                    },
                    "events_url": f"/api/v2/runs/{run.id}/events",
                },
                "meta": _meta(),
            }
        finally:
            session.close()

        if created:
            workers.submit(
                AnalysisExecutor(provider, trusted_intent=trusted_intent).execute,
                run.id,
            )
            provider_handed_to_executor = True
        return response
    finally:
        if not provider_handed_to_executor:
            _close_owned_provider(provider)


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
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
