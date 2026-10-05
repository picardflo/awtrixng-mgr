"""A widget instance: one connector's data, in one shape, on one or more
displays."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel

from app.models.base import HealthStatus, utcnow


class WidgetTarget(SQLModel, table=True):
    """One display a widget is shown on, with its own state.

    The state lives here rather than on the widget because a widget on two
    clocks can perfectly well be fine on one and failing on the other. Rolling
    that up into a single status would show an error for a widget that is
    plainly working, and a badge nobody trusts is worse than no badge.
    """

    __tablename__ = "widget_target"

    widget_id: int = Field(
        foreign_key="widget.id", ondelete="CASCADE", primary_key=True
    )
    device_id: int = Field(
        foreign_key="device.id", ondelete="CASCADE", primary_key=True
    )

    status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    last_error: str | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0
    last_pushed_at: datetime | None = None

    widget: "Widget" = Relationship(back_populates="targets")


class Widget(SQLModel, table=True):
    __tablename__ = "widget"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    connector_id: int = Field(foreign_key="connector.id", ondelete="CASCADE", index=True)

    #: e.g. "weather.current". The connector prefix must match the instance.
    widget_type: str = Field(index=True)

    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    display: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    refresh_seconds: int = 60
    enabled: bool = True

    #: The icon actually pushed at the last collection.
    #:
    #: Not the same as `display["icon"]`: left empty there, the connector picks
    #: one from the data — a cloud or a sun, the current moon phase. Without
    #: remembering it, a list could show a thumbnail for the widgets whose icon
    #: never changes and nothing for those where it is most telling.
    last_icon: str | None = None

    #: Where the app sits in the display's rotation, lowest first.
    #:
    #: AWTRIX offers no working control over this: its `pos` key is documented
    #: as experimental and, measured on v0.98, does nothing at all. The loop
    #: order is simply the order apps were first pushed — so awtrixng-mgr pushes
    #: in this order, and reordering an existing rotation means deleting the
    #: apps and republishing them (see ADR-015).
    position: int = Field(default=0, index=True)

    #: Collection state. Pushing is tracked per display, on WidgetTarget.
    status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    last_success: datetime | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    targets: list[WidgetTarget] = Relationship(
        back_populates="widget",
        cascade_delete=True,
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    @property
    def device_ids(self) -> list[int]:
        return sorted(target.device_id for target in self.targets)
