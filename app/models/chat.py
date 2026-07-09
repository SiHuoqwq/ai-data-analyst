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
