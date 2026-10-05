"""Air quality and UV say what they show.

Both widgets displayed a bare number beside an icon that could not be read:
six "AQI" letters on eight pixels for one, a magenta "UV" under a corner of
sun for the other. The icons are replaced by one each — a gust, a sun — and
the word moves into the text, where a font draws it. Measured on the panel,
`docs/screenshots/panneau-air-uv.png`.

**Why a migration at all.** A descriptor's `default_display` is read once,
when a widget is created. Changing it leaves every widget already on a clock
exactly as it was, which is to say unchanged where the complaint was. These
two are also the pair that predates `show_progress`, so their bar — computed
at every projection — was being thrown away.

**What it will not touch.** Only a display whose text is still one this
project shipped as a default. Someone who typed their own template has
decided what their panel says, and that outranks a better default; their
widget keeps every field, bar included. The rule is deliberately narrow for
the reason `DisplayOptions.from_stored` exists: a migration that rewrites
what a user configured is indistinguishable, from the outside, from losing it.

Revision ID: 8f1c2a7d4b60
Revises: 30ca1cb373ca
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f1c2a7d4b60"
down_revision: str | None = "30ca1cb373ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: widget type -> (texts this project has shipped as a default, new display)
#:
#: The UV text does not change: "UV {{ uv | round }}" was already right, and
#: it is listed so the widget can still be recognised as untouched.
REDESIGNED: dict[str, tuple[frozenset[str], dict[str, object]]] = {
    "weather.air": (
        frozenset({"{{ aqi }}", "{{ aqi }} {{ quality }}"}),
        {"text": "AIR {{ aqi }}", "font": "small", "show_progress": True},
    ),
    "weather.uv": (
        frozenset({"UV {{ uv | round }}", "{{ uv | round }}", "UV {{ uv }}"}),
        {"text": "UV {{ uv | round }}", "font": "large", "show_progress": True},
    ),
}

#: Enough to read and write the column; the table is not described further
#: because nothing here depends on the rest of it.
widget = sa.table(
    "widget",
    sa.column("id", sa.Integer),
    sa.column("widget_type", sa.String),
    sa.column("display", sa.JSON),
)


def _displays(bind):
    rows = bind.execute(
        sa.select(widget.c.id, widget.c.widget_type, widget.c.display).where(
            widget.c.widget_type.in_(tuple(REDESIGNED))
        )
    ).all()
    for widget_id, widget_type, raw in rows:
        # SQLite hands JSON back as a string through some drivers and as a
        # dict through others. Both are read; anything else is left alone.
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                continue
        if isinstance(raw, dict):
            yield widget_id, widget_type, raw


def upgrade() -> None:
    bind = op.get_bind()
    for widget_id, widget_type, display in _displays(bind):
        shipped, replacement = REDESIGNED[widget_type]
        if display.get("text") not in shipped:
            continue
        bind.execute(
            sa.update(widget)
            .where(widget.c.id == widget_id)
            .values(display={**display, **replacement})
        )


def downgrade() -> None:
    """Puts the bare number back, and nothing else.

    The old icons are not restored because they were never stored: a widget
    records the template, and the connector decides the icon at every
    projection. Rolling back the code restores them on the next push.
    """
    bind = op.get_bind()
    previous = {"weather.air": "{{ aqi }}", "weather.uv": "UV {{ uv | round }}"}
    for widget_id, widget_type, display in _displays(bind):
        _, replacement = REDESIGNED[widget_type]
        if display.get("text") != replacement["text"]:
            continue
        bind.execute(
            sa.update(widget)
            .where(widget.c.id == widget_id)
            .values(
                display={
                    **display,
                    "text": previous[widget_type],
                    "font": "large",
                    "show_progress": False,
                }
            )
        )
