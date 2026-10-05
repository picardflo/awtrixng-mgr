"""Installation settings that belong to the application, not to a file.

The README promises an installation that works "sans éditer un seul fichier".
A setting reachable only through `.env` breaks that promise, and the display
language was one: someone switching the interface to French had no way to
learn that the clocks keep speaking English, let alone to change it.

Deliberately a key/value table rather than a column per setting. There is one
key today; a second one must not cost a migration.
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.base import utcnow

#: The language of the words pushed to the matrix. Falls back to the
#: environment, then to English.
LANGUAGE = "language"


class Setting(SQLModel, table=True):
    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=utcnow)
