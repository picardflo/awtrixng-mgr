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


# -- The settings panel -------------------------------------------------------
#
# Found the same way as the device card, and after it: the TypeScript still
# described AWTRIX 3's settings — `volume`, an integer `transition_effect`,
# `time_format` and `date_format` as strftime strings — months of names after
# the backend had moved to NG's. It compiled. The panel would have shown a
# volume slider wired to a field that does not exist.


def test_the_settings_panel_matches_the_schema():
    """Field for field, both ways.

    Both directions on purpose. A key the browser asks for and never receives
    renders as nothing; a key the backend expects and never receives comes
    back as a default, quietly reverting a setting someone just changed.
    """
    from app.schemas.device_settings import DeviceSettings

    declared = declared_in_typescript("DeviceSettings")
    modelled = set(DeviceSettings.model_fields)

    assert declared - modelled == set(), (
        f"the panel asks for settings that do not exist: {sorted(declared - modelled)}"
    )
    assert modelled - declared == set(), (
        f"the backend offers settings the panel never shows: {sorted(modelled - declared)}"
    )


@pytest.mark.parametrize(
    "dead",
    # AWTRIX 3's names. Each one compiled and would have done nothing.
    #
    # `week_starts_monday` is **not** here, and was briefly: it looks like one
    # of these and is not. NG keeps it as `weekdayBar.startOnMonday`, nested
    # with the bar's own colours. A name surviving a migration is not the same
    # thing as a setting surviving it.
    ["volume", "time_format", "date_format", "show_weekday", "transition_effect_code"],
)
def test_no_awtrix3_setting_survives_in_the_panel(dead: str):
    assert dead not in declared_in_typescript("DeviceSettings")


def test_the_quiet_hours_panel_matches_its_schema():
    """Smaller, and worth the same check: it lost a field in the split, and a
    panel still sending `brightness` would be sending it nowhere."""
    from app.schemas.quiet import QuietHours

    declared = declared_in_typescript("QuietHours")
    assert declared == set(QuietHours.model_fields)
    assert "brightness" not in declared


# -- A label that describes some other setting --------------------------------
#
# Twice now, and neither time did anything complain. A toggle read
# "Semaine dès lundi" and switched the weekday display on; another read
# "Afficher le jour" and switched the month names. Both compiled, both read
# perfectly to someone opening the page, and both did the wrong thing — the
# same shape of defect as `{{ quality_code }}` on the previous project, which
# cost an evening.
#
# Nothing can check that a *translation* describes a field. What can be checked
# is that the key naming it is the field's own name, which is why the panel
# derives one from the other.

PANEL = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "features" / "devices" / "DeviceSettings.tsx"
)


def camel(field: str) -> str:
    head, *rest = field.split("_")
    return head + "".join(word.capitalize() for word in rest)


def toggles() -> list[tuple[str, str]]:
    """(translation key, field) for every Toggle in the settings panel."""
    source = PANEL.read_text(encoding="utf-8")
    return re.findall(
        r'label=\{t\("device\.settings\.(\w+)"\)\}\s*\n\s*checked=\{draft\.(\w+)\}',
        source,
    )


def test_the_panel_has_toggles_to_check():
    """Guards the regex above: a refactor that changes the shape would make
    every assertion below vacuously true."""
    assert len(toggles()) >= 6


def test_every_toggle_is_labelled_after_the_field_it_sets():
    wrong = [
        f"{key} sets {field} (expected device.settings.{camel(field)})"
        for key, field in toggles()
        if key != camel(field)
    ]
    assert not wrong, "a toggle is labelled after another setting: " + "; ".join(wrong)


def test_every_toggle_sets_a_field_that_exists():
    from app.schemas.device_settings import DeviceSettings

    unknown = {field for _, field in toggles()} - set(DeviceSettings.model_fields)
    assert not unknown, f"the panel toggles settings that do not exist: {sorted(unknown)}"


# -- Error codes the interface has to translate -------------------------------
#
# Every domain error carries a stable `code`, and the frontend translates it;
# the English message is only the fallback. So a code with no translation is
# an English sentence in a French interface — nothing breaks, nothing warns,
# and nobody notices until they read it.
#
# Nineteen were missing when this test was written, three of them added in
# this session.

MESSAGES_FR = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "messages.fr.ts"
)
MESSAGES_EN = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "messages.en.ts"
)


def backend_codes() -> set[str]:
    """Every `code="..."` raised anywhere in the application."""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).resolve().parents[1] / "app").rglob("*.py")
    )
    return set(re.findall(r'code="([a-z_]+\.[a-z_0-9.]+)"', source))


