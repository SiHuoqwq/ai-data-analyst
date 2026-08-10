import pandas as pd
from pathlib import Path


MAX_UPLOAD_FILENAME_LENGTH = 255
MAX_DATASET_COLUMNS = 1_000
MAX_COLUMN_NAME_LENGTH = 255


class DatasetMetadataValidationError(ValueError):
    pass


def validate_upload_filename(filename: str) -> None:
    if len(filename) > MAX_UPLOAD_FILENAME_LENGTH:
        raise DatasetMetadataValidationError(
            f"文件名过长，最多支持 {MAX_UPLOAD_FILENAME_LENGTH} 个字符。"
        )


def validate_dataframe_columns(df: pd.DataFrame) -> None:
    if len(df.columns) > MAX_DATASET_COLUMNS:
        raise DatasetMetadataValidationError(
            f"文件包含过多列，最多支持 {MAX_DATASET_COLUMNS} 列。"
        )
    if any(len(str(column)) > MAX_COLUMN_NAME_LENGTH for column in df.columns):
        raise DatasetMetadataValidationError(
            f"列名过长，每个列名最多支持 {MAX_COLUMN_NAME_LENGTH} 个字符。"
        )


def parse_file(filepath: str) -> pd.DataFrame:
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        return pd.read_csv(filepath)
    elif ext == ".xlsx":
        return pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def extract_columns_info(df: pd.DataFrame) -> list[dict]:
    validate_dataframe_columns(df)
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
