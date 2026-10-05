"""The names the browser asks for must be the names the backend sends.

This is the one seam no compiler watches. The frontend's `DeviceState`
interface is a *description* of the backend's JSON, not a derivation of it, so
TypeScript checks it against itself and is satisfied. The backend's tests check
Python against Python and are satisfied too. Between the two, nothing.

That gap shipped twice, and the second time is the instructive one.

**First**, the device card still read `bat`, `temp`, `hum` and `wifi_signal` —
AWTRIX 3's names — after the backend had moved to NG's. It compiled, the tests
passed, every tile showed a dash, and Florian found it in his browser.

**Then this test was written and it, too, was wrong.** It compared the
TypeScript against `DeviceState.model_fields`, that is against the *Python*
names. But FastAPI serialises a response model with `by_alias=True`, so the
wire carried `batteryPercent` while the test approved `battery_percent`. Four
tiles came back — exactly the four fields that had no alias — and the rest
stayed empty. A green test over a broken page is worse than no test.

So the comparison below is made against **what the response actually
serialises to**, produced the way FastAPI produces it. The lesson generalises:
a contract test must assert the wire, never the model that is supposed to
describe it.

Crude, deliberately: a generated client would be the grown-up answer, and
would also be a build step to maintain for one interface.
"""

import re
from pathlib import Path

import pytest

from app.services.ng.models import AppEntry, DeviceState

CLIENT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "client.ts"


def declared_in_typescript(interface: str) -> set[str]:
    """Field names of a TS interface, read out of the source."""
    source = CLIENT.read_text(encoding="utf-8")
    match = re.search(rf"export interface {interface} \{{(.*?)\n\}}", source, re.S)
    assert match, f"interface {interface} not found in {CLIENT.name}"
    return set(re.findall(r"^\s*(\w+)\??:", match.group(1), re.M))


def on_the_wire() -> set[str]:
    """The keys a response actually carries.

    `by_alias=True` is not a choice here: it is what FastAPI does to every
    response model, and therefore what the browser receives.
    """
    sample = DeviceState.model_validate(
        {"batteryPercent": 93, "wifiRssi": -63, "lightLevel": 2.8, "ldrRaw": 115,
         "temperature": 29.1, "humidity": 36.2, "fps": 42, "uptimeSeconds": 7193,
         "freeHeapBytes": 102044, "currentApp": "Time", "matrixPower": True,
         "batteryVoltage": 4.14, "brightness": 10, "version": "1.1.2",
         "hostname": "awtrix-cl2", "ipAddress": "192.168.11.211", "uid": "b0cbd8a1b560",
         "boardType": "awtrixng", "resetReason": "software", "lowBattery": False}
    )
    return set(sample.model_dump(by_alias=True))


def test_the_card_asks_for_fields_the_response_actually_carries():
    """Against the wire, not against the model.

    The earlier version of this test compared with `model_fields` and passed
    while the page was blank.
    """
    unknown = declared_in_typescript("DeviceState") - on_the_wire()
    assert not unknown, (
        f"the frontend asks for keys the response does not carry: {sorted(unknown)}. "
        "They will render as a dash, silently."
    )


def test_the_response_speaks_snake_case():
    """The firmware's camelCase stops at the client.

    `validation_alias` reads it; a plain `alias` would also *write* it, since
    FastAPI serialises by alias — which is the bug this pins shut.
    """
    camel = [key for key in on_the_wire() if any(c.isupper() for c in key)]
    assert not camel, f"these keys reach the browser in camelCase: {sorted(camel)}"


@pytest.mark.parametrize(
    "dead",
    # The AWTRIX 3 names, each of which produced an empty tile.
    ["bat", "temp", "hum", "wifi_signal", "lux", "bri", "uptime", "ram", "app"],
)
def test_no_awtrix3_field_name_survives_in_the_client(dead: str):
    assert dead not in declared_in_typescript("DeviceState")


def test_the_readings_the_card_shows_all_reach_the_browser():
    """The six tiles and the footer line, named explicitly.

    Listed rather than inferred: this is the set someone compares against the
    display's own interface, and dropping one should be a decision, not a
    diff nobody noticed.
    """
    shown = {
        "battery_percent", "battery_voltage",
        "wifi_rssi",
        "light_level", "ldr_raw",
        "temperature", "humidity",
        "fps", "brightness",
        "uptime_seconds", "free_heap_bytes", "current_app", "matrix_power",
    }
    missing = shown - on_the_wire()
    assert not missing, f"the card shows readings the response does not carry: {sorted(missing)}"


# -- Every other interface describing a firmware model ------------------------
#
# Florian's question, after the second time: "if other pages are empty the
# same way, say so". These are the remaining interfaces whose shape comes from
# the firmware rather than from our database, which is where the two naming
# conventions can meet. Listed, so adding one is a decision.

FIRMWARE_BACKED = [("DeviceApp", AppEntry)]


@pytest.mark.parametrize(("interface", "model"), FIRMWARE_BACKED)
def test_a_firmware_backed_interface_matches_the_wire(interface: str, model: type):
    sample = model.model_validate({"name": "Time", "origin": "builtin", "inLoop": True,
                                   "enabled": True, "slot": 0, "present": True})
    unknown = declared_in_typescript(interface) - set(sample.model_dump(by_alias=True))
    assert not unknown, (
        f"{interface} asks for keys the response does not carry: {sorted(unknown)}"
    )


@pytest.mark.parametrize(("interface", "model"), FIRMWARE_BACKED)
def test_a_firmware_backed_response_speaks_snake_case(interface: str, model: type):
    sample = model.model_validate({"name": "Time", "origin": "builtin", "inLoop": True})
    camel = [key for key in sample.model_dump(by_alias=True) if any(c.isupper() for c in key)]
    assert not camel, f"{interface} receives camelCase keys: {sorted(camel)}"
