from app.db import database
from app.db.models import MessageModel
from app.v2.db.models import (
    AnalysisRunModel,
    ArtifactModel,
    RunEventModel,
    RunStepModel,
    utc_now,
)
import threading

from app.v2.services.executor import AnalysisExecutor
from app.v2.schemas.conclusions import (
    ConclusionFinding,
    StructuredConclusion,
)
from app.v2.services.provider import (
    ProviderError,
    ProviderPlan,
    ProviderStep,
)
from app.v2.services.runs import AnalysisRunService


class ScriptedRealProvider:
    name = "deepseek"
    model = "mock-deepseek"

    def __init__(self):
        self.history = []
        self.answer_evidence = []

    def set_history(self, history):
        self.history = history

    def before_step(self):
        return None

    def build_plan(self, _question, _file_record):
        return ProviderPlan(
            goal="按类别汇总并绘图",
            steps=(
                ProviderStep(
                    "inspect",
                    "inspect_dataset",
                    "检查字段",
                    {},
                ),
                ProviderStep(
                    "aggregate",
                    "group_aggregate",
                    "按类别汇总",
                    {
                        "group_by": ["category"],
                        "metrics": [
                            {
                                "field": None,
                                "aggregation": "count",
                                "alias": "记录数",
                            },
                            {
                                "field": "sales",
                                "aggregation": "sum",
                                "alias": "销售额",
                            },
                        ],
                        "filters": [],
                        "sort": [{"field": "销售额", "direction": "desc"}],
                        "limit": 20,
                    },
                ),
                ProviderStep(
                    "chart",
                    "create_chart",
                    "生成类别柱状图",
                    {
                        "source_step_id": "aggregate",
                        "chart_type": "bar",
                        "x_field": "category",
                        "y_fields": ["销售额"],
                        "color_field": None,
                        "title": "类别销售额",
                        "limit": 20,
                    },
                ),
            ),
        )

    def build_answer(self, _question, _file_record, evidence):
        self.answer_evidence = evidence
        return "A 类与 B 类销售额来自本次分组结果。"


def create_run(message: str, key: str):
    return AnalysisRunService().create_run(
        conversation_id="conversation-1",
        dataset_version_id="file-1",
        message=message,
        idempotency_key=key,
    )


def test_executor_runs_structured_plan_and_passes_artifact_evidence(v2_runtime):
    session = database.SessionLocal()
    session.add(
        MessageModel(
            id="previous-answer",
            conv_id="conversation-1",
            role="assistant",
            content="上一轮只看了总体数据。",
            tool_calls=None,
            chart_ids=[],
            created_at=utc_now(),
        )
    )
    session.commit()
    session.close()

    provider = ScriptedRealProvider()
    run = create_run("继续按类别分析", "structured-success")

    AnalysisExecutor(provider).execute(run.id)

    session = database.SessionLocal()
    completed = session.get(AnalysisRunModel, run.id)
    steps = (
        session.query(RunStepModel)
        .filter_by(run_id=run.id)
        .order_by(RunStepModel.sequence)
        .all()
    )
    artifacts = session.query(ArtifactModel).filter_by(run_id=run.id).all()
    answer = session.get(MessageModel, completed.answer_message_id)

    assert completed.status == "completed", completed.failure_json
    final_text = next(
        item
        for item in artifacts
        if item.artifact_type == "text"
        and item.title == "分析结论"
    )
    assert final_text.payload_json["content"] == answer.content
    assert answer.content == "A 类与 B 类销售额来自本次分组结果。"
    assert {item.artifact_type for item in artifacts} == {
        "text",
        "metric",
        "table",
        "chart",
    }
    aggregate_step = next(item for item in steps if item.operation == "group_aggregate")
    assert aggregate_step.input_json["arguments"]["group_by"] == ["category"]
    assert aggregate_step.output_summary_json["tool_result"]["scanned_rows"] == 3
    assert provider.history == [
        {"role": "assistant", "content": "上一轮只看了总体数据。"}
    ]
    assert {item["artifact_type"] for item in provider.answer_evidence} == {
        "text",
        "metric",
        "table",
        "chart",
    }
    assert all(item["artifact_id"] for item in provider.answer_evidence)
    session.close()


