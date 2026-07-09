from langchain.tools import tool
import pandas as pd

_df_cache: dict[str, pd.DataFrame] = {}


def set_df(file_id: str, df: pd.DataFrame):
    _df_cache[file_id] = df


def get_df(file_id: str) -> pd.DataFrame:
    if file_id not in _df_cache:
        raise ValueError(f"文件 {file_id} 未加载，请先上传文件")
    return _df_cache[file_id]


@tool
def describe_data(file_id: str) -> str:
    """获取数据的整体统计描述，包括数值列的均值、标准差、分位数等。"""
    df = get_df(file_id)
    return df.describe(include="all").to_string()


@tool
def value_counts(file_id: str, column: str, top_n: int = 10) -> str:
    """统计指定列的值分布，返回出现频率最高的前N个值。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"
    counts = df[column].value_counts().head(top_n)
    return counts.to_string()


@tool
def correlation_analysis(file_id: str) -> str:
    """计算数值列之间的相关系数矩阵，判断变量之间的线性关系强度。"""
    df = get_df(file_id)
    numeric = df.select_dtypes(include=["number"])
    if numeric.shape[1] < 2:
        return "数值列不足2列，无法计算相关系数"
    corr = numeric.corr()
    return corr.to_string()
