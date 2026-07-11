from datetime import datetime
from pydantic import BaseModel


class ChatRequest(BaseModel):
    file_id: str
    message: str
    conversation_id: str | None = None


class ToolCallInfo(BaseModel):
    name: str
    args: dict
    result: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    tool_calls: list[ToolCallInfo] = []
    chart_ids: list[str] = []


# --- Conversation History Schemas ---

class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: list | None = None
    chart_ids: list | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationItem(BaseModel):
    id: str
    file_id: str
    title: str
    mode: str
    created_at: datetime
    message_count: int

    class Config:
        from_attributes = True


class ConversationDetail(BaseModel):
    id: str
    file_id: str
    title: str
    mode: str
    created_at: datetime
    messages: list[MessageItem]

    class Config:
        from_attributes = True
