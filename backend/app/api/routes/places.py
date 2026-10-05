"""Place search, used by the `place` field type."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import places

router = APIRouter(tags=["places"])


class PlaceResult(BaseModel):
    label: str
    name: str
    region: str | None
    country: str | None
    country_code: str | None
    latitude: float
    longitude: float
    timezone: str | None


@router.get("/places", response_model=list[PlaceResult])
async def search_places(
    q: Annotated[str, Query(min_length=0, description="Town or place name")] = "",
    language: Annotated[str, Query(max_length=8)] = "en",
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[PlaceResult]:
    """Search by name. Empty for a query under two characters, never an error.

    This endpoint takes no connector: a place has to be chosen **before** the
    connector exists, which is exactly when `discover()` is not available.
    """
    found = await places.search(q, language=language, limit=limit)
    return [
        PlaceResult(
            label=place.label,
            name=place.name,
            region=place.region,
            country=place.country,
            country_code=place.country_code,
            latitude=place.latitude,
            longitude=place.longitude,
            timezone=place.timezone,
        )
        for place in found
    ]
