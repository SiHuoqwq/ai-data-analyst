import hashlib
import json
import uuid
from dataclasses import dataclass

from app.db.database import SessionLocal
from app.db.models import ConversationModel, FileModel, MessageModel
from app.v2.db.models import AnalysisRunModel, ArtifactModel, utc_now
from app.v2.domain.state_machine import RunStatus, transition_run
from app.v2.services.events import EventEmitter


class RunServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class RunCreationResult:
    run: AnalysisRunModel
    created: bool


class AnalysisRunService:
    def __init__(self, event_emitter: EventEmitter | None = None):
        self.events = event_emitter or EventEmitter()

    def create_run(
        self,
        conversation_id: str,
        dataset_version_id: str | None,
        message: str,
        idempotency_key: str,
        parent_run_id: str | None = None,
        retry_of_run_id: str | None = None,
        provider_name: str = "fake",
        provider_model: str = "deterministic-v1",
    ) -> AnalysisRunModel:
        return self.create_run_result(
            conversation_id=conversation_id,
            dataset_version_id=dataset_version_id,
            message=message,
            idempotency_key=idempotency_key,
            parent_run_id=parent_run_id,
            retry_of_run_id=retry_of_run_id,
            provider_name=provider_name,
            provider_model=provider_model,
        ).run

    def create_run_result(
        self,
        conversation_id: str,
        dataset_version_id: str | None,
        message: str,
        idempotency_key: str,
        parent_run_id: str | None = None,
        retry_of_run_id: str | None = None,
        provider_name: str = "fake",
        provider_model: str = "deterministic-v1",
    ) -> RunCreationResult:
        session = SessionLocal()
        try:
            conversation = session.get(ConversationModel, conversation_id)
            if not conversation:
                raise RunServiceError(
                    "CONVERSATION_NOT_FOUND", "对话不存在", 404
                )
            resolved_version_id = dataset_version_id or conversation.file_id
            file_record = session.get(FileModel, resolved_version_id)
            if not file_record:
                raise RunServiceError(
                    "DATASET_NOT_FOUND", "数据集不存在", 404
                )
            if conversation.file_id != resolved_version_id:
                raise RunServiceError(
                    "CONVERSATION_DATASET_MISMATCH",
                    "数据集与当前对话不一致",
                    409,
                )
            request_body = {
                "message": message,
                "dataset_version_id": resolved_version_id,
                "parent_run_id": parent_run_id,
                "retry_of_run_id": retry_of_run_id,
                "provider": provider_name,
                "model": provider_model,
            }
            request_hash = hashlib.sha256(
                json.dumps(
                    request_body,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            existing = (
                session.query(AnalysisRunModel)
                .filter_by(
                    conversation_id=conversation_id,
                    idempotency_key=idempotency_key,
                )
                .first()
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise RunServiceError(
                        "IDEMPOTENCY_CONFLICT",
                        "幂等键已用于不同请求",
                        409,
                    )
                session.refresh(existing)
                return RunCreationResult(run=existing, created=False)

            now = utc_now()
            trigger = MessageModel(
                id=str(uuid.uuid4()),
                conv_id=conversation_id,
                role="user",
                content=message,
                tool_calls=None,
                chart_ids=[],
                created_at=now,
            )
            run = AnalysisRunModel(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                dataset_version_id=resolved_version_id,
                trigger_message_id=trigger.id,
                parent_run_id=parent_run_id,
                retry_of_run_id=retry_of_run_id,
                status=RunStatus.QUEUED.value,
                context_snapshot_json={
                    "schema_version": "1.0",
                    "selected_message_ids": [trigger.id],
                    "selected_run_ids": [],
                    "selected_artifact_ids": [],
                },
                progress_json={"completed_steps": 0, "total_steps": None},
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                model_config_json={
                    "provider": provider_name,
                    "model": provider_model,
                    "schema_version": "1.0",
                },
                last_event_sequence=0,
                created_at=now,
                updated_at=now,
            )
            session.add(trigger)
            session.add(run)
            session.flush()
            self.events.emit(
                session,
                run,
                "run.started",
                {
                    "status": "queued",
                    "conversation_id": conversation_id,
                    "dataset_version_id": resolved_version_id,
                    "trigger_message_id": trigger.id,
                    "parent_run_id": parent_run_id,
                    "retry_of_run_id": retry_of_run_id,
                },
            )
            session.commit()
            session.refresh(run)
            return RunCreationResult(run=run, created=True)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def request_cancel(self, run_id: str, reason: str) -> AnalysisRunModel:
        session = SessionLocal()
        try:
            run = session.get(AnalysisRunModel, run_id)
            if not run:
                raise RunServiceError("RUN_NOT_FOUND", "分析任务不存在", 404)
            if run.status == RunStatus.CANCELLED.value:
                session.refresh(run)
                return run
            if run.status in {RunStatus.COMPLETED.value, RunStatus.FAILED.value}:
                raise RunServiceError(
                    "RUN_NOT_CANCELLABLE", "当前分析任务不能取消", 409
                )
            if run.cancel_requested_at is None:
                run.cancel_requested_at = utc_now()
            if run.status == RunStatus.QUEUED.value:
                self._confirm_cancel(session, run, reason)
            session.commit()
            session.refresh(run)
            return run
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _confirm_cancel(self, session, run: AnalysisRunModel, reason: str) -> None:
        if run.status == RunStatus.CANCELLED.value:
            return
        transition_run(RunStatus(run.status), RunStatus.CANCELLED)
        now = utc_now()
        run.status = RunStatus.CANCELLED.value
        run.current_phase = None
        run.cancelled_at = now
        run.completed_at = now
        run.updated_at = now
        artifact_ids = [
            item[0]
            for item in session.query(ArtifactModel.id)
            .filter_by(run_id=run.id, status="ready")
            .all()
        ]
        self.events.emit(
            session,
            run,
            "run.cancelled",
            {
                "status": "cancelled",
                "reason": reason,
                "cancelled_at": now.isoformat().replace("+00:00", "Z"),
                "partial_artifact_ids": artifact_ids,
            },
        )
