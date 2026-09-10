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
        "domain-real-estate.csv"
    )
    header = (
        "项目,城市,区域,置业顾问,获客渠道,户型,客户等级,"
        "线索日期,到访日期,认购日期,签约日期,成交金额,回款金额"
    )
    rows = [
        # 自然到访（5 线索，4 成交）
        "云顶壹号,上海,浦东,张伟,自然到访,三居,A,2026-01-05,2026-01-06,2026-01-10,2026-01-15,1000000,500000",
        "云顶壹号,上海,浦东,李娜,自然到访,两居,B,2026-01-08,2026-01-09,2026-01-12,2026-01-18,1200000,600000",
        "云顶壹号,上海,徐汇,王强,自然到访,三居,A,2026-02-02,2026-02-03,2026-02-08,2026-02-12,1100000,550000",
        "云顶壹号,上海,浦东,赵敏,自然到访,两居,C,2026-02-10,2026-02-11,2026-02-15,2026-02-20,1300000,650000",
        "云顶壹号,上海,徐汇,刘洋,自然到访,三居,B,2026-03-01,2026-03-02,2026-03-05,,,",
        # 渠道分销（5 线索，1 成交 —— 高线索低成交）
        "滨江府,杭州,西湖,孙磊,渠道分销,三居,A,2026-01-06,2026-01-08,,,,",
        "滨江府,杭州,西湖,周芳,渠道分销,两居,B,2026-01-15,2026-01-16,,,,",
        "滨江府,杭州,滨江,吴刚,渠道分销,三居,C,2026-02-03,2026-02-05,2026-02-10,2026-02-18,900000,450000",
        "滨江府,杭州,西湖,郑爽,渠道分销,两居,A,2026-02-12,,,,,",
        "滨江府,杭州,滨江,冯涛,渠道分销,三居,B,2026-03-02,2026-03-04,,,,",
    ]
    csv_path.write_text(
        "\n".join([header, *rows]) + "\n", encoding="utf-8"
    )
    columns_info = [
        {"name": "项目", "dtype": "object"},
        {"name": "城市", "dtype": "object"},
        {"name": "区域", "dtype": "object"},
        {"name": "置业顾问", "dtype": "object"},
        {"name": "获客渠道", "dtype": "object"},
        {"name": "户型", "dtype": "object"},
        {"name": "客户等级", "dtype": "object"},
        {"name": "线索日期", "dtype": "datetime64[ns]"},
        {"name": "到访日期", "dtype": "datetime64[ns]"},
        {"name": "认购日期", "dtype": "datetime64[ns]"},
        {"name": "签约日期", "dtype": "datetime64[ns]"},
        {"name": "成交金额", "dtype": "float64"},
        {"name": "回款金额", "dtype": "float64"},
    ]
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = csv_path.name
    file_record.row_count = len(rows)
    file_record.col_count = len(columns_info)
    file_record.columns_info = columns_info
    session.commit()
    session.close()


def _group_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "group_comparison",
            "dimensions": ["获客渠道"],
            "metrics": [
                _metric("成交套数", "签约日期", "count"),
                _metric("成交金额", "成交金额", "sum"),
                _metric("回款金额", "回款金额", "sum"),
                _metric("平均成交金额", None, "ratio"),
            ],
            "include_underperforming": True,
        }
    )


def _monthly_intent():
    return AnalysisIntent.model_validate(
        {
            "analysis_type": "monthly_trend",
            "dimensions": ["获客渠道"],
            "date_field": "签约日期",
            "metrics": [
                _metric("成交套数", "签约日期", "count"),
                _metric("成交金额", "成交金额", "sum"),
                _metric("回款金额", "回款金额", "sum"),
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
    assert len(monthly_charts) == 2
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
        "deal_count",
        "deal_amount_sum",
        "payment_amount_sum",
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
            "dimensions": ["获客渠道"],
            "date_field": "missing_date",
            "metrics": [
                _metric("成交套数", "签约日期", "count"),
                _metric("成交金额", "成交金额", "sum"),
                _metric("回款金额", "回款金额", "sum"),
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
