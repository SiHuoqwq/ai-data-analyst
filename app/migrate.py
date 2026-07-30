import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def upgrade_database(database_url: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", database_url)
    previous_override = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous_override is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous_override


def main() -> int:
    print("[1/2] Applying database migrations (alembic upgrade head)...")
    try:
        upgrade_database(settings.database_url)
    except Exception as exc:
        print(
            f"Migration failed ({type(exc).__name__}). "
            "The backend was not started.",
            file=sys.stderr,
        )
        return 1
    print("Database migration completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
