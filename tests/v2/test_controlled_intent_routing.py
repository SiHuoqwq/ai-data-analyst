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
from app.v2.domain.intent_router import ControlledIntentRouter
from app.v2.schemas.intents import GroupComparisonIntent
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.provider import FakeAnalysisProvider, ProviderError
from app.v2.services.recommendations import DatasetRecommendationService
from app.v2.services.runs import AnalysisRunService


class InvalidIntentProvider:
    name = "mock-invalid-intent"
    model = "invalid-intent"
    max_tool_rounds = 5

    def set_history(self, _history):
        return None

    def before_step(self):
        return None

    def generate_intent(self, _question, _file_record):
        raise ProviderError(
            "INTENT_REPAIR_FAILED",
            "结构化意图修复失败",
            retryable=False,
        )

    def build_plan(self, _question, _file_record):
        raise AssertionError("controlled fallback must compile a workflow")

    def build_conclusion(self, _question, _file_record, registry):
        self.last_conclusion_aliases = registry.create_alias_map(
            registry.items[:4]
        )
        raise ProviderError(
            "UNGROUNDED_ANSWER",
            "使用确定性回答降级",
            retryable=False,
            details={
                "answer_warnings": [
                    "STRUCTURED_CONCLUSION_REJECTED",
                    "STRUCTURED_CONCLUSION_REPAIR_FAILED",
                ]
            },
        )


class ValidIntentProvider(InvalidIntentProvider):
    def __init__(self, intent_mode):
        self.last_intent_mode = intent_mode

    def generate_intent(self, _question, _file_record):
        return GroupComparisonIntent(
            workflow="group_comparison",
            dimensions=["course_category"],
            metric_ids=["enrollment_count", "completion_rate"],
        )


def _prepare_dataset(v2_runtime):
    csv_path = Path(v2_runtime["database_path"]).with_name(
        "controlled-intent-courses.csv"
    )
    rows = [
        "课程类别,课程难度,购买渠道,主要学习设备,课程完成率,是否退款,"
        "课程评分,报名日期,实付金额"
    ]
    rows.extend(
        f"AI应用,高级,短视频平台,Android,{completion},"
        f"{'true' if index == 0 else 'false'},4.2,"
        f"2025-{1 + index % 2:02d}-{3 + index:02d},{199 - index}"
        for index, completion in enumerate(
            [0.3, 0.4, 0.5, 0.4, 0.3, 0.5]
        )
    )
    rows.extend(
        f"数据分析,初级,官网,Windows,{completion},false,"
        f"{'' if index == 0 else '4.8'},"
        f"2025-{1 + index % 2:02d}-{12 + index:02d},{299 - index}"
        for index, completion in enumerate(
            [0.8, 0.7, 0.9, 0.8, 0.7, 0.9]
        )
    )
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    columns = [
        ("课程类别", "object"),
        ("课程难度", "object"),
        ("购买渠道", "object"),
        ("主要学习设备", "object"),
        ("课程完成率", "float64"),
        ("是否退款", "bool"),
        ("课程评分", "float64"),
        ("报名日期", "datetime64[ns]"),
        ("实付金额", "float64"),
    ]
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = csv_path.name
    file_record.row_count = 12
    file_record.col_count = len(columns)
    file_record.columns_info = [
        {"name": name, "dtype": dtype} for name, dtype in columns
    ]
    session.commit()
    session.close()


def test_router_selects_only_high_confidence_fixed_workflows():
    router = ControlledIntentRouter()

    assert router.route("按月份观察课程报名趋势").workflow == "monthly_trend"
    assert router.route("分析各课程类别随时间的收入变化").workflow == "monthly_trend"
    assert router.route("比较不同设备的退款表现").workflow == "group_comparison"
    assert router.route("找出高报名低完成的课程组合").workflow == "group_comparison"
    assert (
        router.route("不同课程类别的关键指标表现有何差异？").workflow
        == "group_comparison"
    )
    assert (
        router.route("不同field-1-edb2cd3b的关键指标表现有何差异？").workflow
        == "group_comparison"
    )
    assert router.route("请分析这份数据").workflow == "unsupported"
    assert (
        router.route("按月比较不同渠道的完成率趋势").workflow
        == "unsupported"
    )


