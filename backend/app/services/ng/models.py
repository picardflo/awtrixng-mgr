"""What the display says about itself.

Every field below was read from a real TC001 on NG 1.1.2; the raw responses
are in `docs/ng-api/*.json`. Everything is optional and `extra="allow"` is on
throughout: the firmware gains fields between releases, and a reader that
breaks on an unknown one would turn a firmware update into an outage.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeviceState(BaseModel):
    """GET /api/v1/device — the closest thing to AWTRIX 3's /api/stats."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    version: str | None = None
    #: The MAC address without separators, e.g. "b0cbd8a1b560". Stable across
    #: a reflash, which makes it the right key for identifying a display.
    uid: str | None = None
    board_type: str | None = Field(default=None, alias="boardType")
    soc: str | None = None
    ip_address: str | None = Field(default=None, alias="ipAddress")
    hostname: str | None = None
    wifi_rssi: int | None = Field(default=None, alias="wifiRssi")
    uptime_seconds: int | None = Field(default=None, alias="uptimeSeconds")
    free_heap_bytes: int | None = Field(default=None, alias="freeHeapBytes")
    #: Why the device last restarted — "software", "poweron", a panic. Nothing
    #: equivalent existed on AWTRIX 3, and it is the first thing worth looking
    #: at when a display has lost its apps.
    reset_reason: str | None = Field(default=None, alias="resetReason")
    fps: int | None = None
    brightness: int | None = None
    light_level: float | None = Field(default=None, alias="lightLevel")
    battery_percent: int | None = Field(default=None, alias="batteryPercent")
    battery_voltage: float | None = Field(default=None, alias="batteryVoltage")
    low_battery: bool | None = Field(default=None, alias="lowBattery")
    temperature: float | None = None
    humidity: float | None = None
    matrix_power: bool | None = Field(default=None, alias="matrixPower")
    current_app: str | None = Field(default=None, alias="currentApp")


class Capabilities(BaseModel):
    """GET /api/v1/capabilities — what this firmware can actually do.

    This route is the reason the project no longer hard-codes effect and
    transition lists the way awtrixhub had to. A display that gains an effect
    in a firmware update offers it without a release here.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    effects: list[str] = Field(default_factory=list)
    palette_effects: list[str] = Field(default_factory=list, alias="paletteEffects")
    transitions: list[str] = Field(default_factory=list)
    overlays: list[str] = Field(default_factory=list)
    palettes: list[str] = Field(default_factory=list)
    #: {"buzzer": true, "track": false, "mp3": false, "radio": false} on a
    #: TC001. Whether to offer a melody field at all follows from this.
    audio: dict[str, bool] = Field(default_factory=dict)
    script_updates: bool | None = Field(default=None, alias="scriptUpdates")
    gpio: dict[str, Any] = Field(default_factory=dict)


class AppEntry(BaseModel):
    """One line of GET /api/v1/apps.

    `origin` is what makes reconciliation safe: it separates the firmware's
    own apps ("builtin") from pushed ones, so a sweep of orphans cannot touch
    Time or Battery. AWTRIX 3's /api/loop gave names and positions only, which
    is how awtrixhub ended up needing a name prefix to tell its own apps apart.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    enabled: bool | None = None
    in_loop: bool | None = Field(default=None, alias="inLoop")
    slot: int | None = None
    present: bool | None = None
    origin: str | None = None

    @property
    def is_builtin(self) -> bool:
        return self.origin == "builtin"


class FileEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    size: int | None = None


class FileListing(BaseModel):
    """GET /api/v1/files?dir=/ICONS.

    The byte counters matter: icons, melodies, palettes and scripts share one
    512 KB partition on a 4 MB ESP32, so installing an icon can fail for want
    of room left by something else entirely.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    files: list[FileEntry] = Field(default_factory=list)
    used_bytes: int | None = Field(default=None, alias="usedBytes")
    total_bytes: int | None = Field(default=None, alias="totalBytes")

    @property
    def free_bytes(self) -> int | None:
        if self.used_bytes is None or self.total_bytes is None:
            return None
        return self.total_bytes - self.used_bytes

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.files if f.name]
