from fastapi import APIRouter, HTTPException
from app.db.conversation_store import (
    get_conversations_for_file,
    get_conversation_with_messages,
)
from app.models.chat import ConversationItem, ConversationDetail, MessageItem

router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.get("/files/{file_id}/conversations", response_model=list[ConversationItem])
def list_conversations(file_id: str):
    convs = get_conversations_for_file(file_id)
    return [
        ConversationItem(
            id=c.id,
            file_id=c.file_id,
            title=c.title,
            mode=c.mode,
            created_at=c.created_at,
            message_count=len(c.messages),
            user_questions=[
                message.content
                for message in sorted(
                    c.messages,
                    key=lambda item: (item.created_at, item.id),
                )
                if message.role == "user"
            ],
        )
        for c in convs
    ]


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str):
    conv = get_conversation_with_messages(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(
        id=conv.id,
        file_id=conv.file_id,
        title=conv.title,
        mode=conv.mode,
        created_at=conv.created_at,
        messages=[
            MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                chart_ids=m.chart_ids,
                created_at=m.created_at,
            )
            for m in conv.messages
        ],
    )
