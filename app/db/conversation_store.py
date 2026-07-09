import uuid
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
    chart = ChartModel(
        id=str(uuid.uuid4()), message_id=message_id,
        chart_type=chart_type, title=title, filepath=filepath, config=config or {},
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    db.close()
    return chart


def get_conversation(conv_id: str) -> ConversationModel | None:
    db = SessionLocal()
    conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
    db.close()
    return conv
