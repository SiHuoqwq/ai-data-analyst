import pandas as pd
from app.services.profiler import generate_profile, detect_outliers_iqr


def test_generate_profile():
    df = pd.DataFrame({
        "name": ["a", "b", "a", "c"],
        "score": [10, 20, 30, 100],
    })
    report = generate_profile(df)
    assert "# 数据质量报告" in report
    assert "4" in report  # row count
    assert "score" in report
    assert "name" in report


def test_detect_outliers_iqr():
    df = pd.DataFrame({"val": [1, 2, 3, 4, 5, 100]})
    result = detect_outliers_iqr(df, "val")
    assert result["count"] == 1
    assert result["rate"] > 0
