import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import database
from app.config import Settings, settings
from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_health_exposes_only_public_fake_provider_status(monkeypatch):
    monkeypatch.setattr(settings, "v2_provider", "fake")

    with TestClient(app) as client:
        app.state.database_revision_status = None
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["provider"] == {
        "mode": "fake",
        "display_name": "Fake",
        "description": "确定性演示/测试模式",
    }
    serialized = response.text.lower()
    assert "api_key" not in serialized
    assert "base_url" not in serialized
    assert "prompt" not in serialized


def test_health_exposes_deepseek_or_unknown_provider_without_secrets(
    monkeypatch,
):
    with TestClient(app) as client:
        app.state.database_revision_status = None

        monkeypatch.setattr(settings, "v2_provider", "deepseek")
        deepseek = client.get("/health").json()["provider"]

        monkeypatch.setattr(settings, "v2_provider", "unconfigured-value")
        unknown = client.get("/health").json()["provider"]

    assert deepseek == {
        "mode": "deepseek",
        "display_name": "DeepSeek",
        "description": "真实模型模式",
    }
    assert unknown == {
        "mode": "unknown",
        "display_name": "Provider 未知",
        "description": "Provider 配置异常",
    }


def test_unmigrated_database_reports_clear_readiness_error(tmp_path):
    database_path = tmp_path / "unmigrated.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    original_database_url = str(database.engine.url)
    database.configure_database(database_url)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            health_response = client.get("/health")
            v2_response = client.get("/api/v2/runs/missing-run")

        assert health_response.status_code == 503
        assert health_response.json()["error"]["code"] == (
            "DATABASE_MIGRATION_REQUIRED"
        )
        assert v2_response.status_code == 503
        assert v2_response.json()["error"]["code"] == (
            "DATABASE_MIGRATION_REQUIRED"
        )

        with sqlite3.connect(database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert "alembic_version" not in tables
        assert "analysis_runs" not in tables
    finally:
        database.configure_database(original_database_url)


def test_explicit_migration_command_upgrades_disposable_database(tmp_path):
    database_path = tmp_path / "release-start.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = (
        f"sqlite:///{database_path.as_posix()}"
    )

    result = subprocess.run(
        [sys.executable, "-m", "app.migrate"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database migration completed" in result.stdout
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert revision == ("0001_minimal_v2",)
    assert {"analysis_runs", "run_steps", "artifacts", "run_events"} <= tables


def test_explicit_migration_uses_application_database_url(tmp_path):
    application_database = tmp_path / "application.db"
    stale_alembic_database = tmp_path / "stale-alembic.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = (
        f"sqlite:///{application_database.as_posix()}"
    )
    environment["ALEMBIC_DATABASE_URL"] = (
        f"sqlite:///{stale_alembic_database.as_posix()}"
    )

    result = subprocess.run(
        [sys.executable, "-m", "app.migrate"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with sqlite3.connect(application_database) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert revision == ("0001_minimal_v2",)
    assert not stale_alembic_database.exists()


def test_windows_start_script_gates_backend_on_migration_exit_code():
    content = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")
    normalized = content.lower()

    assert "py -m app.migrate" in normalized
    assert "if errorlevel 1" in normalized
    assert "migration failed" in normalized
    assert normalized.index("py -m app.migrate") < normalized.index(
        "py -m app.run"
    )


def test_example_environment_matches_frontend_v2_development_port():
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    vite_config = (PROJECT_ROOT / "frontend-v2" / "vite.config.ts").read_text(
        encoding="utf-8"
    )

    assert "FRONTEND_ORIGIN=http://localhost:5174" in content
    assert "V2_PROVIDER=fake" in content
    assert "port: 5174" in vite_config


def test_application_default_origin_matches_frontend_v2_port(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)

    defaults = Settings(_env_file=None)

    assert defaults.frontend_origin == "http://localhost:5174"
