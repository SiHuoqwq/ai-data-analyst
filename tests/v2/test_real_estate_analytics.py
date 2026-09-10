import threading
import time

import pandas as pd
import pytest

from app.db import database
from app.db.models import FileModel
from app.v2.db.models import AnalysisRunModel, ArtifactModel, RunStepModel
from app.v2.domain.intent_router import ControlledIntentRouter
from app.v2.schemas.intents import GroupComparisonIntent
from app.v2.services.analytics import StructuredAnalysisTools
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.plan_compiler import PlanCompiler
from app.v2.services.provider import ProviderError


COLUMNS = [
    "项目",
    "城市",
    "区域",
    "置业顾问",
    "获客渠道",
    "户型",
    "客户等级",
    "线索日期",
    "到访日期",
    "认购日期",
    "签约日期",
    "成交金额",
    "回款金额",
]

COLUMN_DTYPES = {
    "项目": "object",
    "城市": "object",
    "区域": "object",
    "置业顾问": "object",
    "获客渠道": "object",
    "户型": "object",
    "客户等级": "object",
    "线索日期": "datetime64[ns]",
    "到访日期": "datetime64[ns]",
    "认购日期": "datetime64[ns]",
    "签约日期": "datetime64[ns]",
    "成交金额": "float64",
    "回款金额": "float64",
}

# 17 行线索，grain = 每行一个客户线索；覆盖 4 渠道 / 2 项目 / 3 个月 /
# 完整漏斗状态（成交、认购未签约、到访未认购、完全未到访）+ 空金额 + 零分母场景。
ROWS = [
    # 自然到访（6 线索，4 成交）
    ("云顶壹号", "上海", "浦东", "张伟", "自然到访", "三居", "A", "2026-01-05", "2026-01-06", "2026-01-10", "2026-01-15", 1000000.0, 500000.0),
    ("云顶壹号", "上海", "浦东", "李娜", "自然到访", "两居", "B", "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-18", 1200000.0, 600000.0),
    ("云顶壹号", "上海", "徐汇", "王强", "自然到访", "三居", "A", "2026-02-02", "2026-02-03", "2026-02-08", "2026-02-12", 1100000.0, 550000.0),
    ("云顶壹号", "上海", "浦东", "赵敏", "自然到访", "两居", "C", "2026-02-10", "2026-02-11", "2026-02-15", "2026-02-20", 1300000.0, 650000.0),
    ("云顶壹号", "上海", "徐汇", "刘洋", "自然到访", "三居", "B", "2026-03-01", "2026-03-02", "2026-03-05", None, None, None),
    ("云顶壹号", "上海", "浦东", "陈静", "自然到访", "两居", "A", "2026-03-05", None, None, None, None, None),
    # 渠道分销（6 线索，1 成交 —— 高线索低成交）
    ("滨江府", "杭州", "西湖", "孙磊", "渠道分销", "三居", "A", "2026-01-06", "2026-01-08", None, None, None, None),
    ("滨江府", "杭州", "西湖", "周芳", "渠道分销", "两居", "B", "2026-01-15", "2026-01-16", None, None, None, None),
    ("滨江府", "杭州", "滨江", "吴刚", "渠道分销", "三居", "C", "2026-02-03", "2026-02-05", "2026-02-10", "2026-02-18", 900000.0, 450000.0),
    ("滨江府", "杭州", "西湖", "郑爽", "渠道分销", "两居", "A", "2026-02-12", None, None, None, None, None),
    ("滨江府", "杭州", "滨江", "冯涛", "渠道分销", "三居", "B", "2026-03-02", "2026-03-04", None, None, None, None),
    ("滨江府", "杭州", "西湖", "褚明", "渠道分销", "两居", "C", "2026-03-10", None, None, None, None, None),
    # 线上投放（3 线索，1 成交）
    ("云顶壹号", "上海", "浦东", "卫兰", "线上投放", "两居", "B", "2026-01-10", "2026-01-12", None, None, None, None),
    ("云顶壹号", "上海", "徐汇", "蒋欣", "线上投放", "三居", "A", "2026-02-20", "2026-02-22", "2026-02-25", "2026-03-01", 800000.0, 400000.0),
    ("云顶壹号", "上海", "浦东", "沈腾", "线上投放", "两居", "C", "2026-03-08", None, None, None, None, None),
    # 电话营销（2 线索，0 到访 —— 零分母）
    ("滨江府", "杭州", "滨江", "韩雪", "电话营销", "两居", "B", "2026-01-20", None, None, None, None, None),
    ("滨江府", "杭州", "西湖", "杨帆", "电话营销", "三居", "A", "2026-03-15", None, None, None, None, None),
]


