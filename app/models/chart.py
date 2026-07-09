from pydantic import BaseModel


class ChartInfo(BaseModel):
    id: str
    chart_type: str
    title: str
    filepath: str
    config: dict = {}
