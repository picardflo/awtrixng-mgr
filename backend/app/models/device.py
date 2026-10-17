"""A Device is one AWTRIX display."""

from datetime import datetime, time
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.base import HealthStatus, utcnow


class Device(SQLModel, table=True):
    __tablename__ = "device"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    host: str
    port: int = 80

    #: Optional basic auth. Off by default on AWTRIX 3, but available in the
    #: firmware (prior-art §2).
    username: str | None = None
    #: Encrypted at rest (ADR-005). Never returned by the API.
    password_enc: str | None = None

    enabled: bool = True

    # -- Filled in by detection ----------------------------------------------
    firmware: str | None = None
    uid: str | None = None
    status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    last_seen: datetime | None = None
    last_error: str | None = None
    #: Translatable code matching ``last_error`` (see app/core/errors.py).
    last_error_code: str | None = None
    #: Les paramètres qui accompagnaient ce code.
    #:
    #: Sans eux, un message traduit qui porte un `{reason}` affiche le mot
    #: `{reason}` entre accolades — ou, depuis la 0.17.2, retombe sur la
    #: phrase anglaise du backend. Florian l'a vu sur ses widgets météo : une
    #: interface en français, et une ligne en anglais au milieu.
    #:
    #: Le code seul ne suffit donc pas : ce qui se traduit, c'est le code
    #: **avec** ce qui le complète.
    last_error_params: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON)
    )

    # -- Quiet hours ----------------------------------------------------------
    #
    # A window of the day where reminders ring without their melody.
    #
    # **It used to dim the display too, and no longer does.** On AWTRIX 3 that
    # was the whole point: automatic brightness clamped at 2, which is too
    # bright for a bedroom, and the floor could not be changed — so the window
    # turned the sensor off, forced a lower level, remembered what it had
    # overwritten, and put it back in the morning.
    #
    # NG makes `minBrightness` a setting. Measured on a TC001 in a dark room:
    # the panel sits exactly on that floor, and lowering it from 10 to 8 took
    # the display down with it. One setting replaces the schedule, the saved
    # state and the restore — and it is the better answer, because the sensor
    # knows you went to bed early and a 22:00 boundary does not.
    #
    # What survives is the half the sensor cannot do: silence is a matter of
    # time, not of light.

    quiet_hours: bool = False
    #: Local time. The window may cross midnight, which is the case anyone
    #: actually configures.
    quiet_from: time | None = None
    quiet_to: time | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