@pytest.fixture
def real_estate_file(tmp_path):
    source = tmp_path / "real-estate.csv"
    pd.DataFrame(ROWS, columns=COLUMNS).to_csv(
        source, index=False, encoding="utf-8"
    )
    return FileModel(
        id="dataset-1",
        filename="real-estate.csv",
        filepath=str(source),
        file_type="csv",
        row_count=len(ROWS),
        col_count=len(COLUMNS),
        columns_info=[
            {"name": name, "dtype": COLUMN_DTYPES[name]} for name in COLUMNS
        ],
        profile_report="",
    )


def _run_group(intent, file_record):
    plan = PlanCompiler().compile(intent, file_record)
    step = plan.step("group_aggregate")
    return StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        file_record,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )


def _channel_row(df, channel):
    rows = df[df["dimension_1"] == channel]
    assert len(rows) == 1
    return rows.iloc[0]


def test_basic_funnel_counts_and_amounts(real_estate_file):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["lead_count", "visit_count", "subscription_count", "deal_count"],
    )
    result = _run_group(intent, real_estate_file)
    df = result.dataframe

    organic = _channel_row(df, "自然到访")
    assert organic["lead_count"] == 6
    assert organic["visit_count"] == 5
    assert organic["subscription_count"] == 5
    assert organic["deal_count"] == 4

    tele = _channel_row(df, "电话营销")
    assert tele["lead_count"] == 2
    assert tele["visit_count"] == 0
    assert tele["subscription_count"] == 0
    assert tele["deal_count"] == 0


def test_amount_metrics_exclude_null_rows(real_estate_file):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["deal_amount", "payment_amount"],
    )
    result = _run_group(intent, real_estate_file)
    df = result.dataframe

    assert _channel_row(df, "自然到访")["deal_amount_sum"] == 4600000.0
    assert _channel_row(df, "自然到访")["payment_amount_sum"] == 2300000.0
    # 电话营销无成交，金额求和为空 → 0.0
    assert _channel_row(df, "电话营销")["deal_amount_sum"] == 0.0


def test_derived_rates_computed_per_group(real_estate_file):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["visit_rate", "subscription_rate", "deal_rate", "avg_deal_amount"],
    )
    result = _run_group(intent, real_estate_file)
    df = result.dataframe

    organic = _channel_row(df, "自然到访")
    assert organic["visit_rate"] == pytest.approx(5 / 6)
    assert organic["subscription_rate"] == pytest.approx(1.0)
    assert organic["deal_rate"] == pytest.approx(4 / 6)
    assert organic["avg_deal_amount"] == pytest.approx(1150000.0)

    distribution = _channel_row(df, "渠道分销")
    assert distribution["visit_rate"] == pytest.approx(4 / 6)
    assert distribution["subscription_rate"] == pytest.approx(0.25)
    assert distribution["deal_rate"] == pytest.approx(1 / 6)
    assert distribution["avg_deal_amount"] == pytest.approx(900000.0)

    online = _channel_row(df, "线上投放")
    assert online["deal_rate"] == pytest.approx(1 / 3)
    assert online["avg_deal_amount"] == pytest.approx(800000.0)


