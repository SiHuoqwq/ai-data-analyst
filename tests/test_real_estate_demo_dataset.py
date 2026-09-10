"""房地产销售经营 Demo 数据集的可重复性、schema、业务故事与可用性测试。

这些测试面向 `demo/real_estate_sales_demo.csv`，它由仓库内
`demo/generate_real_estate_sales_demo.py` 用固定 seed 确定性生成。

业务故事测试只断言相对关系（谁最高、谁最低、谁明显高于平均），
不写死单个随机数值，避免未来微调生成器时产生脆弱测试。
"""

from pathlib import Path

import pandas as pd
import pytest

from app.db.models import FileModel
from app.v2.domain.intent_router import ControlledIntentRouter
from app.v2.schemas.intents import GroupComparisonIntent, MonthlyTrendIntent
from app.v2.services.analytics import StructuredAnalysisTools
from app.v2.services.plan_compiler import PlanCompiler
from demo.generate_real_estate_sales_demo import (
    CHANNELS,
    CONSULTANTS,
    CUSTOMER_LEVELS,
    DEMO_COLUMNS,
    PROJECTS,
    PROPERTY_TYPES,
    RANDOM_SEED,
    generate_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_DATASET = PROJECT_ROOT / "demo" / "real_estate_sales_demo.csv"

EXPECTED_COLUMNS = [
    "客户编号",
    "线索日期",
    "项目",
    "城市",
    "区域",
    "置业顾问",
    "获客渠道",
    "客户等级",
    "到访日期",
    "认购日期",
    "签约日期",
    "户型",
    "成交金额",
    "回款金额",
]

DATE_COLUMNS = ["线索日期", "到访日期", "认购日期", "签约日期"]
CATEGORICAL_COLUMNS = [
    "项目",
    "城市",
    "区域",
    "置业顾问",
    "获客渠道",
    "客户等级",
    "户型",
]
AMOUNT_COLUMNS = ["成交金额", "回款金额"]

EXPECTED_CITY = "杭州"
EXPECTED_DISTRICTS = ["余杭", "滨江", "钱塘", "萧山"]

DEMO_DTYPES = {
    "客户编号": "object",
    "线索日期": "datetime64[ns]",
    "项目": "object",
    "城市": "object",
    "区域": "object",
    "置业顾问": "object",
    "获客渠道": "object",
    "客户等级": "object",
    "到访日期": "datetime64[ns]",
    "认购日期": "datetime64[ns]",
    "签约日期": "datetime64[ns]",
    "户型": "object",
    "成交金额": "float64",
    "回款金额": "float64",
}

SENSITIVE_COLUMN_MARKERS = [
    "姓名",
    "名字",
    "手机",
    "电话",
    "身份证",
    "证件",
    "地址",
    "邮箱",
    "微信",
]


def _generate(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    output = tmp_path / "real_estate_sales_demo.csv"
    generate_dataset(output)
    return output, _read(output)


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"客户编号": "string"})
    for column in DATE_COLUMNS:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _file_record(path: Path) -> FileModel:
    return FileModel(
        id="real-estate-demo",
        filename=path.name,
        filepath=str(path),
        file_type="csv",
        row_count=520,
        col_count=len(DEMO_COLUMNS),
        columns_info=[
            {"name": name, "dtype": DEMO_DTYPES[name]} for name in DEMO_COLUMNS
        ],
        profile_report="",
    )


def _run_group(intent, record: FileModel):
    plan = PlanCompiler().compile(intent, record)
    step = plan.step("group_aggregate")
    return StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        record,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )


def _run_underperforming(record: FileModel, dimension: str):
    intent = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=[dimension],
        metric_ids=["lead_count", "deal_rate"],
        detect_underperforming=True,
    )
    plan = PlanCompiler().compile(intent, record)
    step = plan.step("underperforming")
    return StructuredAnalysisTools().execute(
        step.operation,
        step.arguments,
        record,
        {},
        output_schema=step.output_schema,
        source_step_id=step.step_id,
    )


# ---------------------------------------------------------------------------
# 第 20 节：schema 校验
# ---------------------------------------------------------------------------


def test_demo_has_520_rows_and_required_columns(tmp_path):
    _, data = _generate(tmp_path)

    assert RANDOM_SEED == 202509
    assert DEMO_COLUMNS == EXPECTED_COLUMNS
    assert list(data.columns) == EXPECTED_COLUMNS
    assert data.shape == (520, len(EXPECTED_COLUMNS))


def test_customer_id_is_unique_and_synthetic(tmp_path):
    _, data = _generate(tmp_path)

    assert data["客户编号"].nunique() == 520
    assert data["客户编号"].notna().all()
    assert data["客户编号"].str.match(r"^C\d{4}$").all()


def test_lead_date_range_covers_every_month(tmp_path):
    _, data = _generate(tmp_path)

    months = data["线索日期"].dt.to_period("M")
    assert months.min() >= pd.Period("2025-01", "M")
    assert months.max() <= pd.Period("2026-06", "M")
    assert months.nunique() == 18
    # 各月份均存在数据，不出现整月断档。
    assert months.value_counts().min() >= 5