def test_executor_persists_structured_tool_error_without_success_message(v2_runtime):
    class InvalidFieldProvider(ScriptedRealProvider):
        def build_plan(self, _question, _file_record):
            return ProviderPlan(
                goal="使用不存在字段",
                steps=(
                    ProviderStep(
                        "invalid",
                        "group_aggregate",
                        "错误字段测试",
                        {
                            "group_by": ["missing"],
                            "metrics": [
                                {
                                    "field": None,
                                    "aggregation": "count",
                                    "alias": "记录数",
                                }
                            ],
                            "filters": [],
                            "sort": [],
                            "limit": 20,
                        },
                    ),
                ),
            )

    run = create_run("测试错误字段", "structured-failure")
    AnalysisExecutor(InvalidFieldProvider()).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    messages = (
        session.query(MessageModel)
        .filter_by(conv_id=run.conversation_id)
        .order_by(MessageModel.created_at)
        .all()
    )
    step = session.query(RunStepModel).filter_by(run_id=run.id).one()

    assert failed.status == "failed"
    assert failed.failure_json["code"] == "SCHEMA_FIELD_NOT_FOUND"
    assert failed.answer_message_id is None
    assert [item.role for item in messages] == ["user"]
    assert step.error_json["code"] == "SCHEMA_FIELD_NOT_FOUND"
    assert "available_fields" not in str(failed.failure_json)
    session.close()


def test_executor_persists_provider_error_code(v2_runtime):
    class UnavailableProvider(ScriptedRealProvider):
        def build_plan(self, _question, _file_record):
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                "分析服务连接超时，请稍后重试",
                retryable=True,
            )

    run = create_run("测试超时", "provider-timeout")
    AnalysisExecutor(UnavailableProvider()).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    assert failed.status == "failed"
    assert failed.failure_json == {
        "code": "PROVIDER_TIMEOUT",
        "message": "分析服务连接超时，请稍后重试",
        "retryable": True,
        "failed_step_id": None,
    }
    session.close()


def test_executor_wires_cooperative_cancellation_into_provider(v2_runtime):
    run = create_run("测试计划修复前取消", "provider-plan-cancel")

    class CancellingProvider(ScriptedRealProvider):
        def set_cancel_check(self, callback):
            self.cancel_check = callback

        def build_plan(self, _question, _file_record):
            AnalysisRunService().request_cancel(run.id, "user_requested")
            assert self.cancel_check() is True
            raise ProviderError(
                "RUN_CANCELLED",
                "分析任务已取消",
                retryable=False,
            )

    AnalysisExecutor(CancellingProvider()).execute(run.id)

    session = database.SessionLocal()
    cancelled = session.get(AnalysisRunModel, run.id)
    assert cancelled.status == "cancelled"
    assert cancelled.failure_json is None
    assert (
        session.query(MessageModel)
        .filter_by(conv_id=run.conversation_id, role="assistant")
        .count()
        == 0
    )
    session.close()


def test_executor_persists_sanitized_provider_error_details(v2_runtime):
    class UnsupportedAnswerProvider(ScriptedRealProvider):
        def build_answer(self, _question, _file_record, _evidence):
            raise ProviderError(
                "UNGROUNDED_ANSWER",
                "分析结论包含无法验证的数字",
                retryable=False,
                details={
                    "unsupported_numbers": [
                        {
                            "token": "88",
                            "semantic_category": "rate",
                        }
                    ]
                },
            )

    run = create_run("测试数字证据错误", "provider-details")
    AnalysisExecutor(UnsupportedAnswerProvider()).execute(run.id)

    session = database.SessionLocal()
    failed_step = (
        session.query(RunStepModel)
        .filter_by(run_id=run.id, operation="generate_answer")
        .one()
    )
    assert failed_step.error_json["details"] == {
        "unsupported_numbers": [
            {
                "token": "88",
                "semantic_category": "rate",
            }
        ]
    }
    session.close()


