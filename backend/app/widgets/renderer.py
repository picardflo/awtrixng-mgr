"""Turn a connector's output into an AWTRIX NG payload.

A pure function: no I/O, no clock, no network. That is what makes the preview
work without a device and the tests work without a service.

It is also the only place that knows both sides — the connector knows nothing
about matrices, the NG client knows nothing about connectors.

**What the move to NG changed here.** Durations became milliseconds, `color`
became `textColor`, `background` became `backgroundColor`, the integer
`pushIcon` became a named `iconMode`, and everything about scrolling moved
into a `scroll` object. The three options with no NG equivalent — `center`,
`rainbow` and `no_scroll` as a flag — are gone from `DisplayOptions` rather
than translated into something that does not exist.
"""

from app.connectors.weather import wmo
from app.schemas.widget_data import DisplayOptions, WidgetData
from app.services.ng.payload import NgPayload, Scroll
from app.widgets import template

#: Firmware defaults. A key equal to one of these is omitted so the payload
#: stays minimal and the display's own settings keep applying.
_FIRMWARE_DEFAULTS = {
    "font": "small",
    "scroll_speed": 100,
    "icon_mode": "fixed",
    "text_case": "inherit",
    "scroll_mode": "wrap",
    "scroll_when_fits": "static",
}


def render(
    data: WidgetData,
    display: DisplayOptions,
    *,
    lifetime_seconds: int | None = None,
) -> NgPayload | None:
    """Build the payload, or None when the app should be removed.

    None is returned when the connector reports no data and the user asked to
    hide the widget rather than leave a stale value on the matrix.
    """
    if data.status == "empty" and display.hide_when_empty:
        return None

    fields: dict[str, object] = {
        # Accents are stripped here, at the boundary with the hardware, so the
        # preview shows exactly what the matrix will.
        "text": template.for_matrix(template.render(display.text, data.values)),
        "duration_ms": display.duration * 1000,
        "icon": (display.icon or data.hint_icon) if display.show_icon else None,
        "text_color": display.color or data.hint_color,
        "background_color": display.background,
        "effect": display.effect,
        # Same rule as the icon: the user's choice, else the
        # connector's suggestion, else nothing.
        "overlay": (
            (display.overlay or data.hint_overlay) if display.show_overlay else None
        ),
        "repeat": display.repeat,
    }

    # Only send what differs from the firmware default.
    if display.icon_mode != _FIRMWARE_DEFAULTS["icon_mode"]:
        fields["icon_mode"] = display.icon_mode
    if display.text_case != _FIRMWARE_DEFAULTS["text_case"]:
        fields["text_case"] = display.text_case
    if display.font != _FIRMWARE_DEFAULTS["font"]:
        fields["font"] = display.font

    scroll = _scroll(display)
    if scroll is not None:
        fields["scroll"] = scroll

    if display.show_days and data.days:
        # Drawn, not a progress bar: the two share the bottom row and a widget
        # showing both would overwrite one with the other.
        fields["draw"] = _day_segments(
            data.days,
            display.color or data.hint_color,
            with_icon=bool(fields.get("icon")),
        )
    elif display.show_progress and data.progress is not None:
        fields["progress"] = data.progress
        # Left empty, the bar takes the colour the connector proposes — the
        # same rule the text already follows. Without it the bar kept the
        # firmware's own default and clashed with a text the service had
        # coloured.
        colour = display.progress_color or data.hint_color
        if colour:
            fields["progress_color"] = colour
        # And the track follows the bar: a dark wash of the same hue rather
        # than a flat black that belongs to nothing. One palette, chosen once,
        # carrying through the text, the bar and its track.
        #
        # Black when there is no colour to wash, and **never** nothing: the
        # firmware paints the unfilled part WHITE, so a 2 % bar lights the
        # whole bottom row and reads as full. Measured on v0.98, and the
        # reason this key is always sent.
        fields["progress_track_color"] = (
            display.progress_background or wmo.dim(colour) or "#000000"
        )


    if lifetime_seconds is not None:
        # NG has no `lifetimeMode`: the key answers `unknown key`. AWTRIX 3's
        # option of marking a stale app rather than removing it is therefore
        # gone, and an app that stops being refreshed simply disappears.
        fields["lifetime_ms"] = lifetime_seconds * 1000

    return NgPayload(**fields)


