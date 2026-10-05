"""Widget DTOs, including the preview that works without a saved widget."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import HealthStatus
from app.schemas.widget_data import DisplayOptions, WidgetData

#: Floor on the refresh interval, so nobody can set 1 second and hammer a
#: service (§31). Mirrors Settings.min_refresh_seconds.
MIN_REFRESH = 5


class WidgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    connector_id: int
    #: The displays this widget appears on. At least one, or it shows nowhere.
    device_ids: list[int] = Field(min_length=1)
    widget_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    display: DisplayOptions = Field(default_factory=DisplayOptions)
    refresh_seconds: int = Field(default=60, ge=MIN_REFRESH, le=86400)
    enabled: bool = True


class WidgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    #: Replaces the whole set. Displays dropped from it lose the app.
    device_ids: list[int] | None = Field(default=None, min_length=1)
    config: dict[str, Any] | None = None
    display: DisplayOptions | None = None
    refresh_seconds: int | None = Field(default=None, ge=MIN_REFRESH, le=86400)
    enabled: bool | None = None
    position: int | None = Field(default=None, ge=0)


class WidgetTargetRead(BaseModel):
    """One display, with its own state.

    A widget can be perfectly fine on one clock and failing on another; a
    single rolled-up status would show an error for something that plainly
    works.
    """

    device_id: int
    status: HealthStatus
    last_error: str | None
    last_error_code: str | None
    last_pushed_at: datetime | None


class WidgetRead(BaseModel):
    id: int
    name: str
    connector_id: int
    targets: list[WidgetTargetRead]
    widget_type: str
    config: dict[str, Any]
    display: dict[str, Any]
    refresh_seconds: int
    enabled: bool
    #: Where it sits in the rotation, lowest first.
    position: int
    status: HealthStatus
    last_success: datetime | None
    last_error: str | None
    last_error_code: str | None
    #: AWTRIX Custom App name, useful when debugging against the device.
    app_name: str
    #: The icon last pushed — the connector's when none was chosen.
    last_icon: str | None = None


class PreviewRequest(BaseModel):
    """Preview an unsaved widget — this is what makes the builder live (§11)."""

    widget_type: str
    display: DisplayOptions
    config: dict[str, Any] = Field(default_factory=dict)
    #: Omit to render the widget's sample data, which is what lets the builder
    #: work before a service is configured or reachable.
    connector_id: int | None = None


class PreviewResponse(BaseModel):
    #: The exact JSON that would be posted to the device, or null when the
    #: widget would be hidden because there is no data.
    payload: dict[str, Any] | None
    #: The rendered text alone, handy for the matrix preview.
    text: str
    data: WidgetData
    #: True when sample data was used instead of a live call.
    sample: bool
    #: Set when a live fetch was attempted and failed; the preview then falls
    #: back to the sample rather than showing nothing.
    warning: str | None = None
    warning_code: str | None = None


class OrderRequest(BaseModel):
    """Widget ids in the order they should appear in the rotation.

    Setting the order is cheap and touches no display. Applying it is not:
    see POST /api/devices/{id}/reorder.
    """

    widget_ids: list[int] = Field(min_length=1)


class ReorderResult(BaseModel):
    ok: bool
    #: How many apps were republished.
    pushed: int
