"""The display's own settings, the ones worth a form.

NG exposes forty-two through `PATCH /api/v1/settings`. These are the ones
someone actually wants to change, and — this is new — every one of them is
**validated by the firmware, which names the field and lists the values it
accepts**. Every range and enumeration below was read from that, not guessed:

    {"brightness": 256}        → out of range
    {"dateOrder": "ZZZ"}       → must be one of: dayMonthYear monthDayYear yearMonthDay
    {"timeSeparatorMode":"Z"}  → must be one of: steady blink pulse

**What the migration improved here.** AWTRIX 3 took time and date formats as
raw `strftime` strings, so the form offered a list of nine incantations and
hoped. NG takes structured choices — order, separator, year length — which a
form can present as what they are. And `soundEnabled` finally exists as a
switch of its own, where AWTRIX 3 had only a volume.

Deliberately absent, and each for a reason:

- `gamma`, `colorCorrection`, `colorTint`, `saturation` — colour calibration.
  The firmware validates the numbers, but a matrix made unreadable from a web
  form is still unreadable, and nothing here says what a good value is.
- `blockNavigation` — locks the display's own buttons. Worth its own decision,
  with a warning, rather than a checkbox in a list.
- `dfplayerVolume`, `mp3Volume`, `radioVolume`, `radioMeta` — hardware a TC001
  does not have. `GET /api/v1/capabilities` says so per display
  (`audio: {buzzer: true, mp3: false, radio: false}`), so offering them would
  mean offering controls for absent hardware.
- The per-app colours (`timeColor`, `dateColor`, …) — they belong with the
  built-in apps panel, not here.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

#: Each of these was read out of a 422. The firmware lists its own vocabulary,
#: so none of it is transcribed from documentation.
TIME_SEPARATORS = ("steady", "blink", "pulse")
DATE_ORDERS = ("dayMonthYear", "monthDayYear", "yearMonthDay")
DATE_SEPARATORS = ("dot", "slash", "dash")
YEAR_MODES = ("none", "twoDigit", "fourDigit")
TRANSITION_DIRECTIONS = ("normal", "reverse")


class DeviceSettings(BaseModel):
    """What the display does, as opposed to what awtrixng-mgr puts on it."""

    # -- Brightness -----------------------------------------------------------
    #: With this on, the firmware recomputes the brightness from the light
    #: sensor and whatever `brightness` holds is overwritten within seconds.
    #: The form says so rather than offering a slider that does nothing.
    auto_brightness: bool = True
    #: 0–255. Measured: 256 answers "out of range".
    brightness: int = Field(default=120, ge=0, le=255)

    #: The floor and ceiling automatic brightness moves between. **New in NG,
    #: and they replace a whole feature.**
    #:
    #: AWTRIX 3 clamped its automatic brightness at 2 with no way to change it
    #: — too bright for a bedroom — so the previous project carried a schedule
    #: that turned the sensor off at dusk, forced a lower level, remembered
    #: what it had overwritten and put it back at dawn. Measured on a TC001 in
    #: a dark room: the panel sits exactly on `minBrightness`, and lowering it
    #: from 10 took the live brightness down with it, 10 → 9 → 8.
    #:
    #: One setting, no schedule, no saved state — and it reads the room rather
    #: than the clock, so it dims when someone actually goes to bed.
    #:
    #: These two live in `/api/v1/system`, not `/api/v1/settings`, and that
    #: route takes **PUT** where the other takes PATCH.
    min_brightness: int = Field(default=10, ge=0, le=255)
    max_brightness: int = Field(default=220, ge=0, le=255)

    # -- Sound ----------------------------------------------------------------
    #: New in NG. AWTRIX 3 could only be silenced by writing a volume of zero,
    #: which then had to be remembered and put back.
    sound_enabled: bool = True
    #: 0–100, measured. AWTRIX 3's was 0–30, which read as a percentage and
    #: was not one; here it finally is.
    buzzer_volume: int = Field(default=80, ge=0, le=100)

    # -- Rotation -------------------------------------------------------------
    #: Seconds an app stays up — but only an app that did not ask for a
    #: duration of its own, and every widget awtrixng-mgr pushes asks. So this
    #: governs the built-in apps, not yours. Stored in seconds and converted:
    #: the firmware's key is `appDurationMs`.
    app_seconds: int = Field(default=7, ge=1, le=120)
    auto_transition: bool = True
    #: A name, not a number. AWTRIX 3 took an integer 0–10 it documented
    #: nowhere; NG names its twenty-two transitions and lists them in
    #: `GET /api/v1/capabilities`, so the form can offer exactly the ones this
    #: display has.
    transition_effect: str = "Slide"
    transition_direction: Literal[TRANSITION_DIRECTIONS] = "normal"  # type: ignore[valid-type]
    transition_ms: int = Field(default=1000, ge=0, le=10000)

    # -- Scrolling ------------------------------------------------------------
    #: The display-wide default. A widget may override it per app.
    scroll_speed: int = Field(default=100, ge=0, le=500)

    # -- Formats --------------------------------------------------------------
    uppercase: bool = True
    celsius: bool = True
    time_24h: bool = True
    time_leading_zero: bool = True
    time_show_seconds: bool = False
    time_separator: Literal[TIME_SEPARATORS] = "pulse"  # type: ignore[valid-type]
    date_order: Literal[DATE_ORDERS] = "dayMonthYear"  # type: ignore[valid-type]
    date_separator: Literal[DATE_SEPARATORS] = "dot"  # type: ignore[valid-type]
    date_year: Literal[YEAR_MODES] = "twoDigit"  # type: ignore[valid-type]
    date_show_weekday: bool = False
    date_month_names: bool = False

    # -- The weekday bar ------------------------------------------------------
    #
    # The row of marks along the bottom of the Time app. Nested under
    # `weekdayBar` in the firmware, with its own colours — only the two that
    # change what is shown are offered here.
    weekday_bar: bool = True
    week_starts_monday: bool = True


#: Our name -> the firmware's. One table, read both ways, so a key cannot be
#: spelled one way when reading and another when writing.
KEYS: dict[str, str] = {
    "auto_brightness": "autoBrightness",
    "brightness": "brightness",
    "sound_enabled": "soundEnabled",
    "buzzer_volume": "buzzerVolume",
    "auto_transition": "autoTransition",
    "transition_effect": "transitionEffect",
    "transition_direction": "transitionDirection",
    "transition_ms": "transitionDurationMs",
    "uppercase": "uppercase",
    "celsius": "useCelsius",
    "time_24h": "time24h",
    "time_leading_zero": "timeLeadingZero",
    "time_show_seconds": "timeShowSeconds",
    "time_separator": "timeSeparatorMode",
    "date_order": "dateOrder",
    "date_separator": "dateSeparator",
    "date_year": "dateYearMode",
    "date_show_weekday": "dateShowWeekday",
    "date_month_names": "dateMonthNames",
}

#: Our name -> the firmware's, for the keys that live in `/api/v1/system`
#: rather than in `/api/v1/settings`. Two routes, two verbs, one form.
SYSTEM_KEYS: dict[str, str] = {
    "min_brightness": "minBrightness",
    "max_brightness": "maxBrightness",
}

#: Settings that do not map one-to-one. Kept apart from KEYS so the common
#: case stays a plain table.
#:
#: `app_seconds` is seconds here and milliseconds on the wire — the unit stays
#: human in the form. `scroll_speed` lives inside the `scroll` object, which
#: has to be sent whole-ish rather than as a flat key.
MS_PER_SECOND = 1000


def read(raw: dict[str, Any], system: dict[str, Any] | None = None) -> DeviceSettings:
    """What the display reports, as far as it can be trusted.

    A missing or malformed key falls back to the model's default rather than
    failing the whole read: a firmware that gains or loses one setting must
    not take the panel down.

    `system` is the answer of `/api/v1/system`, where the brightness floor
    lives. Optional, so a caller that only wants the display settings pays for
    one request rather than two.
    """
    known = DeviceSettings()
    values: dict[str, Any] = {}
    for name, key in KEYS.items():
        if key in raw:
            values[name] = raw[key]
    for name, key in SYSTEM_KEYS.items():
        if system and key in system:
            values[name] = system[key]
    if "appDurationMs" in raw:
        try:
            values["app_seconds"] = max(1, int(raw["appDurationMs"]) // MS_PER_SECOND)
        except (TypeError, ValueError):
            pass
    scroll = raw.get("scroll")
    if isinstance(scroll, dict) and "speed" in scroll:
        values["scroll_speed"] = scroll["speed"]
    bar = raw.get("weekdayBar")
    if isinstance(bar, dict):
        if "show" in bar:
            values["weekday_bar"] = bar["show"]
        if "startOnMonday" in bar:
            values["week_starts_monday"] = bar["startOnMonday"]

    try:
        return DeviceSettings(**values)
    except ValueError:
        # One bad value should not lose all the good ones.
        kept: dict[str, Any] = {}
        for name, value in values.items():
            try:
                DeviceSettings(**{**kept, name: value})
                kept[name] = value
            except ValueError:
                continue
        return DeviceSettings(**kept) if kept else known


def changes(current: DeviceSettings, wanted: DeviceSettings) -> dict[str, Any]:
    """Only what differs, in the firmware's own spelling.

    Partial by design: `PATCH /api/v1/settings` changes only the keys it
    receives, measured — sending the lot would rewrite forty-two settings to
    change one.
    """
    diff: dict[str, Any] = {
        KEYS[name]: getattr(wanted, name)
        for name in KEYS
        if getattr(current, name) != getattr(wanted, name)
    }
    if current.app_seconds != wanted.app_seconds:
        diff["appDurationMs"] = wanted.app_seconds * MS_PER_SECOND
    if current.scroll_speed != wanted.scroll_speed:
        # Nested, and the firmware refuses an unknown sub-key by name.
        diff["scroll"] = {"speed": wanted.scroll_speed}

    bar: dict[str, Any] = {}
    if current.weekday_bar != wanted.weekday_bar:
        bar["show"] = wanted.weekday_bar
    if current.week_starts_monday != wanted.week_starts_monday:
        bar["startOnMonday"] = wanted.week_starts_monday
    if bar:
        # Partial inside the object too: the firmware keeps the four colours
        # it is not sent, and sending them would freeze someone's choice.
        diff["weekdayBar"] = bar
    return diff


def system_changes(current: DeviceSettings, wanted: DeviceSettings) -> dict[str, Any]:
    """The same, for the keys that live in `/api/v1/system`.

    Kept apart because the route is a different one and takes a different
    verb. Mixing them would send `minBrightness` to `/settings`, which answers
    `unknown field` — politely, but it would not take effect.
    """
    return {
        SYSTEM_KEYS[name]: getattr(wanted, name)
        for name in SYSTEM_KEYS
        if getattr(current, name) != getattr(wanted, name)
    }


class DeviceSettingsResult(BaseModel):
    ok: bool
    message: str
    code: str
    settings: DeviceSettings
    #: Which firmware keys were written. Empty when nothing differed.
    applied: list[str] = Field(default_factory=list)
