"""Error codes keep the parameters that complete them.

A translated message carries placeholders — "Open-Meteo a refusé la requête :
{reason}" — and the stored form of an error kept only its **code**. The
interface therefore had a code and nothing to fill it with, and rendered the
word `{reason}` in braces on the card.

0.17.2 stopped showing the hole by falling back to the backend's English
sentence, which always has its values interpolated. Florian saw the cost the
next day: an interface in French with one line in English in the middle of
it. That was the quick fix; this is the real one.

Four columns, one per table that already stores a code, nullable because
every row that exists predates them — and an error from last week has no
parameters to recover. They fill in on the next failure, which is when they
matter.

**No batch_alter_table.** SQLite adds a column without rebuilding the table,
and a rebuild of `device` would drop it while `widget_target` and
`reminder_target` reference it with ON DELETE CASCADE — the failure
`30ca1cb373ca` documents at length.

Revision ID: c2f8b31d9a44
Revises: a3d9e51c7f82
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f8b31d9a44"
down_revision: str | None = "a3d9e51c7f82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every table that carries `last_error_code` carries its parameters too.
#: Listed rather than discovered, so that adding one is a decision.
TABLES = ("connector", "device", "widget", "widget_target")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("last_error_params", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "last_error_params")
