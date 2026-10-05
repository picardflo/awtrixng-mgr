"""Migrations, run the way the application runs them.

A migration that passes from the Alembic CLI can still destroy data in the
container. `app/db/session.py` sets ``PRAGMA foreign_keys=ON`` on every
connection, and the CLI never imports that module — so the CLI runs with
foreign keys *off* and sees none of the cascades the real startup triggers.

That is exactly how awtrixhub's widget_target migration shipped broken: SQLite
rebuilds a table to drop a column, the DROP cascaded, and every row copied into
the new table vanished. Silently: no error, just widgets attached to no
display. The lesson is why these tests run through `init_db()`, the real entry
point, in a subprocess, rather than through the CLI.

**What is deliberately not tested here.** awtrixhub's suite upgraded a database
built at revision `1ff84f19f4ae`, or `6c75b7037ac0`, and checked the rows
survived. Those revisions do not exist in this project: it starts from one
initial migration, because replaying someone else's history — including the
day reminders gained centring and rainbow text, two options NG does not have —
would be ceremony rather than safety.

Those tests come back the first time this project migrates a schema of its
own, against a database someone is actually running.
"""

import sqlite3
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def run(data_dir: Path, *args: str) -> str:
    """Run a command with its own data directory, in a clean interpreter."""
    result = subprocess.run(
        args,
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin", "AWTRIXNG_DATA_DIR": str(data_dir)},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"{args}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def start_app(data_dir: Path) -> None:
    """Bring a database up the way the container does."""
    run(
        data_dir,
        str(BACKEND / ".venv/bin/python"),
        "-c",
        "from app.db.session import init_db; init_db()",
    )


def tables(data_dir: Path) -> set[str]:
    db = sqlite3.connect(data_dir / "awtrixng.db")
    try:
        rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        db.close()
    return {name for (name,) in rows}


def test_a_fresh_database_comes_up(tmp_path: Path):
    """The path every new installation takes, and the only one so far."""
    start_app(tmp_path)
    assert {"device", "connector", "widget", "widget_target", "reminder",
            "reminder_target", "setting"} <= tables(tmp_path)


def test_starting_twice_changes_nothing(tmp_path: Path):
    """`docker compose up -d` runs this on every restart."""
    start_app(tmp_path)
    before = tables(tmp_path)
    start_app(tmp_path)
    assert tables(tmp_path) == before


def test_foreign_keys_are_on_at_runtime(tmp_path: Path):
    """The pragma whose absence lost awtrixhub's widget targets.

    Checked through the application's own engine, not through a connection
    opened here: the point is that the setting is on where the migrations run.
    """
    start_app(tmp_path)
    out = run(
        tmp_path,
        str(BACKEND / ".venv/bin/python"),
        "-c",
        "from app.db.session import engine\n"
        "with engine.connect() as c:\n"
        "    print(c.exec_driver_sql('PRAGMA foreign_keys').scalar())",
    )
    assert out.strip().endswith("1")


def test_the_schema_matches_the_models(tmp_path: Path):
    """No model change without a migration to go with it.

    Autogenerate against the migrated database must find nothing left to do.
    A field added to a model and forgotten here is a column missing in
    production, found at the first write rather than at the first test.
    """
    start_app(tmp_path)
    out = run(
        tmp_path,
        str(BACKEND / ".venv/bin/python"),
        "-c",
        "import app.models  # noqa\n"
        "from alembic.autogenerate import compare_metadata\n"
        "from alembic.migration import MigrationContext\n"
        "from sqlmodel import SQLModel\n"
        "from app.db.session import engine\n"
        "with engine.connect() as c:\n"
        "    diff = compare_metadata(MigrationContext.configure(c), SQLModel.metadata)\n"
        "print(diff)",
    )
    assert out.strip().endswith("[]"), f"the models and the migration disagree: {out}"
