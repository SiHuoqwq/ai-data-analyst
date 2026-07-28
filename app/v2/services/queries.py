from pathlib import Path

from app.config import settings
from app.db.database import SessionLocal
from app.v2.db.models import (
    AnalysisRunModel,
    ArtifactModel,
    RunStepModel,
    as_utc,
)
from app.v2.services.runs import RunServiceError


class AnalysisQueryService:
    def get_run(self, run_id: str) -> dict:
        session = SessionLocal()
        try:
            run = session.get(AnalysisRunModel, run_id)
            if not run:
                raise RunServiceError("RUN_NOT_FOUND", "分析任务不存在", 404)
            return self._run_dict(run)
        finally:
            session.close()

    def list_steps(self, run_id: str) -> list[dict]:
        session = SessionLocal()
        try:
            if not session.get(AnalysisRunModel, run_id):
                raise RunServiceError("RUN_NOT_FOUND", "分析任务不存在", 404)
            steps = (
                session.query(RunStepModel)
                .filter_by(run_id=run_id)
                .order_by(RunStepModel.sequence)
                .all()
            )
            artifact_rows = (
                session.query(ArtifactModel.run_step_id, ArtifactModel.id)
                .filter_by(run_id=run_id, status="ready")
                .all()
            )
            artifact_ids: dict[str, list[str]] = {}
            for step_id, artifact_id in artifact_rows:
                artifact_ids.setdefault(step_id, []).append(artifact_id)
            return [
                {
                    "id": step.id,
                    "plan_step_id": step.plan_step_id,
                    "sequence": step.sequence,
                    "phase": step.phase,
                    "operation": step.operation,
                    "display_name": step.display_name,
                    "status": step.status,
                    "attempt": step.attempt_count,
                    "max_attempts": step.max_attempts,
                    "output_summary": step.output_summary_json,
                    "error": step.error_json,
                    "artifact_ids": artifact_ids.get(step.id, []),
                    "started_at": as_utc(step.started_at),
                    "finished_at": as_utc(step.finished_at),
                }
                for step in steps
            ]
        finally:
            session.close()

    def list_artifacts(self, run_id: str) -> list[dict]:
        session = SessionLocal()
        try:
            if not session.get(AnalysisRunModel, run_id):
                raise RunServiceError("RUN_NOT_FOUND", "分析任务不存在", 404)
            artifacts = (
                session.query(ArtifactModel)
                .filter_by(run_id=run_id, status="ready")
                .order_by(ArtifactModel.created_at, ArtifactModel.id)
                .all()
            )
            return [self._artifact_dict(artifact) for artifact in artifacts]
        finally:
            session.close()

    def get_artifact(self, artifact_id: str) -> dict:
        session = SessionLocal()
        try:
            artifact = session.get(ArtifactModel, artifact_id)
            if not artifact:
                raise RunServiceError(
                    "ARTIFACT_NOT_FOUND", "分析产物不存在", 404
                )
            return self._artifact_dict(artifact)
        finally:
            session.close()

    def artifact_file(self, artifact_id: str) -> Path:
        session = SessionLocal()
        try:
            artifact = session.get(ArtifactModel, artifact_id)
            if not artifact:
                raise RunServiceError(
                    "ARTIFACT_NOT_FOUND", "分析产物不存在", 404
                )
            if (
                artifact.artifact_type != "chart"
                or artifact.storage_backend != "local"
                or not artifact.storage_key
            ):
                raise RunServiceError(
                    "DOWNLOAD_NOT_AVAILABLE", "该分析产物不可下载", 409
                )
            root = Path(settings.chart_dir).resolve()
            candidate = (root / artifact.storage_key).resolve()
            if root not in candidate.parents or not candidate.is_file():
                raise RunServiceError(
                    "ARTIFACT_FILE_NOT_FOUND", "分析产物文件不存在", 404
                )
            return candidate
        finally:
            session.close()

    @staticmethod
    def _run_dict(run: AnalysisRunModel) -> dict:
        terminal = run.status in {"completed", "failed", "cancelled"}
        return {
            "id": run.id,
            "conversation_id": run.conversation_id,
            "dataset_version_id": run.dataset_version_id,
            "trigger_message_id": run.trigger_message_id,
            "answer_message_id": run.answer_message_id,
            "input_message_id": run.trigger_message_id,
            "output_message_id": run.answer_message_id,
            "status": run.status,
            "current_phase": run.current_phase,
            "progress": run.progress_json,
            "failure": run.failure_json,
            "created_at": as_utc(run.created_at),
            "updated_at": as_utc(run.updated_at),
            "started_at": as_utc(run.started_at),
            "completed_at": as_utc(run.completed_at),
            "finished_at": as_utc(run.completed_at),
            "cancelled_at": as_utc(run.cancelled_at),
            "error": run.failure_json,
            "last_event_sequence": run.last_event_sequence,
            "allowed_actions": {
                "cancel": run.status in {"queued", "running"},
                "retry": terminal,
                "open_artifact": run.status == "completed",
            },
        }

    @staticmethod
    def _artifact_dict(artifact: ArtifactModel) -> dict:
        return {
            "id": artifact.id,
            "dataset_version_id": artifact.dataset_version_id,
            "run_id": artifact.run_id,
            "run_step_id": artifact.run_step_id,
            "artifact_type": artifact.artifact_type,
            "status": artifact.status,
            "title": artifact.title,
            "content_format": artifact.content_format,
            "payload": artifact.payload_json,
            "size_bytes": artifact.size_bytes,
            "row_count": artifact.row_count,
            "download_available": artifact.storage_backend == "local",
            "created_at": as_utc(artifact.created_at),
        }
