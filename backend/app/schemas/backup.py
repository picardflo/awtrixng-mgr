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

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import utcnow

#: Bumped when the shape changes. A file from the future is refused outright
#: rather than half-imported.
FORMAT_VERSION = 1


class BackupDevice(BaseModel):
    ref: int
    name: str
    host: str
    port: int = 80
    username: str | None = None
    #: In clear text. Re-encrypted with the local key on restore.
    password: str | None = None
    enabled: bool = True


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
    #: How many credentials the file carries, so the warning can be concrete.
    secrets: int = 0


class RestoreResult(BaseModel):
    ok: bool
    message: str
    code: str
    devices: int = 0
    connectors: int = 0
    widgets: int = 0
    secrets: int = 0
