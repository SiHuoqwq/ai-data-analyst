from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    null_count: int = 0
    null_rate: float = 0.0
    unique_count: int = 0
    sample_values: list = []


class FileDetail(BaseModel):
    id: str
    filename: str
    file_type: str
    row_count: int
    col_count: int
    columns: list[ColumnInfo]
    profile_report: str = ""


class FileListItem(BaseModel):
    id: str
    filename: str
    file_type: str
    row_count: int
    col_count: int
    uploaded_at: str


class FilePreview(BaseModel):
    columns: list[str]
    rows: list[list]
    total_rows: int
