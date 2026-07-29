from dataclasses import dataclass


@dataclass(frozen=True)
class DimensionDefinition:
    id: str
    label: str
    source_field: str


@dataclass(frozen=True)
class DateDefinition:
    id: str
    label: str
    source_field: str
    data_type: str


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    label: str
    semantic: str
    source_field: str | None
    aggregation: str
    unit: str


class LearningDomainRegistry:
    dimensions = {
        "course_category": DimensionDefinition(
            "course_category", "课程类别", "课程类别"
        ),
        "course_difficulty": DimensionDefinition(
            "course_difficulty", "课程难度", "课程难度"
        ),
        "purchase_channel": DimensionDefinition(
            "purchase_channel", "购买渠道", "购买渠道"
        ),
        "primary_device": DimensionDefinition(
            "primary_device", "主要学习设备", "主要学习设备"
        ),
    }
    dates = {
        "enrollment_date": DateDefinition(
            "enrollment_date", "报名日期", "报名日期", "datetime"
        )
    }
    metrics = {
        "enrollment_count": MetricDefinition(
            "enrollment_count",
            "报名人数",
            "报名人数",
            None,
            "count",
            "count",
        ),
        "paid_amount": MetricDefinition(
            "paid_amount",
            "实付金额",
            "实付金额",
            "实付金额",
            "sum",
            "currency",
        ),
        "completion_rate": MetricDefinition(
            "completion_rate",
            "平均完成率",
            "平均完成率",
            "课程完成率",
            "mean",
            "percentage",
        ),
        "refund_rate": MetricDefinition(
            "refund_rate",
            "退款率",
            "退款率",
            "是否退款",
            "rate",
            "percentage",
        ),
        "rating": MetricDefinition(
            "rating",
            "平均评分",
            "平均评分",
            "课程评分",
            "mean",
            "score",
        ),
    }

    def dimension(self, dimension_id: str) -> DimensionDefinition:
        return self.dimensions[dimension_id]

    def date(self, date_id: str) -> DateDefinition:
        return self.dates[date_id]

    def metric(self, metric_id: str) -> MetricDefinition:
        return self.metrics[metric_id]
