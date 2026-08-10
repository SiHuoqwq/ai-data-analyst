import pandas as pd
import numpy as np

from app.services.parser import validate_dataframe_columns


def generate_profile(df: pd.DataFrame) -> str:
    validate_dataframe_columns(df)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    text_cols = df.select_dtypes(include=["object"]).columns.tolist()

    lines = [
        "# 数据质量报告",
        "",
        f"- **行数**: {len(df)}",
        f"- **列数**: {len(df.columns)}",
        f"- **重复行**: {int(df.duplicated().sum())}",
        f"- **数值列**: {len(numeric_cols)}",
        f"- **文本列**: {len(text_cols)}",
        "",
    ]

    if numeric_cols:
        lines.append("## 数值列统计")
        lines.append("")
        lines.append("| 列名 | 均值 | 标准差 | 最小值 | 25% | 50% | 75% | 最大值 |")
        lines.append("|------|------|--------|--------|-----|-----|-----|--------|")
        for col in numeric_cols:
            stats = df[col].describe()
            lines.append(
                f"| {col} | {stats['mean']:.2f} | {stats['std']:.2f} | {stats['min']:.2f} | "
                f"{stats['25%']:.2f} | {stats['50%']:.2f} | {stats['75%']:.2f} | {stats['max']:.2f} |"
            )
        lines.append("")

    if text_cols:
        lines.append("## 文本列概况")
        lines.append("")
        for col in text_cols:
            unique = int(df[col].nunique())
            missing = int(df[col].isnull().sum())
            lines.append(f"- **{col}**: {unique} 个唯一值, 缺失 {missing} 条")

    return "\n".join(lines)


def detect_outliers_iqr(df: pd.DataFrame, column: str) -> dict:
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = df[(df[column] < lower) | (df[column] > upper)]
    return {
        "q1": float(q1), "q3": float(q3), "iqr": float(iqr),
        "lower": float(lower), "upper": float(upper),
        "count": int(len(outliers)),
        "rate": round(len(outliers) / len(df), 4) if len(df) > 0 else 0.0,
    }
