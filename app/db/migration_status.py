from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DatabaseRevisionStatus:
    current_revisions: tuple[str, ...]
    expected_revisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return (
            bool(self.expected_revisions)
            and self.current_revisions == self.expected_revisions
        )

    def public_details(self) -> dict[str, list[str]]:
        return {
            "current_revisions": list(self.current_revisions),
            "expected_revisions": list(self.expected_revisions),
        }


def inspect_database_revision(engine: Engine) -> DatabaseRevisionStatus:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "alembic"),
    )
    expected = tuple(sorted(ScriptDirectory.from_config(config).get_heads()))

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current = tuple(sorted(context.get_current_heads()))

    return DatabaseRevisionStatus(
        current_revisions=current,
        expected_revisions=expected,
    )
