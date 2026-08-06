from pathlib import Path

import numpy as np
import pandas as pd

from demo.generate_learning_operations_demo import (
    DEMO_COLUMNS,
    generate_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_DATASET = PROJECT_ROOT / "demo" / "learning_operations_demo.csv"
EXPECTED_COLUMNS = [
    "课程类别",
    "课程难度",
    "购买渠道",
    "主要学习设备",
    "报名日期",
    "实付金额",
    "课程完成率",
    "是否退款",
    "课程评分",
]


def _generate(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    output = tmp_path / "demo.csv"
    generate_dataset(output)
    return output, pd.read_csv(output)


def _monthly_counts(data: pd.DataFrame) -> pd.DataFrame:
    periods = pd.to_datetime(data["报名日期"]).dt.to_period("M").astype(str)
    return (
        data.assign(月份=periods)
        .groupby(["月份", "课程类别"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )


def test_demo_dataset_has_fixed_public_contract(tmp_path):
    _, data = _generate(tmp_path)

    assert DEMO_COLUMNS == EXPECTED_COLUMNS
    assert list(data.columns) == EXPECTED_COLUMNS
    assert data.shape == (360, 9)

    months = pd.to_datetime(data["报名日期"]).dt.to_period("M")
    assert months.nunique() == 18
    assert str(months.min()) == "2025-01"
    assert str(months.max()) == "2026-06"

    required = [column for column in EXPECTED_COLUMNS if column != "课程评分"]
    assert data[required].notna().all().all()
    assert 1 <= int(data["课程评分"].isna().sum()) <= 36
    assert data["课程评分"].dropna().between(1, 5).all()


def test_demo_dataset_has_stable_business_trends(tmp_path):
    _, data = _generate(tmp_path)
    monthly = _monthly_counts(data)
    month_index = np.arange(len(monthly), dtype=float)

    data_slope = np.polyfit(month_index, monthly["数据分析"], 1)[0]
    frontend_slope = np.polyfit(month_index, monthly["前端开发"], 1)[0]
    assert data_slope >= 0.25
    assert frontend_slope <= -0.25

    volatility = monthly.std(ddof=1)
    other_max = volatility.drop("商业分析").max()
    assert volatility["商业分析"] >= other_max * 1.5

    completion = data.groupby("课程类别")["课程完成率"].mean()
    assert completion["AI 应用"] < completion.drop("AI 应用").min()

    refund_rate = (
        data.assign(退款=data["是否退款"].eq("是").astype(float))
        .groupby("课程类别")["退款"]
        .mean()
    )
    assert refund_rate["AI 应用"] > refund_rate.drop("AI 应用").max()


def test_demo_generation_is_byte_stable_and_matches_committed_file(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    generate_dataset(first)
    generate_dataset(second)

    assert first.read_bytes() == second.read_bytes()
    assert COMMITTED_DATASET.read_bytes() == first.read_bytes()
