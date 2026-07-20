from app.services.llm.factory import get_llm
from app.services.parser import parse_file
from app.services.profiler import generate_profile
from app.db.database import SessionLocal
from sqlalchemy.orm import joinedload

from app.db.models import ConversationModel, FileModel, MessageModel


class ReportSourceNotFoundError(Exception):
    pass


class ReportContextError(Exception):
    pass

REPORT_PROMPT = """你是一个专业的数据分析师。请根据以下信息生成一份数据分析报告。

## 数据概览
{profile}

## 分析对话历史
{history}

## 已生成图表
{charts}

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

严格要求：
- 只能使用以上数据画像、对话记录、工具调用和图表中明确存在的事实。
- 不得补造原始记录中没有出现的指标、数值、业务原因或因果关系。
- 如果证据不足，请明确写“现有分析记录不足以得出该结论”。
"""


async def generate_report(file_id: str, conversation_id: str | None = None) -> str:
    if not conversation_id:
        raise ReportContextError("生成报告必须指定对话")

    db = SessionLocal()
    try:
        file_record = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not file_record:
            raise ReportSourceNotFoundError("文件不存在")

        conversation = (
            db.query(ConversationModel)
            .filter(
                ConversationModel.id == conversation_id,
                ConversationModel.file_id == file_id,
            )
            .first()
        )
        if not conversation:
            raise ReportSourceNotFoundError("指定对话不存在或不属于当前文件")

        profile = file_record.profile_report or generate_profile(parse_file(file_record.filepath))
        messages = (
            db.query(MessageModel)
            .options(joinedload(MessageModel.charts))
            .filter(MessageModel.conv_id == conversation_id)
            .order_by(MessageModel.created_at)
            .all()
        )

        assistant_messages = [m for m in messages if m.role == "assistant" and (m.content or "").strip()]
        if not assistant_messages:
            raise ReportContextError("当前对话还没有可用于报告的分析结果")

        history_lines = []
        chart_lines = []
        for message in messages:
            role = "用户" if message.role == "user" else "助手"
            history_lines.append(f"**{role}**: {(message.content or '')[:2000]}")
            if message.tool_calls:
                history_lines.append(
                    f"**已执行工具调用**: {message.tool_calls}"
                )
            for chart in message.charts:
                chart_lines.append(
                    f"- {chart.title or chart.chart_type}: {chart.filepath}"
                )

        history = "\n\n".join(history_lines)
        charts = "\n".join(chart_lines) if chart_lines else "当前对话未生成图表"
    finally:
        db.close()

    llm = get_llm()
    prompt = REPORT_PROMPT.format(profile=profile, history=history, charts=charts)
    result = await llm.chat([{"role": "user", "content": prompt}])

    return result["content"]
