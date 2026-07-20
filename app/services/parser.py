import pandas as pd
from pathlib import Path


def parse_file(filepath: str) -> pd.DataFrame:
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        return pd.read_csv(filepath)
    elif ext == ".xlsx":
        return pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def extract_columns_info(df: pd.DataFrame) -> list[dict]:
    info = []
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        info.append({
            "name": str(col),
            "dtype": str(df[col].dtype),
            "null_count": null_count,
            "null_rate": round(null_count / len(df), 4) if len(df) > 0 else 0.0,
            "unique_count": int(df[col].nunique()),
            "sample_values": [str(v) for v in df[col].dropna().head(5).tolist()],
        })
    return info