def translated(path: Path) -> set[str]:
    return set(re.findall(r'^  "([^"]+)":', path.read_text(encoding="utf-8"), re.M))


@pytest.mark.parametrize("catalogue", [MESSAGES_FR, MESSAGES_EN])
def test_every_error_code_can_be_translated(catalogue: Path):
    missing = sorted(backend_codes() - translated(catalogue))
    assert not missing, (
        f"{catalogue.name} has no entry for: {missing}. "
        "They reach the user as the backend's English fallback."
    )


# -- Display options with no control --------------------------------------
#
# `show_days` was added to the backend, given a default on the school widget,
# tested on hardware — and had **no switch in the builder**. So a widget
# created before it could never be given one, and Florian's was: he saw a
# solid progress bar and asked whether it worked.
#
# Nothing could have failed. The option existed, the renderer honoured it, the
# default applied to new widgets only. The gap was between a schema and a form,
# which is a seam no compiler watches either.

BUILDER = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "features" / "widgets" / "WidgetBuilder.tsx"
)

SHARED_FIELDS = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "MatrixTextFields.tsx"
)
REMINDER_FORM = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "features" / "reminders" / "ReminderForm.tsx"
)

#: Options the form sets without naming, or deliberately does not offer.
NOT_A_CONTROL = {
    # Set by the icon picker, not by a named field.
    "icon",
}


def controls_in(*paths: Path) -> set[str]:
    """The option names a form actually writes.

    **Not a substring search, which is how this test passed over a hole.** It
    looked for the field's name anywhere in the file, and `effect` appears in
    the comment "on mount this effect would overwrite" — so `effect`, `repeat`
    and `progress_background` were reported as controlled while none of the
    three could be set from the interface at all. A widget could only be given
    an effect by someone posting JSON by hand.

    The sibling test below already parsed `patch({ name` to find the opposite
    fault. Both directions now read the same thing.
    """
    written = re.compile(r"(?:patch|onChange)\(\{\s*(\w+)")
    found: set[str] = set()
    for path in paths:
        found |= set(written.findall(path.read_text(encoding="utf-8")))
    return found


def test_every_display_option_has_a_control():
    """Both files are read as text: the point is precisely that no type
    system connects them."""
    from app.schemas.widget_data import DisplayOptions

    offered = controls_in(BUILDER, SHARED_FIELDS)
    missing = sorted(
        name
        for name in DisplayOptions.model_fields
        if name not in NOT_A_CONTROL and name not in offered
    )
    assert not missing, (
        f"these display options cannot be set from the builder: {missing}. "
        "A widget created before one of them can never be given it."
    )


def test_a_reminder_offers_the_same_presentation_as_a_widget():
    """The gap Florian found: « comme pour les widgets, je dois pouvoir
    choisir la taille du texte ».

    A reminder had three of these and a widget had ten, and the reason was
    that the reminder form had been written first and never caught up. Both
    now render `MatrixTextFields`, so the only way to break this is to stop —
    which is what this checks.
    """
    from app.schemas.matrix_text import MatrixText

    offered = controls_in(SHARED_FIELDS)
    missing = sorted(name for name in MatrixText.model_fields if name not in offered)
    assert not missing, f"no control for: {missing}"

    for form in (BUILDER, REMINDER_FORM):
        assert "MatrixTextFields" in form.read_text(encoding="utf-8"), (
            f"{form.name} no longer uses the shared block — the two will drift "
            "again, which is the whole reason it exists."
        )


def test_a_reminder_sets_no_option_the_backend_drops():
    """`ReminderUpdate` ignores an unknown key instead of refusing it, so a
    stale control here would be a silence rather than a 422."""
    from app.schemas.reminder import ReminderCreate

    written = controls_in(REMINDER_FORM)
    unknown = sorted(written - set(ReminderCreate.model_fields))
    assert not unknown, f"the reminder form writes fields that do not exist: {unknown}"


def test_the_builder_sets_no_option_that_does_not_exist():
    """The other direction: a control writing a field the backend drops.

    `DisplayOptions` forbids unknown keys, so this would be a 422 on save
    rather than a silence — but finding it here beats finding it on a form
    that refuses to submit.
    """
    from app.schemas.widget_data import DisplayOptions

    form = BUILDER.read_text(encoding="utf-8")
    written = set(re.findall(r"patch\(\{\s*(\w+)", form))
    unknown = sorted(written - set(DisplayOptions.model_fields))
    assert not unknown, f"the builder writes options that do not exist: {unknown}"
