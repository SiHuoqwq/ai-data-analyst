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
from app.v2.services.artifacts import ArtifactDraft, ArtifactFactory
from app.v2.services.analytics import (
    StructuredAnalysisTools,
    ToolExecutionError,
    ToolExecutionResult,
)
from app.v2.services.events import EventEmitter
from app.v2.services.evidence import EvidenceRegistry
from app.v2.services.markdown_renderer import ConclusionMarkdownRenderer
from app.v2.services.provider import AnalysisProvider, ProviderError
from app.v2.services.runs import AnalysisRunService
from app.v2.services.tools import V1DataToolAdapter


class AnalysisExecutor:
    def __init__(
        self,
        provider: AnalysisProvider,
        tools: V1DataToolAdapter | None = None,
        artifacts: ArtifactFactory | None = None,
        events: EventEmitter | None = None,
        structured_tools: StructuredAnalysisTools | None = None,
    ):
        self.provider = provider
        self.tools = tools or V1DataToolAdapter()
        self.structured_tools = structured_tools or StructuredAnalysisTools()
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
            history = (
                session.query(MessageModel)
                .filter(
                    MessageModel.conv_id == run.conversation_id,
                    MessageModel.id != run.trigger_message_id,
                )
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(10)
                .all()
            )
            history_context = [
                {"role": item.role, "content": item.content}
                for item in reversed(history)
                if item.role in {"user", "assistant"}
            ]
            self.provider.set_history(history_context)
            set_cancel_check = getattr(
                self.provider, "set_cancel_check", None
            )
            if callable(set_cancel_check):
                def provider_cancel_requested():
                    session.refresh(
                        run, attribute_names=["cancel_requested_at"]
                    )
                    return run.cancel_requested_at is not None

                set_cancel_check(provider_cancel_requested)
            plan = self.provider.build_plan(question, file_record)
            expected_artifact_types: set[str] = set()
            structured_outputs = {
                "inspect_dataset": {"text", "metric"},
                "group_aggregate": {"table"},
                "monthly_trend": {"table"},
                "identify_underperforming": {"table"},
                "create_chart": {"chart"},
            }
            for planned_step in plan.steps:
                if (
                    planned_step.operation == "inspect_dataset"
                    and planned_step.arguments is None
                ):
                    expected_artifact_types.update({"text", "metric", "table"})
                elif planned_step.operation == "create_visualization":
                    expected_artifact_types.add("chart")
                else:
                    expected_artifact_types.update(
                        structured_outputs.get(planned_step.operation, set())
                    )
            total_steps = len(plan.steps) + 2
            run.progress_json = {"completed_steps": 0, "total_steps": total_steps}
            session.commit()

            produced_ids: list[str] = []
            evidence: list[dict] = []
            prior_results: dict[str, ToolExecutionResult] = {}
            tool_rounds = 0
            max_tool_rounds = int(
                getattr(self.provider, "max_tool_rounds", len(plan.steps) + 1)
            )
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
                    provider_step.arguments,
                )
                started = time.monotonic()
                tool_result = None
                if provider_step.arguments is not None:
                    tool_rounds += 1
                    if tool_rounds > max_tool_rounds:
                        raise ProviderError(
                            "TOOL_ROUND_LIMIT_EXCEEDED",
                            "分析工具调用超过允许的轮次",
                            retryable=False,
                        )
                    try:
                        tool_result = self.structured_tools.execute(
                            provider_step.operation,
                            provider_step.arguments,
                            file_record,
                            prior_results,
                        )
                    except ToolExecutionError as tool_error:
                        repair = getattr(self.provider, "repair_step", None)
                        if not callable(repair) or tool_rounds >= max_tool_rounds:
                            raise
                        repaired_step = repair(
                            question,
                            file_record,
                            {
                                "step_id": provider_step.step_id,
                                "operation": provider_step.operation,
                                "arguments": provider_step.arguments,
                            },
                            {
                                "code": tool_error.code,
                                "message": tool_error.message,
                                "details": tool_error.details,
                            },
                            evidence,
                        )
                        if self._cancel_if_requested(session, run, active_step):
                            return
                        if repaired_step is None:
                            raise
                        tool_rounds += 1
                        active_step.attempt_count = 2
                        active_step.max_attempts = 2
                        active_step.operation = repaired_step.operation
                        active_step.display_name = repaired_step.display_name
                        active_step.input_json = {
                            "schema_version": "1.0",
                            "dataset_version_id": run.dataset_version_id,
                            "arguments": repaired_step.arguments or {},
                            "repaired_from": {
                                "code": tool_error.code,
                                "operation": provider_step.operation,
                            },
                        }
                        active_step.updated_at = utc_now()
                        session.commit()
                        tool_result = self.structured_tools.execute(
                            repaired_step.operation,
                            repaired_step.arguments or {},
                            file_record,
                            prior_results,
                        )
                    prior_results[provider_step.step_id] = tool_result
                    drafts = tool_result.drafts
                elif provider_step.operation == "inspect_dataset":
                    drafts = self.tools.inspect(file_record)
                else:
                    drafts = [self.tools.visualize(file_record)]
                artifacts = [
                    self.artifacts.create(session, run, active_step, draft)
                    for draft in drafts
                ]
                session.flush()
                produced_ids.extend(item.id for item in artifacts)
                if tool_result is not None:
                    result_evidence = tool_result.evidence()
                    evidence.extend(
                        {
                            "artifact_id": artifact.id,
                            "artifact_type": artifact.artifact_type,
                            "title": artifact.title,
                            "source_tool": provider_step.operation,
                            **result_evidence,
                        }
                        for artifact in artifacts
                    )
                else:
                    evidence.extend(
                        {
                            "artifact_id": artifact.id,
                            "artifact_type": artifact.artifact_type,
                            "title": artifact.title,
                            "source_tool": provider_step.operation,
                            "summary": {
                                "row_count": artifact.row_count,
                            },
                            "preview": (
                                artifact.payload_json.get("rows", [])[:20]
                                if isinstance(artifact.payload_json, dict)
                                else []
                            ),
                            "warnings": [],
                        }
                        for artifact in artifacts
                    )
                self._complete_step(
                    session,
                    run,
                    active_step,
                    artifacts,
                    int((time.monotonic() - started) * 1000),
                    total_steps,
                    tool_result,
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
                None,
            )
            artifact_types = {
                item[0]
                for item in session.query(ArtifactModel.artifact_type)
                .filter_by(run_id=run.id, status="ready")
                .all()
            }
            if (
                not expected_artifact_types
                or not expected_artifact_types.issubset(artifact_types)
            ):
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
                None,
            )
            registry = EvidenceRegistry.from_tool_evidence(run.id, evidence)
            build_conclusion = getattr(
                self.provider, "build_conclusion", None
            )
            if callable(build_conclusion):
                conclusion = build_conclusion(
                    question, file_record, registry
                )
                registry.validate_conclusion(conclusion)
                answer = ConclusionMarkdownRenderer().render(
                    conclusion, registry
                )
            else:
                answer = self.provider.build_answer(
                    question, file_record, evidence
                )
            if self._cancel_if_requested(session, run, active_step):
                return
            answer_artifact = self.artifacts.create(
                session,
                run,
                active_step,
                ArtifactDraft(
                    artifact_type="text",
                    title="分析结论",
                    content_format="markdown",
                    payload={"format": "markdown", "content": answer},
                ),
            )
            session.flush()
            produced_ids.append(answer_artifact.id)
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
                session,
                run,
                active_step,
                [answer_artifact],
                0,
                total_steps,
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
        except Exception as exc:
            session.rollback()
            run = session.get(AnalysisRunModel, run_id)
            if (
                run
                and isinstance(exc, ProviderError)
                and exc.code == "RUN_CANCELLED"
                and run.cancel_requested_at is not None
            ):
                self.run_service._confirm_cancel(
                    session, run, "user_requested"
                )
                session.commit()
                return
            if run and run.status not in {
                RunStatus.COMPLETED.value,
                RunStatus.FAILED.value,
                RunStatus.CANCELLED.value,
            }:
                if isinstance(exc, ProviderError):
                    error_code = exc.code
                    error_message = exc.user_message
                    retryable = exc.retryable
                    error_details = exc.details
                elif isinstance(exc, ToolExecutionError):
                    error_code = exc.code
                    error_message = exc.message
                    retryable = exc.retryable
                    error_details = exc.details
                else:
                    error_code = "EXECUTION_FAILED"
                    error_message = "分析执行失败"
                    retryable = False
                    error_details = {}
                if active_step is not None:
                    active_step = session.get(RunStepModel, active_step.id)
                    active_step.status = StepStatus.FAILED.value
                    active_step.error_json = {
                        "code": error_code,
                        "message": error_message,
                        "details": error_details,
                        "retryable": retryable,
                    }
                    active_step.finished_at = utc_now()
                failure = {
                    "code": error_code,
                    "message": error_message,
                    "retryable": retryable,
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
            set_cancel_check = getattr(
                self.provider, "set_cancel_check", None
            )
            if callable(set_cancel_check):
                set_cancel_check(None)
            close = getattr(self.provider, "close", None)
            if callable(close):
                close()
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
        arguments=None,
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
                "arguments": arguments or {},
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
        tool_result=None,
    ):
        now = utc_now()
        artifact_ids = [item.id for item in artifacts]
        step.status = StepStatus.COMPLETED.value
        step.output_summary_json = {
            "schema_version": "1.0",
            "description": step.display_name,
            "artifact_ids": artifact_ids,
            "tool_result": tool_result.summary if tool_result else None,
            "warnings": tool_result.warnings if tool_result else [],
            "row_count": tool_result.row_count if tool_result else None,
            "truncated": tool_result.truncated if tool_result else False,
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
