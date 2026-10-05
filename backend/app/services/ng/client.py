"""AWTRIX NG client — the only abstraction that knows the firmware API.

Destructive endpoints stay absent on purpose: nothing here erases the
filesystem, resets settings or triggers a firmware update. A bug in a
scheduler must not be able to brick a display.

**App names no longer need padding.** awtrixng-mgr named its apps `ah000123`
because AWTRIX 3 deleted by *prefix*: removing `ah1` would have taken `ah12`
with it. Measured on NG 1.1.2, that hazard is gone — pushing `zz1`, `zz12` and
`zz1x`, then deleting `zz1`, left the other two standing. The fixed width is
kept for a different reason: among apps whose `origin` is `pushed`, it is what
tells ours apart from one a Berry script or another tool put there.
"""

import logging
from typing import Any

import httpx

from app.core.http import build_client
from app.services.ng import icons
from app.services.ng.models import AppEntry, Capabilities, DeviceState, FileListing
from app.services.ng.payload import NgNotification, NgPayload
from app.services.ng.transport import NgTransport

log = logging.getLogger(__name__)

#: Prefix of the pushed apps this project owns.
APP_PREFIX = "ng"

#: Where icons live on the device.
ICONS_DIR = "/ICONS"


def app_name(widget_id: int) -> str:
    """Pushed-app name for a widget."""
    if not 0 <= widget_id <= 999_999:
        raise ValueError(f"widget id out of range: {widget_id}")
    return f"{APP_PREFIX}{widget_id:06d}"


def is_managed(name: str) -> bool:
    """True when this app belongs to us."""
    suffix = name.removeprefix(APP_PREFIX)
    return name.startswith(APP_PREFIX) and len(suffix) == 6 and suffix.isdigit()


