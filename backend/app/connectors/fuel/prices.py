"""Fuel prices around a point, from the French open data feed.

`prix-des-carburants-en-france-flux-instantane-v2` on data.economie.gouv.fr:
every station required to publish its prices, about ten thousand of them, no
account and no API key. Stations declare their own prices, so a figure can be
a day old or plainly wrong — which is why `updated` is a variable the display
can show rather than something hidden.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.core.errors import ConnectorError

ENDPOINT = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "prix-des-carburants-en-france-flux-instantane-v2/records"
)

#: The six fuels the feed carries. The key is the slug used everywhere — in
#: the configuration, in `fuel_code`, in the column names upstream — and it is
#: never translated: a template comparing against it must keep working when
#: the display language changes.
#:
#: The labels are the names on the pump in France, which is how someone picks
#: theirs. "SP95-E10" rather than "E10" for that reason.
FUELS: dict[str, str] = {
    "gazole": "Gazole",
    "e10": "SP95-E10",
    "sp95": "SP95",
    "sp98": "SP98",
    "e85": "E85",
    "gplc": "GPLc",
}

#: What a new service tracks until someone says otherwise. The two most sold
#: in France; everything else is one click away.
DEFAULT_FUELS = ("gazole", "e10")

#: Fields asked of the API. Narrower than the whole record, which carries
#: opening hours and a services list this never looks at.
_BASE_FIELDS = ("id", "adresse", "ville", "cp", "geom")

#: A station publishes when it feels like it; the feed itself moves all day.
#: An hour is far more often than any price changes, and keeps one call a day
#: per service rather than one per refresh.
CACHE_SECONDS = 3600

#: The API caps a single page at 100, so a dense area needs several.
PAGE_SIZE = 100

#: How far paging will go. Measured: 10 km around Châtelet holds 141 stations,
#: 50 km holds 789 — a single page would have returned 100 of them, in no
#: particular order, and the cheapest could simply not be among them. Beyond
#: this cap the result is the nearest thousand, which is a defensible answer
#: rather than an arbitrary hundred.
MAX_STATIONS = 1000


@dataclass(frozen=True, slots=True)
class Station:
    """One station, for one fuel."""

    #: The feed's own identifier, stable across refreshes. Kept as a string:
    #: it is used as a form value and compared, never counted with.
    id: str
    name: str
    town: str
    address: str
    postcode: str
    price: float
    #: Kilometres from the configured point, as the crow flies.
    distance: float
    #: When the station last published that price, if it said.
    updated: datetime | None


def columns(fuels: tuple[str, ...]) -> tuple[str, ...]:
    """Which columns to ask for, given the fuels a service tracks."""
    wanted = [fuel for fuel in fuels if fuel in FUELS]
    return _BASE_FIELDS + tuple(
        column for fuel in wanted for column in (f"{fuel}_prix", f"{fuel}_maj")
    )


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Kilometres between two points on the globe.

    Computed here rather than asked of the API: the `where` clause can filter
    by distance but does not return it, and "3 km away" is most of what makes
    a price actionable.
    """
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _moment(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def stations(raw: dict[str, Any], fuel: str, latitude: float, longitude: float) -> list[Station]:
    """Every station in the response that sells `fuel`, nearest first.

    A station that does not sell it has a null price rather than a missing
    row, so filtering on the price is what separates "they do not sell E85"
    from "they are out of it today" — both end up excluded, which is right:
    neither can fill a tank this afternoon.
    """
    found: list[Station] = []
    for record in raw.get("results") or []:
        price = record.get(f"{fuel}_prix")
        if not isinstance(price, int | float):
            continue
        point = record.get("geom") or {}
        try:
            distance = haversine(latitude, longitude, float(point["lat"]), float(point["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        town = str(record.get("ville") or "").strip()
        address = str(record.get("adresse") or "").strip()
        found.append(
            Station(
                id=str(record.get("id") or ""),
                # The feed has no brand name — only an address. The town is
                # what fits on a matrix and what someone recognises.
                name=town or address or "?",
                town=town,
                address=address,
                postcode=str(record.get("cp") or "").strip(),
                price=float(price),
                distance=distance,
                updated=_moment(record.get(f"{fuel}_maj")),
            )
        )
    return sorted(found, key=lambda station: station.distance)


def cheapest(found: list[Station]) -> Station | None:
    """The lowest price, and the nearest one when two match.

    `stations()` already sorts by distance, and Python's sort is stable, so
    sorting by price alone keeps that tie-break.
    """
    return min(found, key=lambda station: station.price, default=None)


async def fetch(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    radius_km: int,
    fuels: tuple[str, ...],
) -> dict[str, Any]:
    """Every station within `radius_km`, nearest first, priced.

    Paged, and ordered by distance. One page of a hundred was enough for a
    village and wrong everywhere else: the feed returns them in no particular
    order, so in a city the hundred that came back were an arbitrary hundred
    of the hundred and forty-one, and the cheapest station could simply not be
    in the answer. Nothing said so.
    """
    point = f"geom'POINT({longitude} {latitude})'"
    results: list[dict[str, Any]] = []
    total: int | None = None

    while len(results) < MAX_STATIONS:
        page = await _page(
            client,
            where=f"distance(geom, {point}, {radius_km}km)",
            # Ordering is what makes the cap honest: truncating at the
            # thousandth *nearest* station is an answer; truncating at the
            # hundredth arbitrary one is a coin toss.
            order_by=f"distance(geom, {point})",
            select=",".join(columns(fuels)),
            offset=len(results),
        )
        if total is None:
            total = page.get("total_count")
        rows = page.get("results") or []
        results.extend(rows)
        if len(rows) < PAGE_SIZE:
            break

    return {"total_count": total if total is not None else len(results), "results": results}


async def _page(client: httpx.AsyncClient, *, offset: int, **params: Any) -> dict[str, Any]:
    try:
        response = await client.get(
            ENDPOINT, params={**params, "limit": PAGE_SIZE, "offset": offset}
        )
    except httpx.HTTPError as exc:
        raise ConnectorError(
            f"The fuel price service is unreachable: {exc or type(exc).__name__}",
            code="fuel.unreachable",
            params={"reason": str(exc) or type(exc).__name__},
        ) from exc

    if response.status_code >= 400:
        raise ConnectorError(
            f"The fuel price service refused the request: {_reason(response)}",
            code="fuel.rejected",
            params={"reason": _reason(response)},
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorError(
            "The fuel price service returned a non-JSON response.",
            code="fuel.bad_response",
        ) from exc


def _reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return str(response.status_code)
    message = body.get("message") or body.get("error_code")
    return str(message or response.status_code)
