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

    if display.show_progress and data.progress is not None:
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

    if display.show_series != "none" and data.series:
        values = [int(round(value)) for value in data.series]
        fields["bar_chart" if display.show_series == "bar" else "line_chart"] = values

    if lifetime_seconds is not None:
        # NG has no `lifetimeMode`: the key answers `unknown key`. AWTRIX 3's
        # option of marking a stale app rather than removing it is therefore
        # gone, and an app that stops being refreshed simply disappears.
        fields["lifetime_ms"] = lifetime_seconds * 1000

    return NgPayload(**fields)


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
