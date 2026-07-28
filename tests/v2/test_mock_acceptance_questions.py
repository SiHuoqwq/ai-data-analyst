from pathlib import Path

from app.db import database
from app.db.models import FileModel, MessageModel
from app.v2.db.models import AnalysisRunModel, ArtifactModel
from app.v2.services.executor import AnalysisExecutor
from app.v2.services.provider import ProviderError, ProviderPlan, ProviderStep
from app.v2.services.runs import AnalysisRunService


class AcceptanceProvider:
    name = "mock"
    model = "deterministic-acceptance"

    def __init__(self, plan: ProviderPlan):
        self.plan = plan

    def set_history(self, _history):
        return None

    def before_step(self):
        return None

    def build_plan(self, _question, _file_record):
        return self.plan

    def build_conclusion(self, _question, _file_record, registry):
        aliases = registry.create_alias_map(registry.items[:4])
        self.last_conclusion_aliases = aliases
        raise ProviderError(
            "UNGROUNDED_ANSWER",
            "分析服务返回的结论无法由本次结构化证据验证",
            retryable=False,
            details={
                "answer_warnings": [
                    "STRUCTURED_CONCLUSION_REJECTED",
                    "STRUCTURED_CONCLUSION_REPAIR_FAILED",
                ],
                "conclusion_diagnostics": [
                    {
                        "phase": "initial",
                        "error_types": ["INVALID_JSON"],
                        "field_paths": [],
                        "error_count": 1,
                        "unknown_reference_count": 0,
                        "narrative_number_token_count": 0,
                        "response_length": 8,
                        "response_sha256": "a" * 64,
                    },
                    {
                        "phase": "repair",
                        "error_types": [
                            "INVALID_JSON",
                            "RESPONSE_REPAIR_FAILED",
                        ],
                        "field_paths": [],
                        "error_count": 1,
                        "unknown_reference_count": 0,
                        "narrative_number_token_count": 0,
                        "response_length": 8,
                        "response_sha256": "b" * 64,
                    },
                ],
            },
        )


def metric(field, aggregation, alias):
    return {
        "field": field,
        "aggregation": aggregation,
        "alias": alias,
    }


def test_mock_first_and_second_acceptance_questions_complete(v2_runtime):
    csv_path = Path(v2_runtime["database_path"]).with_name("courses.csv")
    csv_path.write_text(
        "课程类别,课程难度,购买渠道,主要学习设备,完成率,是否退款,课程评分,报名日期,实付金额\n"
        "AI应用,高级,短视频平台,Android,0.4,否,4.2,2025-01-03,199\n"
        "AI应用,高级,短视频平台,Android,0.6,是,4.0,2025-02-03,159\n"
        "数据分析,初级,官网,Windows,0.8,否,4.8,2025-01-12,299\n"
        "数据分析,初级,官网,Windows,0.7,否,,2025-02-12,269\n",
        encoding="utf-8",
    )
    session = database.SessionLocal()
    file_record = session.get(FileModel, "file-1")
    file_record.filepath = str(csv_path)
    file_record.filename = "courses.csv"
    file_record.row_count = 4
    file_record.col_count = 9
    session.commit()
    session.close()

    first_plan = ProviderPlan(
        goal="分析课程组合表现",
        steps=(
            ProviderStep("inspect", "inspect_dataset", "检查字段", {}),
            ProviderStep(
                "aggregate",
                "group_aggregate",
                "汇总课程组合",
                {
                    "group_by": ["课程类别", "课程难度", "购买渠道", "主要学习设备"],
                    "metrics": [
                        metric(None, "count", "报名人数"),
                        metric("完成率", "rate", "平均完成率"),
                        metric("是否退款", "rate", "退款率"),
                        metric("课程评分", "mean", "平均课程评分"),
                    ],
                    "filters": [],
                    "sort": [{"field": "报名人数", "direction": "desc"}],
                    "limit": 20,
                },
            ),
            ProviderStep(
                "chart",
                "create_chart",
                "绘制课程组合图",
                {
                    "source_step_id": "aggregate",
                    "chart_type": "bar",
                    "x_field": "课程类别",
                    "y_fields": ["报名人数", "平均完成率", "退款率", "平均课程评分"],
                    "color_field": None,
                    "title": "课程组合表现",
                    "limit": 20,
                },
            ),
        ),
    )
    second_plan = ProviderPlan(
        goal="分析月度趋势",
        steps=(
            ProviderStep("inspect", "inspect_dataset", "检查字段", {}),
            ProviderStep(
                "trend",
                "monthly_trend",
                "汇总月度趋势",
                {
                    "date_field": "报名日期",
                    "category_field": "课程类别",
                    "metrics": [
                        metric(None, "count", "报名人数"),
                        metric("实付金额", "sum", "实付金额"),
                        metric("完成率", "rate", "平均完成率"),
                    ],
                    "filters": [],
                    "limit": 100,
                },
            ),
            ProviderStep(
                "chart",
                "create_chart",
                "绘制月度趋势",
                {
                    "source_step_id": "trend",
                    "chart_type": "line",
                    "x_field": "月份",
                    "y_fields": ["报名人数", "实付金额", "平均完成率"],
                    "color_field": "课程类别",
                    "title": "课程月度趋势",
                    "limit": 50,
                },
            ),
        ),
    )

    run_service = AnalysisRunService()
    first = run_service.create_run(
        "conversation-1", "file-1", "分析课程组合表现", "mock-question-one"
    )
    AnalysisExecutor(AcceptanceProvider(first_plan)).execute(first.id)
    second = run_service.create_run(
        "conversation-1", "file-1", "分析课程月度趋势", "mock-question-two"
    )
    AnalysisExecutor(AcceptanceProvider(second_plan)).execute(second.id)

    session = database.SessionLocal()
    runs = [session.get(AnalysisRunModel, item.id) for item in (first, second)]
    assert [item.status for item in runs] == ["completed", "completed"], [
        item.failure_json for item in runs
    ]
    assert all(item.answer_message_id for item in runs)
    messages = (
        session.query(MessageModel)
        .filter_by(conv_id="conversation-1")
        .order_by(MessageModel.created_at, MessageModel.id)
        .all()
    )
    assert [item.role for item in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    for run in runs:
        artifacts = (
            session.query(ArtifactModel).filter_by(run_id=run.id).all()
        )
        assert {item.artifact_type for item in artifacts} >= {
            "table",
            "chart",
            "text",
        }
        assert sum(item.artifact_type == "chart" for item in artifacts) == 3
        answer_artifact = next(
            item
            for item in artifacts
            if item.artifact_type == "text" and item.title == "分析结论"
        )
        assert (
            answer_artifact.payload_json["answer_mode"]
            == "deterministic_fallback"
        )
        assert "## 关键结果" in answer_artifact.payload_json["content"]

    first_answer = session.get(MessageModel, runs[0].answer_message_id)
    second_answer = session.get(MessageModel, runs[1].answer_message_id)
    assert "50.00%" in first_answer.content
    assert "¥299.00" in second_answer.content
    assert "2025-01" in second_answer.content
    assert "2025-02" in second_answer.content
    session.close()
