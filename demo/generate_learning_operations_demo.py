"""Generate the public, deterministic learning-operations demo dataset."""

from __future__ import annotations

import argparse
import calendar
import csv
import random
from datetime import date
from pathlib import Path


RANDOM_SEED = 20260806
DEMO_COLUMNS = [
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

CATEGORY_ORDER = ["数据分析", "前端开发", "商业分析", "AI 应用", "产品设计"]
DIFFICULTIES = ["入门", "进阶", "高级"]
CHANNELS = ["官网", "搜索平台", "短视频平台", "学习社群", "企业合作"]
DEVICES = ["Windows", "macOS", "Android", "iOS"]


def _months() -> list[tuple[int, int]]:
    return [
        (year, month)
        for year in (2025, 2026)
        for month in range(1, 13)
        if date(year, month, 1) <= date(2026, 6, 1)
    ]


def _category_counts(month_index: int) -> dict[str, int]:
    growth_step = month_index * 6 // 18
    return {
        "数据分析": 3 + growth_step,
        "前端开发": 8 - growth_step,
        "商业分析": 0 if month_index % 2 == 0 else 6,
        "AI 应用": 4,
        "产品设计": 2,
    }


def _bounded(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _make_row(
    rng: random.Random,
    category: str,
    year: int,
    month: int,
    row_number: int,
) -> dict[str, object]:
    difficulty = rng.choices(DIFFICULTIES, weights=[4, 4, 2], k=1)[0]
    channel = rng.choices(CHANNELS, weights=[4, 3, 2, 2, 1], k=1)[0]
    device = rng.choices(DEVICES, weights=[4, 2, 3, 2], k=1)[0]
    day = rng.randint(1, calendar.monthrange(year, month)[1])

    price_base = {
        "数据分析": 299,
        "前端开发": 259,
        "商业分析": 329,
        "AI 应用": 399,
        "产品设计": 239,
    }[category]
    paid_amount = round(price_base * rng.uniform(0.72, 1.0), 2)

    completion_base = {
        "数据分析": 0.74,
        "前端开发": 0.64,
        "商业分析": 0.69,
        "AI 应用": 0.47,
        "产品设计": 0.77,
    }[category]
    difficulty_effect = {"入门": 0.04, "进阶": 0.0, "高级": -0.08}[difficulty]
    completion = round(
        _bounded(completion_base + difficulty_effect + rng.uniform(-0.10, 0.10), 0.12, 1.0),
        4,
    )

    refund_base = {
        "数据分析": 0.04,
        "前端开发": 0.08,
        "商业分析": 0.06,
        "AI 应用": 0.22,
        "产品设计": 0.03,
    }[category]
    refund_probability = refund_base + (0.05 if completion < 0.50 else 0.0)
    refunded = rng.random() < refund_probability

    rating: object
    if row_number % 17 == 0:
        rating = ""
    else:
        rating = round(
            _bounded(
                3.2 + completion * 1.7 - (0.35 if refunded else 0) + rng.uniform(-0.25, 0.25),
                1.0,
                5.0,
            ),
            1,
        )

    return {
        "课程类别": category,
        "课程难度": difficulty,
        "购买渠道": channel,
        "主要学习设备": device,
        "报名日期": date(year, month, day).isoformat(),
        "实付金额": paid_amount,
        "课程完成率": completion,
        "是否退款": "是" if refunded else "否",
        "课程评分": rating,
    }


def generate_dataset(output_path: Path) -> None:
    """Write the same public demo dataset on every invocation."""
    rng = random.Random(RANDOM_SEED)
    rows: list[dict[str, object]] = []
    row_number = 0
    for month_index, (year, month) in enumerate(_months()):
        counts = _category_counts(month_index)
        for category in CATEGORY_ORDER:
            for _ in range(counts[category]):
                row_number += 1
                rows.append(
                    _make_row(rng, category, year, month, row_number)
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEMO_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成析数公开演示用的完全合成课程运营数据。"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("learning_operations_demo.csv"),
        help="输出 CSV 路径",
    )
    args = parser.parse_args()
    generate_dataset(args.output)
    print(f"Generated deterministic demo dataset: {args.output}")


if __name__ == "__main__":
    main()
