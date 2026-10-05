"""Keeping the device's app loop and the database in agreement (architecture §6.3).

Pushing a widget once is not enough. The device can reboot and lose every
custom app; someone can delete one from its web interface; a widget can be
deleted or disabled while the device is unplugged, leaving an app nobody owns.

Reconciling answers all of those with one comparison: what `GET /api/v1/apps`
shows against what the database says should be there.

It is also what makes "disabled" mean something. A disabled widget is simply
not expected, so the next pass removes it from the matrix.

**What NG changed, and it matters here more than anywhere.** AWTRIX 3's
`/api/loop` gave names and positions and nothing else, so telling our apps
from the firmware's own rested entirely on a name prefix. NG labels every app
with an `origin`, so a builtin can no longer be mistaken for an orphan even if
someone names a widget to look like one. Both checks are applied — the origin
and the name — because this is the code path that deleted a live display's
apps twice on the previous project.
"""

import logging
from dataclasses import dataclass, field

from app.models import Widget
from app.services.ng.client import NgClient, app_name, is_managed
from app.services.ng.models import AppEntry

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Reconciliation:
    """What a pass found. The caller decides what to do with it."""

    device_id: int
    #: Apps on the device that awtrixng-mgr manages but no longer wants.
    orphans: list[str] = field(default_factory=list)
    #: Widgets that should be on the matrix and are not.
    missing: list[int] = field(default_factory=list)

    @property
    def drifted(self) -> bool:
        return bool(self.orphans or self.missing)


def compare(device_id: int, widgets: list[Widget], apps: list[AppEntry]) -> Reconciliation:
    """Pure comparison, so the interesting part needs no device to test.

    Only apps that are ours are considered, and "ours" needs two things to be
    true: NG reports the app as `pushed`, and the name is one we write. The
    builtin Time and Battery apps, an app a Berry script put there, and
    anything pushed by hand are all none of our business.
    """
    managed = {app.name for app in apps if app.is_pushed and is_managed(app.name)}
    expected = {
        app_name(widget.id): widget.id
        for widget in widgets
        if widget.enabled and device_id in widget.device_ids
    }

    return Reconciliation(
        device_id=device_id,
        orphans=sorted(managed - expected.keys()),
        missing=sorted(expected[name] for name in expected.keys() - managed),
    )


async def reconcile(
    device_id: int, widgets: list[Widget], client: NgClient
) -> Reconciliation:
    """Read the display and say what drifted. Removes orphans; the caller
    re-pushes what is missing, since that needs a connector."""
    apps = await client.get_apps()
    result = compare(device_id, widgets, apps)

    for orphan in result.orphans:
        await client.delete_app(orphan)
        log.info("removed orphan app %s from device %s", orphan, device_id)

    if result.missing:
        log.info("device %s is missing %d app(s)", device_id, len(result.missing))

    return result
