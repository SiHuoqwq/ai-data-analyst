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
            dimensions=["lead_channel"],
            metric_ids=["deal_count", "deal_amount"],
        )


class CountingFallbackProvider(ValidIntentProvider):
    def __init__(self):
        super().__init__("model")
        self.history_calls = 0
        self.intent_calls = 0

    def set_history(self, _history):
        self.history_calls += 1

    def generate_intent(self, question, file_record):
        self.intent_calls += 1
        return super().generate_intent(question, file_record)


def _prepare_dataset(v2_runtime):
    csv_path = Path(v2_runtime["database_path"]).with_name(
        "controlled-intent-real-estate.csv"
    )
    header = (
        "项目,城市,区域,置业顾问,获客渠道,户型,客户等级,"
        "线索日期,到访日期,认购日期,签约日期,成交金额,回款金额"
    )
    rows = [
        "云顶壹号,上海,浦东,张伟,自然到访,三居,A,2026-01-05,2026-01-06,2026-01-10,2026-01-15,1000000,500000",
        "云顶壹号,上海,徐汇,李娜,自然到访,两居,B,2026-02-02,2026-02-03,2026-02-08,2026-02-12,1100000,550000",
        "滨江府,杭州,西湖,孙磊,渠道分销,三居,A,2026-01-06,2026-01-08,,,,",
        "滨江府,杭州,滨江,吴刚,渠道分销,三居,C,2026-02-03,2026-02-05,2026-02-10,2026-02-18,900000,450000",
        "云顶壹号,上海,浦东,卫兰,线上投放,两居,B,2026-01-10,2026-01-12,,,,",
        "滨江府,杭州,西湖,周芳,线上投放,两居,A,2026-03-02,2026-03-04,,,,",
    ]
    csv_path.write_text(
        "\n".join([header, *rows]) + "\n", encoding="utf-8"
    )
    columns = [
        ("项目", "object"),
        ("城市", "object"),
        ("区域", "object"),
        ("置业顾问", "object"),
        ("获客渠道", "object"),
        ("户型", "object"),
        ("客户等级", "object"),
        ("线索日期", "datetime64[ns]"),
        ("到访日期", "datetime64[ns]"),
        ("认购日期", "datetime64[ns]"),
        ("签约日期", "datetime64[ns]"),
        ("成交金额", "float64"),
        ("回款金额", "float64"),
    ]
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = csv_path.name
    file_record.row_count = len(rows)
    file_record.col_count = len(columns)
    file_record.columns_info = [
        {"name": name, "dtype": dtype} for name, dtype in columns
    ]
    session.commit()
    session.close()


def test_router_selects_only_high_confidence_fixed_workflows():
    router = ControlledIntentRouter()

    # 验收问题
    assert router.route("各渠道成交套数怎么样？").workflow == "group_comparison"
    assert router.route("哪个项目成交金额最高？").workflow == "group_comparison"
    assert (
        router.route("最近几个月成交金额趋势如何？").workflow
        == "monthly_trend"
    )
    assert (
        router.route("各置业顾问销售表现怎么样？").workflow
        == "group_comparison"
    )
    # 月度趋势
    assert router.route("按月份分析销售趋势").workflow == "monthly_trend"
    assert (
        router.route("最近几个月回款金额趋势如何？").workflow
        == "monthly_trend"
    )
    # 分组对比
    assert router.route("比较不同户型的成交表现").workflow == "group_comparison"
    assert (
        router.route("不同客户等级的成交套数和回款有何差异？").workflow
        == "group_comparison"
    )
    # 不支持
    assert router.route("请分析这份数据").workflow == "unsupported"
    assert (
        router.route("按月比较不同渠道的成交表现").workflow
        == "unsupported"
    )


def test_default_intent_returns_real_estate_contract():
    router = ControlledIntentRouter()

    group = router.default_intent(router.route("哪个项目成交金额最高？"))
    assert group.workflow == "group_comparison"
    assert group.dimensions == ["lead_channel"]
    assert group.metric_ids == ["deal_count", "deal_amount"]

    monthly = router.default_intent(
        router.route("最近几个月成交金额趋势如何？")
    )
    assert monthly.workflow == "monthly_trend"
    assert monthly.series_dimension == "lead_channel"
    assert monthly.metric_ids == ["deal_count", "deal_amount"]


