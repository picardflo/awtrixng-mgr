"""Reminders against a real display: the notification route and the buzzer.

    AWTRIXNG_TEST_HOST=awtrix-cl2.home.lan .venv/bin/python -m pytest -m device \
        tests/test_device_reminders.py

**These make a noise.** They play a short melody on the clock they are pointed
at. Short and never looped, but someone in the room will hear them.

What can and cannot be proved from here. A test cannot listen, so "the buzzer
sounded" is out of reach. Three things stand in for it, and together they are
most of the way there:

- the firmware **parses** the RTTTL and says where it broke — a malformed
  melody comes back as a 422 naming the offset, which only a real parser can
  do;
- `wakeup` was expected to be measurable, and the measurement said no — see
  the test at the foot of this file;
- the device **declares** a buzzer in its capabilities, and exposes
  `soundEnabled` and `buzzerVolume` as settings — neither of which AWTRIX 3
  had.
"""

import asyncio
import os

import pytest

from app.core.errors import DeviceRejectedError
from app.core.protected import is_protected
from app.models import Reminder
from app.services.ng.client import NgClient
from app.services.ng.transport import HttpTransport
from app.services.scheduler import reminders as reminder_pass

pytestmark = pytest.mark.device

#: Short, and never looped. Three notes.
MELODY = "test:d=8,o=6,b=180:c,e,g"

SETTLE_SECONDS = 1.5


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
        await ng.aclose()


def a_reminder(**extra) -> Reminder:
    from datetime import time

    return Reminder(
        name="Essai",
        message="DEBOUT",
        at=time(6, 30),
        weekdays="0,1,2,3,4,5,6",
        duration_seconds=3,
        **extra,
    )


# -- The hardware says it can -------------------------------------------------


async def test_the_display_declares_a_buzzer(client):
    """`audio.buzzer` — AWTRIX 3 never said whether a clock had one, so the
    previous project offered a melody field and hoped."""
    capabilities = await client.get_capabilities()
    assert capabilities.audio.get("buzzer") is True


async def test_sound_is_a_setting_of_its_own(client):
    """New in NG. AWTRIX 3 could only be silenced by writing a volume of zero,
    which then had to be remembered and put back."""
    settings = await client.get_settings()
    assert "soundEnabled" in settings
    assert 0 <= settings["buzzerVolume"] <= 100


# -- The melody ---------------------------------------------------------------


async def test_a_reminder_with_its_melody_is_accepted_and_drawn(client):
    """The whole path: the model, the projection, the wire, the matrix."""
    payload = reminder_pass.payload_for(a_reminder(melody=MELODY))
    body = payload.to_json()
    assert body["soundRtttl"] == MELODY, "the melody must survive the projection"

    await client.notify(payload)
    await asyncio.sleep(SETTLE_SECONDS)
    assert any(await client.get_screen()), "a notification that lights nothing is not one"


async def test_the_firmware_really_parses_the_melody(client):
    """The strongest evidence available without ears.

    A malformed RTTTL comes back naming the offset it choked on. Only a parser
    answers like that — a firmware that ignored the field would say nothing,
    which is exactly what AWTRIX 3 did.
    """
    with pytest.raises(DeviceRejectedError) as raised:
        await client._t.request(
            "POST", "/notifications", json={"text": "x", "soundRtttl": "pas-une-melodie"}
        )
    assert raised.value.field == "soundRtttl"
    assert "offset" in raised.value.message


async def test_a_silenced_reminder_carries_no_melody(client):
    """Bedroom mode drops the melody at the source rather than muting the
    clock: silencing the whole display would stop everything else that buzzes
    and need putting back afterwards."""
    quiet = reminder_pass.payload_for(a_reminder(melody=MELODY), silent=True).to_json()
    assert "soundRtttl" not in quiet
    assert quiet["text"] == "DEBOUT", "it still appears, it simply makes no sound"

    await client.notify(reminder_pass.payload_for(a_reminder(melody=MELODY), silent=True))
    await asyncio.sleep(SETTLE_SECONDS)


# -- Waking the matrix --------------------------------------------------------


async def test_wakeup_does_not_light_a_panel_that_is_off(client):
    """Pinned because it is a surprise, not because it is right.

    Reminders carry `wakeup` on the stated principle that an alert nobody can
    see is not an alert. Measured on NG 1.1.2, the key is **accepted and does
    nothing**:

    - panel off: the notification is accepted, the framebuffer draws it — 36
      pixels lit — and `power` stays false. It is heard and never seen.
    - brightness at zero: `wakeup` does not raise it either, with or without
      the key. Tested both ways.

    So nothing in the firmware will light a dark display for an alert. The day
    1.1.x gains that, this test fails and the finding is out of date — which
    is the point of pinning it.
    """
    was_on = (await client.get_display())["power"]
    try:
        await client.set_power(False)
        await client.notify(reminder_pass.payload_for(a_reminder()))
        await asyncio.sleep(SETTLE_SECONDS)

        assert (await client.get_display())["power"] is False, (
            "wakeup now lights the panel — good news, and this test is stale"
        )
        # The firmware did compose the frame; only the LEDs stayed off.
        assert any(await client.get_screen())
    finally:
        await client.set_power(was_on)


async def test_the_reminder_pass_lights_the_panel_itself(client):
    """End to end, on hardware: panel off, reminder sent, panel on.

    This is the whole point of the measurement above. `wakeup` is inert, so
    the application switches the panel on before notifying — Florian's call,
    5 October 2026 — and leaves it on, because restoring the previous state
    would hide the alert at the moment it matters.
    """
    was_on = (await client.get_display())["power"]
    try:
        await client.set_power(False)
        assert (await client.get_display())["power"] is False

        from datetime import datetime

        fired = await reminder_pass.send(a_reminder(), {1: client}, datetime.now())
        await asyncio.sleep(SETTLE_SECONDS)

        assert fired.sent_to == [1]
        assert (await client.get_display())["power"] is True, (
            "the pass must light the panel: the firmware does not"
        )
        assert any(await client.get_screen())
    finally:
        await client.set_power(was_on)
