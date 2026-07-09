from langchain.tools import tool
import pandas as pd
from app.services.tools.statistics import get_df
from app.services.chart_engine import draw_bar, draw_line, draw_pie, draw_scatter, draw_heatmap


@tool
def draw_bar_chart(file_id: str, x_column: str, y_column: str, title: str = "") -> str:
    """生成柱状图。x_column为横轴（分类），y_column为纵轴（数值）。"""
    df = get_df(file_id)
    if x_column not in df.columns or y_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    agg_df = df.groupby(x_column)[y_column].mean().reset_index().sort_values(y_column, ascending=False)
    filepath = draw_bar(agg_df, x_column, y_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_line_chart(file_id: str, x_column: str, y_column: str, title: str = "") -> str:
    """生成折线图，适合展示趋势变化。"""
    df = get_df(file_id)
    if x_column not in df.columns or y_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    filepath = draw_line(df, x_column, y_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_pie_chart(file_id: str, labels_column: str, values_column: str, title: str = "") -> str:
    """生成饼图，展示各部分占比。"""
    df = get_df(file_id)
    if labels_column not in df.columns or values_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    agg_df = df.groupby(labels_column)[values_column].sum().reset_index()
    filepath = draw_pie(agg_df, labels_column, values_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_scatter_chart(file_id: str, x_column: str, y_column: str, title: str = "") -> str:
    """生成散点图，展示两个数值变量之间的关系。"""
    df = get_df(file_id)
    if x_column not in df.columns or y_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    filepath = draw_scatter(df, x_column, y_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_heatmap_chart(file_id: str, title: str = "") -> str:
    """生成相关系数热力图，展示所有数值列之间的相关性。"""
    df = get_df(file_id)
    numeric = df.select_dtypes(include=["number"])
    if numeric.shape[1] < 2:
        return "数值列不足2列，无法生成热力图"
    filepath = draw_heatmap(numeric.corr(), title)
    return f"图表已生成: {filepath}"
