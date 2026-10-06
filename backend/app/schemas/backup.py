"""Configuration backup.

Everything tedious to retype — displays, services, widgets with their
templates, icons, colours, positions and targets — in one readable JSON file.

**Credentials are included, in clear text.** An earlier version left them out;
that made the file safe to mislay but turned a restore into a hunt for every
API key — and some services show a key once and never again. A backup that
does not restore is half a backup.

The file therefore carries credentials and must be kept like credentials. It
says so in its own first field, so that anyone opening it knows, and the export
button says so before downloading.

References use ids local to the file, not database ids: restoring into a fresh
installation remaps everything.
"""

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import utcnow

#: Bumped when the shape changes. A file from the future is refused outright
#: rather than half-imported.
#:
#: 2 — reminders, and the quiet hours of each display. Version 1 carried
#: displays, services and widgets, and left every reminder out: their hours,
#: their rhythms, their melodies and their targets were not in the file at
#: all. The quiet window went the same way, and the two belong together —
#: a reminder's `rings_at_night` is the exception to that window.
#:
#: Found by exporting a real installation and restoring it into an empty one,
#: which is the only way this kind of hole is ever found.
FORMAT_VERSION = 2


class BackupDevice(BaseModel):
    ref: int
    name: str
    host: str
    port: int = 80
    username: str | None = None
    #: In clear text. Re-encrypted with the local key on restore.
    password: str | None = None
    enabled: bool = True

    #: The quiet window, which was left out of format 1 along with the
    #: reminders — and the two belong together: a reminder's
    #: `rings_at_night` is the exception to *this*, so restoring one without
    #: the other restores a rule and loses what it applies to.
    quiet_hours: bool = False
    quiet_from: time | None = None
    quiet_to: time | None = None


class BackupConnector(BaseModel):
    ref: int
    type: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    #: In clear text. Re-encrypted with the local key on restore.
    secrets: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class BackupWidget(BaseModel):
    name: str
    #: BackupConnector.ref
    connector: int
    #: BackupDevice.ref values
    devices: list[int] = Field(default_factory=list)
    widget_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    display: dict[str, Any] = Field(default_factory=dict)
    refresh_seconds: int = 60
    position: int = 0
    enabled: bool = True


class BackupReminder(BaseModel):
    """A reminder, with the displays it rings on.

    Its whole presentation travels with it. A reminder restored without its
    font or its letter case is not the reminder that was backed up — it is a
    different one that happens to say the same words.
    """

    name: str
    message: str
    #: BackupDevice.ref values
    devices: list[int] = Field(default_factory=list)
    icon: str | None = None
    color: str | None = None
    #: "07:45:00"
    at: time
    #: Monday is 0.
    days: list[int] = Field(default_factory=list)
    every_weeks: int = 1
    anchor: date | None = None
    on_date: date | None = None
    countdown_to: date | None = None
    duration_seconds: int = 10
    repeat_count: int = 0
    repeat_every_minutes: int = 2
    melody: str | None = None
    rings_at_night: bool = False
    enabled: bool = True

    # The presentation block, as `MatrixText` declares it.
    background: str | None = None
    effect: str | None = None
    overlay: str | None = None
    icon_mode: str = "fixed"
    text_case: str = "inherit"
    font: str = "small"
    scroll_mode: str = "wrap"
    scroll_speed: int = 100
    scroll_when_fits: str = "static"


#: First field of the file, so it is the first thing anyone sees on opening it.
WARNING = (
    "This file contains credentials in clear text. Keep it as carefully as you "
    "would keep the credentials themselves."
)


class Backup(BaseModel):
    warning: str = WARNING
    format: int = FORMAT_VERSION
    exported_at: datetime = Field(default_factory=utcnow)
    #: Version of awtrixng-mgr that wrote the file.
    app_version: str = ""
    devices: list[BackupDevice] = Field(default_factory=list)
    connectors: list[BackupConnector] = Field(default_factory=list)
    widgets: list[BackupWidget] = Field(default_factory=list)
    #: **None, not an empty list, when the file predates format 2.**
    #:
    #: The distinction decides what a restore does. An empty list means "there
    #: were no reminders", and restoring it clears them, because restore means
    #: "look like the backup". `None` means the file cannot speak about
    #: reminders at all, and clearing them on its word would be inventing an
    #: instruction it never gave.
    reminders: list[BackupReminder] | None = None


class BackupSummary(BaseModel):
    """What a file holds, and what it would replace. Shown before restoring."""

    ok: bool
    message: str
    code: str
    exported_at: datetime | None = None
    app_version: str | None = None
    devices: int = 0
    connectors: int = 0
    widgets: int = 0
    #: None when the file predates format 2 and holds no reminder section —
    #: which is not the same as holding an empty one, and the interface says
    #: so rather than printing a reassuring zero.
    reminders: int | None = None
    #: How many credentials the file carries, so the warning can be concrete.
    secrets: int = 0


class RestoreResult(BaseModel):
    ok: bool
    message: str
    code: str
    devices: int = 0
    connectors: int = 0
    widgets: int = 0
    reminders: int = 0
    #: Reminders the installation already had, kept because the file was
    #: written before reminders were carried. Their targets are re-attached by
    #: host and port — see the restore route.
    reminders_kept: int = 0
    secrets: int = 0
