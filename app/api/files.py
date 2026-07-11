import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.parser import parse_file, extract_columns_info
from app.services.profiler import generate_profile
from app.config import settings
from app.db.database import SessionLocal
from app.db.models import FileModel
from app.models.file import FileDetail, FileListItem, FilePreview, ColumnInfo

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", response_model=FileDetail)
async def upload_file(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(400, f"不支持的文件格式: .{ext}")

    file_id = str(uuid.uuid4())
    filepath = f"{settings.upload_dir}/{file_id}.{ext}"

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    df = parse_file(filepath)
    columns_info = extract_columns_info(df)
    profile = generate_profile(df)

    db = SessionLocal()
    record = FileModel(
        id=file_id, filename=file.filename, filepath=filepath,
        file_type=ext, row_count=len(df), col_count=len(df.columns),
        columns_info=columns_info, profile_report=profile,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    columns = [ColumnInfo(**c) for c in columns_info]

    result = FileDetail(
        id=record.id, filename=record.filename, file_type=record.file_type,
        row_count=record.row_count, col_count=record.col_count,
        columns=columns, profile_report=record.profile_report,
    )
    db.close()
    return result


@router.get("", response_model=list[FileListItem])
def list_files():
    db = SessionLocal()
    records = db.query(FileModel).order_by(FileModel.uploaded_at.desc()).all()
    result = [
        FileListItem(
            id=r.id, filename=r.filename, file_type=r.file_type,
            row_count=r.row_count, col_count=r.col_count,
            uploaded_at=r.uploaded_at.isoformat() if r.uploaded_at else "",
        )
        for r in records
    ]
    db.close()
    return result


@router.get("/{file_id}", response_model=FileDetail)
def get_file(file_id: str):
    db = SessionLocal()
    record = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not record:
        db.close()
        raise HTTPException(404, "文件不存在")
    columns = [ColumnInfo(**c) for c in (record.columns_info or [])]
    result = FileDetail(
        id=record.id, filename=record.filename, file_type=record.file_type,
        row_count=record.row_count, col_count=record.col_count,
        columns=columns, profile_report=record.profile_report or "",
    )
    db.close()
    return result


@router.get("/{file_id}/preview", response_model=FilePreview)
def preview_file(file_id: str, rows: int = 20):
    db = SessionLocal()
    record = db.query(FileModel).filter(FileModel.id == file_id).first()
    db.close()
    if not record:
        raise HTTPException(404, "文件不存在")

    df = parse_file(record.filepath)
    preview_df = df.head(rows)
    return FilePreview(
        columns=list(df.columns),
        rows=preview_df.fillna("").values.tolist(),
        total_rows=len(df),
    )


@router.delete("/{file_id}")
def delete_file(file_id: str):
    import os
    db = SessionLocal()
    record = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not record:
        db.close()
        raise HTTPException(404, "文件不存在")

    if os.path.exists(record.filepath):
        os.remove(record.filepath)

    db.delete(record)
    db.commit()
    db.close()
    return {"ok": True}
