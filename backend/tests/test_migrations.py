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

The history-walking tests this file once said it did not need are now here:
`30ca1cb373ca` alters a table that a running installation already has rows in,
which is exactly the case the note said would bring them back.
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


# ---------------------------------------------------------------------------
# 6976918846d4 -> 30ca1cb373ca : quiet hours replace bedroom mode
# ---------------------------------------------------------------------------
#
# The migration drops six columns from `device`. SQLite cannot drop a column
# without rebuilding the table, and the rebuild drops the old one — which,
# with foreign keys on, cascades into `widget_target` and `reminder_target`.
# Both reference `device.id` with ON DELETE CASCADE.
#
# These tests exist because that is not a theory: it is how awtrixhub lost
# every widget target once, silently.

BEFORE_QUIET = "6976918846d4"


@pytest.fixture
def populated(tmp_path: Path) -> Path:
    """A database at the revision before the split, with rows worth losing."""
    run(tmp_path, str(BACKEND / ".venv/bin/alembic"), "upgrade", BEFORE_QUIET)

    db = sqlite3.connect(tmp_path / "awtrixng.db")
    db.executescript(
        """
        INSERT INTO device (id,name,host,port,enabled,status,night_mode,night_from,
                            night_to,night_brightness,night_active,created_at,updated_at)
          VALUES (1,'Bureau','awtrix-cl2',80,1,'HEALTHY',1,'22:00:00','07:00:00',
                  1,0,'2026-10-05','2026-10-05'),
                 (2,'Salon','awtrix-cl1',80,1,'HEALTHY',0,NULL,NULL,
                  1,0,'2026-10-05','2026-10-05');
        INSERT INTO connector (id,type,name,config,secrets,enabled,status,
                               consecutive_failures,created_at,updated_at)
          VALUES (1,'weather','Meteo','{}','{}',1,'HEALTHY',0,'2026-10-05','2026-10-05');
        INSERT INTO widget (id,name,connector_id,widget_type,config,display,
                            refresh_seconds,enabled,position,status,
                            consecutive_failures,created_at,updated_at)
          VALUES (1,'Meteo actuelle',1,'weather.current','{}','{}',600,1,0,'HEALTHY',
                  0,'2026-10-05','2026-10-05');
        INSERT INTO widget_target (widget_id,device_id,status,consecutive_failures)
          VALUES (1,1,'HEALTHY',0), (1,2,'HEALTHY',0);
        INSERT INTO reminder (id,name,message,at,every_weeks,weekdays,duration_seconds,
                              scroll_mode,scroll_speed,repeat_count,repeat_every_minutes,
                              rings_at_night,enabled,created_at,updated_at)
          VALUES (1,'Poubelles','SORTIR','19:00:00',1,'0,1,2,3,4',10,'wrap',100,0,2,
                  0,1,'2026-10-05','2026-10-05');
        INSERT INTO reminder_target (reminder_id,device_id) VALUES (1,1);
        """
    )
    db.commit()
    db.close()
    return tmp_path


def rows(data_dir: Path, sql: str) -> list[tuple]:
    db = sqlite3.connect(data_dir / "awtrixng.db")
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_the_window_is_carried_over(populated: Path):
    """The half that survives the split must survive the migration too.

    Read back through the application rather than off the column: the copy is
    a raw SQL UPDATE, so the value keeps whatever spelling it had — `22:00:00`
    where SQLAlchemy would have written `22:00:00.000000`. What matters is
    that the model still parses it, not how it is spelled.
    """
    start_app(populated)
    out = run(
        populated,
        str(BACKEND / ".venv/bin/python"),
        "-c",
        "from sqlmodel import Session, select\n"
        "from app.db.session import engine\n"
        "from app.models import Device\n"
        "with Session(engine) as s:\n"
        "    for d in s.exec(select(Device).order_by(Device.id)).all():\n"
        "        print(d.name, d.quiet_hours, d.quiet_from, d.quiet_to)",
    )
    assert "Bureau True 22:00:00 07:00:00" in out
    assert "Salon False None None" in out


def test_the_widget_targets_survive_the_rebuild(populated: Path):
    """The failure this whole file exists for.

    Dropping a column rebuilds `device`; the drop of the old table cascades
    into every row that references it. Without the pragma turned off, this
    comes back empty and nothing says so.
    """
    start_app(populated)
    assert rows(populated, "SELECT widget_id, device_id FROM widget_target ORDER BY device_id") == [
        (1, 1),
        (1, 2),
    ]


def test_the_reminder_targets_survive_too(populated: Path):
    """Same table shape, same cascade, and nobody would look at it."""
    start_app(populated)
    assert rows(populated, "SELECT reminder_id, device_id FROM reminder_target") == [(1, 1)]


