from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.config import settings
from app.db import database
from app.db.models import ConversationModel, FileModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def v2_runtime(tmp_path, monkeypatch):
    database_path = tmp_path / "v2-runtime.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    original_database_url = str(database.engine.url)
    original_chart_dir = settings.chart_dir
    database.configure_database(database_url)

    chart_dir = tmp_path / "charts"
    chart_dir.mkdir()
    monkeypatch.setattr(settings, "chart_dir", str(chart_dir))

    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "category,sales\nA,100\nB,200\nA,150\n",
        encoding="utf-8",
    )

    session = database.SessionLocal()
    session.add(
        FileModel(
            id="file-1",
            filename="sales.csv",
            filepath=str(csv_path),
            file_type="csv",
            row_count=3,
            col_count=2,
            columns_info=[],
            profile_report="",
        )
    )
    session.add(
        ConversationModel(
            id="conversation-1",
            file_id="file-1",
            title="销售分析",
        )
    )
    session.commit()
    session.close()

    yield {
        "database_url": database_url,
        "database_path": database_path,
        "chart_dir": chart_dir,
    }

    database.configure_database(original_database_url)
    settings.chart_dir = original_chart_dir