def test_funnel_stage_ordering_and_null_propagation(tmp_path):
    _, data = _generate(tmp_path)

    lead = data["线索日期"]
    visit = data["到访日期"]
    subscription = data["认购日期"]
    contract = data["签约日期"]

    assert (lead.notna()).all()
    assert (visit.notna() | visit.isna()).all()  # 到访可缺失

    assert ((lead <= visit) | visit.isna()).all()
    assert ((visit <= subscription) | subscription.isna()).all()
    assert ((subscription <= contract) | contract.isna()).all()

    # 未到访 -> 后续阶段必须为空。
    assert data.loc[visit.isna(), "认购日期"].isna().all()
    assert data.loc[visit.isna(), "签约日期"].isna().all()
    # 未认购 -> 不得签约。
    assert data.loc[subscription.isna(), "签约日期"].isna().all()


def test_deal_amount_null_contract_gating(tmp_path):
    _, data = _generate(tmp_path)

    contracted = data["签约日期"].notna()
    not_contracted = ~contracted

    assert data.loc[not_contracted, "成交金额"].isna().all()
    assert data.loc[not_contracted, "回款金额"].isna().all()
    assert data.loc[contracted, "成交金额"].notna().all()
    # 成交金额不允许用 0 占位。
    assert (data.loc[contracted, "成交金额"] > 0).all()


def test_payment_amount_bounded_by_deal_amount(tmp_path):
    _, data = _generate(tmp_path)

    contracted = data["签约日期"].notna()
    deals = data[contracted]
    paid = deals[deals["回款金额"].notna()]

    assert (paid["回款金额"] >= 0).all()
    assert (paid["回款金额"] <= paid["成交金额"]).all()
    # 成交客户中允许少量未记录回款，但不得大量缺失。
    assert deals["回款金额"].notna().mean() >= 0.7


def test_categorical_values_are_within_frozen_sets(tmp_path):
    _, data = _generate(tmp_path)

    assert set(data["项目"]) <= set(PROJECTS)
    assert (data["城市"] == EXPECTED_CITY).all()
    assert set(data["区域"]) <= set(EXPECTED_DISTRICTS)
    assert set(data["置业顾问"]) <= set(CONSULTANTS)
    assert set(data["获客渠道"]) <= set(CHANNELS)
    assert set(data["客户等级"]) <= set(CUSTOMER_LEVELS)
    assert set(data["户型"]) <= set(PROPERTY_TYPES)
    assert len(CONSULTANTS) == 12
    assert len(CHANNELS) == 6
    assert len(PROJECTS) == 4


def test_no_sensitive_personal_fields(tmp_path):
    _, data = _generate(tmp_path)

    for column in data.columns:
        assert not any(marker in str(column) for marker in SENSITIVE_COLUMN_MARKERS)
    # 置业顾问使用匿名编号，不出现真实姓名。
    assert data["置业顾问"].str.match(r"^顾问\d{2}$").all()
    # 客户编号不携带任何可辨识个人信息。
    assert data["客户编号"].str.match(r"^C\d{4}$").all()


def test_funnel_distribution_within_spec_ranges(tmp_path):
    _, data = _generate(tmp_path)

    total = len(data)
    visited = data["到访日期"].notna().sum()
    subscribed = data["认购日期"].notna().sum()
    contracted = data["签约日期"].notna().sum()

    assert 0.50 <= visited / total <= 0.65
    assert 0.45 <= subscribed / visited <= 0.65
    assert 0.50 <= contracted / subscribed <= 0.75
    assert 80 <= contracted <= 120


# ---------------------------------------------------------------------------
# 第 21 节：业务故事（相对关系）
# ---------------------------------------------------------------------------


def _channel_stats(data: pd.DataFrame) -> pd.DataFrame:
    stats = data.groupby("获客渠道").agg(
        lead_count=("客户编号", "count"),
        visit_count=("到访日期", "count"),
        deal_count=("签约日期", "count"),
    )
    stats["visit_rate"] = stats["visit_count"] / stats["lead_count"]
    stats["deal_rate"] = stats["deal_count"] / stats["lead_count"]
    return stats


def test_short_video_channel_has_highest_volume_lowest_conversion(tmp_path):
    _, data = _generate(tmp_path)
    stats = _channel_stats(data)

    short_video = stats.loc["短视频平台"]
    assert short_video["lead_count"] == stats["lead_count"].max()
    assert short_video["deal_rate"] == stats["deal_rate"].min()


def test_referral_channel_deal_rate_above_overall_average(tmp_path):
    _, data = _generate(tmp_path)
    stats = _channel_stats(data)

    overall_deal_rate = stats["deal_count"].sum() / stats["lead_count"].sum()
    referral = stats.loc["老带新"]
    assert referral["deal_rate"] > overall_deal_rate


