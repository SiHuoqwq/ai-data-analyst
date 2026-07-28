import time
import uuid

from app.db.database import SessionLocal
from app.db.models import FileModel, MessageModel
from app.v2.db.models import (
    AnalysisRunModel,
    ArtifactModel,
    RunStepModel,
    utc_now,
)
from app.v2.domain.state_machine import RunStatus, StepStatus, transition_run
from app.v2.services.artifacts import ArtifactFactory
from app.v2.services.events import EventEmitter
from app.v2.services.provider import AnalysisProvider
from app.v2.services.runs import AnalysisRunService
from app.v2.services.tools import V1DataToolAdapter


class AnalysisExecutor:
    def __init__(
        self,
        provider: AnalysisProvider,
        tools: V1DataToolAdapter | None = None,
        artifacts: ArtifactFactory | None = None,
        events: EventEmitter | None = None,
    ):
        self.provider = provider
        self.tools = tools or V1DataToolAdapter()
        self.artifacts = artifacts or ArtifactFactory()
        self.events = events or EventEmitter()
        self.run_service = AnalysisRunService(self.events)

    def execute(self, run_id: str) -> None:
        session = SessionLocal()
        active_step = None
        try:
            run = session.get(AnalysisRunModel, run_id)
            if not run or run.status != RunStatus.QUEUED.value:
                return
            if self._cancel_if_requested(session, run):
                return

            transition_run(RunStatus(run.status), RunStatus.RUNNING)
            now = utc_now()
            run.status = RunStatus.RUNNING.value
            run.current_phase = "plan_generation"
            run.started_at = now
            run.updated_at = now
            self.events.emit(
                session,
                run,
                "run.status",
                {
                    "status": "running",
                    "current_phase": "plan_generation",
                    "progress": {"completed_steps": 0, "total_steps": None},
                    "summary": "正在生成分析计划",
                },
            )
            session.commit()

            file_record = session.get(FileModel, run.dataset_version_id)
            question = session.get(MessageModel, run.trigger_message_id).content
            plan = self.provider.build_plan(question, file_record)
            total_steps = len(plan.steps) + 2
            run.progress_json = {"completed_steps": 0, "total_steps": total_steps}
            session.commit()

            produced_ids: list[str] = []
            step_sequence = 0
            for provider_step in plan.steps:
                if self._cancel_if_requested(session, run, active_step):
                    return
                self.provider.before_step()
                if self._cancel_if_requested(session, run, active_step):
                    return
                step_sequence += 1
                active_step = self._start_step(
                    session,
                    run,
                    step_sequence,
                    "execution",
                    provider_step.operation,
                    provider_step.display_name,
                    provider_step.step_id,
                    total_steps,
                )
                started = time.monotonic()
                if provider_step.operation == "inspect_dataset":
                    drafts = self.tools.inspect(file_record)
                else:
                    drafts = [self.tools.visualize(file_record)]
                artifacts = [
                    self.artifacts.create(session, run, active_step, draft)
                    for draft in drafts
                ]
                session.flush()
                produced_ids.extend(item.id for item in artifacts)
                self._complete_step(
                    session,
                    run,
                    active_step,
                    artifacts,
                    int((time.monotonic() - started) * 1000),
                    total_steps,
                )
                active_step = None

            if self._cancel_if_requested(session, run, active_step):
                return
            step_sequence += 1
            active_step = self._start_step(
                session,
                run,
                step_sequence,
                "result_validation",
                "validate_results",
                "校验分析结果",
                None,
                total_steps,
            )
            artifact_types = {
                item[0]
                for item in session.query(ArtifactModel.artifact_type)
                .filter_by(run_id=run.id, status="ready")
                .all()
            }
            if artifact_types != {"text", "metric", "table", "chart"}:
                raise RuntimeError("required artifacts missing")
            self._complete_step(
                session, run, active_step, [], 0, total_steps
            )
            active_step = None

            if self._cancel_if_requested(session, run, active_step):
                return
            step_sequence += 1
            active_step = self._start_step(
                session,
                run,
                step_sequence,
                "answer_generation",
                "generate_answer",
                "生成最终回答",
                None,
                total_steps,
            )
            answer = self.provider.build_answer(
                question, file_record, produced_ids
            )
            answer_message = MessageModel(
                id=str(uuid.uuid4()),
                conv_id=run.conversation_id,
                role="assistant",
                content=answer,
                tool_calls=None,
                chart_ids=[],
                created_at=utc_now(),
            )
            session.add(answer_message)
            session.flush()
            self._complete_step(
                session, run, active_step, [], 0, total_steps
            )
            active_step = None

            transition_run(RunStatus(run.status), RunStatus.COMPLETED)
            completed_at = utc_now()
            run.status = RunStatus.COMPLETED.value
            run.current_phase = None
            run.answer_message_id = answer_message.id
            run.completed_at = completed_at
            run.updated_at = completed_at
            self.events.emit(
                session,
                run,
                "answer.completed",
                {
                    "answer_message_id": answer_message.id,
                    "content_format": "markdown",
                    "artifact_ids": produced_ids,
                },
            )
            self.events.emit(
                session,
                run,
                "run.completed",
                {
                    "status": "completed",
                    "answer_message_id": answer_message.id,
                    "artifact_ids": produced_ids,
                    "completed_at": completed_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            run = session.get(AnalysisRunModel, run_id)
            if run and run.status not in {
                RunStatus.COMPLETED.value,
                RunStatus.FAILED.value,
                RunStatus.CANCELLED.value,
            }:
                if active_step is not None:
                    active_step = session.get(RunStepModel, active_step.id)
                    active_step.status = StepStatus.FAILED.value
                    active_step.error_json = {
                        "code": "EXECUTION_FAILED",
                        "message": "分析步骤执行失败",
                        "retryable": False,
                    }
                    active_step.finished_at = utc_now()
                failure = {
                    "code": "EXECUTION_FAILED",
                    "message": "分析执行失败",
                    "retryable": False,
                    "failed_step_id": active_step.id if active_step else None,
                }
                run.status = RunStatus.FAILED.value
                run.current_phase = None
                run.failure_json = failure
                run.completed_at = utc_now()
                run.updated_at = run.completed_at
                partial_ids = [
                    item[0]
                    for item in session.query(ArtifactModel.id)
                    .filter_by(run_id=run.id, status="ready")
                    .all()
                ]
                self.events.emit(
                    session,
                    run,
                    "run.failed",
                    {
                        "status": "failed",
                        "error": failure,
                        "partial_artifact_ids": partial_ids,
                        "retry_of_run_id": run.retry_of_run_id,
                    },
                    active_step.id if active_step else None,
                )
                session.commit()
        finally:
            session.close()

    def _start_step(
        self,
        session,
        run,
        sequence,
        phase,
        operation,
        display_name,
        plan_step_id,
        total_steps,
    ):
        now = utc_now()
        run.current_phase = phase
        run.updated_at = now
        step = RunStepModel(
            id=str(uuid.uuid4()),
            run_id=run.id,
            plan_step_id=plan_step_id,
            sequence=sequence,
            phase=phase,
            operation=operation,
            display_name=display_name,
            status=StepStatus.RUNNING.value,
            input_json={
                "schema_version": "1.0",
                "dataset_version_id": run.dataset_version_id,
            },
            attempt_count=1,
            max_attempts=1,
            idempotency_key=f"{run.id}:{sequence}:1",
            created_at=now,
            updated_at=now,
            started_at=now,
        )
        session.add(step)
        session.flush()
        self.events.emit(
            session,
            run,
            "run.status",
            {
                "status": "running",
                "current_phase": phase,
                "progress": run.progress_json,
                "summary": display_name,
            },
        )
        self.events.emit(
            session,
            run,
            "step.started",
            {
                "step_id": step.id,
                "plan_step_id": plan_step_id,
                "step_sequence": sequence,
                "phase": phase,
                "operation": operation,
                "display_name": display_name,
                "status": "running",
                "attempt": 1,
            },
            step.id,
        )
        session.commit()
        return step

    def _complete_step(
        self,
        session,
        run,
        step,
        artifacts,
        duration_ms,
        total_steps,
    ):
        now = utc_now()
        artifact_ids = [item.id for item in artifacts]
        step.status = StepStatus.COMPLETED.value
        step.output_summary_json = {
            "schema_version": "1.0",
            "description": step.display_name,
            "artifact_ids": artifact_ids,
        }
        step.finished_at = now
        step.updated_at = now
        completed_steps = int(run.progress_json["completed_steps"]) + 1
        run.progress_json = {
            "completed_steps": completed_steps,
            "total_steps": total_steps,
        }
        run.updated_at = now
        for artifact in artifacts:
            self.events.emit(
                session,
                run,
                "artifact.created",
                {
                    "artifact_id": artifact.id,
                    "step_id": step.id,
                    "artifact_type": artifact.artifact_type,
                    "title": artifact.title,
                    "status": "ready",
                    "summary": {"artifact_type": artifact.artifact_type},
                    "preview_url": f"/api/v2/artifacts/{artifact.id}",
                },
                step.id,
            )
        self.events.emit(
            session,
            run,
            "step.completed",
            {
                "step_id": step.id,
                "status": "completed",
                "summary": step.display_name,
                "row_count": sum(
                    artifact.row_count or 0 for artifact in artifacts
                )
                or None,
                "artifact_ids": artifact_ids,
                "warnings": [],
                "duration_ms": duration_ms,
            },
            step.id,
        )
        session.commit()

    def _cancel_if_requested(self, session, run, active_step=None):
        session.refresh(run)
        if run.cancel_requested_at is None:
            return False
        if active_step is not None:
            active_step = session.get(RunStepModel, active_step.id)
            if active_step and active_step.status in {
                StepStatus.PENDING.value,
                StepStatus.RUNNING.value,
            }:
                active_step.status = StepStatus.CANCELLED.value
                active_step.finished_at = utc_now()
                active_step.updated_at = active_step.finished_at
        self.run_service._confirm_cancel(session, run, "user_requested")
        session.commit()
        return True
