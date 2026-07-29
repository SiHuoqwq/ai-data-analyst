import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd
from pydantic import ValidationError

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from app.config import settings
from app.db.models import FileModel
from app.services.parser import parse_file
from app.v2.schemas.analysis import TOOL_INPUT_MODELS
from app.v2.services.artifacts import ArtifactDraft


TRUTHY = {"1", "true", "yes", "y", "是", "已退款", "退款"}
FALSY = {"0", "false", "no", "n", "否", "未退款"}


def _chart_unit(field: str) -> str:
    normalized = field.lower()
    if any(marker in normalized for marker in ("完成率", "退款率", "比例", "rate")):
        return "percentage"
    if any(marker in normalized for marker in ("金额", "收入", "销售额", "amount", "revenue")):
        return "currency"
    if any(marker in normalized for marker in ("评分", "得分", "score", "rating")):
        return "score"
    if any(marker in normalized for marker in ("人数", "数量", "记录数", "count")):
        return "count"
    return "number"


def _wrapped_label(value: str, width: int = 14) -> str:
    return "\n".join(
        value[index : index + width]
        for index in range(0, len(value), width)
    )


def _chart_alt_text(
    title: str,
    full_labels: list[str],
    y_fields: list[str],
    unit: str,
    max_length: int = 500,
) -> str:
    prefix = f"{title}；完整分类："
    suffix = f"；指标：{', '.join(y_fields)}；量纲：{unit}"
    selected: list[str] = []
    for label in full_labels:
        candidate = selected + [label]
        omitted = len(full_labels) - len(candidate)
        omission = f"；其余 {omitted} 个组合见对应表格" if omitted else ""
        text = f"{prefix}{'；'.join(candidate)}{omission}{suffix}"
        if len(text) > max_length:
            break
        selected = candidate

    if not selected and full_labels:
        omission = (
            f"；其余 {len(full_labels) - 1} 个组合见对应表格"
            if len(full_labels) > 1
            else ""
        )
        available = max_length - len(prefix) - len(omission) - len(suffix)
        selected = [full_labels[0][: max(0, available)]]

    omitted = len(full_labels) - len(selected)
    omission = f"；其余 {omitted} 个组合见对应表格" if omitted else ""
    return f"{prefix}{'；'.join(selected)}{omission}{suffix}"[:max_length]


def _configure_chinese_font() -> str | None:
    preferred = {
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "WenQuanYi Micro Hei",
    }
    for font_path in font_manager.findSystemFonts():
        try:
            name = font_manager.FontProperties(fname=font_path).get_name()
            if name not in preferred:
                continue
            font_manager.fontManager.addfont(font_path)
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
        except (OSError, RuntimeError):
            continue
    return None


_CHART_FONT = _configure_chinese_font()


class ToolExecutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable


@dataclass
class ToolExecutionResult:
    status: str
    summary: dict[str, Any]
    preview: list[dict[str, Any]]
    row_count: int
    truncated: bool
    warnings: list[str]
    drafts: list[ArtifactDraft]
    validated_input: dict[str, Any]
    dataframe: pd.DataFrame | None = field(default=None, repr=False)

    def evidence(self, *, complete: bool = False) -> dict[str, Any]:
        preview = self.preview[:20]
        if complete and self.dataframe is not None:
            preview = _json_rows(self.dataframe)
        return {
            "summary": self.summary,
            "preview": preview,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "warnings": self.warnings,
        }


def _json_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _table_payload(df: pd.DataFrame) -> dict[str, Any]:
    columns = []
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            data_type = "number"
        elif pd.api.types.is_bool_dtype(series):
            data_type = "boolean"
        elif pd.api.types.is_datetime64_any_dtype(series):
            data_type = "datetime"
        else:
            data_type = "string"
        columns.append(
            {"key": str(column), "label": str(column), "data_type": data_type}
        )
    return {"columns": columns, "rows": _json_rows(df)}


