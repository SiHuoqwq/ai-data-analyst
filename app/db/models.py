import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.database import Base


class FileModel(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    row_count = Column(Integer, default=0)
    col_count = Column(Integer, default=0)
    columns_info = Column(JSON, default=list)
    profile_report = Column(Text, default="")
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversations = relationship("ConversationModel", back_populates="file", cascade="all, delete-orphan")


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    title = Column(String, default="新对话")
    mode = Column(String, default="agent")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    file = relationship("FileModel", back_populates="conversations")
    messages = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conv_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, default="")
    tool_calls = Column(JSON, default=None)
    chart_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversation = relationship("ConversationModel", back_populates="messages")
    charts = relationship("ChartModel", back_populates="message", cascade="all, delete-orphan")


class ChartModel(Base):
    __tablename__ = "charts"

    id = Column(String, primary_key=True)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    chart_type = Column(String, nullable=False)
    title = Column(String, default="")
    filepath = Column(String, nullable=False)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    message = relationship("MessageModel", back_populates="charts")
