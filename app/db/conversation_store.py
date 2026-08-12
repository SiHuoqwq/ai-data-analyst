import uuid
import os
from sqlalchemy.orm import selectinload
from app.db.database import SessionLocal
from app.db.models import ConversationModel, MessageModel, ChartModel


def create_conversation(file_id: str, title: str = "新对话") -> ConversationModel:
    db = SessionLocal()
    conv = ConversationModel(id=str(uuid.uuid4()), file_id=file_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.close()
    return conv


def save_message(conv_id: str, role: str, content: str, tool_calls: list | None = None, chart_ids: list | None = None) -> MessageModel:
    db = SessionLocal()
    msg = MessageModel(
        id=str(uuid.uuid4()), conv_id=conv_id, role=role,
        content=content, tool_calls=tool_calls, chart_ids=chart_ids or [],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    db.close()
    return msg


def save_chart(message_id: str, chart_type: str, title: str, filepath: str, config: dict | None = None) -> ChartModel:
    db = SessionLocal()
    try:
        chart = ChartModel(
            id=str(uuid.uuid4()), message_id=message_id,
            chart_type=chart_type, title=title, filepath=filepath, config=config or {},
        )
        db.add(chart)
        db.commit()
        db.refresh(chart)
        return chart
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_assistant_message_with_charts(
    conv_id: str,
    content: str,
    tool_calls: list | None = None,
    chart_paths: list[str] | None = None,
) -> MessageModel:
    """Persist the assistant message and its charts in one transaction."""
    db = SessionLocal()
    try:
        paths = chart_paths or []
        msg = MessageModel(
            id=str(uuid.uuid4()),
            conv_id=conv_id,
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            chart_ids=paths,
        )
        db.add(msg)
        db.flush()

        for filepath in paths:
            db.add(ChartModel(
                id=str(uuid.uuid4()),
                message_id=msg.id,
                chart_type="auto",
                title=os.path.basename(filepath),
                filepath=filepath,
                config={},
            ))

        db.commit()
        db.refresh(msg)
        return msg
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_conversation(conv_id: str) -> ConversationModel | None:
    db = SessionLocal()
    conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
    db.close()
    return conv


def get_conversation_for_file(conv_id: str, file_id: str) -> ConversationModel | None:
    db = SessionLocal()
    conv = (
        db.query(ConversationModel)
        .filter(ConversationModel.id == conv_id, ConversationModel.file_id == file_id)
        .first()
    )
    db.close()
    return conv


def get_conversations_for_file(file_id: str) -> list[ConversationModel]:
    db = SessionLocal()
    convs = (
        db.query(ConversationModel)
        .options(selectinload(ConversationModel.messages))
        .filter(ConversationModel.file_id == file_id)
        .order_by(ConversationModel.created_at.desc())
        .all()
    )
    db.close()
    return convs


def get_conversation_with_messages(conv_id: str) -> ConversationModel | None:
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    conv = (
        db.query(ConversationModel)
        .options(joinedload(ConversationModel.messages))
        .filter(ConversationModel.id == conv_id)
        .first()
    )
    db.close()
    return conv


def count_messages(conv_id: str) -> int:
    db = SessionLocal()
    count = db.query(MessageModel).filter(MessageModel.conv_id == conv_id).count()
    db.close()
    return count