#: The firmware's own weekday bar, read off the panel under the Date app:
#: seven runs of three pixels, one apart, from column 2, on the bottom row.
#: Reproduced rather than invented, so a widget and the Date app align pixel
#: for pixel when they follow each other in the rotation.
DAY_ROW = 7
DAY_GAP = 1
DAY_WIDE = 3
DAY_FIRST_COLUMN = 2

#: **With an icon, three pixels per day does not fit**, and the icon wins:
#: it occupies columns 0 to 8 of every row including the bottom one, so the
#: first two segments were painted over. Measured, not predicted — the first
#: version of this drew a bar the icon then ate.
#:
#: Seven runs of two with a gap is 20 columns, which lands at 10..29 of the
#: 23 an icon leaves. Florian said two pixels per day before any of this was
#: written; the firmware's three is what fits when nothing else is there.
DAY_NARROW = 2
DAY_FIRST_COLUMN_WITH_ICON = 10

#: An 8x8 icon and the column of space after it.
ICON_COLUMNS = 9

#: The firmware's own two, measured: #ffffff for the day you are in, #666666
#: for the rest. A day still to come takes the widget's colour instead, which
#: is what makes "two school days left" readable at a glance.
COLOUR_TODAY = "#ffffff"
COLOUR_OFF = "#2a2a2a"


def _day_segments(
    days: list[str], colour: str | None, *, with_icon: bool
) -> list[list[object]]:
    """Seven draw commands, one per day.

    `past` is a dark wash of the widget's colour, `school` the colour itself,
    `today` white, and a day off dimmer still. Four shades rather than two:
    the firmware only has to say which day it is, this has to say how much of
    the week is left.
    """
    width = DAY_NARROW if with_icon else DAY_WIDE
    first = DAY_FIRST_COLUMN_WITH_ICON if with_icon else DAY_FIRST_COLUMN
    base = colour or "#ffffff"
    shade = {
        "today": COLOUR_TODAY,
        "school": base,
        "past": wmo.dim(base, 0.25) or COLOUR_OFF,
        "off": COLOUR_OFF,
    }
    return [
        [
            "rect",
            first + index * (width + DAY_GAP),
            DAY_ROW,
            width,
            1,
            shade.get(state, COLOUR_OFF),
        ]
        for index, state in enumerate(days[:7])
    ]


def _scroll(display: DisplayOptions) -> Scroll | None:
    """The scroll object, or None when every part of it is the default.

    Sending `{"scroll": {}}` would be noise; sending a full object would
    override display-wide settings the user may have set on the device itself.
    """
    fields: dict[str, object] = {}
    if display.scroll_mode != _FIRMWARE_DEFAULTS["scroll_mode"]:
        fields["mode"] = display.scroll_mode
    if display.scroll_speed != _FIRMWARE_DEFAULTS["scroll_speed"]:
        fields["speed"] = display.scroll_speed
    if display.scroll_when_fits != _FIRMWARE_DEFAULTS["scroll_when_fits"]:
        fields["when_fits"] = display.scroll_when_fits
    return Scroll(**fields) if fields else None


def lifetime_for(refresh_seconds: int) -> int:
    """How long a pushed app stays valid without an update.

    Three missed refreshes, with a floor so a fast widget does not vanish on a
    single hiccup. This is the firmware-side safety net: if awtrixng-mgr stops,
    apps go away on their own instead of showing dead data forever.
    """
    return max(60, refresh_seconds * 3)