def test_executor_completes_with_deterministic_answer_after_conclusion_repair_fails(
    v2_runtime,
):
    class RejectedConclusionProvider(ScriptedRealProvider):
        def build_conclusion(self, _question, _file_record, registry):
            self.last_conclusion_aliases = registry.create_alias_map(
                registry.items[:4]
            )
            raise ProviderError(
                "UNGROUNDED_ANSWER",
                "分析服务返回的结论无法由本次结构化证据验证",
                retryable=False,
                details={
                    "conclusion_diagnostics": [
                        {
                            "phase": "initial",
                            "error_types": ["INVALID_JSON"],
                            "field_paths": [],
                            "error_count": 1,
                            "unknown_reference_count": 0,
                            "narrative_number_token_count": 0,
                            "response_length": 8,
                            "response_sha256": "a" * 64,
                        },
                        {
                            "phase": "repair",
                            "error_types": [
                                "INVALID_JSON",
                                "RESPONSE_REPAIR_FAILED",
                            ],
                            "field_paths": [],
                            "error_count": 1,
                            "unknown_reference_count": 0,
                            "narrative_number_token_count": 0,
                            "response_length": 8,
                            "response_sha256": "b" * 64,
                        },
                    ],
                    "answer_warnings": [
                        "STRUCTURED_CONCLUSION_REJECTED",
                        "STRUCTURED_CONCLUSION_REPAIR_FAILED",
                    ],
                },
            )

    run = create_run("请按类别汇总销售额", "fallback-success")
    AnalysisExecutor(RejectedConclusionProvider()).execute(run.id)

    session = database.SessionLocal()
    completed = session.get(AnalysisRunModel, run.id)
    answer_step = (
        session.query(RunStepModel)
        .filter_by(run_id=run.id, operation="generate_answer")
        .one()
    )
    final_text = (
        session.query(ArtifactModel)
        .filter_by(
            run_id=run.id,
            artifact_type="text",
            title="分析结论",
        )
        .one()
    )
    answer = session.get(MessageModel, completed.answer_message_id)
    event_types = [
        item[0]
        for item in session.query(RunEventModel.event_type)
        .filter_by(run_id=run.id)
        .all()
    ]

    assert completed.status == "completed", completed.failure_json
    assert final_text.payload_json["answer_mode"] == "deterministic_fallback"
    assert final_text.payload_json["answer_warnings"] == [
        "STRUCTURED_CONCLUSION_REJECTED",
        "STRUCTURED_CONCLUSION_REPAIR_FAILED",
    ]
    assert final_text.payload_json["content"] == answer.content
    assert "## 分析概览" in answer.content
    assert "## 关键结果" in answer.content
    assert "## 运营建议" in answer.content
    assert "## 数据限制" in answer.content
    assert "¥250.00" in answer.content
    assert answer_step.output_summary_json["answer_mode"] == (
        "deterministic_fallback"
    )
    assert answer_step.output_summary_json["conclusion_diagnostics"][0][
        "error_types"
    ] == ["INVALID_JSON"]
    assert "answer.completed" in event_types
    assert "run.completed" in event_types
    assert "run.failed" not in event_types
    session.close()


def test_executor_does_not_fallback_after_cancellation_during_conclusion(
    v2_runtime,
):
    run = create_run("取消最终结论", "fallback-cancel")

    class CancellingConclusionProvider(ScriptedRealProvider):
        def build_conclusion(self, _question, _file_record, registry):
            self.last_conclusion_aliases = registry.create_alias_map(
                registry.items[:2]
            )
            AnalysisRunService().request_cancel(run.id, "user_requested")
            raise ProviderError(
                "UNGROUNDED_ANSWER",
                "分析服务返回的结论无法验证",
                retryable=False,
            )

    AnalysisExecutor(CancellingConclusionProvider()).execute(run.id)

    session = database.SessionLocal()
    cancelled = session.get(AnalysisRunModel, run.id)
    assert cancelled.status == "cancelled"
    assert cancelled.answer_message_id is None
    assert (
        session.query(ArtifactModel)
        .filter_by(run_id=run.id, title="分析结论")
        .count()
        == 0
    )
    session.close()


def test_executor_persists_model_and_repaired_model_answer_modes(v2_runtime):
    class ValidConclusionProvider(ScriptedRealProvider):
        def __init__(self, mode):
            super().__init__()
            self.last_conclusion_mode = mode
            self.last_conclusion_diagnostics = (
                [{"phase": "initial", "error_types": ["INVALID_JSON"]}]
                if mode == "repaired_model"
                else []
            )

        def build_conclusion(self, _question, _file_record, registry):
            aliases = registry.create_alias_map(registry.items[:2])
            self.last_conclusion_aliases = aliases
            return StructuredConclusion(
                headline="可信结论",
                overview="结果已由结构化证据验证。",
                findings=[
                    ConclusionFinding(
                        title="关键结果",
                        statement="分组结果可以支持后续判断。",
                        evidence_refs=[
                            entry.alias for entry in aliases.entries
                        ],
                    )
                ],
                recommendations=[],
                limitations=[],
            )

    session = database.SessionLocal()
    modes = []
    for index, expected_mode in enumerate(("model", "repaired_model")):
        run = create_run(
            f"验证 {expected_mode}",
            f"answer-mode-{index}",
        )
        AnalysisExecutor(ValidConclusionProvider(expected_mode)).execute(
            run.id
        )
        artifact = (
            session.query(ArtifactModel)
            .filter_by(
                run_id=run.id,
                artifact_type="text",
                title="分析结论",
            )
            .one()
        )
        modes.append(artifact.payload_json["answer_mode"])
        if expected_mode == "repaired_model":
            assert artifact.payload_json["answer_warnings"] == [
                "STRUCTURED_CONCLUSION_REJECTED"
            ]

    assert modes == ["model", "repaired_model"]
    session.close()


