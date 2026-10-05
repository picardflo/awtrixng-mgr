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
    """One step of a scale: what it is called, drawn and coloured."""

    #: Never translated — what a template compares against.
    code: str
    icon: int
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
# The colours are sampled from the icons themselves rather than chosen beside
# them, so the text can never disagree with the disc it sits next to.
# ---------------------------------------------------------------------------

#: These spell "AQI" in the band's own colour. Preferred over a cloud on a
#: coloured disc, which could be anything: beside a bare "30" on 32 pixels,
#: three letters say what the number is.
#:
#: 37022 is the same orange as 37016, pixel for pixel — a duplicate in the
#: gallery, not a seventh band.
AQI_BANDS: tuple[tuple[float, Band], ...] = (
    (20, Band("good", 37015, "#8cfe0c")),
    (40, Band("fair", 37018, "#fcfe1c")),
    (60, Band("moderate", 37016, "#f48a1c")),
    (80, Band("poor", 37017, "#f40214")),
    (100, Band("very_poor", 37020, "#9402fc")),
)
AQI_WORST = Band("extremely_poor", 37023, "#845a24")

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

UV_ICON = 64310

UV_BANDS: tuple[tuple[float, Band], ...] = (
    (3, Band("low", UV_ICON, "#6fd504")),
    (6, Band("moderate", UV_ICON, "#f9ff1b")),
    (8, Band("high", UV_ICON, "#f78818")),
    (11, Band("very_high", UV_ICON, "#f60017")),
)
UV_EXTREME = Band("extreme", UV_ICON, "#9000fe")

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
