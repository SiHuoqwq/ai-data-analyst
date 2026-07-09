from app.services.llm.factory import get_llm
from app.services.parser import parse_file
from app.services.profiler import generate_profile
from app.db.database import SessionLocal
from app.db.models import FileModel, MessageModel

REPORT_PROMPT = """你是一个专业的数据分析师。请根据以下信息生成一份数据分析报告。

## 数据概览
{profile}

## 分析对话历史
{history}

请按以下结构生成报告（Markdown格式）：

# 数据分析报告

## 1. 数据概览
简要描述数据规模、字段

## 2. 关键发现
列出3-5个核心洞察，用数据支撑

## 3. 数据质量
指出缺失值、异常值等质量问题

## 4. 建议
基于分析结果，给出2-3条可行建议
"""


async def generate_report(file_id: str, conversation_id: str | None = None) -> str:
    db = SessionLocal()
    file_record = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_record:
        db.close()
        return "文件不存在"

    profile = file_record.profile_report or generate_profile(parse_file(file_record.filepath))

    history = "无对话记录"
    if conversation_id:
        messages = (
            db.query(MessageModel)
            .filter(MessageModel.conv_id == conversation_id)
            .order_by(MessageModel.created_at)
            .all()
        )
        if messages:
            lines = []
            for m in messages:
                role = "用户" if m.role == "user" else "助手"
                content = (m.content or "")[:500]
                lines.append(f"**{role}**: {content}")
            history = "\n\n".join(lines)

    db.close()

    llm = get_llm()
    prompt = REPORT_PROMPT.format(profile=profile, history=history)
    result = await llm.chat([{"role": "user", "content": prompt}])

    return result["content"]
