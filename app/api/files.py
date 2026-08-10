import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.parser import (
    DatasetMetadataValidationError,
    extract_columns_info,
    parse_file,
    validate_upload_filename,
)
from app.services.profiler import generate_profile
from app.config import settings
from app.db.database import SessionLocal
from app.db.models import ChartModel, ConversationModel, FileModel, MessageModel
from app.models.file import FileDetail, FileListItem, FilePreview, ColumnInfo

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", response_model=FileDetail)
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename or ""
    try:
        validate_upload_filename(filename)
    except DatasetMetadataValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx"):
        raise HTTPException(400, f"不支持的文件格式: .{ext}")

    file_id = str(uuid.uuid4())
    filepath = f"{settings.upload_dir}/{file_id}.{ext}"

    try:
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        df = parse_file(filepath)
        columns_info = extract_columns_info(df)
        profile = generate_profile(df)
    except DatasetMetadataValidationError as exc:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(422, f"文件解析失败: {exc}") from exc

    db = SessionLocal()
    record = FileModel(
        id=file_id, filename=filename, filepath=filepath,
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
    db = SessionLocal()
    record = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not record:
        db.close()
        raise HTTPException(404, "文件不存在")

    chart_paths = [
        filepath
        for (filepath,) in (
            db.query(ChartModel.filepath)
            .join(MessageModel, ChartModel.message_id == MessageModel.id)
            .join(ConversationModel, MessageModel.conv_id == ConversationModel.id)
            .filter(ConversationModel.file_id == file_id)
            .all()
        )
    ]
    uploaded_path = record.filepath

    db.delete(record)
    db.commit()
    db.close()

    # Database relations are removed first. Any failed filesystem cleanup leaves
    # a harmless unreferenced file rather than a database row pointing to no file.
    for path in [uploaded_path, *chart_paths]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return {"ok": True}
