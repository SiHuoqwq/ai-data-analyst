"""Generate the deterministic real-estate sales demo dataset.

数据 grain：一行 = 一条房地产客户销售线索（销售机会），`客户编号` 唯一。

所有数据均为完全合成的模拟数据，不包含真实公司、客户或个人信息。
生成器只用 Python 标准库，固定随机种子 `RANDOM_SEED`，相同脚本每次都会
产生字节一致的 CSV。
"""

from __future__ import annotations

import argparse
import calendar
import csv
import random
from datetime import date, timedelta
from pathlib import Path


RANDOM_SEED = 202509

CITY = "杭州"
START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 6, 30)

DEMO_COLUMNS = [
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

PROJECTS = ["云栖澜庭", "滨江悦府", "钱塘云筑", "湘湖映月"]
PROJECT_DISTRICTS = {
    "云栖澜庭": "余杭",
    "滨江悦府": "滨江",
    "钱塘云筑": "钱塘",
    "湘湖映月": "萧山",
}
PROJECT_TARGETS = {
    "云栖澜庭": 150,
    "滨江悦府": 120,
    "钱塘云筑": 160,
    "湘湖映月": 90,
}

CHANNELS = ["短视频平台", "搜索广告", "房产平台", "自然到访", "渠道中介", "老带新"]
CHANNEL_TARGETS = {
    "短视频平台": 150,
    "搜索广告": 100,
    "房产平台": 90,
    "自然到访": 70,
    "渠道中介": 60,
    "老带新": 50,
}

CONSULTANTS = [f"顾问{i:02d}" for i in range(1, 13)]
PROJECT_CONSULTANTS = {
    "云栖澜庭": ["顾问01", "顾问02", "顾问03"],
    "滨江悦府": ["顾问04", "顾问05", "顾问06"],
    "钱塘云筑": ["顾问07", "顾问08", "顾问09"],
    "湘湖映月": ["顾问10", "顾问11", "顾问12"],
}
# 顾问08 在钱塘云筑负责线索较多（用于演示「负责多但成交一般」）。
PROJECT_CONSULTANT_LEAD_WEIGHTS = {
    "云栖澜庭": {"顾问01": 1.0, "顾问02": 1.0, "顾问03": 1.0},
    "滨江悦府": {"顾问04": 1.0, "顾问05": 1.0, "顾问06": 1.0},
    "钱塘云筑": {"顾问07": 1.0, "顾问08": 2.0, "顾问09": 1.0},
    "湘湖映月": {"顾问10": 1.0, "顾问11": 1.0, "顾问12": 1.0},
}

CUSTOMER_LEVELS = ["A", "B", "C"]
LEVEL_TARGETS = {"A": 104, "B": 234, "C": 182}

PROPERTY_TYPES = ["两房", "三房", "四房", "改善四房"]
PROJECT_PROPERTY_WEIGHTS = {
    "云栖澜庭": {"两房": 25, "三房": 45, "四房": 20, "改善四房": 10},
    "滨江悦府": {"两房": 15, "三房": 35, "四房": 25, "改善四房": 25},
    "钱塘云筑": {"两房": 30, "三房": 45, "四房": 20, "改善四房": 5},
    "湘湖映月": {"两房": 20, "三房": 40, "四房": 25, "改善四房": 15},
}

DEAL_AMOUNT_RANGES = {
    "云栖澜庭": (1_800_000, 3_200_000),
    "滨江悦府": (3_000_000, 5_200_000),
    "钱塘云筑": (1_600_000, 2_800_000),
    "湘湖映月": (2_200_000, 3_800_000),
}

# 各渠道漏斗：到访概率、到访后认购概率、认购后签约概率。
CHANNEL_FUNNEL = {
    "短视频平台": (0.38, 0.38, 0.40),
    "搜索广告": (0.55, 0.50, 0.52),
    "房产平台": (0.65, 0.58, 0.60),
    "自然到访": (0.71, 0.58, 0.60),
    "渠道中介": (0.68, 0.62, 0.66),
    "老带新": (0.77, 0.72, 0.68),
}

LEVEL_FACTORS = {"A": 1.18, "B": 1.00, "C": 0.82}

PROJECT_DEAL_FACTORS = {
    "云栖澜庭": 1.00,
    "滨江悦府": 1.00,
    "钱塘云筑": 0.72,
    "湘湖映月": 1.00,
}

CONSULTANT_DEAL_FACTORS = {
    "顾问01": 1.0, "顾问02": 1.0, "顾问03": 1.0,
    "顾问04": 1.0, "顾问05": 1.5, "顾问06": 1.0,
    "顾问07": 1.0, "顾问08": 0.85, "顾问09": 1.0,
    "顾问10": 1.0, "顾问11": 1.4, "顾问12": 1.0,
}

# 18 个月轻度季节性权重（2025-01 至 2026-06）。
MONTH_WEIGHTS = {
    (2025, 1): 0.75, (2025, 2): 0.70, (2025, 3): 0.90, (2025, 4): 1.00,
    (2025, 5): 1.05, (2025, 6): 0.95, (2025, 7): 0.90, (2025, 8): 0.95,
    (2025, 9): 1.20, (2025, 10): 1.25, (2025, 11): 1.05, (2025, 12): 0.95,
    (2026, 1): 0.80, (2026, 2): 0.75, (2026, 3): 0.95, (2026, 4): 1.05,
    (2026, 5): 1.10, (2026, 6): 1.00,
}


def _clamp(value: float, lower: float = 0.02, upper: float = 0.98) -> float:
    return min(upper, max(lower, value))


def _distribute(total: int, weights: dict) -> dict:
    """按权重把 total 拆成整数计数，且总和严格等于 total（最大余数法）。"""
    keys = list(weights)
    values = [weights[key] for key in keys]
    denominator = sum(values)
    raw = [total * value / denominator for value in values]
    result = {key: int(value) for key, value in zip(keys, raw)}
    remainder = total - sum(result.values())
    order = sorted(
        range(len(keys)),
        key=lambda index: raw[index] - int(raw[index]),
        reverse=True,
    )
    for index in order[:remainder]:
        result[keys[index]] += 1
    return result


def _later(rng: random.Random, start: date, min_days: int, max_days: int) -> date:
    result = start + timedelta(days=rng.randint(min_days, max_days))
    return min(result, END_DATE)


def _round_thousand(rng: random.Random, low: int, high: int) -> int:
    return round(rng.uniform(low, high) / 1000) * 1000


def _payment(rng: random.Random, deal_amount: int) -> int | None:
    roll = rng.random()
    if roll < 0.10:
        return None
    if roll < 0.30:
        return deal_amount
    return round(deal_amount * rng.uniform(0.15, 0.95) / 1000) * 1000


def _make_row(
    rng: random.Random,
    index: int,
    channel: str,
    project: str,
    level: str,
    year: int,
    month: int,
) -> dict[str, object]:
    consultants = PROJECT_CONSULTANTS[project]
    consultant = rng.choices(
        consultants,
        weights=[PROJECT_CONSULTANT_LEAD_WEIGHTS[project][item] for item in consultants],
        k=1,
    )[0]
    property_type = rng.choices(
        PROPERTY_TYPES,
        weights=[PROJECT_PROPERTY_WEIGHTS[project][item] for item in PROPERTY_TYPES],
        k=1,
    )[0]

    lead_day = rng.randint(1, calendar.monthrange(year, month)[1])
    lead_date = date(year, month, lead_day)

    visit_p, sub_p, deal_p = CHANNEL_FUNNEL[channel]
    level_factor = LEVEL_FACTORS[level]
    project_factor = PROJECT_DEAL_FACTORS[project]
    consultant_factor = CONSULTANT_DEAL_FACTORS[consultant]

    visited = rng.random() < _clamp(visit_p * level_factor)
    subscribed = visited and rng.random() < _clamp(sub_p * level_factor)
    contracted = (
        subscribed
        and rng.random()
        < _clamp(deal_p * level_factor * project_factor * consultant_factor)
    )

    visit_date = _later(rng, lead_date, 0, 7) if visited else None
    subscription_date = _later(rng, visit_date, 3, 15) if subscribed else None
    contract_date = _later(rng, subscription_date, 5, 20) if contracted else None

    deal_amount: int | None = None
    payment_amount: int | None = None
    if contracted:
        low, high = DEAL_AMOUNT_RANGES[project]
        deal_amount = _round_thousand(rng, low, high)
        payment_amount = _payment(rng, deal_amount)

    return {
        "客户编号": f"C{index + 1:04d}",
        "线索日期": lead_date.isoformat(),
        "项目": project,
        "城市": CITY,
        "区域": PROJECT_DISTRICTS[project],
        "置业顾问": consultant,
        "获客渠道": channel,
        "客户等级": level,
        "到访日期": visit_date.isoformat() if visit_date else "",
        "认购日期": subscription_date.isoformat() if subscription_date else "",
        "签约日期": contract_date.isoformat() if contract_date else "",
        "户型": property_type,
        "成交金额": deal_amount if deal_amount is not None else "",
        "回款金额": payment_amount if payment_amount is not None else "",
    }


def generate_dataset(output_path: Path) -> None:
    """在每次调用时写出完全一致的房地产销售 Demo 数据集。"""
    rng = random.Random(RANDOM_SEED)

    month_list: list[tuple[int, int]] = []
    for (year, month), count in _distribute(520, MONTH_WEIGHTS).items():
        month_list.extend([(year, month)] * count)

    # 分层抽样：每个渠道内按项目目标比例分配，再在每个（渠道, 项目）格内按
    # 客户等级目标比例分配。这样渠道 / 项目 / 等级三者的边际分布都精确，
    # 且相互之间平衡，避免随机噪声淹没某一维度的业务故事。
    triples: list[tuple[str, str, str]] = []
    for channel, channel_count in CHANNEL_TARGETS.items():
        project_counts = _distribute(channel_count, PROJECT_TARGETS)
        for project, project_count in project_counts.items():
            level_counts = _distribute(project_count, LEVEL_TARGETS)
            for level, level_count in level_counts.items():
                triples.extend([(channel, project, level)] * level_count)

    rng.shuffle(triples)
    rng.shuffle(month_list)

    rows = [
        _make_row(
            rng,
            index,
            triples[index][0],
            triples[index][1],
            triples[index][2],
            *month_list[index],
        )
        for index in range(520)
    ]
    rows.sort(key=lambda row: (row["线索日期"], row["客户编号"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEMO_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成析数公开演示用的完全合成房地产销售数据。"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("real_estate_sales_demo.csv"),
        help="输出 CSV 路径",
    )
    args = parser.parse_args()
    generate_dataset(args.output)
    print(f"Generated deterministic demo dataset: {args.output}")


if __name__ == "__main__":
    main()