def test_router_rejects_monthly_derived_rate_metrics():
    router = ControlledIntentRouter()

    deal = router.route("最近几个月成交转化率趋势如何？")
    assert deal.workflow == "unsupported"
    assert deal.derived_rate_metric == "deal_rate"

    visit = router.route("最近几个月到访率趋势如何？")
    assert visit.workflow == "unsupported"
    assert visit.derived_rate_metric == "visit_rate"

    subscribe = router.route("最近几个月认购转化率趋势如何？")
    assert subscribe.workflow == "unsupported"
    assert subscribe.derived_rate_metric == "subscription_rate"


def test_router_keeps_legal_monthly_metrics_supported():
    router = ControlledIntentRouter()

    assert (
        router.route("最近几个月成交金额趋势如何？").workflow
        == "monthly_trend"
    )
    assert (
        router.route("最近几个月成交套数趋势如何？").workflow
        == "monthly_trend"
    )
    assert router.route("最近几个月情况怎么样？").workflow == "monthly_trend"


def test_router_group_context_keeps_deal_rate_supported():
    router = ControlledIntentRouter()

    assert (
        router.route("各渠道的成交转化率怎么样？").workflow
        == "group_comparison"
    )


def test_router_produces_monthly_derived_rate_refusal_message():
    router = ControlledIntentRouter()

    message = router.monthly_derived_rate_refusal("deal_rate")
    assert "成交转化率" in message
    assert "成交套数" in message
    assert "成交金额" in message
    assert "回款金额" in message


