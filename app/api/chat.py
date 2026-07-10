import json as json_module
import uuid
import os
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.models.chat import ChatRequest
from app.services.agent import AgentController
from app.services.tools.statistics import set_df
from app.services.parser import parse_file
from app.db.database import SessionLocal
from app.db.models import FileModel
from app.db.conversation_store import create_conversation, save_message, save_chart

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

agent = AgentController()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    # Load file into cache
    db = SessionLocal()
    file_record = db.query(FileModel).filter(FileModel.id == req.file_id).first()
    db.close()
    if not file_record:
        async def error_stream():
            yield f"data: {json_module.dumps({'error': '文件不存在'})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    df = parse_file(file_record.filepath)
    set_df(req.file_id, df)

    # Create or get conversation
    conv_id = req.conversation_id or create_conversation(req.file_id).id

    # Save user message
    save_message(conv_id, "user", req.message)

    async def event_stream():
        collected_text = ""
        tool_calls_log = []
        chart_ids = []

        async for event_type, content in agent.run_stream(req.file_id, req.message):
            if event_type == "tool":
                tool_calls_log.append(content)
                yield f"data: {json_module.dumps({'type': 'tool', 'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "text":
                collected_text += content
                yield f"data: {json_module.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "tool_result":
                if "图表已生成:" in content:
                    for line in content.split("\n"):
                        if "图表已生成:" in line:
                            chart_path = line.split("图表已生成:")[-1].strip()
                            chart_name = os.path.basename(chart_path)
                            save_chart(str(uuid.uuid4()), "auto", chart_name, chart_path)
                            chart_ids.append(chart_path)
                            yield f"data: {json_module.dumps({'type': 'chart', 'path': chart_path}, ensure_ascii=False)}\n\n"

        yield f"data: {json_module.dumps({'type': 'done', 'conversation_id': conv_id, 'chart_paths': chart_ids}, ensure_ascii=False)}\n\n"

        # Save assistant message
        save_message(
            conv_id, "assistant", collected_text,
            tool_calls=tool_calls_log if tool_calls_log else None,
            chart_ids=chart_ids if chart_ids else None,
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
