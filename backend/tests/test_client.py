"""The client's contract: which route, which verb, which body.

Two lessons from the previous project are pinned here. One is that a sweep of
"orphan" apps must never be able to reach the firmware's own — that mistake
wiped a display in service, twice. The other is that an app name has to be
unambiguously ours or not ours.
"""

import pytest
import respx

from app.services.ng.client import APP_PREFIX, NgClient, app_name, is_managed
from app.services.ng.payload import NgNotification, NgPayload
from app.services.ng.transport import HttpTransport

BASE = "http://display.test"


@pytest.fixture
def client():
    return NgClient(HttpTransport("display.test"))


# -- Naming -------------------------------------------------------------------


def test_app_name_is_fixed_width():
    assert app_name(1) == f"{APP_PREFIX}000001"
    assert app_name(123456) == f"{APP_PREFIX}123456"


def test_app_name_refuses_an_id_it_cannot_represent():
    with pytest.raises(ValueError):
        app_name(1_000_000)


def test_is_managed_only_claims_our_own():
    assert is_managed(f"{APP_PREFIX}000042")
    assert not is_managed("Time")
    assert not is_managed(f"{APP_PREFIX}42")  # unpadded: not a name we write
    assert not is_managed(f"{APP_PREFIX}abcdef")
    assert not is_managed("Battery")


# -- Reading ------------------------------------------------------------------


@respx.mock
async def test_device_state_survives_an_unknown_field(client):
    """The firmware gains fields between releases; a reader that broke on one
    would turn a firmware update into an outage."""
    respx.get(f"{BASE}/api/v1/device").respond(
        json={"version": "1.1.2", "uid": "b0cbd8a1b560", "aFieldFromTheFuture": 1}
    )
    device = await client.get_device()
    assert device.version == "1.1.2"
    assert device.uid == "b0cbd8a1b560"


@respx.mock
async def test_capabilities_are_read_not_assumed(client):
    """This route is why effect and transition lists are no longer hard-coded."""
    respx.get(f"{BASE}/api/v1/capabilities").respond(
        json={
            "effects": ["Plasma", "Radar"],
            "transitions": ["Slide"],
            "overlays": ["rain"],
            "palettes": ["Ocean"],
            "audio": {"buzzer": True, "mp3": False},
        }
    )
    capabilities = await client.get_capabilities()
    assert capabilities.effects == ["Plasma", "Radar"]
    assert capabilities.audio["buzzer"] is True


@respx.mock
async def test_get_screen_returns_the_pixels_only(client):
    respx.get(f"{BASE}/api/v1/display/screen").respond(
        json={"width": 32, "height": 8, "pixels": [0, 16711680, 255]}
    )
    assert await client.get_screen() == [0, 16711680, 255]


@respx.mock
async def test_logs_hand_back_their_cursor(client):
    """Polling from the returned cursor is what keeps a log view cheap."""
    respx.get(f"{BASE}/api/v1/logs").respond(json={"next": 9, "lines": ["boot: AWTRIX NG"]})
    lines, cursor = await client.get_logs()
    assert lines == ["boot: AWTRIX NG"]
    assert cursor == 9


# -- Apps ---------------------------------------------------------------------


@respx.mock
async def test_builtin_apps_are_never_claimed_as_ours(client):
    """The failure this guards against deleted a display's apps twice on the
    previous project. `origin` is what makes it checkable rather than
    inferred from a name."""
    respx.get(f"{BASE}/api/v1/apps").respond(
        json=[
            {"name": "Time", "origin": "builtin"},
            {"name": "Battery", "origin": "builtin"},
            {"name": f"{APP_PREFIX}000007", "origin": "pushed"},
            {"name": "someone-elses", "origin": "pushed"},
        ]
    )
    assert await client.list_managed_apps() == [f"{APP_PREFIX}000007"]


