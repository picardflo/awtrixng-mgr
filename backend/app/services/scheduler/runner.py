"""Running one widget: collect once, render once, push to each display.

Kept apart from the loop so it can be called on its own — by a manual refresh,
or by a test — without starting a scheduler.

The split matters: collecting is the expensive part and is shared, while an
unreachable display is a local problem. A clock unplugged in the living room
must not stop the same widget from showing in the office, nor delay its next
collection.
"""

import logging
from dataclasses import dataclass, field

from app.connectors.base import Connector
from app.core.errors import AwtrixNgError
from app.models import Widget
from app.schemas.widget_data import DisplayOptions, WidgetData
from app.services.ng.client import NgClient, app_name
from app.services.scheduler.cache import SourceCache
from app.widgets.renderer import lifetime_for, render

log = logging.getLogger(__name__)


@dataclass(slots=True)
class TargetOutcome:
    """What happened on one display."""

    device_id: int
    ok: bool
    #: True when the app was removed because the connector reported no data.
    removed: bool = False
    error: AwtrixNgError | None = None


@dataclass(slots=True)
class WidgetOutcome:
    """What happened to one widget. The caller writes it to the database, so
    running a widget stays free of persistence concerns."""

    widget_id: int
    #: Whether the upstream data could be collected at all. This is what drives
    #: the widget's schedule; a failed push does not delay the next collection.
    collected: bool
    error: AwtrixNgError | None = None
    data: WidgetData | None = None
    #: The icon that went out, once the connector's suggestion and the user's
    #: choice have been arbitrated.
    icon: str | None = None
    targets: list[TargetOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.collected and all(target.ok for target in self.targets)


async def run_widget(
    widget: Widget,
    connector: Connector,
    clients: dict[int, NgClient],
    cache: SourceCache,
) -> WidgetOutcome:
    """Collect through the cache, render, and push to every display. Never raises."""
    try:
        key, ttl = connector.request_key(widget.widget_type, widget.config)
        raw = await cache.get_or_collect(
            key, ttl, lambda: connector.collect(widget.widget_type, widget.config)
        )
        data = connector.project(widget.widget_type, widget.config, raw)
    except AwtrixNgError as exc:
        log.warning("widget %s could not collect: %s", widget.name, exc.message)
        return WidgetOutcome(widget.id, collected=False, error=exc)
    except Exception as exc:  # noqa: BLE001
        # A connector bug must not take the scheduler down with it (§18).
        log.exception("widget %s raised an unexpected error", widget.name)
        return WidgetOutcome(
            widget.id,
            collected=False,
            error=AwtrixNgError(
                f"Unexpected error: {exc}", code="widget.unexpected_error"
            ),
        )

    display = DisplayOptions.model_validate(widget.display or {})
    payload = render(data, display, lifetime_seconds=lifetime_for(widget.refresh_seconds))
    # Kept so a list can show what the matrix shows, rather than only the icons
    # someone pinned by hand. None when the renderer withholds the app
    # entirely — "hide when empty" — and there is nothing on the matrix to
    # report.
    pushed_icon = payload.icon if payload is not None else None
    name = app_name(widget.id)

    targets = [
        await _push(device_id, client, name, payload)
        for device_id, client in clients.items()
    ]
    return WidgetOutcome(
        widget.id, collected=True, data=data, targets=targets, icon=pushed_icon
    )


async def _push(device_id: int, client: NgClient, name: str, payload) -> TargetOutcome:
    try:
        if payload is None:
            # No data and the user asked to hide: remove the app rather than
            # leave a stale value on the matrix.
            await client.delete_app(name)
            return TargetOutcome(device_id, ok=True, removed=True)

        # The icon must exist on the device before the app references it,
        # otherwise the matrix shows text with a blank square. Failing to
        # install one is not worth dropping the whole widget for.
        if payload.icon:
            try:
                await client.ensure_icon(payload.icon)
            except AwtrixNgError as exc:
                log.warning("icon %s unavailable: %s", payload.icon, exc.message)

        await client.push_app(name, payload)
        return TargetOutcome(device_id, ok=True)
    except AwtrixNgError as exc:
        log.warning("could not push %s to device %s: %s", name, device_id, exc.message)
        return TargetOutcome(device_id, ok=False, error=exc)


def backoff(refresh_seconds: int, consecutive_failures: int) -> int:
    """Delay before retrying a widget whose collection failed.

    Doubles per failure, capped: a service that is down should not be hammered,
    but it must still be retried often enough to notice when it comes back.
    """
    if consecutive_failures <= 0:
        return refresh_seconds
    delay = refresh_seconds * (2 ** min(consecutive_failures, 5))
    return min(delay, MAX_BACKOFF_SECONDS)


MAX_BACKOFF_SECONDS = 900
