"""Tests against a real AWTRIX NG display. Deselected unless asked for:

    AWTRIXNG_TEST_HOST=awtrix-cl2.home.lan .venv/bin/python -m pytest -m device

Mocks prove the client sends what we *think* the firmware wants. Only a real
display proves the firmware agrees. Every route the project depends on is
exercised here, which is how a firmware update that moves something gets found
by running a test instead of by a widget going blank.

**These tests write to the display they are pointed at**: they push an app,
switch to it, and remove it. Pointing them at a display someone relies on is
the one way they can do harm, so they refuse to start without an explicit host
and they refuse a few names outright.
"""

import os

import pytest

from app.core.protected import is_protected
from app.services.ng.client import NgClient
from app.services.ng.models import DeviceState
from app.services.ng.payload import NgPayload
from app.services.ng.transport import HttpTransport

pytestmark = pytest.mark.device

#: Name of the app these tests push. Deliberately not in the project's own
#: namespace, so a stray leftover cannot be mistaken for a widget.
TEST_APP = "pytestprobe"


@pytest.fixture
def host() -> str:
    target = os.environ.get("AWTRIXNG_TEST_HOST", "")
    if not target:
        pytest.skip("set AWTRIXNG_TEST_HOST to run the device tests")
    # The same guard the CLI uses, so there is one list to maintain and one
    # place where the rule can be got wrong.
    if is_protected(target):
        pytest.fail(f"{target} is a display in service: these tests write, refusing to run")
    return target


@pytest.fixture
async def client(host):
    ng = NgClient(HttpTransport(host))
    try:
        yield ng
    finally:
        # Never leave the probe app behind, whatever the test did.
        try:
            await ng.delete_app(TEST_APP)
        except Exception:  # noqa: BLE001 — cleanup must not mask a real failure
            pass
        await ng.aclose()


# -- Reading ------------------------------------------------------------------


async def test_the_display_identifies_itself(client):
    device = await client.get_device()
    assert isinstance(device, DeviceState)
    assert device.version
    # The uid is the MAC without separators, and survives a reflash — which is
    # what makes it the right key for identifying a display.
    assert device.uid and len(device.uid) == 12


async def test_capabilities_describe_this_firmware(client):
    capabilities = await client.get_capabilities()
    assert capabilities.effects, "a display with no effects means the route moved"
    assert capabilities.transitions
    assert "buzzer" in capabilities.audio
    # Hard-coding these lists is exactly what this route exists to stop.
    assert set(capabilities.palette_effects) <= set(capabilities.effects)


async def test_settings_use_the_documented_names(client):
    settings = await client.get_settings()
    # `textColor`, not `color`: the rename that catches every port.
    assert "textColor" in settings
    assert "appDurationMs" in settings


async def test_the_builtin_apps_are_recognisable_as_such(client):
    apps = await client.get_apps()
    assert any(app.is_builtin for app in apps)
    assert all(app.name for app in apps)


async def test_the_boot_log_can_be_read_and_resumed(client):
    lines, cursor = await client.get_logs()
    assert lines
    assert cursor >= len(lines)
    _, again = await client.get_logs(since=cursor)
    assert again >= cursor


# -- Writing ------------------------------------------------------------------


async def test_a_pushed_app_appears_and_can_be_removed(client):
    await client.push_app(TEST_APP, NgPayload(text="ok", text_color="#00ff00", duration_ms=1000))

    names = {app.name: app for app in await client.get_apps()}
    assert TEST_APP in names
    assert names[TEST_APP].origin == "pushed"

    await client.delete_app(TEST_APP)
    assert TEST_APP not in {app.name for app in await client.get_apps()}


async def test_the_screen_can_be_read_back(client):
    """The whole point of the live preview: what the matrix is actually
    showing, not what we believe we sent."""
    pixels = await client.get_screen()
    assert len(pixels) == 32 * 8
    assert all(isinstance(pixel, int) for pixel in pixels)


async def test_an_awtrix3_key_is_refused_by_name(client):
    """This is the measured behaviour the error handling is built on. If a
    firmware release ever starts accepting `color` in silence, the project
    needs to know."""
    from app.core.errors import DeviceRejectedError

    with pytest.raises(DeviceRejectedError) as raised:
        await client._t.request(
            "PUT", f"/apps/pushed/{TEST_APP}", json={"text": "x", "color": "#ffffff"}
        )
    assert raised.value.field == "color"


async def test_deleting_one_app_leaves_a_longer_name_alone(client):
    """AWTRIX 3 deleted by prefix, which is why the previous project padded
    every app name to a fixed width. Measured here so the day it changes back
    is a failing test rather than a display losing widgets."""
    await client.push_app(TEST_APP, NgPayload(text="a"))
    await client.push_app(f"{TEST_APP}2", NgPayload(text="b"))
    try:
        await client.delete_app(TEST_APP)
        names = {app.name for app in await client.get_apps()}
        assert TEST_APP not in names
        assert f"{TEST_APP}2" in names
    finally:
        await client.delete_app(f"{TEST_APP}2")
