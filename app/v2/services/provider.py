import time
from dataclasses import dataclass
from typing import Protocol

from app.db.models import FileModel


@dataclass(frozen=True)
class ProviderStep:
    step_id: str
    operation: str
    display_name: str


@dataclass(frozen=True)
class ProviderPlan:
    goal: str
    steps: tuple[ProviderStep, ...]


class AnalysisProvider(Protocol):
    name: str
    model: str

    def build_plan(self, question: str, file_record: FileModel) -> ProviderPlan: ...

    def before_step(self) -> None: ...

    def build_answer(
        self,
        question: str,
        file_record: FileModel,
        artifact_ids: list[str],
    ) -> str: ...


class FakeAnalysisProvider:
    name = "fake"
    model = "deterministic-v1"

    def __init__(self, step_delay_seconds: float = 0):
        self.step_delay_seconds = step_delay_seconds

    def build_plan(self, question: str, file_record: FileModel) -> ProviderPlan:
        if question == "[fake:fail]":
            raise RuntimeError("controlled fake provider failure")
        return ProviderPlan(
            goal=f"检查 {file_record.filename} 并生成可验证的数据摘要",
            steps=(
                ProviderStep("inspect_dataset", "inspect_dataset", "检查数据概况"),
                ProviderStep("create_chart", "create_visualization", "生成概览图表"),
            ),
        )

    def before_step(self) -> None:
        if self.step_delay_seconds:
            time.sleep(self.step_delay_seconds)

    def build_answer(
        self,
        question: str,
        file_record: FileModel,
        artifact_ids: list[str],
    ) -> str:
        references = "、".join(f"`{artifact_id}`" for artifact_id in artifact_ids)
        return (
            f"已完成对 **{file_record.filename}** 的确定性数据概览。"
            f"结论与展示内容来自结构化产物：{references}。"
        )
