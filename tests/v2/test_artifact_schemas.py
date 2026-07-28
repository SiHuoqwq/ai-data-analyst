import pytest
from pydantic import ValidationError

from app.v2.schemas.artifacts import (
    ChartArtifactPayload,
    MetricArtifactPayload,
    TableArtifactPayload,
    TextArtifactPayload,
)


def test_core_artifact_payloads_are_strict_and_structured():
    text = TextArtifactPayload(format="markdown", content="分析完成")
    metric = MetricArtifactPayload(
        label="记录数",
        value=3,
        display_value="3",
        unit=None,
    )
    table = TableArtifactPayload(
        columns=[{"key": "sales", "label": "销售额", "data_type": "number"}],
        rows=[{"sales": 100}],
    )
    chart = ChartArtifactPayload(
        renderer="static-image",
        chart_type="bar",
        title="销售额",
        image_url="/api/v2/artifacts/art-1/download",
        alt_text="销售额柱状图",
    )

    assert text.model_dump()["format"] == "markdown"
    assert metric.model_dump()["value"] == 3
    assert table.model_dump()["rows"] == [{"sales": 100}]
    assert chart.model_dump()["image_url"].startswith("/api/")


@pytest.mark.parametrize(
    "image_url",
    ["./storage/charts/a.png", r"D:\private\a.png", "/absolute/server/a.png"],
)
def test_chart_payload_rejects_physical_paths(image_url):
    with pytest.raises(ValidationError):
        ChartArtifactPayload(
            renderer="static-image",
            chart_type="bar",
            title="销售额",
            image_url=image_url,
            alt_text="销售额柱状图",
        )
