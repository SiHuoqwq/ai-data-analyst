from langchain.tools import tool
import pandas as pd
from app.services.tools.statistics import get_df


@tool
def trend_analysis(file_id: str, column: str, date_column: str | None = None) -> str:
    """分析指定列的数值趋势。如果有日期列，按日期排序后分析；否则按行序分析。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    if not pd.api.types.is_numeric_dtype(df[column]):
        return f"列 '{column}' 不是数值类型，无法分析趋势"

    if date_column and date_column in df.columns:
        df = df.copy()
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df = df.sort_values(date_column)

    values = df[column].dropna().values
    if len(values) < 3:
        return f"'{column}' 有效数据不足（{len(values)}个值），至少需要3个数据点"

    n = len(values)
    half = n // 2
    first_half_mean = values[:half].mean()
    second_half_mean = values[half:].mean()
    change = ((second_half_mean - first_half_mean) / first_half_mean * 100) if first_half_mean != 0 else 0

    direction = "上升" if change > 0 else "下降"
    return (
        f"## '{column}' 趋势分析\n\n"
        f"- 前半段均值: {first_half_mean:.2f}\n"
        f"- 后半段均值: {second_half_mean:.2f}\n"
        f"- 变化: {change:+.1f}% ({direction}趋势)\n"
        f"- 整体均值: {values.mean():.2f}\n"
        f"- 整体标准差: {values.std():.2f}"
    )


@tool
def detect_outliers(file_id: str, column: str) -> str:
    """使用IQR方法检测指定列的异常值。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    if not pd.api.types.is_numeric_dtype(df[column]):
        return f"列 '{column}' 不是数值类型，无法检测异常值"

    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = df[(df[column] < lower) | (df[column] > upper)]

    lines = [
        f"## '{column}' 异常值检测 (IQR)\n",
        f"- Q1: {q1:.2f}, Q3: {q3:.2f}, IQR: {iqr:.2f}",
        f"- 正常范围: [{lower:.2f}, {upper:.2f}]",
        f"- 异常值: {len(outliers)} 个 ({len(outliers)/len(df)*100:.1f}%)",
    ]
    if len(outliers) > 0:
        lines.append(f"\n异常数据:\n{outliers.head(10).to_string()}")
    return "\n".join(lines)


@tool
def data_summary(file_id: str) -> str:
    """生成数据的综合摘要，包括行列数、缺失值、重复值、各列基本信息。"""
    df = get_df(file_id)
    lines = [
        f"## 数据摘要\n",
        f"- 行数: {len(df)}",
        f"- 列数: {len(df.columns)}",
        f"- 缺失值总计: {int(df.isnull().sum().sum())}",
        f"- 重复行: {int(df.duplicated().sum())}",
        f"\n### 各列信息\n",
    ]
    for col in df.columns:
        dtype = str(df[col].dtype)
        nulls = int(df[col].isnull().sum())
        uniques = int(df[col].nunique())
        sample = df[col].dropna().head(3).tolist()
        lines.append(f"- **{col}** ({dtype}): {nulls} 缺失, {uniques} 唯一值, 样例: {sample}")
    return "\n".join(lines)