def test_controlled_fallback_completes_both_fixed_workflows(v2_runtime):
    _prepare_dataset(v2_runtime)
    service = AnalysisRunService()
    first = service.create_run(
        "conversation-1",
        "file-1",
        "比较不同课程类别、难度、渠道和设备的完成率与退款率，找出低表现组合",
        "controlled-group",
    )
    AnalysisExecutor(InvalidIntentProvider()).execute(first.id)
    second = service.create_run(
        "conversation-1",
        "file-1",
        "按月份分析各课程类别的报名人数、实付金额和完成率趋势",
        "controlled-monthly",
    )
    AnalysisExecutor(InvalidIntentProvider()).execute(second.id)

    session = database.SessionLocal()
    runs = [
        session.get(AnalysisRunModel, run.id)
        for run in (first, second)
    ]
    assert [run.status for run in runs] == ["completed", "completed"], [
        run.failure_json for run in runs
    ]
    assert [
        run.context_snapshot_json["intent_mode"] for run in runs
    ] == ["controlled_fallback", "controlled_fallback"]
    assert [
        message.role
        for message in session.query(MessageModel)
        .filter_by(conv_id="conversation-1")
        .order_by(MessageModel.created_at, MessageModel.id)
        .all()
    ] == ["user", "assistant", "user", "assistant"]

    first_operations = [
        step.operation
        for step in session.query(RunStepModel)
        .filter_by(run_id=first.id)
        .order_by(RunStepModel.sequence)
        .all()
    ]
    assert first_operations[:4] == [
        "inspect_dataset",
        "group_aggregate",
        "identify_underperforming",
        "chart_planning",
    ]
    monthly_artifacts = (
        session.query(ArtifactModel).filter_by(run_id=second.id).all()
    )
    assert sum(
        artifact.artifact_type == "chart"
        for artifact in monthly_artifacts
    ) == 3
    monthly_table = next(
        artifact
        for artifact in monthly_artifacts
        if artifact.artifact_type == "table"
    )
    assert monthly_table.payload_json["columns"][0]["key"] == "period"
    assert all(
        artifact.payload_json["answer_mode"] == "deterministic_fallback"
        for artifact in session.query(ArtifactModel)
        .filter(
            ArtifactModel.run_id.in_([first.id, second.id]),
            ArtifactModel.artifact_type == "text",
            ArtifactModel.title == "分析结论",
        )
        .all()
    )
    intent_events = (
        session.query(RunEventModel)
        .filter(
            RunEventModel.run_id.in_([first.id, second.id]),
            RunEventModel.event_type == "run.status",
        )
        .all()
    )
    assert {
        event.payload_json.get("intent_mode")
        for event in intent_events
        if event.payload_json.get("intent_mode")
    } == {"controlled_fallback"}
    session.close()


def test_fake_provider_executes_template_recommendations_as_compiled_workflows(
    v2_runtime,
):
    _prepare_dataset(v2_runtime)
    provider = FakeAnalysisProvider()
    generated = DatasetRecommendationService().get_or_generate(
        "file-1",
        provider,
    )

    assert generated.source == "template"
    assert {item["intent_type"] for item in generated.recommendations} == {
        "group_comparison",
        "monthly_trend",
    }

    service = AnalysisRunService()
    runs = {}
    for item in generated.recommendations:
        run = service.create_run(
            "conversation-1",
            "file-1",
            item["question"],
            f"fake-template-{item['intent_type']}",
        )
        AnalysisExecutor(provider).execute(run.id)
        runs[item["intent_type"]] = run

    session = database.SessionLocal()
    stored = {
        intent_type: session.get(AnalysisRunModel, run.id)
        for intent_type, run in runs.items()
    }
    assert {item.status for item in stored.values()} == {"completed"}
    assert {
        item.context_snapshot_json["intent_mode"]
        for item in stored.values()
    } == {"controlled_fallback"}
    operations = {
        intent_type: [
            step.operation
            for step in session.query(RunStepModel)
            .filter_by(run_id=run.id)
            .order_by(RunStepModel.sequence)
            .all()
        ]
        for intent_type, run in runs.items()
    }
    assert "group_aggregate" in operations["group_comparison"]
    assert "monthly_trend" in operations["monthly_trend"]
    session.close()


