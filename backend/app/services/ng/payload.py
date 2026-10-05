"""Model of the JSON sent to an AWTRIX NG display.

Every key here was **probed against a real TC001** running NG 1.1.2 rather
than copied from the documentation: the firmware answers 422 naming the
offending field, which makes the device its own reference. The probe log lives
in `docs/ng-api/payload-keys.md`.

Two consequences of that probing shape this module.

**The key set is small, and it is not the AWTRIX 3 one renamed.** Several keys
that looked like obvious camelCase translations do not exist at all: there is
no `center`, `noScroll`, `scrollSpeed`, `textOffset`, `topText`, `rainbow`,
`background`, `pos`, `blinkText`, `fadeText`, `bar`, `line` or `gradient`.
Scrolling moved into a `scroll` object, the background became
`backgroundColor`, and bar/line became `barChart`/`lineChart`. Writing the
AWTRIX 3 name costs a 422, not a silent miss — which is the good news.

**Validation is strict but not uniform.** `textCase`, `iconMode`, `effect`,
`overlay`, `palette`, `scroll.*` and `draw` are all checked and refused.
`progress`, `repeat`, `barChart` and `lineChart` are **not**: the device
answered `{"ok": true}` to `{"progress": 500}` and to `{"barChart": "zz"}`.
So the constraints below are ours, not the firmware's, and they are what keeps
a bad value from reaching the matrix as something arbitrary.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Measured: `{"iconMode": "zz"}` -> must be one of "fixed", "pushOnce", "push".
IconMode = Literal["fixed", "pushOnce", "push"]

#: Measured: `{"textCase": "zz"}` -> must be one of "inherit", "upper", "asTyped".
TextCase = Literal["inherit", "upper", "asTyped"]

#: Measured: `{"font": "zz"}` -> must be one of "small", "large".
#:
#: Worth more than it sounds on a panel eight rows tall. `small` is the
#: default and draws five rows; `large` draws seven — and the seven it uses
#: are exactly the ones above the progress bar, so a number can fill the
#: display and still carry a bar underneath. Checked on hardware.
Font = Literal["small", "large"]

#: Draw commands the firmware knows. Measured one by one: "fill", "fillRect"
#: and "fillCircle" are *not* among them, they answer `unknown draw command`.
#: A command is an array with its name first — `["pixel", x, y, colour]` —
#: never an object: `{"type": "pixel"}` is refused with "each draw command
#: must be an array, name first".
DRAW_COMMANDS = frozenset({"pixel", "line", "rect", "circle", "bitmap", "text"})


class Scroll(BaseModel):
    """Per-app scrolling. The same shape the device uses in its own settings.

    An unknown sub-key is refused by name (`scroll.zz` -> "unknown field"), so
    there is no silent-typo risk here either. Values are left as free strings:
    the firmware refuses an unknown one with "unknown value", and hard-coding
    its enumerations would be exactly the kind of guessing `capabilities`
    exists to avoid.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str | None = None
    direction: str | None = None
    entry: str | None = None
    when_fits: str | None = Field(default=None, serialization_alias="whenFits")
    speed: int | None = Field(default=None, ge=0)
    gap: int | None = Field(default=None, ge=0)
    hold_ms: int | None = Field(default=None, ge=0, serialization_alias="holdMs")


class NgPayload(BaseModel):
    """Keys accepted by both a pushed app and a notification.

    Field names are snake_case; the firmware's camelCase lives only in the
    aliases, which is what keeps the wire format in one readable place.
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    # -- Text -----------------------------------------------------------------
    text: str | None = None
    text_case: TextCase | None = Field(default=None, serialization_alias="textCase")
    font: Font | None = None
    scroll: Scroll | None = None

    # -- Colours ---------------------------------------------------------------
    #: `color` is gone; this is the key that replaced it, and the single most
    #: common porting mistake from AWTRIX 3.
    text_color: str | None = Field(default=None, serialization_alias="textColor")
    background_color: str | None = Field(default=None, serialization_alias="backgroundColor")

    #: Either a built-in palette name or a list of colour stops. The firmware
    #: declares the names it knows in GET /api/v1/capabilities, so nothing is
    #: hard-coded here.
    palette: str | list[Any] | None = None

    # -- Icon ------------------------------------------------------------------
    icon: str | None = None
    icon_mode: IconMode | None = Field(default=None, serialization_alias="iconMode")

    # -- Charts and drawing ----------------------------------------------------
    bar_chart: list[int] | None = Field(default=None, serialization_alias="barChart")
    line_chart: list[int] | None = Field(default=None, serialization_alias="lineChart")
    #: Raw drawing primitives, each `[name, *args]`. Validated here because the
    #: firmware checks the command name but we would rather not post something
    #: it will refuse.
    draw: list[list[Any]] | None = None

    progress: int | None = Field(default=None, ge=0, le=100)
    progress_color: str | None = Field(default=None, serialization_alias="progressColor")
    progress_track_color: str | None = Field(
        default=None, serialization_alias="progressTrackColor"
    )

    # -- Display ---------------------------------------------------------------
    #: Milliseconds, not seconds. The `Ms` suffix is the rule across NG, and
    #: sending AWTRIX 3's `duration` gets a 422.
    duration_ms: int | None = Field(default=None, ge=0, serialization_alias="durationMs")
    lifetime_ms: int | None = Field(default=None, ge=0, serialization_alias="lifetimeMs")
    repeat: int | None = Field(default=None, ge=0)
    effect: str | None = None
    overlay: str | None = None

    @field_validator("draw")
    @classmethod
    def _known_draw_commands(cls, draw: list[list[Any]] | None) -> list[list[Any]] | None:
        """Refuse a draw command the firmware does not know, here rather than
        on the wire. A 422 arriving from the device mid-tick is a scheduler
        problem; a ValidationError at build time is a caller problem."""
        for index, command in enumerate(draw or []):
            if not command or not isinstance(command[0], str):
                raise ValueError(f"draw[{index}] must start with a command name")
            if command[0] not in DRAW_COMMANDS:
                known = ", ".join(sorted(DRAW_COMMANDS))
                raise ValueError(f"unknown draw command {command[0]!r} (known: {known})")
        return draw

    def to_json(self) -> dict[str, Any]:
        """The exact dict sent to the device.

        Null values are omitted rather than sent: every key is optional, and a
        null would be one more thing for the firmware to have an opinion about.
        """
        return self.model_dump(mode="json", exclude_none=True, by_alias=True)


class NgNotification(NgPayload):
    """A notification. Adds the six keys the pushed-app route refuses.

    Each was probed on both routes: `hold`, `stack`, `wakeup`, `sound`,
    `soundRtttl` and `soundLoop` answer `unknown key` on
    `PUT /api/v1/apps/pushed/<name>` and `{"ok": true}` here. Keeping them in a
    subclass means a widget payload cannot accidentally carry one.
    """

    hold: bool | None = None
    stack: bool | None = None
    wakeup: bool | None = None
    #: Name of a melody stored on the device, under /MELODIES.
    sound: str | None = None
    #: An inline RTTTL string. The firmware parses it and says where it broke:
    #: `missing ':' after the melody name (at offset 1)`.
    sound_rtttl: str | None = Field(default=None, serialization_alias="soundRtttl")
    sound_loop: bool | None = Field(default=None, serialization_alias="soundLoop")
