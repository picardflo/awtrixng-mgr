"""Device DTOs. A password goes in; it never comes back out (§5.2)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import HealthStatus
from app.services.ng.models import DeviceState


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1)
    port: int = Field(default=80, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    enabled: bool = True


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    #: None leaves the password untouched, "" clears it.
    password: str | None = None
    enabled: bool | None = None


class DeviceRead(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str | None
    has_password: bool
    enabled: bool
    firmware: str | None
    uid: str | None
    status: HealthStatus
    last_seen: datetime | None
    last_error: str | None
    #: Translatable code for ``last_error``, when the failure produced one.
    last_error_code: str | None = None


class DeviceTestResult(BaseModel):
    ok: bool
    #: English message, readable on its own from the API.
    message: str
    #: Stable code the frontend translates. See app/core/errors.py.
    code: str
    #: Interpolation values for the translated message.
    params: dict[str, Any] = Field(default_factory=dict)
    firmware: str | None = None
    uid: str | None = None
    stats: DeviceState | None = None


class NotifyRequest(BaseModel):
    """Test notification sent from the UI.

    Pydantic drops fields that are not declared here, without a word — which is
    how a melody sent from the reminder form reached this route and went no
    further. Anything the UI may send must therefore be listed.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = "awtrixng-mgr"
    icon: str | None = None
    color: str | None = None
    duration: int = Field(default=5, ge=1, le=120)
    #: `rainbow` is gone: measured on NG, `palette` colours effects, not text.
    #: An overlay is the thing NG gained in its place, and it is visible.
    overlay: str | None = None
    #: RTTTL, played by the clock's buzzer if it has one. Named as it is in the
    #: reminder model rather than as the firmware names it.
    melody: str | None = None
    #: Light the matrix if it is asleep — a melody nobody can see arriving is
    #: hard to tell from a melody that did not play.
    wakeup: bool = False
