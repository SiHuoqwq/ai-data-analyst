import pytest
import pandas as pd
from app.services.tools.statistics import set_df, get_df, describe_data, value_counts
from app.services.tools.aggregation import group_analysis, filter_data
from app.services.tools.analysis import trend_analysis, data_summary, detect_outliers


@pytest.fixture
def sample_df():
    df = pd.DataFrame({
        "product": ["A", "B", "A", "C", "B"],
        "sales": [100, 200, 150, 300, 250],
        "date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"],
    })
    set_df("test_file", df)
    return df


def test_describe_data(sample_df):
    result = describe_data.invoke({"file_id": "test_file"})
    assert "sales" in result


def test_value_counts(sample_df):
    result = value_counts.invoke({"file_id": "test_file", "column": "product"})
    assert "A" in result
    assert "B" in result


def test_group_analysis(sample_df):
    result = group_analysis.invoke({"file_id": "test_file", "group_column": "product", "agg_column": "sales", "method": "sum"})
    assert "250" in result or "300" in result


def test_filter_data(sample_df):
    result = filter_data.invoke({"file_id": "test_file", "column": "sales", "operator": "gt", "value": "150"})
    assert "2" in result or "3" in result


def test_trend_analysis(sample_df):
    result = trend_analysis.invoke({"file_id": "test_file", "column": "sales"})
    assert "趋势分析" in result


def test_data_summary(sample_df):
    result = data_summary.invoke({"file_id": "test_file"})
    assert "product" in result
