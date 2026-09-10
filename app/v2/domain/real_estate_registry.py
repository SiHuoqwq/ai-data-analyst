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
    numerator_metric_id: str | None = None
    denominator_metric_id: str | None = None

    @property
    def is_derived(self) -> bool:
        return (
            self.numerator_metric_id is not None
            and self.denominator_metric_id is not None
        )


class RealEstateDomainRegistry:
    dimensions = {
        "project_name": DimensionDefinition(
            "project_name", "项目", "项目"
        ),
        "city": DimensionDefinition(
            "city", "城市", "城市"
        ),
        "district": DimensionDefinition(
            "district", "区域", "区域"
        ),
        "sales_consultant": DimensionDefinition(
            "sales_consultant", "置业顾问", "置业顾问"
        ),
        "lead_channel": DimensionDefinition(
            "lead_channel", "获客渠道", "获客渠道"
        ),
        "property_type": DimensionDefinition(
            "property_type", "户型", "户型"
        ),
        "customer_level": DimensionDefinition(
            "customer_level", "客户等级", "客户等级"
        ),
    }
    dates = {
        "lead_date": DateDefinition(
            "lead_date", "线索日期", "线索日期", "datetime"
        ),
        "visit_date": DateDefinition(
            "visit_date", "到访日期", "到访日期", "datetime"
        ),
        "subscription_date": DateDefinition(
            "subscription_date", "认购日期", "认购日期", "datetime"
        ),
        "contract_date": DateDefinition(
            "contract_date", "签约日期", "签约日期", "datetime"
        ),
    }
    metrics = {
        "lead_count": MetricDefinition(
            "lead_count", "线索数", "线索数", None, "count", "count"
        ),
        "visit_count": MetricDefinition(
            "visit_count", "到访数", "到访数", "到访日期", "count", "count"
        ),
        "subscription_count": MetricDefinition(
            "subscription_count",
            "认购数",
            "认购数",
            "认购日期",
            "count",
            "count",
        ),
        "deal_count": MetricDefinition(
            "deal_count", "成交套数", "成交套数", "签约日期", "count", "count"
        ),
        "deal_amount": MetricDefinition(
            "deal_amount",
            "成交金额",
            "成交金额",
            "成交金额",
            "sum",
            "currency",
        ),
        "payment_amount": MetricDefinition(
            "payment_amount",
            "回款金额",
            "回款金额",
            "回款金额",
            "sum",
            "currency",
        ),
        "visit_rate": MetricDefinition(
            "visit_rate",
            "到访率",
            "到访率",
            None,
            "ratio",
            "percentage",
            "visit_count",
            "lead_count",
        ),
        "subscription_rate": MetricDefinition(
            "subscription_rate",
            "认购转化率",
            "认购转化率",
            None,
            "ratio",
            "percentage",
            "subscription_count",
            "visit_count",
        ),
        "deal_rate": MetricDefinition(
            "deal_rate",
            "成交转化率",
            "成交转化率",
            None,
            "ratio",
            "percentage",
            "deal_count",
            "lead_count",
        ),
        "avg_deal_amount": MetricDefinition(
            "avg_deal_amount",
            "平均成交金额",
            "平均成交金额",
            None,
            "ratio",
            "currency",
            "deal_amount",
            "deal_count",
        ),
    }

    def dimension(self, dimension_id: str) -> DimensionDefinition:
        return self.dimensions[dimension_id]

    def date(self, date_id: str) -> DateDefinition:
        return self.dates[date_id]

    def metric(self, metric_id: str) -> MetricDefinition:
        return self.metrics[metric_id]

    def metric_by_semantic(self, semantic: str) -> MetricDefinition:
        for definition in self.metrics.values():
            if definition.semantic == semantic:
                return definition
        raise KeyError(semantic)