def test_controlled_fallback_completes_both_fixed_workflows(v2_runtime):
    _prepare_dataset(v2_runtime)
    service = AnalysisRunService()
    first = service.create_run(
        "conversation-1",
        "file-1",
        "各获客渠道的成交套数和成交金额怎么样？",
        "controlled-group",
    )
    AnalysisExecutor(InvalidIntentProvider()).execute(first.id)
    second = service.create_run(
        "conversation-1",
        "file-1",
        "最近几个月成交金额趋势如何？",
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
    assert first_operations[:3] == [
        "inspect_dataset",
        "group_aggregate",
        "chart_planning",
    ]
    monthly_artifacts = (
        session.query(ArtifactModel).filter_by(run_id=second.id).all()
    )
    assert sum(
        artifact.artifact_type == "chart"
        for artifact in monthly_artifacts
    ) == 2
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
    runs = []
    for item in generated.recommendations:
        run = service.create_run(
            "conversation-1",
            "file-1",
            item["question"],
            f"fake-template-{item['id']}",
        )
        AnalysisExecutor(provider).execute(run.id)
        runs.append(run)

    session = database.SessionLocal()
    stored = [session.get(AnalysisRunModel, run.id) for run in runs]
    assert {item.status for item in stored} == {"completed"}, [
        item.failure_json for item in stored
    ]
    assert {
        item.context_snapshot_json["intent_mode"] for item in stored
    } == {"controlled_fallback"}
    operations = [
        step.operation
        for run in runs
        for step in session.query(RunStepModel)
        .filter_by(run_id=run.id)
        .order_by(RunStepModel.sequence)
        .all()
    ]
    assert "group_aggregate" in operations
    assert "monthly_trend" in operations
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


def test_fake_provider_refuses_monthly_derived_rate(v2_runtime):
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")

    with pytest.raises(ProviderError) as raised:
        FakeAnalysisProvider().generate_intent(
            "最近几个月成交转化率趋势如何？",
            file_record,
        )

    assert raised.value.code == "UNSUPPORTED_MONTHLY_METRIC"
    assert "成交转化率" in raised.value.user_message
    session.close()


def test_executor_refuses_monthly_derived_rate_with_user_visible_message(
    v2_runtime,
):
    _prepare_dataset(v2_runtime)
    run = AnalysisRunService().create_run(
        "conversation-1",
        "file-1",
        "最近几个月成交转化率趋势如何？",
        "derived-rate-refusal",
    )

    AnalysisExecutor(InvalidIntentProvider()).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    assert failed.status == "failed"
    assert failed.failure_json["code"] == "UNSUPPORTED_MONTHLY_METRIC"
    assert "成交转化率" in failed.failure_json["message"]
    assert "成交套数" in failed.failure_json["message"]
    assert failed.answer_message_id is None
    assert session.query(RunStepModel).filter_by(run_id=run.id).count() == 0
    session.close()


def test_executor_persists_model_and_repaired_model_intent_modes(v2_runtime):
    _prepare_dataset(v2_runtime)
    service = AnalysisRunService()
    runs = []
    for mode in ("model", "repaired_model"):
        run = service.create_run(
            "conversation-1",
            "file-1",
            "比较各获客渠道的成交表现",
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


def test_single_group_run_completes_with_table_and_without_chart(v2_runtime):
    _prepare_dataset(v2_runtime)
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    csv_path = Path(file_record.filepath)
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    unified = [lines[0]]
    for row in lines[1:]:
        parts = row.split(",")
        parts[4] = "自然到访"
        unified.append(",".join(parts))
    csv_path.write_text("\n".join(unified) + "\n", encoding="utf-8")
    session.close()

    run = AnalysisRunService().create_run(
        "conversation-1",
        "file-1",
        "比较各获客渠道的成交套数和成交金额怎么样？",
        "single-group-no-chart",
    )
    AnalysisExecutor(ValidIntentProvider("model")).execute(run.id)

    session = database.SessionLocal()
    stored = session.get(AnalysisRunModel, run.id)
    artifacts = session.query(ArtifactModel).filter_by(run_id=run.id).all()
    assert stored.status == "completed", stored.failure_json
    assert any(item.artifact_type == "table" for item in artifacts)
    assert not any(item.artifact_type == "chart" for item in artifacts)
    session.close()


def _prepare_dataset_without_consultant(v2_runtime):
    csv_path = Path(v2_runtime["database_path"]).with_name(
        "controlled-intent-no-consultant.csv"
    )
    header = (
        "项目,城市,区域,获客渠道,户型,客户等级,"
        "线索日期,到访日期,认购日期,签约日期,成交金额,回款金额"
    )
    rows = [
        "云顶壹号,上海,浦东,自然到访,三居,A,2026-01-05,2026-01-06,2026-01-10,2026-01-15,1000000,500000",
        "滨江府,杭州,西湖,渠道分销,三居,A,2026-01-06,2026-01-08,,,,",
    ]
    csv_path.write_text(
        "\n".join([header, *rows]) + "\n", encoding="utf-8"
    )
    columns = [
        ("项目", "object"),
        ("城市", "object"),
        ("区域", "object"),
        ("获客渠道", "object"),
        ("户型", "object"),
        ("客户等级", "object"),
        ("线索日期", "datetime64[ns]"),
        ("到访日期", "datetime64[ns]"),
        ("认购日期", "datetime64[ns]"),
        ("签约日期", "datetime64[ns]"),
        ("成交金额", "float64"),
        ("回款金额", "float64"),
    ]
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = csv_path.name
    file_record.row_count = len(rows)
    file_record.col_count = len(columns)
    file_record.columns_info = [
        {"name": name, "dtype": dtype} for name, dtype in columns
    ]
    session.commit()
    session.close()


def test_missing_sales_consultant_fields_refuse_before_provider_or_artifact_execution(
    v2_runtime,
):
    _prepare_dataset_without_consultant(v2_runtime)
    question = "请分析各置业顾问的成交套数和成交金额排名"
    run = AnalysisRunService().create_run(
        "conversation-1",
        "file-1",
        question,
        "missing-consultant-fields",
    )
    provider = CountingFallbackProvider()

    AnalysisExecutor(provider).execute(run.id)

    session = database.SessionLocal()
    failed = session.get(AnalysisRunModel, run.id)
    assert failed.status == "failed"
    assert failed.failure_json == {
        "code": "MISSING_REQUIRED_FIELDS",
        "message": (
            "当前数据中缺少「置业顾问」字段，"
            "因此暂时无法进行置业顾问维度分析。"
        ),
        "retryable": False,
        "failed_step_id": None,
    }
    assert provider.history_calls == 0
    assert provider.intent_calls == 0
    assert session.query(RunStepModel).filter_by(run_id=run.id).count() == 0
    assert session.query(ArtifactModel).filter_by(run_id=run.id).count() == 0
    assert (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1", role="assistant")
        .count()
        == 0
    )
    session.close()