def test_qiantang_project_high_volume_low_conversion(tmp_path):
    _, data = _generate(tmp_path)
    stats = data.groupby("项目").agg(
        lead_count=("客户编号", "count"),
        deal_count=("签约日期", "count"),
    )
    stats["deal_rate"] = stats["deal_count"] / stats["lead_count"]

    qiantang = stats.loc["钱塘云筑"]
    # 线索量位于项目最高档（至少前二）。
    assert qiantang["lead_count"] >= sorted(stats["lead_count"])[-2]
    # 成交率低于至少两个其他主要项目。
    others = stats.loc[stats.index != "钱塘云筑", "deal_rate"]
    assert (qiantang["deal_rate"] < others).sum() >= 2


def test_binjiang_project_has_highest_average_deal_amount(tmp_path):
    _, data = _generate(tmp_path)
    stats = data.groupby("项目").agg(
        deal_count=("签约日期", "count"),
        deal_amount_sum=("成交金额", "sum"),
    )
    stats["avg_deal_amount"] = stats["deal_amount_sum"] / stats["deal_count"]

    assert stats["avg_deal_amount"].idxmax() == "滨江悦府"
    assert stats.loc["滨江悦府", "avg_deal_amount"] == stats["avg_deal_amount"].max()


def test_consultants_show_meaningful_performance_spread(tmp_path):
    _, data = _generate(tmp_path)
    stats = data.groupby("置业顾问").agg(
        lead_count=("客户编号", "count"),
        deal_count=("签约日期", "count"),
    )
    stats["deal_rate"] = stats["deal_count"] / stats["lead_count"]

    assert stats["deal_rate"].max() - stats["deal_rate"].min() >= 0.08
    assert stats["deal_rate"].max() >= stats["deal_rate"].median() * 1.4
    # 至少一名顾问负责线索明显多于平均（负责线索较多）。
    assert stats["lead_count"].max() >= stats["lead_count"].mean() * 1.3


def test_customer_level_conversion_ordering(tmp_path):
    _, data = _generate(tmp_path)
    stats = data.groupby("客户等级").agg(
        lead_count=("客户编号", "count"),
        deal_count=("签约日期", "count"),
    )
    stats["deal_rate"] = stats["deal_count"] / stats["lead_count"]

    assert stats.loc["A", "deal_rate"] > stats.loc["B", "deal_rate"] > stats.loc["C", "deal_rate"]


def test_generation_is_byte_stable_and_matches_committed_file(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    generate_dataset(first)
    generate_dataset(second)

    assert first.read_bytes() == second.read_bytes()
    assert COMMITTED_DATASET.read_bytes() == first.read_bytes()


# ---------------------------------------------------------------------------
# 第 22 节：underperforming 验收
# ---------------------------------------------------------------------------


def test_underperforming_identifies_short_video_channel(tmp_path):
    csv_path, _ = _generate(tmp_path)
    result = _run_underperforming(_file_record(csv_path), "lead_channel")

    assert result.status == "success"
    matched = set(result.dataframe["dimension_1"])
    assert "短视频平台" in matched


# ---------------------------------------------------------------------------
# 第 23 节：验收问题（确定性路径可支持）
# ---------------------------------------------------------------------------


def test_acceptance_questions_supported_by_deterministic_path(tmp_path):
    csv_path, _ = _generate(tmp_path)
    record = _file_record(csv_path)

    # Q1 各获客渠道的线索数、成交套数和成交转化率
    q1 = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["lead_count", "deal_count", "deal_rate"],
    )
    assert _run_group(q1, record).status == "success"

    # Q3 哪个项目成交金额最高
    q3 = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["project_name"],
        metric_ids=["deal_amount"],
    )
    assert _run_group(q3, record).status == "success"

    # Q4 各置业顾问成交套数排名
    q4 = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["sales_consultant"],
        metric_ids=["deal_count"],
    )
    assert _run_group(q4, record).status == "success"

    # Q5 不同渠道到访率
    q5 = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["lead_channel"],
        metric_ids=["visit_rate"],
    )
    assert _run_group(q5, record).status == "success"

    # Q6 最近几个月成交金额趋势
    q6 = MonthlyTrendIntent(
        workflow="monthly_trend",
        series_dimension="lead_channel",
        metric_ids=["deal_amount"],
    )
    plan = PlanCompiler().compile(q6, record)
    monthly_step = plan.step("monthly_aggregate")
    monthly_result = StructuredAnalysisTools().execute(
        monthly_step.operation,
        monthly_step.arguments,
        record,
        {},
        output_schema=monthly_step.output_schema,
        source_step_id=monthly_step.step_id,
    )
    assert monthly_result.status == "success"

    # Q7 不同户型成交表现
    q7 = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["property_type"],
        metric_ids=["deal_count", "deal_amount"],
    )
    assert _run_group(q7, record).status == "success"

    # Q8 不同客户等级的成交转化表现
    q8 = GroupComparisonIntent(
        workflow="group_comparison",
        dimensions=["customer_level"],
        metric_ids=["deal_rate"],
    )
    assert _run_group(q8, record).status == "success"