def _as_rate(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    def convert(value):
        if pd.isna(value):
            return None
        normalized = str(value).strip().lower()
        if normalized in TRUTHY:
            return 1.0
        if normalized in FALSY:
            return 0.0
        return None

    return series.map(convert).astype(float)


def _as_number(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.astype("string").str.strip()
    percent = text.str.endswith("%", na=False)
    cleaned = (
        text.str.replace(",", "", regex=False)
        .str.replace(r"[￥¥$元\s]", "", regex=True)
        .str.replace("%", "", regex=False)
    )
    numeric = pd.to_numeric(cleaned, errors="coerce").astype("Float64")
    numeric.loc[percent] = numeric.loc[percent] / 100
    return numeric


class StructuredAnalysisTools:
    def execute(
        self,
        operation: str,
        arguments: dict[str, Any],
        file_record: FileModel,
        prior_results: dict[str, ToolExecutionResult],
    ) -> ToolExecutionResult:
        model = TOOL_INPUT_MODELS.get(operation)
        if model is None:
            raise ToolExecutionError(
                "UNKNOWN_TOOL",
                "请求的分析工具不在允许列表中",
                {"tool": operation, "allowed_tools": list(TOOL_INPUT_MODELS)},
            )
        try:
            validated = model.model_validate(arguments).model_dump(mode="json")
        except ValidationError as exc:
            raise ToolExecutionError(
                "INVALID_INPUT",
                "分析工具参数无效",
                {"issues": exc.errors(include_url=False, include_input=False)},
            ) from exc

        if operation == "create_chart":
            return self._create_chart(validated, prior_results)

        df = parse_file(file_record.filepath)
        if df.empty:
            raise ToolExecutionError("EMPTY_RESULT", "数据集没有可分析的记录")
        if operation == "inspect_dataset":
            return self._inspect(df, validated)
        if operation == "group_aggregate":
            return self._group_aggregate(df, validated)
        if operation == "monthly_trend":
            return self._monthly_trend(df, validated)
        if operation == "identify_underperforming":
            return self._underperforming(df, validated)
        raise ToolExecutionError("UNKNOWN_TOOL", "请求的分析工具不在允许列表中")

    def _require_fields(self, df: pd.DataFrame, fields: list[str | None]):
        missing = sorted({field for field in fields if field and field not in df})
        if missing:
            raise ToolExecutionError(
                "SCHEMA_FIELD_NOT_FOUND",
                f"字段 {', '.join(missing)} 不存在",
                {
                    "fields": missing,
                    "available_fields": [str(item) for item in df.columns],
                },
            )

    def _apply_filters(
        self, df: pd.DataFrame, filters: list[dict[str, Any]]
    ) -> pd.DataFrame:
        self._require_fields(df, [item["field"] for item in filters])
        result = df
        for item in filters:
            series = result[item["field"]]
            operator = item["operator"]
            value = item.get("value")
            if operator == "eq":
                mask = series == value
            elif operator == "ne":
                mask = series != value
            elif operator == "gt":
                mask = series > value
            elif operator == "gte":
                mask = series >= value
            elif operator == "lt":
                mask = series < value
            elif operator == "lte":
                mask = series <= value
            elif operator == "in":
                mask = series.isin(value if isinstance(value, list) else [value])
            elif operator == "not_in":
                mask = ~series.isin(value if isinstance(value, list) else [value])
            elif operator == "contains":
                mask = series.astype(str).str.contains(
                    str(value), regex=False, na=False
                )
            elif operator == "is_null":
                mask = series.isna()
            elif operator == "not_null":
                mask = series.notna()
            else:
                raise ToolExecutionError("INVALID_INPUT", "不支持的过滤方式")
            result = result[mask]
        return result

    def _aggregate(
        self,
        df: pd.DataFrame,
        group_by: list[str],
        metrics: list[dict[str, Any]],
    ) -> pd.DataFrame:
        fields = group_by + [item.get("field") for item in metrics]
        self._require_fields(df, fields)
        working = df.copy()
        grouped = working.groupby(group_by, dropna=False, sort=False)
        pieces = [grouped.size().rename("__group_size")]
        aliases = []
        for index, metric in enumerate(metrics):
            alias = metric["alias"]
            aliases.append(alias)
            aggregation = metric["aggregation"]
            field_name = metric.get("field")
            if aggregation == "count":
                value = grouped.size().rename(alias)
            else:
                if aggregation in {"sum", "mean", "min", "max"}:
                    working[field_name] = _as_number(working[field_name])
                if aggregation == "rate":
                    working[field_name] = _as_rate(working[field_name])
                    value = working.groupby(
                        group_by, dropna=False, sort=False
                    )[field_name].mean().rename(alias)
                else:
                    value = getattr(
                        working.groupby(group_by, dropna=False, sort=False)[
                            field_name
                        ],
                        aggregation,
                    )().rename(alias)
            pieces.append(value)
        result = pd.concat(pieces, axis=1).reset_index()
        return result[group_by + aliases]

    def _inspect(
        self, df: pd.DataFrame, validated: dict[str, Any]
    ) -> ToolExecutionResult:
        numeric_fields = []
        date_fields = []
        categorical_fields = []
        for column in df.columns:
            name = str(column)
            if pd.api.types.is_numeric_dtype(df[column]):
                numeric_fields.append(name)
                continue
            normalized_name = name.lower()
            looks_like_date = any(
                marker in normalized_name
                for marker in ("日期", "时间", "date", "time", "月份", "month")
            )
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                date_fields.append(name)
            elif looks_like_date:
                parsed = pd.to_datetime(df[column], errors="coerce")
                if parsed.notna().mean() >= 0.8:
                    date_fields.append(name)
                else:
                    categorical_fields.append(name)
            elif _as_number(df[column]).notna().mean() >= 0.8:
                numeric_fields.append(name)
            else:
                categorical_fields.append(name)
        missing = {
            str(column): int(df[column].isna().sum())
            for column in df.columns
            if df[column].isna().any()
        }
        summary = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "numeric_fields": numeric_fields,
            "categorical_fields": categorical_fields,
            "date_fields": date_fields,
            "missing_counts": missing,
        }
        text = (
            f"数据集包含 {len(df)} 行、{len(df.columns)} 列。"
            f"数值字段 {len(numeric_fields)} 个，日期字段 {len(date_fields)} 个。"
        )
        drafts = [
            ArtifactDraft(
                artifact_type="text",
                title="数据字段概览",
                content_format="markdown",
                payload={"format": "markdown", "content": text},
            ),
            ArtifactDraft(
                artifact_type="metric",
                title="数据记录数",
                content_format="json",
                payload={
                    "label": "数据记录数",
                    "value": len(df),
                    "display_value": f"{len(df):,}",
                    "unit": "行",
                },
            ),
        ]
        return ToolExecutionResult(
            "success", summary, [], 0, False, [], drafts, validated
        )

    def _group_aggregate(
        self, df: pd.DataFrame, validated: dict[str, Any]
    ) -> ToolExecutionResult:
        filtered = self._apply_filters(df, validated["filters"])
        if filtered.empty:
            raise ToolExecutionError("EMPTY_RESULT", "筛选后没有可分析记录")
        result = self._aggregate(
            filtered, validated["group_by"], validated["metrics"]
        )
        for sort in reversed(validated["sort"]):
            if sort["field"] not in result.columns:
                raise ToolExecutionError(
                    "SCHEMA_FIELD_NOT_FOUND",
                    f"排序字段 {sort['field']} 不存在",
                    {"available_fields": list(result.columns)},
                )
            result = result.sort_values(
                sort["field"], ascending=sort["direction"] == "asc"
            )
        full_count = len(result)
        result = result.head(validated["limit"]).reset_index(drop=True)
        summary = {
            "description": "多维分组统计",
            "group_by": validated["group_by"],
            "metrics": [item["alias"] for item in validated["metrics"]],
            "scanned_rows": len(filtered),
        }
        draft = ArtifactDraft(
            artifact_type="table",
            title="分组统计结果",
            content_format="json",
            payload=_table_payload(result),
            row_count=full_count,
        )
        return ToolExecutionResult(
            "success",
            summary,
            _json_rows(result.head(20)),
            full_count,
            full_count > len(result),
            [],
            [draft],
            validated,
            result,
        )

    def _monthly_trend(
        self, df: pd.DataFrame, validated: dict[str, Any]
    ) -> ToolExecutionResult:
        fields = [validated["date_field"], validated["category_field"]]
        self._require_fields(df, fields)
        filtered = self._apply_filters(df, validated["filters"]).copy()
        parsed = pd.to_datetime(filtered[validated["date_field"]], errors="coerce")
        invalid_count = int(parsed.isna().sum())
        filtered = filtered[parsed.notna()].copy()
        filtered["月份"] = parsed[parsed.notna()].dt.to_period("M").astype(str)
        if filtered.empty:
            raise ToolExecutionError("EMPTY_RESULT", "日期字段没有可用值")
        full_result = self._aggregate(
            filtered,
            ["月份", validated["category_field"]],
            validated["metrics"],
        ).sort_values(["月份", validated["category_field"]])
        full_count = len(full_result)
        result = full_result.head(validated["limit"]).reset_index(drop=True)
        warnings = (
            [f"{invalid_count} 条记录的日期无效，已排除"] if invalid_count else []
        )
        category_field = validated["category_field"]
        metric_signals = {}
        for metric in validated["metrics"]:
            metric_name = metric["alias"]
            trend_rows = []
            for category, subset in full_result.groupby(
                category_field, dropna=False
            ):
                values = pd.to_numeric(
                    subset.sort_values("月份")[metric_name],
                    errors="coerce",
                ).dropna()
                if values.empty:
                    continue
                first = float(values.iloc[0])
                last = float(values.iloc[-1])
                change_rate = (
                    (last - first) / abs(first) if first else 0.0
                )
                period_changes = (
                    values.pct_change()
                    .replace([float("inf"), float("-inf")], pd.NA)
                    .dropna()
                )
                volatility = (
                    float(period_changes.std(ddof=0))
                    if len(period_changes)
                    else 0.0
                )
                trend_rows.append(
                    {
                        "category": str(category),
                        "change_rate": round(change_rate, 6),
                        "change_rate_stddev": round(volatility, 6),
                    }
                )
            ordered = sorted(
                trend_rows, key=lambda item: item["category"]
            )
            metric_signals[metric_name] = {
                "fastest_growth": (
                    {
                        "category": max(
                            ordered, key=lambda item: item["change_rate"]
                        )["category"],
                        "change_rate": max(
                            item["change_rate"] for item in ordered
                        ),
                    }
                    if ordered
                    else None
                ),
                "largest_decline": (
                    {
                        "category": min(
                            ordered, key=lambda item: item["change_rate"]
                        )["category"],
                        "change_rate": min(
                            item["change_rate"] for item in ordered
                        ),
                    }
                    if ordered
                    else None
                ),
                "most_volatile": (
                    {
                        "category": max(
                            ordered,
                            key=lambda item: item[
                                "change_rate_stddev"
                            ],
                        )["category"],
                        "change_rate_stddev": max(
                            item["change_rate_stddev"] for item in ordered
                        ),
                    }
                    if ordered
                    else None
                ),
            }
        primary_metric = validated["metrics"][0]["alias"]
        trend_signals = {
            "primary_metric": primary_metric,
            **metric_signals[primary_metric],
            "by_metric": metric_signals,
        }
        summary = {
            "description": "按月份和类别统计趋势",
            "date_field": validated["date_field"],
            "category_field": validated["category_field"],
            "metrics": [item["alias"] for item in validated["metrics"]],
            "scanned_rows": len(filtered),
            "trend_signals": trend_signals,
        }
        draft = ArtifactDraft(
            artifact_type="table",
            title="月度趋势",
            content_format="json",
            payload=_table_payload(result),
            row_count=full_count,
        )
        return ToolExecutionResult(
            "success",
            summary,
            _json_rows(result.head(20)),
            full_count,
            full_count > len(result),
            warnings,
            [draft],
            validated,
            full_result.reset_index(drop=True),
        )

    def _underperforming(
        self, df: pd.DataFrame, validated: dict[str, Any]
    ) -> ToolExecutionResult:
        self._require_fields(
            df, validated["group_by"] + [validated["completion_field"]]
        )
        working = df.copy()
        working[validated["completion_field"]] = _as_number(
            working[validated["completion_field"]]
        )
        grouped = (
            working.groupby(validated["group_by"], dropna=False)
            .agg(
                报名人数=(validated["completion_field"], "size"),
                平均完成率=(validated["completion_field"], "mean"),
            )
            .reset_index()
        )
        eligible = grouped[
            grouped["报名人数"] >= validated["min_sample_size"]
        ].copy()
        if eligible.empty:
            raise ToolExecutionError(
                "EMPTY_RESULT", "没有组合达到最小样本量要求"
            )
        volume_threshold = float(
            eligible["报名人数"].quantile(validated["high_volume_quantile"])
        )
        completion_threshold = float(
            eligible["平均完成率"].quantile(
                validated["low_completion_quantile"]
            )
        )
        result = eligible[
            (eligible["报名人数"] >= volume_threshold)
            & (eligible["平均完成率"] <= completion_threshold)
        ].sort_values(["平均完成率", "报名人数"], ascending=[True, False])
        result = result.head(validated["limit"]).reset_index(drop=True)
        rule = {
            "min_sample_size": validated["min_sample_size"],
            "high_volume_quantile": validated["high_volume_quantile"],
            "low_completion_quantile": validated["low_completion_quantile"],
            "volume_threshold": volume_threshold,
            "completion_threshold": completion_threshold,
        }
        summary = {
            "description": "高报名但低完成率组合",
            "rule": rule,
            "matched_groups": len(result),
        }
        draft = ArtifactDraft(
            artifact_type="table",
            title="高报名低完成率组合",
            content_format="json",
            payload=_table_payload(result),
            row_count=len(result),
        )
        return ToolExecutionResult(
            "success",
            summary,
            _json_rows(result),
            len(result),
            False,
            [],
            [draft],
            validated,
            result,
        )

    def _create_chart(
        self,
        validated: dict[str, Any],
        prior_results: dict[str, ToolExecutionResult],
    ) -> ToolExecutionResult:
        source = prior_results.get(validated["source_step_id"])
        if source is None or source.dataframe is None:
            raise ToolExecutionError(
                "SOURCE_RESULT_NOT_FOUND",
                "图表引用的分析步骤不存在或没有表格结果",
                {"source_step_id": validated["source_step_id"]},
            )
        df = source.dataframe.head(validated["limit"]).copy()
        required = [validated["x_field"], *validated["y_fields"]]
        if validated["color_field"]:
            required.append(validated["color_field"])
        self._require_fields(df, required)
        if df.empty:
            raise ToolExecutionError("EMPTY_RESULT", "没有可绘制的数据")

        x_field = validated["x_field"]
        color_field = validated["color_field"]
        group_by = source.validated_input.get("group_by") or []
        label_fields = [
            field for field in group_by if field in df.columns
        ]
        full_labels = (
            df[label_fields].astype(str).agg(" / ".join, axis=1)
            if len(label_fields) > 1
            else df[x_field].astype(str)
        )
        unit_groups: dict[str, list[str]] = {}
        for y_field in validated["y_fields"]:
            unit_groups.setdefault(_chart_unit(y_field), []).append(y_field)

        drafts = []
        for unit, y_fields in unit_groups.items():
            fig, ax = plt.subplots(figsize=(10, 5.5))
            if validated["chart_type"] == "bar":
                x = range(len(df))
                width = 0.8 / len(y_fields)
                for index, y_field in enumerate(y_fields):
                    values = pd.to_numeric(df[y_field], errors="coerce")
                    ax.bar(
                        [item + index * width for item in x],
                        values,
                        width=width,
                        label=y_field,
                    )
                ax.set_xticks(
                    [
                        item + width * (len(y_fields) - 1) / 2
                        for item in x
                    ],
                    [_wrapped_label(value) for value in full_labels],
                    rotation=35,
                    ha="right",
                )
            elif color_field:
                for category, subset in df.groupby(color_field, dropna=False):
                    for y_field in y_fields:
                        ax.plot(
                            subset[x_field].astype(str),
                            pd.to_numeric(subset[y_field], errors="coerce"),
                            marker="o",
                            label=f"{category} · {y_field}",
                        )
                ax.tick_params(axis="x", rotation=35)
            else:
                for y_field in y_fields:
                    ax.plot(
                        df[x_field].astype(str),
                        pd.to_numeric(df[y_field], errors="coerce"),
                        marker="o",
                        label=y_field,
                    )
                ax.tick_params(axis="x", rotation=35)
            title = validated["title"]
            if len(unit_groups) > 1:
                title = f"{title}（{', '.join(y_fields)}）"
            if len(source.dataframe) > validated["limit"]:
                title = f"{title}，展示前 {validated['limit']} 项"
            ax.set_title(title)
            ax.set_xlabel(" / ".join(label_fields) if label_fields else x_field)
            ax.legend()
            fig.tight_layout()
            chart_root = Path(settings.chart_dir)
            chart_root.mkdir(parents=True, exist_ok=True)
            chart_path = chart_root / f"{uuid.uuid4()}.png"
            fig.savefig(
                chart_path,
                dpi=150,
                bbox_inches="tight",
                facecolor="white",
            )
            plt.close(fig)
            drafts.append(
                ArtifactDraft(
                    artifact_type="chart",
                    title=title,
                    content_format="png",
                    chart_filepath=str(chart_path),
                    chart_type=validated["chart_type"],
                    alt_text=_chart_alt_text(
                        title,
                        full_labels,
                        y_fields,
                        unit,
                    ),
                )
            )
        summary = {
            "description": "已生成静态图表",
            "chart_type": validated["chart_type"],
            "source_step_id": validated["source_step_id"],
            "plotted_rows": len(df),
            "unit_groups": {
                unit: fields for unit, fields in unit_groups.items()
            },
        }
        return ToolExecutionResult(
            "success", summary, [], len(df), False, [], drafts, validated
        )
