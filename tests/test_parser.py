import pandas as pd
import pytest
from app.services.parser import parse_file, extract_columns_info


def test_parse_csv(tmp_path):
    csv_path = tmp_path / "test.csv"
    df = pd.DataFrame({"name": ["a", "b", "c"], "value": [1, 2, 3]})
    df.to_csv(csv_path, index=False)

    result = parse_file(str(csv_path))
    assert result.shape == (3, 2)
    assert list(result.columns) == ["name", "value"]


def test_parse_excel(tmp_path):
    xlsx_path = tmp_path / "test.xlsx"
    df = pd.DataFrame({"x": [1, 2]})
    df.to_excel(xlsx_path, index=False)

    result = parse_file(str(xlsx_path))
    assert result.shape == (2, 1)


def test_parse_unsupported_raises(tmp_path):
    bad = tmp_path / "test.txt"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported"):
        parse_file(str(bad))


def test_extract_columns_info():
    df = pd.DataFrame({"name": ["a", "b", None], "score": [1.0, 2.0, 3.0]})
    info = extract_columns_info(df)
    assert len(info) == 2
    assert info[0]["null_count"] == 1
    assert info[0]["null_rate"] == pytest.approx(1/3, 0.01)
    assert info[1]["dtype"] == "float64"
