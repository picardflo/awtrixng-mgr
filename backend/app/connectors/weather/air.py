"""Air quality, UV and pollen, from Open-Meteo's air-quality API.

A **second host** — `air-quality-api.open-meteo.com` — so this is one more
request than the forecast, unlike the sun widget which rode along on the
existing one. The three widgets below share it between them.

No account and no key, like the forecast.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import ConnectorError

ENDPOINT = "https://air-quality-api.open-meteo.com/v1/air-quality"

#: Asked for in one call, split between three widgets.
VARIABLES = (
    "european_aqi",
    "pm10",
    "pm2_5",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "carbon_monoxide",
    "uv_index",
    "alder_pollen",
    "birch_pollen",
    "grass_pollen",
    "ragweed_pollen",
)

#: Air quality moves slowly and the model publishes hourly.
CACHE_SECONDS = 1800


@dataclass(frozen=True, slots=True)
class Band:
    """One step of a scale: what it is called, and what colour says so.

    No icon. Both scales used to carry one per band, and both have been
    measured out of it — see `AQI_ICON` and `UV_ICON`. A band is a colour,
    and the colour reaches the panel three times over: the text, the bar and
    the bar's track.
    """

    #: Never translated — what a template compares against.
    code: str
    colour: str


def _pick(bands: tuple[tuple[float, Band], ...], value: float | None, last: Band) -> Band:
    if value is None:
        return last
    for ceiling, band in bands:
        if value < ceiling:
            return band
    return last


# ---------------------------------------------------------------------------
# European AQI
#
# Thresholds read from Open-Meteo's own documentation, which states them as
# the European Environment Agency's bands "revised in 2024". Two properties
# matter and are easy to get wrong:
#
#   - the index is the *highest* of the five pollutant indices, not an average
#   - it is not a scale out of a hundred: above 100 it keeps going
#
# ---------------------------------------------------------------------------

#: One icon for the widget, not one per band.
#:
#: Six icons spelling "AQI" stood here, each in its band's colour — three
#: letters on eight pixels, chosen on the theory that beside a bare number
#: they would say what the number was. Read back off the panel they are a
#: smear, and Florian asked what the orange blob was meant to be. The theory
#: was right and the execution impossible: eight pixels do not hold three
#: letters.
#:
#: So the word moved into the text, where the font can draw it, and the icon
#: went to the one thing it does well: 7789 "Air Quality", a gust blowing
#: through, animated. The icon says *air*, the colour says *how good*. This is
#: how `weather.humidity` is built — a fixed blue drop, the reading in the
#: colour — and the two widgets now read as siblings.
AQI_ICON = 7789

#: The colours outlived the icons they were sampled from, and are now the
#: scale itself: green, yellow, orange, red, purple, brown.
#:
#: The European Environment Agency's own 2024 legend was the obvious
#: replacement and was measured against this one on the panel. Its best band
#: is a cyan (#50f0e6) which, beside the gust, merges with it into one
#: blue-green smear — the number stops being separable from the icon. The
#: ramp below keeps them apart at every step, which on 32 pixels outranks
#: matching a legend nobody is holding up next to the clock.
AQI_BANDS: tuple[tuple[float, Band], ...] = (
    (20, Band("good", "#8cfe0c")),
    (40, Band("fair", "#fcfe1c")),
    (60, Band("moderate", "#f48a1c")),
    (80, Band("poor", "#f40214")),
    (100, Band("very_poor", "#9402fc")),
)
AQI_WORST = Band("extremely_poor", "#845a24")

AQI_ENGLISH = {
    "good": "Good",
    "fair": "Fair",
    "moderate": "Moderate",
    "poor": "Poor",
    "very_poor": "Very poor",
    "extremely_poor": "Extremely poor",
}
AQI_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "good": "Bon",
        "fair": "Moyen",
        "moderate": "Dégradé",
        "poor": "Mauvais",
        "very_poor": "Très mauvais",
        "extremely_poor": "Extrêmement mauvais",
    }
}


def aqi_band(value: float | None) -> Band:
    return _pick(AQI_BANDS, value, AQI_WORST)


# ---------------------------------------------------------------------------
# UV index — the WHO scale, which is a published standard.
# ---------------------------------------------------------------------------

#: 75377 "Sunny_Good": a sun whose rays pulse, animated.
#:
#: It replaces 64310, which drew a yellow corner of sun above the letters U
#: and V in magenta. Two colours of its own, neither of them the band's, and
#: on the panel the letters are unreadable — the text beside it says "UV"
#: already, in a font built for it.
#:
#: Fixed yellow, deliberately: a sun is yellow at every index, and the band
#: is said by the colour of "UV 7" and of the bar under it. Checked at both
#: ends of the scale — a yellow sun beside green text at UV 2, beside orange
#: at UV 7 — and it reads as a sun either way.
UV_ICON = 75377

#: Where the index stops having bands and becomes "extreme". A bar is drawn
#: against this, and anything above fills it — which is what extreme means.
UV_CEILING = 11.0

UV_BANDS: tuple[tuple[float, Band], ...] = (
    (3, Band("low", "#6fd504")),
    (6, Band("moderate", "#f9ff1b")),
    (8, Band("high", "#f78818")),
    (11, Band("very_high", "#f60017")),
)
UV_EXTREME = Band("extreme", "#9000fe")

UV_ENGLISH = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "very_high": "Very high",
    "extreme": "Extreme",
}
UV_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "low": "Faible",
        "moderate": "Modéré",
        "high": "Élevé",
        "very_high": "Très élevé",
        "extreme": "Extrême",
    }
}


def uv_band(value: float | None) -> Band:
    return _pick(UV_BANDS, value, UV_EXTREME)


# ---------------------------------------------------------------------------
# Pollen
#
# The figure is the information. Open-Meteo publishes grains per cubic metre
# and **no bands at all**, and the published scales contradict one another — a
# clinical one opens the birch season at 10 grains where a consumer forecast
# still calls 14 "low".
#
# An earlier version invented a per-family ladder from the most widely
# published scale. It is gone. Someone allergic knows the number they react
# to; a word chosen here would have sat between them and it, and would have
# been wrong for somebody.
#
# What is kept is what the API itself distinguishes: which plant. The icon
# follows the species, and its colour is sampled from that icon.
# ---------------------------------------------------------------------------

POLLEN_ICON_TREE = 52669
POLLEN_ICON_GRASS = 52670
POLLEN_ICON_WEED = 36978

#: slug -> (field in the response, icon, colour sampled from that icon)
POLLENS: dict[str, tuple[str, int, str]] = {
    "alder": ("alder_pollen", POLLEN_ICON_TREE, "#24aa14"),
    "birch": ("birch_pollen", POLLEN_ICON_TREE, "#24aa14"),
    "grass": ("grass_pollen", POLLEN_ICON_GRASS, "#24aa14"),
    "ragweed": ("ragweed_pollen", POLLEN_ICON_WEED, "#845a24"),
}

POLLEN_ENGLISH_NAMES = {
    "alder": "Alder",
    "birch": "Birch",
    "grass": "Grass",
    "ragweed": "Ragweed",
}

POLLEN_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "alder": "Aulne",
        "birch": "Bouleau",
        "grass": "Graminées",
        "ragweed": "Ambroisie",
    }
}


# ---------------------------------------------------------------------------


async def fetch(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    try:
        response = await client.get(
            ENDPOINT,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(VARIABLES),
                "timezone": "auto",
            },
        )
    except httpx.HTTPError as exc:
        raise ConnectorError(
            f"Open-Meteo air quality is unreachable: {exc or type(exc).__name__}",
            code="air.unreachable",
            params={"reason": str(exc) or type(exc).__name__},
        ) from exc

    if response.status_code >= 400:
        reason = _reason(response)
        raise ConnectorError(
            f"Open-Meteo air quality refused the request: {reason}",
            code="air.rejected",
            params={"reason": reason},
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorError(
            "Open-Meteo air quality returned a non-JSON response.",
            code="air.bad_response",
        ) from exc


def _reason(response: httpx.Response) -> str:
    try:
        return str(response.json().get("reason") or response.status_code)
    except ValueError:
        return str(response.status_code)
