"""The transport's job is to turn the firmware's answers into ours.

The 422 case carries most of the weight: NG names the field it refused, and
that name is the single most useful thing the device can tell a user. Losing
it to a generic "device unreachable" would throw away the main ergonomic gain
of the migration.
"""

import httpx
import pytest
import respx

from app.core.errors import DeviceRejectedError, DeviceUnreachableError
from app.services.ng.transport import HttpTransport

BASE = "http://display.test"


@pytest.fixture
def transport():
    return HttpTransport("display.test")


@respx.mock
async def test_get_prefixes_every_route(transport):
    route = respx.get(f"{BASE}/api/v1/device").respond(json={"version": "1.1.2"})
    assert await transport.get("/device") == {"version": "1.1.2"}
    assert route.called


@respx.mock
async def test_a_body_always_carries_its_content_type(transport):
    """Measured: a body without `Content-Type: application/json` answers 415,
    and the request simply never takes effect."""
    route = respx.put(f"{BASE}/api/v1/apps/pushed/x").respond(json={"ok": True})
    await transport.request("PUT", "/apps/pushed/x", json={"text": "hi"})
    assert route.calls.last.request.headers["content-type"] == "application/json"


@respx.mock
async def test_a_delete_sends_no_body(transport):
    """AWTRIX 3 deleted by posting an empty body, so empty had a second
    meaning. NG has DELETE, and the ambiguity goes with it."""
    route = respx.delete(f"{BASE}/api/v1/apps/x").respond(200, json={"ok": True})
    await transport.request("DELETE", "/apps/x")
    assert route.calls.last.request.content == b""


@respx.mock
async def test_422_names_the_field(transport):
    respx.put(f"{BASE}/api/v1/apps/pushed/x").respond(
        422,
        json={
            "error": {
                "code": "validationFailed",
                "message": 'unknown key "color"',
                "field": "color",
            }
        },
    )
    with pytest.raises(DeviceRejectedError) as raised:
        await transport.request("PUT", "/apps/pushed/x", json={"color": "#fff"})

    assert raised.value.field == "color"
    assert "color" in raised.value.message
    assert raised.value.code == "device.rejected"


@respx.mock
async def test_a_422_without_the_expected_body_is_still_a_rejection(transport):
    """The request arrived and was understood. Reporting it as an unreachable
    display would send whoever reads the log looking at the network."""
    respx.put(f"{BASE}/api/v1/apps/pushed/x").respond(422, text="nope")
    with pytest.raises(DeviceRejectedError) as raised:
        await transport.request("PUT", "/apps/pushed/x", json={"a": 1})
    assert raised.value.field is None


@respx.mock
async def test_401_is_an_authentication_problem(transport):
    respx.get(f"{BASE}/api/v1/device").respond(401)
    with pytest.raises(DeviceUnreachableError) as raised:
        await transport.get("/device")
    assert raised.value.code == "device.auth_failed"


@respx.mock
async def test_an_empty_answer_is_not_an_error(transport):
    respx.delete(f"{BASE}/api/v1/apps/x").respond(200, content=b"")
    assert await transport.request("DELETE", "/apps/x") is None


@respx.mock
async def test_html_means_this_is_not_an_ng_display(transport):
    """An AWTRIX 3 at this address answers its own web UI on an unknown path.
    Saying so is more useful than a JSON parse error."""
    respx.get(f"{BASE}/api/v1/device").respond(200, html="<html>AWTRIX</html>")
    with pytest.raises(DeviceUnreachableError) as raised:
        await transport.get("/device")
    assert raised.value.code == "device.not_awtrix_ng"


@respx.mock
async def test_a_connection_failure_names_the_target(transport):
    respx.get(f"{BASE}/api/v1/device").mock(side_effect=httpx.ConnectTimeout(""))
    with pytest.raises(DeviceUnreachableError) as raised:
        await transport.get("/device")
    # ConnectTimeout stringifies to "", so the class name has to stand in.
    assert "ConnectTimeout" in raised.value.message
    assert raised.value.params["target"] == f"{BASE}:80"


@respx.mock
async def test_an_upload_uses_the_file_field(transport):
    """The multipart field is `file`; AWTRIX 3 called it `image`."""
    route = respx.post(f"{BASE}/api/v1/files").respond(json={"ok": True})
    await transport.post_file(
        "/files",
        field="file",
        filename="55274.gif",
        content=b"GIF89a",
        content_type="image/gif",
        params={"dir": "/ICONS"},
    )
    body = route.calls.last.request.content
    assert b'name="file"' in body
    assert b"55274.gif" in body
    assert route.calls.last.request.url.params["dir"] == "/ICONS"