def test_nothing_else_is_lost(populated: Path):
    start_app(populated)
    assert len(rows(populated, "SELECT id FROM device")) == 2
    assert len(rows(populated, "SELECT id FROM widget")) == 1
    assert len(rows(populated, "SELECT id FROM reminder")) == 1


def test_the_old_columns_are_gone(populated: Path):
    start_app(populated)
    columns = {row[1] for row in rows(populated, "PRAGMA table_info(device)")}
    assert not columns & {
        "night_mode", "night_from", "night_to",
        "night_brightness", "night_active", "night_saved",
    }
    assert {"quiet_hours", "quiet_from", "quiet_to"} <= columns


def test_foreign_keys_are_on_again_afterwards(populated: Path):
    """The pragma is turned off for the rebuild. Leaving it off would mean the
    application runs without the constraint it relies on."""
    start_app(populated)
    out = run(
        populated,
        str(BACKEND / ".venv/bin/python"),
        "-c",
        "from app.db.session import engine\n"
        "with engine.connect() as c:\n"
        "    print(c.exec_driver_sql('PRAGMA foreign_keys').scalar())",
    )
    assert out.strip().endswith("1")


# ---------------------------------------------------------------------------
# 8f1c2a7d4b60 — air quality and UV say what they show
#
# The first migration in this project that rewrites what a user can see rather
# than what the schema holds, which is why it is tested on a widget somebody
# customised as well as on one they never touched.
# ---------------------------------------------------------------------------

BEFORE_REDESIGN = "30ca1cb373ca"


@pytest.fixture
def with_widgets(tmp_path: Path) -> Path:
    """Three widgets: two on their shipped defaults, one written by hand."""
    run(tmp_path, str(BACKEND / ".venv/bin/alembic"), "upgrade", BEFORE_REDESIGN)

    db = sqlite3.connect(tmp_path / "awtrixng.db")
    db.executescript(
        """
        INSERT INTO connector (id,type,name,config,secrets,enabled,status,
                               consecutive_failures,created_at,updated_at)
          VALUES (1,'weather','Meteo','{}','{}',1,'HEALTHY',0,'2026-10-05','2026-10-05');
        INSERT INTO widget (id,name,connector_id,widget_type,config,display,
                            refresh_seconds,enabled,position,status,
                            consecutive_failures,created_at,updated_at)
          VALUES
           (1,'Qualite de l''air',1,'weather.air','{}',
            '{"text":"{{ aqi }}","font":"large","show_progress":false,"duration":8}',
            1800,1,0,'HEALTHY',0,'2026-10-05','2026-10-05'),
           (2,'Indice UV',1,'weather.uv','{}',
            '{"text":"UV {{ uv | round }}","font":"large","show_progress":false,"duration":8}',
            1800,1,1,'HEALTHY',0,'2026-10-05','2026-10-05'),
           (3,'Air a moi',1,'weather.air','{}',
            '{"text":"{{ quality }}","font":"small","show_progress":false,"duration":12}',
            1800,1,2,'HEALTHY',0,'2026-10-05','2026-10-05');
        """
    )
    db.commit()
    db.close()
    return tmp_path


def displays(data_dir: Path) -> dict[int, dict]:
    import json

    return {
        widget_id: json.loads(raw)
        for widget_id, raw in rows(data_dir, "SELECT id, display FROM widget")
    }


def test_the_bare_number_gains_its_word(with_widgets: Path):
    start_app(with_widgets)
    air = displays(with_widgets)[1]
    assert air["text"] == "AIR {{ aqi }}"
    assert air["font"] == "small"


def test_the_bar_both_widgets_were_computing_is_switched_on(with_widgets: Path):
    """Neither widget ever drew one. The projection filled `progress` at every
    collection and the renderer dropped it for want of this flag — the same
    fault the sun widget had, found the same way: by looking at a clock."""
    start_app(with_widgets)
    after = displays(with_widgets)
    assert after[1]["show_progress"] is True
    assert after[2]["show_progress"] is True


def test_a_template_somebody_typed_is_left_alone(with_widgets: Path):
    """Including its bar. Turning that on would be an improvement nobody
    asked for on a widget whose owner has already said what they want."""
    start_app(with_widgets)
    mine = displays(with_widgets)[3]
    assert mine == {
        "text": "{{ quality }}",
        "font": "small",
        "show_progress": False,
        "duration": 12,
    }


def test_the_fields_nobody_mentioned_are_kept(with_widgets: Path):
    """A migration that wrote a whole display would silently reset `duration`,
    `effect`, the colours — every field it did not think to carry over."""
    start_app(with_widgets)
    assert displays(with_widgets)[2]["duration"] == 8


def test_starting_again_changes_nothing(with_widgets: Path):
    start_app(with_widgets)
    once = displays(with_widgets)
    start_app(with_widgets)
    assert displays(with_widgets) == once
