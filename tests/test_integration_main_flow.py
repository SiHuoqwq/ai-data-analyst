import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api import chat as chat_api
from app.config import settings
from app.db import database
from app.db.conversation_store import save_chart
from app.db.models import ChartModel, ConversationModel, FileModel, MessageModel
from app.main import app
from app.services.agent import AgentController
from app.services import parser, profiler, report_generator


class FakeAnalysisLLM:
    def __init__(self, file_id: str):
        self.file_id = file_id
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "tool-call-1",
                    "name": "draw_bar_chart",
                    "args": {
                        "file_id": self.file_id,
                        "x_column": "category",
                        "y_column": "sales",
                        "title": "类别平均销售额",
                    },
                }],
            }
        return {
            "content": "分析完成：B 类别的平均销售额最高，为 200。",
            "tool_calls": None,
        }


class FakeReportLLM:
    def __init__(self):
        self.prompt = ""

    async def chat(self, messages, tools=None):
        self.prompt = messages[-1]["content"]
        return {"content": "# 测试报告\n\n仅基于指定对话生成。", "tool_calls": None}


def parse_sse(response) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    original_database_url = str(database.engine.url)
    original_upload_dir = settings.upload_dir
    original_chart_dir = settings.chart_dir

    upload_dir = tmp_path / "uploads"
    chart_dir = tmp_path / "charts"
    upload_dir.mkdir()
    chart_dir.mkdir()

    database_url = f"sqlite:///{(tmp_path / 'integration.db').as_posix()}"
    database.configure_database(database_url)
    database.init_db()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "chart_dir", str(chart_dir))

    yield

    database.configure_database(original_database_url)
    settings.upload_dir = original_upload_dir
    settings.chart_dir = original_chart_dir


