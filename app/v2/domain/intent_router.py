from dataclasses import dataclass
from typing import Literal

from app.v2.schemas.intents import (
    DomainIntent,
    GroupComparisonIntent,
    MonthlyTrendIntent,
)


WorkflowDecision = Literal[
    "group_comparison",
    "monthly_trend",
    "unsupported",
]


@dataclass(frozen=True)
class IntentRoutingDecision:
    workflow: WorkflowDecision
    group_score: int
    monthly_score: int


class ControlledIntentRouter:
    monthly_signals = {
        "最近几个月": 4,
        "按月": 4,
        "月份": 3,
        "月度": 3,
        "趋势": 2,
        "环比": 3,
        "随时间": 3,
        "销售趋势": 3,
        "增长": 1,
        "下滑": 1,
        "下降": 1,
        "波动": 1,
        "变化": 1,
    }
    group_signals = {
        "项目": 3,
        "楼盘": 3,
        "置业顾问": 3,
        "销售顾问": 3,
        "获客渠道": 3,
        "客户等级": 3,
        "户型": 3,
        "区域": 3,
        "城市": 3,
        "排名": 3,
        "渠道": 2,
        "线索": 2,
        "到访": 2,
        "认购": 2,
        "签约": 2,
        "回款": 2,
        "成交金额": 3,
        "成交套数": 3,
        "成交转化": 3,
        "成交情况": 2,
        "成交表现": 2,
        "对比": 2,
        "比较": 2,
        "差异": 2,
        "哪些": 2,
        "哪个": 2,
    }

    def route(self, question: str) -> IntentRoutingDecision:
        normalized = question.strip().lower()
        monthly = self._score(normalized, self.monthly_signals)
        group = self._score(normalized, self.group_signals)
        if max(monthly, group) < 3:
            workflow: WorkflowDecision = "unsupported"
        elif monthly >= 3 and group >= 3 and abs(monthly - group) < 3:
            workflow = "unsupported"
        elif monthly > group:
            workflow = "monthly_trend"
        else:
            workflow = "group_comparison"
        return IntentRoutingDecision(workflow, group, monthly)

    def default_intent(
        self,
        decision: IntentRoutingDecision,
    ) -> DomainIntent:
        if decision.workflow == "group_comparison":
            return GroupComparisonIntent(
                workflow="group_comparison",
                dimensions=["lead_channel"],
                metric_ids=["deal_count", "deal_amount"],
                detect_underperforming=False,
            )
        if decision.workflow == "monthly_trend":
            return MonthlyTrendIntent(
                workflow="monthly_trend",
                series_dimension="lead_channel",
                metric_ids=["deal_count", "deal_amount"],
            )
        raise ValueError("unsupported intent has no executable defaults")

    @staticmethod
    def _score(question: str, signals: dict[str, int]) -> int:
        return sum(
            weight for signal, weight in signals.items() if signal in question
        )
