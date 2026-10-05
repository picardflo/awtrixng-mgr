"""Place search, so nobody has to know their own latitude.

Open-Meteo's geocoding API is public, needs no key, and speaks the caller's
language. Results come back ordered by relevance, so "Lyon" answers the French
city before the Mississippi one.
"""

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.errors import AwtrixNgError
from app.core.http import build_client

log = logging.getLogger(__name__)

ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"


class Place(BaseModel):
    name: str
    #: Region or state, when the API knows one. Disambiguates same-named towns.
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    latitude: float
    longitude: float
    timezone: str | None = None
    population: int | None = None

    @property
    def label(self) -> str:
        parts = [self.name, self.region, self.country_code]
        return ", ".join(part for part in parts if part)


def _to_place(entry: dict[str, Any]) -> Place | None:
    try:
        return Place(
            name=str(entry["name"]),
            region=entry.get("admin1"),
            country=entry.get("country"),
            country_code=entry.get("country_code"),
            latitude=float(entry["latitude"]),
            longitude=float(entry["longitude"]),
            timezone=entry.get("timezone"),
            population=entry.get("population"),
        )
    except (KeyError, TypeError, ValueError):
        return None


async def search(query: str, *, language: str = "en", limit: int = 8) -> list[Place]:
    """Find places by name. Returns an empty list rather than raising on a miss."""
    query = query.strip()
    if len(query) < 2:
        return []

    client = build_client()
    try:
        response = await client.get(
            ENDPOINT,
            params={
                "name": query,
                "count": limit,
                "language": language,
                "format": "json",
            },
        )
    except httpx.HTTPError as exc:
        raise AwtrixNgError(
            f"The place search is unreachable: {exc or type(exc).__name__}",
            code="places.unreachable",
            params={"reason": str(exc) or type(exc).__name__},
        ) from exc
    finally:
        await client.aclose()

    if response.status_code >= 400:
        raise AwtrixNgError(
            f"The place search refused the request (HTTP {response.status_code}).",
            code="places.rejected",
            params={"status": response.status_code},
        )

    try:
        entries = (response.json() or {}).get("results") or []
    except ValueError:
        return []

    return [place for entry in entries if (place := _to_place(entry))]