def test_zero_denominator_yields_none_not_zero(real_estate_file):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["visit_rate", "subscription_rate", "deal_rate", "avg_deal_amount"],
    )
    result = _run_group(intent, real_estate_file)
    df = result.dataframe

    tele = _channel_row(df, "电话营销")
    # 到访率 = 0/2 = 0（分母 > 0，非 None）
    assert tele["visit_rate"] == 0.0
    # 成交转化率 = 0/2 = 0
    assert tele["deal_rate"] == 0.0
    # 认购转化率 = 0/0 → None
    assert pd.isna(tele["subscription_rate"])
    # 平均成交金额 = 0/0 → None
    assert pd.isna(tele["avg_deal_amount"])


def test_underperforming_identifies_high_lead_low_deal_rate(real_estate_file):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["lead_count", "deal_rate"],
        detect_underperforming=True,
    )
    plan = PlanCompiler().compile(intent, real_estate_file)
    step = plan.step("underperforming")
    result = StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        real_estate_file,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )

    df = result.dataframe
    assert "lead_count" in df.columns
    assert "deal_rate" in df.columns
    # 渠道分销：6 线索 + 低成交转化率，应被识别
    matched = set(df["dimension_1"])
    assert "渠道分销" in matched
    assert "自然到访" not in matched


def test_group_artifact_contract_shape_is_stable(real_estate_file):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["lead_count", "deal_rate"],
    )
    result = _run_group(intent, real_estate_file)

    table = next(
        draft for draft in result.drafts if draft.artifact_type == "table"
    )
    payload = table.payload
    assert set(payload) == {"columns", "rows"}
    assert [c["key"] for c in payload["columns"]] == [
        "dimension_1",
        "lead_count",
        "deal_rate",
    ]
    assert [c["data_type"] for c in payload["columns"]] == [
        "string",
        "number",
        "number",
    ]
    contract = result.output_contract
    assert [m.id for m in contract.result_schema.metrics] == [
        "lead_count",
        "deal_rate",
    ]
    assert contract.result_schema.metrics[1].unit == "percentage"


class RealEstateIntentProvider:
    name = "mock-real-estate"
    model = "deterministic-real-estate"
    max_tool_rounds = 5

    def set_history(self, _history):
        return None

    def before_step(self):
        return None

    def generate_intent(self, _question, _file_record):
        return GroupComparisonIntent(
            workflow="group_comparison",
            dimensions=["lead_channel"],
            metric_ids=["lead_count", "deal_rate"],
            detect_underperforming=False,
        )

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


def test_executor_end_to_end_produces_real_estate_artifacts(
    v2_runtime, tmp_path
):
    from app.db.models import FileModel as FM

    csv_path = tmp_path / "executor-real-estate.csv"
    pd.DataFrame(ROWS, columns=COLUMNS).to_csv(
        csv_path, index=False, encoding="utf-8"
    )
    session = database.SessionLocal()
    try:
        record = session.get(FM, "file-1")
        record.filepath = str(csv_path)
        record.filename = csv_path.name
        record.row_count = len(ROWS)
        record.col_count = len(COLUMNS)
        record.columns_info = [
            {"name": name, "dtype": COLUMN_DTYPES[name]} for name in COLUMNS
        ]
        session.commit()
    finally:
        session.close()

    from app.v2.services.runs import AnalysisRunService

    run = AnalysisRunService().create_run(
        conversation_id="conversation-1",
        dataset_version_id="file-1",
        message="各获客渠道的线索数和成交转化率分别是多少？",
        idempotency_key="real-estate-e2e",
    )

    AnalysisExecutor(RealEstateIntentProvider()).execute(run.id)

    session = database.SessionLocal()
    try:
        completed = session.get(AnalysisRunModel, run.id)
        assert completed.status == "completed", completed.failure_json
        artifacts = session.query(ArtifactModel).filter_by(run_id=run.id).all()
        types = {item.artifact_type for item in artifacts}
        assert {"text", "metric", "table"} <= types
        steps = (
            session.query(RunStepModel)
            .filter_by(run_id=run.id)
            .order_by(RunStepModel.sequence)
            .all()
        )
        assert [item.operation for item in steps[:2]] == [
            "inspect_dataset",
            "group_aggregate",
        ]
    finally:
        session.close()
