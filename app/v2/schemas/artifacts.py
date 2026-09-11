from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TextArtifactPayload(StrictModel):
    format: Literal["markdown", "plain_text"]
    content: str = Field(min_length=1)
    answer_mode: Literal[
        "model",
        "repaired_model",
        "deterministic_fallback",
    ] | None = None
    answer_warnings: list[str] = Field(default_factory=list, max_length=10)


class MetricArtifactPayload(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    value: int | float | str
    display_value: str = Field(min_length=1)
    unit: str | None = None


class TableColumn(StrictModel):
    key: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=256)
    data_type: Literal["string", "number", "boolean", "datetime", "null"]
    unit: Literal["count", "currency", "percentage", "score", "number"] | None = None


class TableArtifactPayload(StrictModel):
    columns: list[TableColumn] = Field(min_length=1, max_length=100)
    rows: list[dict[str, Any]] = Field(max_length=100)


class ChartArtifactPayload(StrictModel):
    renderer: Literal["static-image"]
    chart_type: Literal["bar", "line", "scatter", "heatmap"]
    title: str = Field(min_length=1, max_length=300)
    image_url: str = Field(min_length=1)
    alt_text: str = Field(min_length=1, max_length=500)

    @field_validator("image_url")
    @classmethod
    def browser_url_only(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith(("/absolute/", "/storage/../")):
            raise ValueError("image_url must be an application URL")
        if "\\" in value or value.startswith("./"):
            raise ValueError("image_url cannot be a physical path")
        return value


ArtifactPayload = (
    TextArtifactPayload
    | MetricArtifactPayload
    | TableArtifactPayload
    | ChartArtifactPayload
)
