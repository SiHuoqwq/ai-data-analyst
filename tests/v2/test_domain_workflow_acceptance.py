from pathlib import Path

from app.db import database
from app.db.models import FileModel, MessageModel
from app.v2.db.models import AnalysisRunModel, ArtifactModel, RunStepModel
from app.v2.schemas.intents import AnalysisIntent
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.provider import ProviderError
from app.v2.services.runs import AnalysisRunService


class IntentAcceptanceProvider:
    name = "mock-intent"
    model = "deterministic-intent"
    max_tool_rounds = 5

    def __init__(self, intent: AnalysisIntent):
        self.intent = intent
        self.intent_calls = 0
        self.plan_calls = 0

    def set_history(self, _history):
        return None

    def before_step(self):
        return None

    def generate_intent(self, _question, _file_record):
        self.intent_calls += 1
        return self.intent

    def build_plan(self, _question, _file_record):
        self.plan_calls += 1
        raise AssertionError("新主路径不得调用旧的完整计划生成")

    def build_conclusion(self, _question, _file_record, registry):
        self.last_conclusion_aliases = registry.create_alias_map(
            registry.items[:4]
        )
        raise ProviderError(
            "UNGROUNDED_ANSWER",
            "结构化结论未通过证据校验",
            retryable=False,
            details={
                "answer_warnings": [
                    "STRUCTURED_CONCLUSION_REJECTED",
                    "STRUCTURED_CONCLUSION_REPAIR_FAILED",
                ]
            },
        )


def _metric(semantic, source_field, aggregation):
    return {
        "semantic": semantic,
        "source_field": source_field,
        "aggregation": aggregation,
    }


def _prepare_dataset(v2_runtime):
    csv_path = Path(v2_runtime["database_path"]).with_name(
        "domain-courses.csv"
    )
    rows = [
        "course_category,difficulty,channel,device,completion,refunded,"
        "rating,enrolled_at,paid_amount"
    ]
    rows.extend(
        f"AI,advanced,video,Android,{completion},"
        f"{'true' if index == 0 else 'false'},4.2,"
        f"2025-{1 + index % 2:02d}-{3 + index:02d},{199 - index}"
        for index, completion in enumerate(
            [0.3, 0.4, 0.5, 0.4, 0.3, 0.5]
        )
    )
    rows.extend(
        f"Data,basic,web,Windows,{completion},false,"
        f"{'' if index == 0 else '4.8'},"
        f"2025-{1 + index % 2:02d}-{12 + index:02d},{299 - index}"
        for index, completion in enumerate(
            [0.8, 0.7, 0.9, 0.8, 0.7, 0.9]
        )
    )
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    columns_info = [
        {"name": "course_category", "dtype": "object"},
        {"name": "difficulty", "dtype": "object"},
        {"name": "channel", "dtype": "object"},
        {"name": "device", "dtype": "object"},
        {"name": "completion", "dtype": "float64"},
        {"name": "refunded", "dtype": "bool"},
        {"name": "rating", "dtype": "float64"},
        {"name": "enrolled_at", "dtype": "datetime64[ns]"},
        {"name": "paid_amount", "dtype": "float64"},
    ]
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = csv_path.name
    file_record.row_count = 12
    file_record.col_count = 9
    file_record.columns_info = columns_info
    session.commit()
    session.close()


def _group_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "group_comparison",
            "dimensions": [
                "course_category",
                "difficulty",
                "channel",
                "device",
            ],
            "metrics": [
                _metric("报名人数", None, "count"),
                _metric("平均完成率", "completion", "mean"),
                _metric("退款率", "refunded", "rate"),
                _metric("平均评分", "rating", "mean"),
            ],
            "include_underperforming": True,
        }
    )


def _monthly_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "monthly_trend",
            "dimensions": ["course_category"],
            "date_field": "enrolled_at",
            "metrics": [
                _metric("报名人数", None, "count"),
                _metric("实付金额", "paid_amount", "sum"),
                _metric("平均完成率", "completion", "mean"),
            ],
        }
    )


