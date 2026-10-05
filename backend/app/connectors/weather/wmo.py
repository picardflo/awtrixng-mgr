"""WMO weather codes 0-99, as returned by Open-Meteo in `weather_code`.

Labels are prose that can end up on the matrix through a template, so they
follow the installation's display language (`app.core.language`) rather than
the browser's. The **slug** never changes: it is what a template compares
against, and a condition that renamed itself on a language switch would break
every widget quietly.
"""

from app.core import language

#: code -> (stable slug, English label)
CODES: dict[int, tuple[str, str]] = {
    0: ("clear", "Clear"),
    1: ("mainly_clear", "Mainly clear"),
    2: ("partly_cloudy", "Partly cloudy"),
    3: ("overcast", "Overcast"),
    45: ("fog", "Fog"),
    48: ("rime_fog", "Rime fog"),
    51: ("drizzle_light", "Light drizzle"),
    53: ("drizzle", "Drizzle"),
    55: ("drizzle_dense", "Heavy drizzle"),
    56: ("freezing_drizzle_light", "Freezing drizzle"),
    57: ("freezing_drizzle_dense", "Freezing drizzle"),
    61: ("rain_slight", "Light rain"),
    63: ("rain", "Rain"),
    65: ("rain_heavy", "Heavy rain"),
    66: ("freezing_rain_light", "Freezing rain"),
    67: ("freezing_rain_heavy", "Freezing rain"),
    71: ("snow_slight", "Light snow"),
    73: ("snow", "Snow"),
    75: ("snow_heavy", "Heavy snow"),
    77: ("snow_grains", "Snow grains"),
    80: ("showers_slight", "Light showers"),
    81: ("showers", "Showers"),
    82: ("showers_violent", "Violent showers"),
    85: ("snow_showers_slight", "Light snow showers"),
    86: ("snow_showers_heavy", "Snow showers"),
    95: ("thunderstorm", "Thunderstorm"),
    96: ("thunderstorm_hail", "Thunderstorm with hail"),
    99: ("thunderstorm_hail_heavy", "Thunderstorm with heavy hail"),
}

_UNKNOWN = ("unknown", "Unknown")

#: slug -> label, per language. English lives in CODES above; anything missing
#: here falls back to it, so a new code is usable before it is translated.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "clear": "Dégagé",
        "mainly_clear": "Plutôt dégagé",
        "partly_cloudy": "Partiellement nuageux",
        "overcast": "Couvert",
        "fog": "Brouillard",
        "rime_fog": "Brouillard givrant",
        "drizzle_light": "Bruine légère",
        "drizzle": "Bruine",
        "drizzle_dense": "Bruine forte",
        "freezing_drizzle_light": "Bruine verglaçante",
        "freezing_drizzle_dense": "Bruine verglaçante",
        "rain_slight": "Pluie faible",
        "rain": "Pluie",
        "rain_heavy": "Forte pluie",
        "freezing_rain_light": "Pluie verglaçante",
        "freezing_rain_heavy": "Pluie verglaçante",
        "snow_slight": "Neige faible",
        "snow": "Neige",
        "snow_heavy": "Forte neige",
        "snow_grains": "Grésil",
        "showers_slight": "Averses faibles",
        "showers": "Averses",
        "showers_violent": "Averses violentes",
        "snow_showers_slight": "Averses de neige faibles",
        "snow_showers_heavy": "Averses de neige",
        "thunderstorm": "Orage",
        "thunderstorm_hail": "Orage et grêle",
        "thunderstorm_hail_heavy": "Orage et forte grêle",
        "unknown": "Inconnu",
    },
}


def describe(code: int | None) -> tuple[str, str]:
    """(stable slug, label in the display language).

    Never raises on an unexpected value: an unknown code is described as such
    rather than blanking the widget.
    """
    try:
        slug, english = _UNKNOWN if code is None else CODES[int(code)]
    except (KeyError, TypeError, ValueError):
        slug, english = _UNKNOWN
    return slug, language.localise(TRANSLATIONS, slug, english)


#: Temperature thresholds and the colour each band gets, coldest first.
#: Answers the "colour by temperature" option of §6.
#: Anchors, not thresholds: the colour between two of them is interpolated.
#: The five are the ones this project has always used, placed at the middle of
#: the range each one used to cover rather than at its edge.
_TEMPERATURE_STOPS: tuple[tuple[float, str], ...] = (
    (-10.0, "#7ec8ff"),  # deep cold — pale blue
    (5.0, "#4aa8ff"),    # cold — blue
    (15.0, "#3ddc84"),   # mild — green
    (24.0, "#f5a524"),   # warm — amber
    (34.0, "#f4526b"),   # hot — red
)