def test_fake_provider_executes_each_template_for_minimal_dataset_fields(
    v2_runtime,
):
    csv_path = Path(v2_runtime["database_path"]).with_name(
        "minimal-template-fields.csv"
    )
    csv_path.write_text(
        "segment,observed_at,score\n"
        "A,2026-01-05,0.82\n"
        "B,2026-02-12,0.74\n",
        encoding="utf-8",
    )
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = csv_path.name
    file_record.row_count = 2
    file_record.col_count = 3
    file_record.columns_info = [
        {"name": "segment", "dtype": "object"},
        {"name": "observed_at", "dtype": "datetime64[ns]"},
        {"name": "score", "dtype": "float64"},
    ]
    session.commit()
    session.close()

    provider = FakeAnalysisProvider()
    generated = DatasetRecommendationService().get_or_generate(
        "file-1",
        provider,
    )
    assert [
        item["intent_type"] for item in generated.recommendations
    ] == ["group_comparison", "monthly_trend"]

    service = AnalysisRunService()
    run_ids = {}
    for item in generated.recommendations:
        run = service.create_run(
            "conversation-1",
            "file-1",
            item["question"],
            f"minimal-template-{item['intent_type']}",
        )
        AnalysisExecutor(provider).execute(run.id)
        run_ids[item["intent_type"]] = run.id

    session = database.SessionLocal()
    stored = {
        intent_type: session.get(AnalysisRunModel, run_id)
        for intent_type, run_id in run_ids.items()
    }
    assert {run.status for run in stored.values()} == {"completed"}
    assert {
        run.context_snapshot_json["intent_mode"] for run in stored.values()
    } == {"controlled_fallback"}
    operations = {
        intent_type: [
            step.operation
            for step in session.query(RunStepModel)
            .filter_by(run_id=run_id)
            .order_by(RunStepModel.sequence)
            .all()
        ]
        for intent_type, run_id in run_ids.items()
    }
    assert "group_aggregate" in operations["group_comparison"]
    assert "monthly_trend" in operations["monthly_trend"]
    session.close()


def test_fake_provider_marks_unsupported_questions_for_safe_plan_fallback(
    v2_runtime,
):
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")

    with pytest.raises(ProviderError) as raised:
        FakeAnalysisProvider().generate_intent(
            "Please inspect this dataset.",
            file_record,
        )

    assert raised.value.code == "FAKE_SAFE_PLAN_FALLBACK"
    session.close()


def test_executor_persists_model_and_repaired_model_intent_modes(v2_runtime):
    _prepare_dataset(v2_runtime)
    service = AnalysisRunService()
    runs = []
    for mode in ("model", "repaired_model"):
        run = service.create_run(
            "conversation-1",
            "file-1",
            "比较不同课程类别的完成率",
            f"intent-mode-{mode}",
        )
        AnalysisExecutor(ValidIntentProvider(mode)).execute(run.id)
        runs.append(run)

    session = database.SessionLocal()
    stored = [
        session.get(AnalysisRunModel, run.id) for run in runs
    ]
    assert [run.status for run in stored] == ["completed", "completed"]
    assert [
        run.context_snapshot_json["intent_mode"] for run in stored
    ] == ["model", "repaired_model"]
    session.close()


def test_unsupported_fallback_executes_no_tools_or_assistant_message(
    v2_runtime,
):
    _prepare_dataset(v2_runtime)
    run = AnalysisRunService().create_run(
        "conversation-1",
        "file-1",
        "请分析一下这份数据",
        "controlled-unsupported",
    )

    AnalysisExecutor(InvalidIntentProvider()).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    assert failed.status == "failed"
    assert failed.failure_json["code"] == "UNSUPPORTED_ANALYSIS_INTENT"
    assert failed.answer_message_id is None
    assert (
        session.query(RunStepModel).filter_by(run_id=run.id).count()
        == 0
    )
    assert (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1", role="assistant")
        .count()
        == 0
    )
    session.close()