def test_executor_allows_one_bounded_tool_argument_repair(v2_runtime):
    class RepairingProvider(ScriptedRealProvider):
        def __init__(self):
            super().__init__()
            self.repair_calls = 0

        def build_plan(self, _question, _file_record):
            return ProviderPlan(
                goal="修正字段后汇总",
                steps=(
                    ProviderStep("inspect", "inspect_dataset", "检查字段", {}),
                    ProviderStep(
                        "aggregate",
                        "group_aggregate",
                        "按类别汇总",
                        {
                            "group_by": ["missing"],
                            "metrics": [
                                {
                                    "field": None,
                                    "aggregation": "count",
                                    "alias": "记录数",
                                }
                            ],
                            "filters": [],
                            "sort": [],
                            "limit": 20,
                        },
                    ),
                    ProviderStep(
                        "chart",
                        "create_chart",
                        "生成图表",
                        {
                            "source_step_id": "aggregate",
                            "chart_type": "bar",
                            "x_field": "category",
                            "y_fields": ["记录数"],
                            "color_field": None,
                            "title": "类别记录数",
                            "limit": 20,
                        },
                    ),
                ),
            )

        def repair_step(
            self,
            _question,
            _file_record,
            failed_step,
            error,
            _evidence,
        ):
            self.repair_calls += 1
            assert failed_step["operation"] == "group_aggregate"
            assert error["code"] == "SCHEMA_FIELD_NOT_FOUND"
            return ProviderStep(
                "aggregate",
                "group_aggregate",
                "按可用类别字段汇总",
                {
                    "group_by": ["category"],
                    "metrics": [
                        {
                            "field": None,
                            "aggregation": "count",
                            "alias": "记录数",
                        }
                    ],
                    "filters": [],
                    "sort": [],
                    "limit": 20,
                },
            )

    provider = RepairingProvider()
    provider.max_tool_rounds = 4
    run = create_run("请自动修正字段", "repair-success")

    AnalysisExecutor(provider).execute(run.id)

    session = database.SessionLocal()
    completed = session.get(AnalysisRunModel, run.id)
    aggregate = (
        session.query(RunStepModel)
        .filter_by(run_id=run.id, operation="group_aggregate")
        .one()
    )
    assert completed.status == "completed"
    assert provider.repair_calls == 1
    assert aggregate.attempt_count == 2
    assert aggregate.max_attempts == 2
    assert aggregate.input_json["arguments"]["group_by"] == ["category"]
    session.close()


def test_executor_honors_cancel_requested_during_final_answer(v2_runtime):
    entered_answer = threading.Event()
    release_answer = threading.Event()

    class BlockingAnswerProvider(ScriptedRealProvider):
        def build_answer(self, _question, _file_record, evidence):
            self.answer_evidence = evidence
            entered_answer.set()
            assert release_answer.wait(timeout=3)
            return "这个答案不应在取消后保存。"

    provider = BlockingAnswerProvider()
    run = create_run("在最终回答时取消", "cancel-during-answer")
    worker = threading.Thread(
        target=AnalysisExecutor(provider).execute, args=(run.id,)
    )
    worker.start()
    assert entered_answer.wait(timeout=5)

    requested = AnalysisRunService().request_cancel(run.id, "user_requested")
    assert requested.status == "running"
    release_answer.set()
    worker.join(timeout=5)
    assert not worker.is_alive()

    session = database.SessionLocal()
    cancelled = session.get(AnalysisRunModel, run.id)
    assert cancelled.status == "cancelled"
    assert cancelled.answer_message_id is None
    assert (
        session.query(MessageModel)
        .filter_by(conv_id=run.conversation_id, role="assistant")
        .count()
        == 0
    )
    session.close()


def test_executor_validates_artifacts_required_by_plan_not_global_four_types(
    v2_runtime,
):
    class InspectOnlyProvider(ScriptedRealProvider):
        def build_plan(self, _question, _file_record):
            return ProviderPlan(
                goal="只检查字段",
                steps=(
                    ProviderStep(
                        "inspect", "inspect_dataset", "检查字段", {}
                    ),
                ),
            )

        def build_answer(self, _question, _file_record, evidence):
            self.answer_evidence = evidence
            return "字段检查完成。"

    provider = InspectOnlyProvider()
    run = create_run("只检查字段", "inspect-only")
    AnalysisExecutor(provider).execute(run.id)

    session = database.SessionLocal()
    completed = session.get(AnalysisRunModel, run.id)
    artifacts = session.query(ArtifactModel).filter_by(run_id=run.id).all()
    assert completed.status == "completed"
    assert {item.artifact_type for item in artifacts} == {"text", "metric"}
    session.close()
