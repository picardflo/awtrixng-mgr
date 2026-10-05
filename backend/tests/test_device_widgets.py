"""Every widget type, rendered and pushed to a real display.

    AWTRIXNG_TEST_HOST=awtrix-cl2.home.lan .venv/bin/python -m pytest -m device \
        tests/test_device_widgets.py

Why this exists. The widgets came over from a project that spoke to AWTRIX 3,
and carrying them across on the strength of the unit tests would have proved
only that they still produce the payload *we* expect. It would not prove the
firmware accepts it, and NG refuses what it does not understand.

So each one is rendered from its own sample data, pushed, and the matrix read
back. Three things can go wrong and each is told apart:

- the payload is **refused** — a 422 naming the field, the useful case;
- the payload is accepted and the matrix stays **dark** — accepted and
  meaningless, which is the failure AWTRIX 3 used to give silently;
- the matrix lights up, which is as far as an automated check can go. Whether
  it is *legible* is a judgement, so the test prints the pixels for a human.

The sample data is the connector's own, so no service is called and the test
needs no network beyond the display.
"""

import os

import pytest

from app.connectors import registry
from app.core.protected import is_protected
from app.schemas.widget_data import DisplayOptions
from app.services.ng.client import NgClient
from app.services.ng.transport import HttpTransport
from app.widgets.renderer import render

pytestmark = pytest.mark.device

#: Pushed under a name of its own so a leftover cannot be mistaken for a widget.
TEST_APP = "pytestwidget"

#: Long enough that the app is still up when the screen is read, and that the
#: transition has finished. Measured: the default transition runs for a second.
HOLD_MS = 60_000
SETTLE_SECONDS = 2.2


def widget_types() -> list[str]:
    registry.load_all()
    return [w.type for d in registry.descriptors() for w in d.widgets]


@pytest.fixture
def host() -> str:
    target = os.environ.get("AWTRIXNG_TEST_HOST", "")
    if not target:
        pytest.skip("set AWTRIXNG_TEST_HOST to run the device tests")
    if is_protected(target):
        pytest.fail(f"{target} is a display in service: these tests write, refusing to run")
    return target


@pytest.fixture
async def client(host):
    ng = NgClient(HttpTransport(host))
    try:
        yield ng
    finally:
        try:
            await ng.delete_app(TEST_APP)
        except Exception:  # noqa: BLE001 — cleanup must not mask a real failure
            pass
        await ng.aclose()


def art(pixels: list[int], width: int = 32, height: int = 8) -> str:
    return "\n".join(
        "".join("#" if pixels[row * width + col] else "." for col in range(width))
        for row in range(height)
    )


@pytest.mark.parametrize("widget_type", widget_types())
async def test_a_widget_reaches_the_matrix(client, widget_type: str):
    """Rendered from its sample data, pushed, and read back off the panel."""
    import asyncio

    descriptor = registry.widget_descriptor(widget_type)
    assert descriptor is not None, f"{widget_type} is not registered"

    display = descriptor.default_display or DisplayOptions()
    payload = render(descriptor.sample_data, display)
    assert payload is not None, "sample data should never render to nothing"

    # The icon the connector suggests has to be on the device, or the firmware
    # draws the text alone — which would still light the matrix and hide the
    # problem.
    body = payload.to_json()
    if body.get("icon"):
        await client.ensure_icon(body["icon"])

    payload.duration_ms = HOLD_MS
    await client.push_app(TEST_APP, payload)
    await client.switch_to(TEST_APP)
    await asyncio.sleep(SETTLE_SECONDS)

    pixels = await client.get_screen()
    print(f"\n--- {widget_type}  {body}\n{art(pixels)}")

    assert any(pixels), (
        f"{widget_type} was accepted by the firmware and drew nothing. "
        f"Payload: {body}"
    )
