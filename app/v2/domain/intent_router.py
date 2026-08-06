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
        "change by month": 4,
        "按月": 4,
        "月份": 3,
        "月度": 3,
        "趋势": 2,
        "增长": 1,
        "下滑": 1,
        "下降": 1,
        "波动": 1,
        "环比": 3,
        "随时间": 3,
    }
    group_signals = {
        "key outcomes compare across": 3,
        "不同课程": 3,
        "不同类别": 3,
        "不同难度": 3,
        "不同渠道": 3,
        "不同设备": 3,
        "对比": 2,
        "比较": 2,
        "完成率": 1,
        "退款率": 1,
        "评分": 1,
        "低表现": 3,
        "高报名低完成": 4,
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
                dimensions=[
                    "course_category",
                    "course_difficulty",
                    "purchase_channel",
                    "primary_device",
                ],
                metric_ids=[
                    "enrollment_count",
                    "completion_rate",
                    "refund_rate",
                    "rating",
                ],
                detect_underperforming=True,
            )
        if decision.workflow == "monthly_trend":
            return MonthlyTrendIntent(
                workflow="monthly_trend",
                series_dimension="course_category",
                metric_ids=[
                    "enrollment_count",
                    "paid_amount",
                    "completion_rate",
                ],
            )
        raise ValueError("unsupported intent has no executable defaults")

    @staticmethod
    def _score(question: str, signals: dict[str, int]) -> int:
        return sum(
            weight for signal, weight in signals.items() if signal in question
        )