def upload_sample_csv(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/files/upload",
        files={
            "file": (
                "sales.csv",
                b"category,sales\nA,100\nB,200\nA,150\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200
    return response.json()


def test_main_analysis_flow_persists_real_message_chart_and_report_context(
    isolated_runtime,
    monkeypatch,
):
    with TestClient(app) as client:
        uploaded = upload_sample_csv(client)
        assert uploaded["row_count"] == 3
        assert "# 数据质量报告" in uploaded["profile_report"]

        fake_analysis_llm = FakeAnalysisLLM(uploaded["id"])
        fake_agent = AgentController()
        fake_agent.llm = fake_analysis_llm
        monkeypatch.setattr(chat_api, "agent", fake_agent)

        chat_response = client.post(
            "/api/v1/chat/stream",
            json={"file_id": uploaded["id"], "message": "按类别画销售额柱状图"},
        )
        assert chat_response.status_code == 200
        events = parse_sse(chat_response)
        assert [event["type"] for event in events] == ["tool", "chart", "text", "done"]

        done_event = events[-1]
        conversation_id = done_event["conversation_id"]
        assert len(done_event["chart_paths"]) == 1

        db = database.SessionLocal()
        try:
            file_record = db.query(FileModel).filter_by(id=uploaded["id"]).one()
            conversation = db.query(ConversationModel).filter_by(id=conversation_id).one()
            messages = (
                db.query(MessageModel)
                .filter_by(conv_id=conversation_id)
                .order_by(MessageModel.created_at)
                .all()
            )
            chart = db.query(ChartModel).one()
            assistant_message = next(message for message in messages if message.role == "assistant")

            assert file_record.profile_report
            assert conversation.file_id == uploaded["id"]
            assert [message.role for message in messages] == ["user", "assistant"]
            assert assistant_message.tool_calls[0]["name"] == "draw_bar_chart"
            assert chart.message_id == assistant_message.id
            assert chart.filepath in assistant_message.chart_ids
            assert Path(chart.filepath).exists()
            orphan_count = (
                db.query(ChartModel)
                .outerjoin(MessageModel, ChartModel.message_id == MessageModel.id)
                .filter(MessageModel.id.is_(None))
                .count()
            )
            assert orphan_count == 0
        finally:
            db.close()

        history_response = client.get(f"/api/v1/conversations/{conversation_id}")
        assert history_response.status_code == 200
        assert len(history_response.json()["messages"]) == 2

        fake_report_llm = FakeReportLLM()
        monkeypatch.setattr(report_generator, "get_llm", lambda: fake_report_llm)
        report_response = client.post(
            "/api/v1/report/generate",
            json={"file_id": uploaded["id"], "conversation_id": conversation_id},
        )
        assert report_response.status_code == 200
        assert report_response.json()["report"].startswith("# 测试报告")
        assert "分析完成：B 类别的平均销售额最高" in fake_report_llm.prompt
        assert "draw_bar_chart" in fake_report_llm.prompt
        assert done_event["chart_paths"][0] in fake_report_llm.prompt


def test_xls_upload_is_rejected_with_clear_error(isolated_runtime):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("legacy.xls", b"not-an-xls", "application/vnd.ms-excel")},
        )

    assert response.status_code == 400
    assert "不支持的文件格式" in response.json()["detail"]


def test_upload_rejects_overlong_filename_without_echoing_it(isolated_runtime):
    filename = f"{'x' * 252}.csv"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/files/upload",
            files={"file": (filename, b"value\n1\n", "text/csv")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "文件名过长，最多支持 255 个字符。"
    assert filename not in response.text
    assert list(Path(settings.upload_dir).iterdir()) == []


def test_upload_rejects_more_than_one_thousand_columns(isolated_runtime):
    columns = [f"column_{index}" for index in range(1_001)]
    content = f"{','.join(columns)}\n{','.join('1' for _ in columns)}\n".encode()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("wide.csv", content, "text/csv")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "文件包含过多列，最多支持 1000 列。"
    assert "column_1000" not in response.text
    assert list(Path(settings.upload_dir).iterdir()) == []


def test_upload_rejects_overlong_column_name_without_echoing_it(isolated_runtime):
    column_name = "sensitive-" + ("x" * 246)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/files/upload",
            files={
                "file": (
                    "long-column.csv",
                    f"{column_name}\n1\n".encode(),
                    "text/csv",
                )
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "列名过长，每个列名最多支持 255 个字符。"
    assert column_name not in response.text
    assert list(Path(settings.upload_dir).iterdir()) == []


@pytest.mark.parametrize(
    ("columns", "expected_message"),
    [
        ([f"column_{index}" for index in range(1_001)], "文件包含过多列"),
        (["x" * 256], "列名过长"),
    ],
)
@pytest.mark.parametrize(
    "entrypoint",
    [parser.extract_columns_info, profiler.generate_profile],
)
def test_column_metadata_entrypoints_enforce_the_same_bounded_profile(
    columns,
    expected_message,
    entrypoint,
):
    dataframe = pd.DataFrame(columns=columns)

    with pytest.raises(ValueError, match=expected_message):
        entrypoint(dataframe)


def test_sqlite_foreign_keys_reject_orphan_chart(isolated_runtime):
    db = database.SessionLocal()
    try:
        assert db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        db.close()

    with pytest.raises(IntegrityError):
        save_chart("missing-message", "bar", "orphan", "missing.png")


def test_report_requires_analysis_in_the_specified_conversation(
    isolated_runtime,
):
    with TestClient(app) as client:
        uploaded = upload_sample_csv(client)
        other_file = client.post(
            "/api/v1/files/upload",
            files={"file": ("other.csv", b"x,y\n1,2\n", "text/csv")},
        ).json()

        db = database.SessionLocal()
        try:
            conversation = ConversationModel(id="other-conversation", file_id=other_file["id"])
            db.add(conversation)
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/v1/report/generate",
            json={
                "file_id": uploaded["id"],
                "conversation_id": "other-conversation",
            },
        )

    assert response.status_code == 404
    assert "不属于当前文件" in response.json()["detail"]


def test_sse_returns_typed_error_event(isolated_runtime, monkeypatch):
    class FailingAgent:
        async def run_stream(self, file_id, message):
            raise RuntimeError("controlled failure")
            yield

    with TestClient(app) as client:
        uploaded = upload_sample_csv(client)
        monkeypatch.setattr(chat_api, "agent", FailingAgent())
        response = client.post(
            "/api/v1/chat/stream",
            json={"file_id": uploaded["id"], "message": "触发错误"},
        )

    assert response.status_code == 200
    assert parse_sse(response) == [{"type": "error", "message": "分析失败，请重试"}]
