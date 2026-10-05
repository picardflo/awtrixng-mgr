"""A Device is one AWTRIX display."""

from datetime import datetime, time

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

    # -- Bedroom mode ---------------------------------------------------------
    #
    # A window where the display is dimmed and the buzzer silenced. The
    # firmware has no such notion: its only brightness controls are a manual
    # level, one driven by the light sensor, and a deep sleep that turns the
    # matrix off. The schedule therefore lives here.

    night_mode: bool = False
    #: Local time. The window may cross midnight, which is the case anyone
    #: actually configures.
    night_from: time | None = None
    night_to: time | None = None
    #: 0–255, like `BRI`. Low, not off: a clock you cannot read at night is a
    #: clock that is off. One rather than two — the firmware's automatic
    #: brightness floors at 2, so a window set there changes nothing in a dark
    #: room.
    night_brightness: int = 1

    #: What the display was set to when the window opened, as the firmware's
    #: own keys. Persisted rather than held in memory: an awtrixng-mgr restarted
    #: at three in the morning must still know what to put back at seven.
    night_saved: str | None = None
    #: Whether the window is currently applied. Compared against the schedule
    #: on each pass, so a boundary missed while awtrixng-mgr was down is caught
    #: up rather than skipped.
    night_active: bool = False

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