def colour_for_temperature(celsius: float | None) -> str | None:
    """A colour on a continuous scale, interpolated between the stops below.

    Bands came first, and had two faults a mock-up made obvious. Half a degree
    across a boundary flipped green to amber — 19.5 and 20.5 looked like
    different weather. And eight degrees inside one band rendered identically:
    -8 °C and 0 °C were the same pale blue.

    What bands did well is name a category — it freezes, it is cold, it is
    mild — and that is kept by anchoring the same five colours rather than
    inventing a palette. Below the first stop and above the last, the colour
    holds: there is no sensible blue beyond pale blue.
    """
    if celsius is None:
        return None

    if celsius <= _TEMPERATURE_STOPS[0][0]:
        return _TEMPERATURE_STOPS[0][1]
    if celsius >= _TEMPERATURE_STOPS[-1][0]:
        return _TEMPERATURE_STOPS[-1][1]

    for (low, cold), (high, warm) in zip(
        _TEMPERATURE_STOPS, _TEMPERATURE_STOPS[1:], strict=False
    ):
        if low <= celsius <= high:
            return _mix(cold, warm, (celsius - low) / (high - low))
    return _TEMPERATURE_STOPS[-1][1]


#: Humidity, anchored the way a person experiences it rather than evenly.
#:
#: The interesting range is narrow — between 40 % and 60 % nothing is worth
#: saying, and the colour barely moves. What matters is the two ends: air dry
#: enough to crack your lips, and air that makes 25 °C feel like 30.
_HUMIDITY_STOPS: tuple[tuple[float, str], ...] = (
    (20.0, "#f5a524"),   # dry — amber
    (40.0, "#3ddc84"),   # comfortable — green
    (60.0, "#3ddc84"),   # still comfortable: the plateau is deliberate
    (80.0, "#4aa8ff"),   # humid — blue
    (95.0, "#7e6bff"),   # saturated — violet, which nothing else here uses
)


def colour_for_humidity(percent: float | None) -> str | None:
    """A colour on the same kind of scale as the temperature one.

    The plateau between 40 and 60 is the point: a widget whose colour drifts
    through every shade of green across the comfortable range is noise. It
    should sit still while nothing is happening and move when something is.
    """
    return _on_scale(_HUMIDITY_STOPS, percent)


def _on_scale(
    stops: tuple[tuple[float, str], ...], value: float | None
) -> str | None:
    """Interpolate `value` between anchored stops, holding at both ends."""
    if value is None:
        return None
    if value <= stops[0][0]:
        return stops[0][1]
    if value >= stops[-1][0]:
        return stops[-1][1]
    for (low, cold), (high, warm) in zip(stops, stops[1:], strict=False):
        if low <= value <= high:
            if high == low:
                return cold
            return _mix(cold, warm, (value - low) / (high - low))
    return stops[-1][1]


def dim(colour: str | None, fraction: float = 0.18) -> str | None:
    """The same colour, far darker. What a progress track should be.

    Pure black under a coloured bar is readable and says nothing; the
    firmware's own white default is worse, because at 2 % the whole bottom row
    lights up and reads as full. A dark wash of the bar's own colour keeps the
    two obviously related — which is the point of choosing a palette at all.
    """
    if not colour:
        return None
    return _mix("#000000", colour, fraction)


