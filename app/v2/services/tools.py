import json

import pandas as pd

from app.db.models import FileModel
from app.services.chart_engine import draw_bar
from app.services.parser import parse_file
from app.v2.services.artifacts import ArtifactDraft


def _group_summary(df: pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
    numeric_columns = list(df.select_dtypes(include=["number"]).columns)
    if not numeric_columns:
        summary = pd.DataFrame({"metric": ["row_count"], "value": [len(df)]})
        return summary, "metric", "value"

    value_column = str(numeric_columns[0])
    category_columns = [
        column for column in df.columns if column not in numeric_columns
    ]
    if category_columns:
        category_column = str(category_columns[0])
        summary = (
            df.groupby(category_column, dropna=False)[value_column]
            .mean()
            .reset_index()
            .head(20)
        )
        return summary, category_column, value_column

    summary = df[[value_column]].head(20).reset_index()
    return summary, "index", value_column


def _table_payload(summary: pd.DataFrame) -> dict:
    rows = json.loads(summary.to_json(orient="records", date_format="iso"))
    columns = []
    for column in summary.columns:
        data_type = (
            "number"
            if pd.api.types.is_numeric_dtype(summary[column])
            else "string"
        )
        columns.append(
            {"key": str(column), "label": str(column), "data_type": data_type}
        )
    return {"columns": columns, "rows": rows}


class V1DataToolAdapter:
    """Convert deterministic V1 parser/chart capabilities into V2 drafts."""

    def inspect(self, file_record: FileModel) -> list[ArtifactDraft]:
        df = parse_file(file_record.filepath)
        summary, _, _ = _group_summary(df)
        return [
            ArtifactDraft(
                artifact_type="text",
                title="数据概况",
                content_format="markdown",
                payload={
                    "format": "markdown",
                    "content": f"数据包含 {len(df)} 行、{len(df.columns)} 列。",
                },
            ),
            ArtifactDraft(
                artifact_type="metric",
                title="总行数",
                content_format="json",
                payload={
                    "label": "总行数",
                    "value": len(df),
                    "display_value": str(len(df)),
                    "unit": None,
                },
            ),
            ArtifactDraft(
                artifact_type="table",
                title="分组汇总",
                content_format="json",
                payload=_table_payload(summary),
                row_count=len(summary),
            ),
        ]

    def visualize(self, file_record: FileModel) -> ArtifactDraft:
        df = parse_file(file_record.filepath)
        summary, x_column, y_column = _group_summary(df)
        filepath = draw_bar(summary, x_column, y_column, "数据概览")
        return ArtifactDraft(
            artifact_type="chart",
            title="数据概览",
            content_format="png",
            chart_filepath=filepath,
            chart_type="bar",
            alt_text=f"按 {x_column} 展示 {y_column} 的柱状图",
        )
