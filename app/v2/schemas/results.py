from typing import Any, Literal

from pydantic import Field

from app.v2.schemas.analysis import Aggregation, StrictAnalysisModel


DimensionRole = Literal["time", "series", "category"]
ResultDataType = Literal["date", "string", "number", "boolean"]
MetricUnit = Literal["count", "currency", "percentage", "score", "number"]


class ResultDimension(StrictAnalysisModel):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=256)
    role: DimensionRole
    data_type: ResultDataType
    source_field: str = Field(min_length=1, max_length=256)


class ResultMetric(StrictAnalysisModel):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=256)
    unit: MetricUnit
    aggregation: Aggregation
    nullable: bool
    source_field: str | None = Field(default=None, max_length=256)


class ResultSchema(StrictAnalysisModel):
    dimensions: list[ResultDimension] = Field(min_length=1, max_length=4)
    metrics: list[ResultMetric] = Field(min_length=1, max_length=10)
    grain: list[str] = Field(min_length=1, max_length=4)
    time_granularity: Literal["month"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def field_ids(self) -> set[str]:
        return {
            item.id
            for item in [*self.dimensions, *self.metrics]
        }


class ToolOutputContract(StrictAnalysisModel):
    result_schema: ResultSchema = Field(
        validation_alias="schema",
        serialization_alias="schema",
    )
    rows: list[dict[str, Any]]
    full_row_count: int = Field(ge=0)
    preview_row_count: int = Field(ge=0)
    source_tool: str = Field(min_length=1, max_length=100)
    source_step_id: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
