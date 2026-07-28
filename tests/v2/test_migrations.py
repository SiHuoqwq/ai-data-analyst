from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_upgrade_downgrade_upgrade_preserves_v1_and_creates_v2_tables(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    config = alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    expected_v1 = {"files", "conversations", "messages", "charts"}
    expected_v2 = {"analysis_runs", "run_steps", "artifacts", "run_events"}
    assert expected_v1 | expected_v2 <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []

    command.downgrade(config, "base")
    assert expected_v1 <= set(inspect(engine).get_table_names())
    assert expected_v2.isdisjoint(inspect(engine).get_table_names())

    command.upgrade(config, "head")
    assert expected_v1 | expected_v2 <= set(inspect(engine).get_table_names())
    engine.dispose()
