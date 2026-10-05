"""The names the browser asks for must be the names the backend sends.

This is the one seam no compiler watches. The frontend's `DeviceState`
interface is a *description* of the backend's JSON, not a derivation of it, so
TypeScript checks it against itself and is satisfied. The backend's tests check
Python against Python and are satisfied too. Between the two, nothing.

That gap shipped: the device card still read `bat`, `temp`, `hum` and
`wifi_signal` — AWTRIX 3's names — after the backend had moved to NG's. It
compiled, the tests passed, and every tile on the page showed a dash. Florian
found it in his browser.

So the contract is asserted here, by reading the TypeScript and comparing it
with the Pydantic model. Crude, deliberately: a generated client would be the
grown-up answer, and would also be a build step to maintain for one interface.
"""

import re
from pathlib import Path

import pytest

from app.services.ng.models import DeviceState

CLIENT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "client.ts"


def declared_in_typescript(interface: str) -> set[str]:
    """Field names of a TS interface, read out of the source."""
    source = CLIENT.read_text(encoding="utf-8")
    match = re.search(rf"export interface {interface} \{{(.*?)\n\}}", source, re.S)
    assert match, f"interface {interface} not found in {CLIENT.name}"
    return set(re.findall(r"^\s*(\w+)\??:", match.group(1), re.M))


def test_the_card_asks_for_fields_the_backend_sends():
    """Every name in the TypeScript must exist on the Python model."""
    unknown = declared_in_typescript("DeviceState") - set(DeviceState.model_fields)
    assert not unknown, (
        f"the frontend asks for fields the backend does not send: {sorted(unknown)}. "
        "They will render as a dash, silently."
    )


@pytest.mark.parametrize(
    "dead",
    # The AWTRIX 3 names, each of which produced an empty tile.
    ["bat", "temp", "hum", "wifi_signal", "lux", "bri", "uptime", "ram", "app"],
)
def test_no_awtrix3_field_name_survives_in_the_client(dead: str):
    assert dead not in declared_in_typescript("DeviceState")


def test_the_readings_the_card_shows_are_all_modelled():
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
    missing = shown - set(DeviceState.model_fields)
    assert not missing, f"the card shows readings the model does not carry: {sorted(missing)}"
