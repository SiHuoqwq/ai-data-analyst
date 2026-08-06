from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, create_engine, inspect, text


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
    expected_v2 = {
        "analysis_runs",
        "run_steps",
        "artifacts",
        "run_events",
        "dataset_recommendations",
    }
    assert expected_v1 | expected_v2 <= set(inspect(engine).get_table_names())
    recommendation_columns = {
        item["name"]: item for item in inspect(engine).get_columns("dataset_recommendations")
    }
    assert {
        "id",
        "dataset_version_id",
        "recommendations_json",
        "source",
        "provider_name",
        "provider_model",
        "created_at",
        "updated_at",
    } == set(recommendation_columns)
    assert inspect(engine).get_pk_constraint("dataset_recommendations")[
        "constrained_columns"
    ] == ["id"]
    for required_column in (
        "id",
        "dataset_version_id",
        "recommendations_json",
        "source",
        "created_at",
        "updated_at",
    ):
        assert not recommendation_columns[required_column]["nullable"]
    assert recommendation_columns["provider_name"]["nullable"]
    assert recommendation_columns["provider_model"]["nullable"]
    assert isinstance(recommendation_columns["created_at"]["type"], DateTime)
    assert isinstance(recommendation_columns["updated_at"]["type"], DateTime)
    recommendation_foreign_keys = inspect(engine).get_foreign_keys(
        "dataset_recommendations"
    )
    assert any(
        item["constrained_columns"] == ["dataset_version_id"]
        and item["referred_table"] == "files"
        and item.get("options", {}).get("ondelete") == "CASCADE"
        for item in recommendation_foreign_keys
    )
    assert any(
        item["column_names"] == ["dataset_version_id"]
        for item in inspect(engine).get_unique_constraints("dataset_recommendations")
    )
    assert any(
        "source IN ('model','template')" in item["sqltext"]
        for item in inspect(engine).get_check_constraints("dataset_recommendations")
    )
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []

    command.downgrade(config, "base")
    assert expected_v1 <= set(inspect(engine).get_table_names())
    assert expected_v2.isdisjoint(inspect(engine).get_table_names())

    command.upgrade(config, "head")
    assert expected_v1 | expected_v2 <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_alembic_database_url_environment_override(tmp_path, monkeypatch):
    target = tmp_path / "environment-override.db"
    database_url = f"sqlite:///{target.as_posix()}"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", database_url)
    config = alembic_config("sqlite:///Z:/path-that-must-not-be-used/app.db")

    command.upgrade(config, "head")

    assert target.is_file()
    assert "analysis_runs" in inspect(create_engine(database_url)).get_table_names()
