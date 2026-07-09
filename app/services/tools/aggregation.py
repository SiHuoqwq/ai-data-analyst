from langchain.tools import tool
import pandas as pd
from app.services.tools.statistics import get_df


@tool
def group_analysis(file_id: str, group_column: str, agg_column: str, method: str = "mean") -> str:
    """按指定列分组，对另一列进行聚合（mean/sum/count/min/max）。"""
    df = get_df(file_id)
    if group_column not in df.columns:
        return f"分组列 '{group_column}' 不存在。可用列: {list(df.columns)}"
    if agg_column not in df.columns:
        return f"聚合列 '{agg_column}' 不存在。可用列: {list(df.columns)}"

    methods = {"mean": "mean", "sum": "sum", "count": "count", "min": "min", "max": "max"}
    if method not in methods:
        return f"不支持的聚合方式: {method}，支持: {list(methods.keys())}"

    result = df.groupby(group_column)[agg_column].agg(method).sort_values(ascending=False)
    return result.to_string()


@tool
def filter_data(file_id: str, column: str, operator: str, value: str) -> str:
    """按条件筛选数据（operator: eq/gt/lt/ge/le/contains），返回筛选后的行数和前10行。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    operators = {
        "eq": lambda c, v: df[c] == v,
        "gt": lambda c, v: pd.to_numeric(df[c], errors="coerce") > float(v),
        "lt": lambda c, v: pd.to_numeric(df[c], errors="coerce") < float(v),
        "ge": lambda c, v: pd.to_numeric(df[c], errors="coerce") >= float(v),
        "le": lambda c, v: pd.to_numeric(df[c], errors="coerce") <= float(v),
        "contains": lambda c, v: df[c].astype(str).str.contains(v, na=False),
    }
    if operator not in operators:
        return f"不支持的运算符: {operator}，支持: {list(operators.keys())}"

    try:
        mask = operators[operator](column, value)
        filtered = df[mask]
        return f"筛选结果: {len(filtered)} 行 (共 {len(df)} 行)\n\n{filtered.head(10).to_string()}"
    except Exception as e:
        return f"筛选失败: {str(e)}"


@tool
def sort_data(file_id: str, column: str, order: str = "desc", top_n: int = 10) -> str:
    """按指定列排序，返回前N行。order: asc/desc。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    ascending = order.lower() == "asc"
    sorted_df = df.sort_values(column, ascending=ascending).head(top_n)
    return sorted_df.to_string()
