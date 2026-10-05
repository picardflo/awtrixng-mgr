"""Database access. SQLite in WAL mode (ADR-002)."""

import logging
import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.core.config import get_settings
from app.core.errors import AwtrixNgError

log = logging.getLogger(__name__)

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:
    """WAL so API reads do not block scheduler writes; foreign_keys because
    SQLite does not enforce them by default."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def check_data_dir() -> None:
    """Check that the data directory is usable.

    Without this, a plain permission problem surfaces as five screens of
    SQLAlchemy traceback ending in "unable to open database file", which does
    not say what to do about it. The case is common under Docker: /data is a
    bind mount whose ownership comes from the host.
    """
    directory = _settings.data_dir
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AwtrixNgError(
            f"Cannot create the data directory {directory}: {exc}",
            code="data_dir.not_creatable",
            params={"path": str(directory), "reason": str(exc)},
        ) from exc

    if not os.access(directory, os.W_OK | os.X_OK):
        raise AwtrixNgError(
            f"The data directory {directory} is not writable (uid "
            f"{os.geteuid()}). Under Docker this is the volume mounted on "
            f"/data: check its ownership on the host.",
            code="data_dir.not_writable",
            params={"path": str(directory), "uid": os.geteuid()},
        )


def init_db() -> None:
    """Bring the database up to the latest schema.

    Migrations run at application startup: a `git pull` followed by
    `docker compose up -d` is enough to upgrade a deployment without losing the
    configuration (§30.13).
    """
    check_data_dir()

    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", _settings.database_url)
    command.upgrade(config, "head")

    # The display language is read once here rather than per widget: a
    # projection runs far from a session, and opening one to learn a
    # two-letter code would be absurd.
    from sqlmodel import Session

    from app.api.routes.settings import load_into_memory

    with Session(engine) as session:
        load_into_memory(session)
    log.info("database ready at %s", _settings.database_url)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
