"""Reminders get the presentation options widgets already had.

Florian, after redesigning two widgets: « comme pour les widgets, je dois
pouvoir choisir la taille du texte et les différentes options dans "Avancé"
qui seraient compatibles avec les rappels ».

A reminder offered three — scroll mode, scroll speed, background — against a
widget's ten, and nothing explained the gap. The list now lives in one place,
`app/schemas/matrix_text.py`, and both read from it.

Six columns, all with the default the shared declaration gives them, so an
existing reminder behaves exactly as it did before: `inherit` letter case is
the display's own, `static` when-fits is what the firmware already does for a
short word, and `small` is the font every reminder has been drawn in since the
first one.

**No batch_alter_table.** SQLite adds a column without rebuilding the table,
and a rebuild here would drop `reminder` while `reminder_target` references it
with ON DELETE CASCADE — the failure `30ca1cb373ca` documents at length. The
plain ALTER never touches the referencing table, so there is nothing to guard
against.

Revision ID: a3d9e51c7f82
Revises: 8f1c2a7d4b60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3d9e51c7f82"
down_revision: str | None = "8f1c2a7d4b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: name -> (type, default). The defaults are `MatrixText`'s own; an existing
#: reminder must look exactly as it looked yesterday.
COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None], ...] = (
    ("effect", sa.String(), None),
    ("overlay", sa.String(), None),
    ("icon_mode", sa.String(), "fixed"),
    ("text_case", sa.String(), "inherit"),
    ("font", sa.String(), "small"),
    ("scroll_when_fits", sa.String(), "static"),
)


def upgrade() -> None:
    for name, type_, default in COLUMNS:
        op.add_column(
            "reminder",
            sa.Column(
                name,
                type_,
                nullable=default is None,
                server_default=sa.text(f"'{default}'") if default else None,
            ),
        )


def downgrade() -> None:
    for name, _, _ in reversed(COLUMNS):
        op.drop_column("reminder", name)