def _mix(cold: str, warm: str, fraction: float) -> str:
    """Blend two `#rrggbb` strings, channel by channel.

    Linear in sRGB rather than in a perceptual space: the stops are close
    enough that the difference is invisible on eight pixels, and a colour
    science dependency for a weather widget would be a poor trade.
    """
    a = tuple(int(cold[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(warm[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(
        f"{round(x + (y - x) * fraction):02x}" for x, y in zip(a, b, strict=True)
    )


# ---------------------------------------------------------------------------
# Animated icons
#
# LaMetric ids, all verified as 8x8 animated GIFs. 12181-12198 are a coherent
# weather set designed together; the thunderstorm had to come from elsewhere.
# awtrixng-mgr installs them on the device on demand, so the user never has to
# hand-download an icon through the AWTRIX web interface.
#
# Nothing is redistributed here: these are numbers, and the files stay on
# LaMetric until a device asks for one (prior-art §5).
# ---------------------------------------------------------------------------

#: A falling drop that splashes, 21 frames. Chosen by Florian for the humidity
#: widget: it reads as water *in the air* rather than as weather to come,
#: which is the distinction that widget exists for.
ICON_HUMIDITY = 26543

ICON_CLEAR_DAY = 12182
ICON_CLEAR_NIGHT = 12181
ICON_PARTLY_CLOUDY_DAY = 12183
ICON_PARTLY_CLOUDY_NIGHT = 12195
#: 12197 "Cloudy" was the obvious pick by name, but at eight pixels it is a
#: diagonal smudge in the corner — someone looking at it asked what it was
#: meant to be. 12246 draws a cloud centred in the frame.
ICON_CLOUDY = 12246
ICON_FOG = 12196
ICON_RAIN = 12186
ICON_SNOW = 12185
ICON_SLEET = 12198
ICON_WIND = 12194
ICON_THUNDERSTORM = 11428

#: Icons that already say "precipitation": when the sky is one of these, it is
#: more precise than anything a probability could suggest — snow stays snow.
PRECIPITATION_ICONS: frozenset[int] = frozenset(
    {ICON_RAIN, ICON_SNOW, ICON_SLEET, ICON_THUNDERSTORM}
)

#: Above this, rain is worth announcing even under a clear sky; below it, the
#: sky itself is the better picture. Fifty is where forecasters put "likely",
#: and the number has to be somewhere.
LIKELY_PERCENT = 50


def precipitation_icon(
    code: int | None, probability: float | None = None, *, is_day: bool = True
) -> str:
    """The icon for a rain widget.

    Driven by the probability rather than by the sky alone. A first version
    showed rain whenever it was not already raining, which put a downpour next
    to "0 %" on a clear afternoon — the widget contradicting its own number.

    Three cases, in order: it is already precipitating, so show what kind; rain
    is likely, so show rain; otherwise show the sky, which is the useful half
    of the message when the other half is "0 %".
    """
    sky = icon_for(code, is_day=is_day)
    if sky and int(sky) in PRECIPITATION_ICONS:
        return sky
    if probability is not None and probability >= LIKELY_PERCENT:
        return str(ICON_RAIN)
    return sky or str(ICON_RAIN)


#: Three states, the same three `precipitation_icon` branches on. Muted when
#: it is dry, because a bright blue "0 %" over a sun contradicts both the
#: icon and the number it is printed next to.
DRY = "#8a9aa8"
LIKELY = "#4aa8ff"
FALLING = "#2d7fd3"


def colour_for_precipitation(code: int | None, probability: float | None) -> str:
    """The colour for a rain widget, branching exactly where the icon does.

    Written against `precipitation_icon` deliberately: the two answered the
    same question differently, so at 0 % the widget showed a sun in bright
    blue. Whatever rule the icon follows, the colour follows it too — if one
    gains a case, so does the other, and the test below holds them together.
    """
    sky = icon_for(code, is_day=True)
    if sky and int(sky) in PRECIPITATION_ICONS:
        return FALLING
    if probability is not None and probability >= LIKELY_PERCENT:
        return LIKELY
    return DRY


#: Every icon this connector may ask for, so a caller can pre-install the set.
WEATHER_ICONS: tuple[int, ...] = (
    ICON_CLEAR_DAY,
    ICON_CLEAR_NIGHT,
    ICON_PARTLY_CLOUDY_DAY,
    ICON_PARTLY_CLOUDY_NIGHT,
    ICON_CLOUDY,
    ICON_FOG,
    ICON_RAIN,
    ICON_SNOW,
    ICON_SLEET,
    ICON_WIND,
    ICON_THUNDERSTORM,
)

#: Codes that do not depend on daylight.
_BY_CODE: dict[int, int] = {
    3: ICON_CLOUDY,
    45: ICON_FOG,
    48: ICON_FOG,
    51: ICON_RAIN,
    53: ICON_RAIN,
    55: ICON_RAIN,
    56: ICON_SLEET,
    57: ICON_SLEET,
    61: ICON_RAIN,
    63: ICON_RAIN,
    65: ICON_RAIN,
    66: ICON_SLEET,
    67: ICON_SLEET,
    71: ICON_SNOW,
    73: ICON_SNOW,
    75: ICON_SNOW,
    77: ICON_SNOW,
    80: ICON_RAIN,
    81: ICON_RAIN,
    82: ICON_RAIN,
    85: ICON_SNOW,
    86: ICON_SNOW,
    95: ICON_THUNDERSTORM,
    96: ICON_THUNDERSTORM,
    99: ICON_THUNDERSTORM,
}

#: Codes with a day and a night variant.
_BY_DAYLIGHT: dict[int, tuple[int, int]] = {
    0: (ICON_CLEAR_DAY, ICON_CLEAR_NIGHT),
    1: (ICON_CLEAR_DAY, ICON_CLEAR_NIGHT),
    2: (ICON_PARTLY_CLOUDY_DAY, ICON_PARTLY_CLOUDY_NIGHT),
}


def icon_for(code: int | None, *, is_day: bool = True) -> str | None:
    """Animated icon id for a WMO code, as the string AWTRIX expects."""
    try:
        numeric = int(code)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

    if numeric in _BY_DAYLIGHT:
        day, night = _BY_DAYLIGHT[numeric]
        return str(day if is_day else night)

    chosen = _BY_CODE.get(numeric)
    return str(chosen) if chosen is not None else None


# ---------------------------------------------------------------------------
# Weather overlays — AWTRIX NG only
# ---------------------------------------------------------------------------
#
# NG draws weather *over* the app, from a list it declares in
# `GET /api/v1/capabilities`: drizzle, frost, rain, snow, storm, thunder.
#
# The fit with the WMO families this module already distinguishes is almost
# one to one, which is not luck — the firmware's six were plainly chosen
# against the same vocabulary. So this is one more column in a table that
# already decides the icon and the colour, not a new mechanism.
#
# **Measured over a real widget** (icon + "18°" + colour), eight frames each,
# counting pixels added and pixels of the text disturbed:
#
#     drizzle    1 / 3 / 6 added     5 of 62 text pixels
#     snow       3 / 5 / 7           8
#     rain       7 / 10 / 19        10
#     storm     17 / 25 / 33        12
#     thunder   14 / 22 / 31        17
#     frost     52 / 52 / 52         7   — and it does not move
#
# Two of those numbers changed a decision.
#
# `frost` is not falling weather at all: it is a **static frame** around the
# edges. It barely touches the text, but it occupies the bottom row, which is
# where a progress bar is drawn. Fine on a temperature widget, wrong on one
# showing a bar.
#
# `thunder` disturbs more of the text than anything else — a quarter of it.
# Kept anyway for 95-99: a thunderstorm is precisely the moment a glance at
# the clock should be interrupted. `storm` is the quieter alternative and is
# left to whoever prefers it.

#: Overlays the firmware draws. Names as it spells them, refused otherwise.
OVERLAY_DRIZZLE = "drizzle"
OVERLAY_RAIN = "rain"
OVERLAY_SNOW = "snow"
OVERLAY_STORM = "storm"
OVERLAY_THUNDER = "thunder"
OVERLAY_FROST = "frost"

#: WMO code -> overlay. Only weather that *falls* or *freezes* is here: fog,
#: cloud and clear sky have nothing to draw, and an overlay on a clear day
#: would be a lie told in pixels.
_OVERLAY_BY_CODE: dict[int, str] = {
    51: OVERLAY_DRIZZLE, 53: OVERLAY_DRIZZLE, 55: OVERLAY_DRIZZLE,
    # Freezing drizzle and freezing rain: the frost frame says "it is sticking"
    # in a way a rain overlay cannot.
    56: OVERLAY_FROST, 57: OVERLAY_FROST,
    61: OVERLAY_RAIN, 63: OVERLAY_RAIN, 65: OVERLAY_RAIN,
    66: OVERLAY_FROST, 67: OVERLAY_FROST,
    71: OVERLAY_SNOW, 73: OVERLAY_SNOW, 75: OVERLAY_SNOW, 77: OVERLAY_SNOW,
    80: OVERLAY_RAIN, 81: OVERLAY_RAIN, 82: OVERLAY_RAIN,
    85: OVERLAY_SNOW, 86: OVERLAY_SNOW,
    95: OVERLAY_THUNDER, 96: OVERLAY_THUNDER, 99: OVERLAY_THUNDER,
}

#: Every overlay this module may ask for, so a caller can check them against
#: what the display declares it can draw.
OVERLAYS: frozenset[str] = frozenset(_OVERLAY_BY_CODE.values())


def overlay_for(code: int | None) -> str | None:
    """The overlay for a WMO code, or None when there is nothing to draw.

    None is the common answer and the right default: most codes are cloud and
    sunshine, and a matrix that drizzles under a clear sky is worse than one
    that draws nothing.
    """
    try:
        return _OVERLAY_BY_CODE.get(int(code))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
