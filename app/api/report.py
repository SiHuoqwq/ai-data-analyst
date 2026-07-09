from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.report_generator import generate_report

router = APIRouter(prefix="/api/v1/report", tags=["report"])


class ReportRequest(BaseModel):
    file_id: str
    conversation_id: str | None = None


@router.post("/generate")
async def generate(req: ReportRequest):
    try:
        report = await generate_report(req.file_id, req.conversation_id)
        return {"report": report}
    except Exception as e:
        raise HTTPException(500, f"生成报告失败: {str(e)}")
