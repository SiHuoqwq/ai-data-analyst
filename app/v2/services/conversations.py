import uuid

from app.db.database import SessionLocal
from app.db.models import ConversationModel, FileModel
from app.v2.db.models import as_utc, utc_now


class ConversationServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ConversationService:
    def create(self, file_id: str, title: str | None = None) -> dict:
        session = SessionLocal()
        try:
            if not session.get(FileModel, file_id):
                raise ConversationServiceError(
                    "DATASET_NOT_FOUND", "数据集不存在", 404
                )
            created_at = utc_now()
            conversation = ConversationModel(
                id=str(uuid.uuid4()),
                file_id=file_id,
                title=title or "新分析",
                mode="agent",
                created_at=created_at,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return {
                "id": conversation.id,
                "file_id": conversation.file_id,
                "title": conversation.title,
                "mode": conversation.mode,
                "created_at": as_utc(conversation.created_at),
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