def test_two_domain_workflows_compile_execute_and_preserve_conversation(
    v2_runtime,
):
    _prepare_dataset(v2_runtime)
    run_service = AnalysisRunService()
    providers = [
        IntentAcceptanceProvider(_group_intent()),
        IntentAcceptanceProvider(_monthly_intent()),
    ]
    first = run_service.create_run(
        "conversation-1",
        "file-1",
        "比较课程组合表现",
        "domain-question-one",
    )
    AnalysisExecutor(providers[0]).execute(first.id)
    second = run_service.create_run(
        "conversation-1",
        "file-1",
        "分析课程月度趋势",
        "domain-question-two",
    )
    AnalysisExecutor(providers[1]).execute(second.id)

    session = database.SessionLocal()
    runs = [
        session.get(AnalysisRunModel, item.id)
        for item in (first, second)
    ]
    assert [item.status for item in runs] == ["completed", "completed"], [
        item.failure_json for item in runs
    ]
    assert all(provider.intent_calls == 1 for provider in providers)
    assert all(provider.plan_calls == 0 for provider in providers)
    assert all(item.answer_message_id for item in runs)
    messages = (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1")
        .order_by(MessageModel.created_at, MessageModel.id)
        .all()
    )
    assert [item.role for item in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    first_steps = (
        session.query(RunStepModel)
        .filter_by(run_id=first.id)
        .order_by(RunStepModel.sequence)
        .all()
    )
    assert [item.operation for item in first_steps[:4]] == [
        "inspect_dataset",
        "group_aggregate",
        "identify_underperforming",
        "chart_planning",
    ]
    second_steps = (
        session.query(RunStepModel)
        .filter_by(run_id=second.id)
        .order_by(RunStepModel.sequence)
        .all()
    )
    assert [item.operation for item in second_steps[:4]] == [
        "inspect_dataset",
        "monthly_trend",
        "calculate_trend_signals",
        "chart_planning",
    ]

    monthly_artifacts = (
        session.query(ArtifactModel).filter_by(run_id=second.id).all()
    )
    monthly_charts = [
        item
        for item in monthly_artifacts
        if item.artifact_type == "chart"
    ]
    assert len(monthly_charts) == 3
    monthly_table = next(
        item
        for item in monthly_artifacts
        if item.artifact_type == "table"
    )
    assert [
        item["key"] for item in monthly_table.payload_json["columns"]
    ] == [
        "period",
        "series",
        "enrollment_count",
        "paid_amount_sum",
        "completion_rate_mean",
    ]
    assert all(
        artifact.payload_json["image_url"]
        == f"/api/v2/artifacts/{artifact.id}/download"
        for artifact in monthly_charts
    )
    assert all(
        ":" not in artifact.payload_json["image_url"]
        for artifact in monthly_charts
    )
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
    session.close()


def test_invalid_intent_fails_before_tools_and_creates_no_assistant_message(
    v2_runtime,
):
    _prepare_dataset(v2_runtime)
    invalid_intent = AnalysisIntent.model_validate(
        {
            "analysis_type": "monthly_trend",
            "dimensions": ["course_category"],
            "date_field": "missing_date",
            "metrics": [
                _metric("报名人数", None, "count"),
                _metric("实付金额", "paid_amount", "sum"),
                _metric("平均完成率", "completion", "mean"),
            ],
        }
    )
    run = AnalysisRunService().create_run(
        "conversation-1",
        "file-1",
        "分析无法识别的日期字段",
        "invalid-domain-question",
    )

    AnalysisExecutor(
        IntentAcceptanceProvider(invalid_intent)
    ).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    assert failed.status == "failed"
    assert failed.failure_json["code"] == "FIELD_NOT_FOUND"
    assert failed.answer_message_id is None
    assert (
        session.query(RunStepModel).filter_by(run_id=run.id).count()
        == 0
    )
    assistant_messages = (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1", role="assistant")
        .count()
    )
    assert assistant_messages == 0
    session.close()