@respx.mock
async def test_a_builtin_named_like_ours_is_still_not_ours(client):
    """Belt and braces: ownership needs both the origin and the name."""
    respx.get(f"{BASE}/api/v1/apps").respond(
        json=[{"name": f"{APP_PREFIX}000001", "origin": "builtin"}]
    )
    assert await client.list_managed_apps() == []


@respx.mock
async def test_push_uses_put_on_the_pushed_route(client):
    route = respx.put(f"{BASE}/api/v1/apps/pushed/ng000001").respond(json={"ok": True})
    await client.push_app("ng000001", NgPayload(text="hi", text_color="#fff"))
    assert route.calls.last.request.read() == b'{"text":"hi","textColor":"#fff"}'


@respx.mock
async def test_delete_targets_the_plain_app_route(client):
    """Deleting is `/apps/<name>`, not `/apps/pushed/<name>` — and measured on
    hardware, it matches the exact name: pushing zz1, zz12 and zz1x then
    deleting zz1 left the other two standing."""
    route = respx.delete(f"{BASE}/api/v1/apps/ng000001").respond(json={"ok": True})
    await client.delete_app("ng000001")
    assert route.called


@respx.mock
async def test_switch_names_the_app_in_the_body(client):
    route = respx.put(f"{BASE}/api/v1/apps/active").respond(json={"ok": True})
    await client.switch_to("Time")
    assert route.calls.last.request.read() == b'{"name":"Time"}'


@respx.mock
async def test_a_notification_goes_to_its_own_route(client):
    route = respx.post(f"{BASE}/api/v1/notifications").respond(json={"ok": True})
    await client.notify(NgNotification(text="ding", wakeup=True))
    assert b'"wakeup":true' in route.calls.last.request.read()


# -- Icons --------------------------------------------------------------------


@respx.mock
async def test_an_icon_already_installed_is_not_downloaded_again(client):
    respx.get(f"{BASE}/api/v1/files").respond(
        json={"files": [{"name": "55274.gif"}], "usedBytes": 1, "totalBytes": 524288}
    )
    upload = respx.post(f"{BASE}/api/v1/files")
    assert await client.ensure_icon("55274") is True
    assert not upload.called


@respx.mock
async def test_the_device_is_listed_once_per_client(client):
    """One listing per display per scheduler tick, not one per widget."""
    listing = respx.get(f"{BASE}/api/v1/files").respond(
        json={"files": [{"name": "55274.gif"}, {"name": "12061.gif"}]}
    )
    await client.ensure_icon("55274")
    await client.ensure_icon("12061")
    assert listing.call_count == 1


async def test_a_non_numeric_icon_is_left_alone(client):
    """A name is a file the user put there themselves; guessing would be wrong."""
    assert await client.ensure_icon("my-own-icon") is True
    assert await client.ensure_icon(None) is False


@respx.mock
async def test_installing_an_icon_posts_it_to_the_icons_directory(client):
    respx.get(f"{BASE}/api/v1/files").respond(json={"files": []})
    respx.get("https://developer.lametric.com/content/apps/icon_thumbs/55274").respond(
        200, content=b"GIF89a-fake", headers={"content-type": "image/gif"}
    )
    upload = respx.post(f"{BASE}/api/v1/files").respond(json={"ok": True})

    assert await client.ensure_icon("55274") is True

    request = upload.calls.last.request
    assert request.url.params["dir"] == "/ICONS"
    body = request.read()
    # The filename carries no directory: the folder is a query parameter now,
    # where AWTRIX 3 wanted "ICONS/55274.gif" inside the field.
    assert b'filename="55274.gif"' in body
    assert b'name="file"' in body
    await client.aclose()


@respx.mock
async def test_file_listing_reports_what_is_left(client):
    """Icons, melodies, palettes and scripts share one 512 KB partition, so an
    icon can fail to install because of something else entirely."""
    respx.get(f"{BASE}/api/v1/files").respond(
        json={"files": [], "usedBytes": 40960, "totalBytes": 524288}
    )
    listing = await client.list_files()
    assert listing.free_bytes == 483328