class NgClient:
    def __init__(self, transport: NgTransport) -> None:
        self._t = transport
        #: Device icon listing, fetched at most once per client. Clients are
        #: built per scheduler tick, so this costs one listing per device per
        #: tick rather than one per widget.
        self._icons: set[str] | None = None
        self._outbound: httpx.AsyncClient | None = None

    # -- Reading ---------------------------------------------------------------

    async def get_device(self) -> DeviceState:
        return DeviceState.model_validate(await self._t.get("/device"))

    async def get_capabilities(self) -> Capabilities:
        """What this firmware can do — effects, transitions, palettes, audio.

        Worth calling rather than assuming: it is what lets the UI offer
        exactly the effects the display in front of the user actually has.
        """
        return Capabilities.model_validate(await self._t.get("/capabilities"))

    async def get_version(self) -> str | None:
        return (await self._t.get("/version") or {}).get("version")

    async def get_settings(self) -> dict[str, Any]:
        return await self._t.get("/settings")

    async def update_settings(self, settings: dict[str, Any]) -> None:
        """Partial update: only the keys sent are changed."""
        await self._t.request("PATCH", "/settings", json=settings)

    async def get_screen(self) -> list[int]:
        """The matrix as packed RGB integers, left to right, top to bottom.

        The route answers `{"width": 32, "height": 8, "pixels": [...]}`; only
        the pixels are returned here, since the geometry is a property of the
        panel and is already in the device state.
        """
        screen = await self._t.get("/display/screen")
        return list(screen.get("pixels") or [])

    async def get_display(self) -> dict[str, Any]:
        """Panel state: power, brightness, the active overlay, the moodlight."""
        return await self._t.get("/display")

    async def set_power(self, on: bool) -> None:
        """Turn the matrix on or off.

        **New in NG, and it has no AWTRIX 3 equivalent.** The old firmware
        offered only `/api/sleep`, a deep sleep for a number of seconds — a
        battery measure, not a switch. This is a switch: the panel goes dark,
        `matrixPower` says so, and nothing is lost.

        Measured, because `PATCH /api/v1/display` is one of the routes that
        does **not** refuse what it does not know — `{"zz": "ZZZ"}` answers
        `{"ok": true}`. Only `power` and `overlay` are validated there. So a
        typo in this call would fail silently, which is why it takes a bool
        and builds the body itself.
        """
        await self._t.request("PATCH", "/display", json={"power": bool(on)})
        log.info("matrix power %s", "on" if on else "off")

    async def set_brightness(self, level: int) -> None:
        """Panel brightness, 0–255. Overridden within seconds when the
        display's `autoBrightness` setting is on."""
        await self._t.request("PATCH", "/display", json={"brightness": int(level)})

    async def get_logs(self, since: int = 0) -> tuple[list[str], int]:
        """Boot log, and the cursor to pass next time.

        The firmware keeps a ring buffer and answers `{"next": N, "lines":
        [...]}`, so polling from the returned cursor gives only what is new.
        Nothing like it existed on AWTRIX 3.
        """
        body = await self._t.get("/logs", params={"since": since} if since else None)
        return list(body.get("lines") or []), int(body.get("next") or since)

    # -- Apps ------------------------------------------------------------------

    async def get_apps(self) -> list[AppEntry]:
        """Everything on the display: builtin, pushed and scripted."""
        return [AppEntry.model_validate(entry) for entry in await self._t.get("/apps")]

    async def list_managed_apps(self) -> list[str]:
        """Names of the pushed apps this project owns.

        `origin` does the heavy lifting here: a builtin app can no longer be
        mistaken for an orphan, which is the failure that twice wiped a
        display on the previous project. The test is a whitelist — the app has
        to be `pushed` — so an origin NG grows later is left alone rather than
        swept up.
        """
        return [
            app.name
            for app in await self.get_apps()
            if app.is_pushed and is_managed(app.name)
        ]

    async def push_app(self, name: str, payload: NgPayload) -> None:
        """Create or replace a pushed app.

        Pushed apps do not survive a reboot — NG dropped AWTRIX 3's `save` —
        so the scheduler is what puts them back, not the device.
        """
        await self._t.request("PUT", f"/apps/pushed/{name}", json=payload.to_json())
        log.info("pushed app %s", name)

    async def delete_app(self, name: str) -> None:
        """Remove one app, matched by its exact name."""
        await self._t.request("DELETE", f"/apps/{name}")
        log.info("deleted app %s", name)

    async def switch_to(self, name: str) -> None:
        """Bring an app to the front. 404 if no app goes by that name."""
        await self._t.request("PUT", "/apps/active", json={"name": name})

    # -- Notifications ---------------------------------------------------------

    async def notify(self, payload: NgNotification) -> None:
        await self._t.request("POST", "/notifications", json=payload.to_json())

    # -- Files and icons -------------------------------------------------------
    #
    # Unlike AWTRIX 3, where both routes were undocumented and read out of the
    # firmware's own web UI, these are part of the published API.

    async def list_files(self, directory: str = ICONS_DIR) -> FileListing:
        return FileListing.model_validate(await self._t.get("/files", params={"dir": directory}))

    async def ensure_icon(self, icon: str | None) -> bool:
        """Install a LaMetric icon on the display if it is not there yet.

        Only numeric ids are handled: anything else is a file the user put
        there themselves, and guessing at it would be wrong. Returns True when
        the icon is available afterwards.

        A failure here must never stop a widget from being pushed — text
        without its icon still beats a blank matrix — so the caller treats the
        result as advisory.
        """
        if not icon or not icon.isdigit():
            return bool(icon)

        if self._icons is None:
            self._icons = set((await self.list_files()).names)

        if icons.icon_filename(int(icon)) in self._icons:
            return True

        if self._outbound is None:
            self._outbound = build_client()
        filename = await self.install_icon(int(icon), self._outbound)
        self._icons.add(filename)
        return True

    async def install_icon(self, icon_id: int, http: httpx.AsyncClient) -> str:
        """Fetch an icon from LaMetric and store it on the display.

        Stills are converted rather than refused: for whole families — the moon
        phases among them — the icon *is* the information and no animated
        equivalent exists.
        """
        payload, animated = await icons.download(icon_id, http)
        if not animated:
            # PNG from the gallery; the firmware would store it and draw
            # nothing.
            payload = icons.to_gif(payload)
        filename = icons.icon_filename(icon_id)
        await self._t.post_file(
            "/files",
            field="file",
            filename=filename,
            content=payload,
            content_type="image/gif",
            params={"dir": ICONS_DIR},
        )
        log.info("installed icon %s", filename)
        return filename

    async def aclose(self) -> None:
        if self._outbound is not None:
            await self._outbound.aclose()
            self._outbound = None
        await self._t.aclose()
