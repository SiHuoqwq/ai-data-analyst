import json as json_module
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.chat import ChatRequest
from app.services.agent import AgentController
from app.services.tools.statistics import set_df
from app.services.parser import parse_file
from app.db.database import SessionLocal
from app.db.models import FileModel
from app.db.conversation_store import (
    create_conversation,
    get_conversation,
    save_assistant_message_with_charts,
    save_message,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
logger = logging.getLogger(__name__)

agent = AgentController()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    # Load file into cache
    db = SessionLocal()
    file_record = db.query(FileModel).filter(FileModel.id == req.file_id).first()
    db.close()
    if not file_record:
        raise HTTPException(status_code=404, detail="文件不存在")

    df = parse_file(file_record.filepath)
    set_df(req.file_id, df)

    # Create or get conversation
    if req.conversation_id:
        conversation = get_conversation(req.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="对话不存在")
        if conversation.file_id != req.file_id:
            raise HTTPException(status_code=400, detail="对话不属于当前文件")
        conv_id = conversation.id
    else:
        conv_id = create_conversation(req.file_id).id

    # Save user message
    save_message(conv_id, "user", req.message)

    async def event_stream():
        collected_text = ""
        tool_calls_log = []
        chart_ids = []

        try:
            async for event_type, content in agent.run_stream(req.file_id, req.message):
                if event_type == "tool":
                    try:
                        parsed_calls = json_module.loads(content)
                        if isinstance(parsed_calls, list):
                            tool_calls_log.extend(parsed_calls)
                    except (json_module.JSONDecodeError, TypeError):
                        pass
                    yield f"data: {json_module.dumps({'type': 'tool', 'content': content}, ensure_ascii=False)}\n\n"
                elif event_type == "text":
                    collected_text += content
                    yield f"data: {json_module.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
                elif event_type == "tool_result" and "图表已生成:" in content:
                    for line in content.split("\n"):
                        if "图表已生成:" in line:
                            chart_path = line.split("图表已生成:")[-1].strip()
                            if chart_path not in chart_ids:
                                chart_ids.append(chart_path)
                                yield f"data: {json_module.dumps({'type': 'chart', 'path': chart_path}, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception("Analysis stream failed for conversation %s", conv_id)
            payload = {"type": "error", "message": "分析失败，请重试"}
            yield f"data: {json_module.dumps(payload, ensure_ascii=False)}\n\n"
            return

        save_assistant_message_with_charts(
            conv_id, collected_text,
            tool_calls=tool_calls_log or None,
            chart_paths=chart_ids,
        )
        yield f"data: {json_module.dumps({'type': 'done', 'conversation_id': conv_id, 'chart_paths': chart_ids}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
