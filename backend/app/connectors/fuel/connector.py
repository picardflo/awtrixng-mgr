"""Fuel prices near a point, from the French open data feed.

No account and no API key, like Open-Meteo and the school calendar — the whole
point of the dataset is that it is public.

Two choices shape this connector:

- **The place and the radius belong to the service, the fuel to the widget.**
  Someone tracks one neighbourhood and several fuels, not the reverse. One
  service, one call, as many widgets as they have tanks to fill.
- **Which fuels a service tracks is configured.** A car runs on one or two of
  the six, and asking for the other four would mean columns nobody reads and a
  widget form offering choices that make no sense for this household.
"""

from typing import Any

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.fuel import prices
from app.connectors.registry import register
from app.core.errors import ConnectorError
from app.schemas.fields import FormField, Option, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData

#: "Fuel ani" in the gallery: a red pump, animated. Chosen by the person who
#: looks at it every day, over the static green one this shipped with.
ICON = "55274"

DEFAULT_RADIUS_KM = 10
MIN_RADIUS_KM = 1
#: Past this the nearest station stops being somewhere you would actually go,
#: and the hundred-row page starts to bite in a dense area.
MAX_RADIUS_KM = 50


@register
class FuelConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="fuel",
        name="Fuel prices",
        description=(
            "The cheapest pump near a place, from the French open data feed. "
            "No account, no API key."
        ),
        icon="fuel",
        requires_credentials=False,
        config_schema=[
            FormField(
                name="place",
                label="Place",
                type="place",
                required=True,
                placeholder="Les Essarts-le-Roi, Lyon…",
                help="Distances are measured from here.",
            ),
            FormField(
                name="radius",
                label="Radius",
                type="number",
                default=DEFAULT_RADIUS_KM,
                min=MIN_RADIUS_KM,
                max=MAX_RADIUS_KM,
                unit="km",
                help="How far to look. As the crow flies.",
            ),
            FormField(
                name="fuels",
                label="Fuels",
                type="multiselect",
                default=list(prices.DEFAULT_FUELS),
                help="Only the ones you use. The others are not even fetched.",
                options=[Option(value=slug, label=label) for slug, label in prices.FUELS.items()],
            ),
            FormField(
                name="excluded_stations",
                label="Stations to ignore",
                # Stores what is *rejected*, not what is kept. A list of kept
                # stations would silently drop any station that opened, moved
                # into the radius or started selling your fuel after this was
                # configured — quite possibly the cheapest one, and nothing
                # would say so. Rejections are a handful, and they stay true.
                type="remote_multiselect",
                source="stations",
                help=(
                    "Tick a station whose price is no use to you. The feed "
                    "carries no brand, only the address."
                ),
            ),
        ],
        widgets=[
            WidgetDescriptor(
                type="fuel.cheapest",
                name="Cheapest fuel",
                description="The lowest price for one fuel, and where it is.",
                fields=[
                    FormField(
                        name="fuel",
                        label="Fuel",
                        # Fed by discover(), so the list holds exactly the
                        # fuels this service tracks. Offering all six here
                        # would let someone build a widget for a fuel the
                        # service never fetches — silently empty, forever.
                        type="remote_select",
                        source="fuels",
                        required=True,
                    ),
                ],
                variables=[
                    Variable(name="price", label="Price (€/L)", example="1.99"),
                    Variable(
                        name="fuel",
                        label="Name on the pump — the same in every language",
                        example="SP95-E10",
                    ),
                    Variable(
                        name="station", label="Town of the station", example="Les Essarts-le-Roi"
                    ),
                    Variable(name="address", label="Street", example="12 RUE DE PARIS"),
                    Variable(name="distance", label="Distance (km)", example="1.3"),
                    Variable(name="updated", label="Price published on", example="03/10/2026"),
                    Variable(
                        name="age_days",
                        label="How old the price is, in days",
                        example="2",
                    ),
                    Variable(
                        name="count",
                        label="Stations selling it within the radius",
                        example="11",
                    ),
                ],
                # The price alone: it is what the glance is for, and "1.99"
                # is already five of the characters left beside an icon.
                default_display=DisplayOptions(text="{{ price }}", duration=8),
                default_refresh=prices.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={
                        "price": 1.99,
                        "fuel": "SP95-E10",
                        "station": "Les Essarts-le-Roi",
                        "address": "12 RUE DE PARIS",
                        "distance": 1.3,
                        "updated": "03/10/2026",
                        "count": 11,
                        "age_days": 2,
                    },
                    hint_icon=ICON,
                    hint_color=prices.COLOUR_FRESH,
                ),
            ),
        ],
    )

    # -- Configuration --------------------------------------------------------

    def _coordinates(self) -> tuple[float, float]:
        place = self.config.get("place") or {}
        try:
            return float(place["latitude"]), float(place["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConnectorError("Pick a place for this connector.", code="fuel.no_place") from exc

    def _radius(self) -> int:
        raw = self.config.get("radius", DEFAULT_RADIUS_KM)
        try:
            radius = int(float(raw))
        except (TypeError, ValueError):
            radius = DEFAULT_RADIUS_KM
        return max(MIN_RADIUS_KM, min(MAX_RADIUS_KM, radius))

    def _fuels(self) -> tuple[str, ...]:
        """The fuels this service tracks, in catalogue order.

        An empty selection falls back to the defaults rather than fetching no
        column at all: a service that silently returns nothing is harder to
        diagnose than one showing a price for a fuel you do not burn.
        """
        chosen = self.config.get("fuels")
        if isinstance(chosen, list | tuple):
            kept = tuple(slug for slug in prices.FUELS if slug in set(chosen))
            if kept:
                return kept
        return prices.DEFAULT_FUELS

    def _excluded(self) -> frozenset[str]:
        """Station ids this service ignores."""
        raw = self.config.get("excluded_stations")
        if not isinstance(raw, list | tuple):
            return frozenset()
        return frozenset(str(value).strip() for value in raw if str(value).strip())

    async def discover(
        self, source: str, query: str | None, context: dict[str, Any]
    ) -> list[Option]:
        if source == "fuels":
            return [Option(value=slug, label=prices.FUELS[slug]) for slug in self._fuels()]
        if source == "stations":
            return await self._nearby()
        return []

    async def _nearby(self) -> list[Option]:
        """Every station in the radius, nearest first, priced.

        Named by town and street because the feed has no brand: "Coignières ·
        222/224 RN 10" is what someone recognises, and the price is what makes
        the odd one out obvious.
        """
        latitude, longitude = self._coordinates()
        fuels = self._fuels()
        raw = await prices.fetch(self.client, latitude, longitude, self._radius(), fuels)

        seen: dict[str, Option] = {}
        for fuel in fuels:
            for station in prices.stations(raw, fuel, latitude, longitude):
                if station.id in seen:
                    continue
                seen[station.id] = Option(
                    value=station.id,
                    label=f"{station.town} · {station.address}".strip(" ·"),
                    hint=(
                        f"{prices.FUELS[fuel]} {station.price} € · "
                        f"{station.distance:.1f} km"
                    ),
                )
        return list(seen.values())

    # -- Collection -----------------------------------------------------------

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        # Every widget of this service reads one response, whatever its fuel:
        # the columns are asked for once, up front.
        latitude, longitude = self._coordinates()
        fuels = ",".join(self._fuels())
        return (
            f"fuel:{latitude:.4f},{longitude:.4f}:{self._radius()}:{fuels}",
            prices.CACHE_SECONDS,
        )

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        latitude, longitude = self._coordinates()
        return await prices.fetch(self.client, latitude, longitude, self._radius(), self._fuels())

    async def test_connection(self) -> ConnectorTestResult:
        latitude, longitude = self._coordinates()
        fuels = self._fuels()
        try:
            raw = await prices.fetch(self.client, latitude, longitude, self._radius(), fuels)
        except ConnectorError as exc:
            return ConnectorTestResult(
                ok=False, message=exc.message, code=exc.code, params=exc.params
            )

        counts = {
            prices.FUELS[fuel]: len(prices.stations(raw, fuel, latitude, longitude))
            for fuel in fuels
        }
        total = raw.get("total_count") or 0
        if not total:
            # Not an error: a valid radius over empty country. Saying so beats
            # a green tick above a widget that will never show a price.
            return ConnectorTestResult(
                ok=False,
                message=f"No station within {self._radius()} km.",
                code="fuel.no_station",
                params={"radius": self._radius()},
            )

        return ConnectorTestResult(
            ok=True,
            message=(
                f"{total} station(s) within {self._radius()} km: "
                + ", ".join(f"{label} {count}" for label, count in counts.items())
                + "."
            ),
            code="fuel.ok",
            params={"stations": total, "radius": self._radius()},
            details=counts,
        )

    # -- Projection -----------------------------------------------------------

    def project(self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]) -> WidgetData:
        latitude, longitude = self._coordinates()
        fuel = str(config.get("fuel") or "").strip() or self._fuels()[0]
        excluded = self._excluded()
        found = [
            station
            for station in prices.stations(raw, fuel, latitude, longitude)
            if station.id not in excluded
        ]
        best = prices.cheapest(found)

        if best is None:
            # Every value empty rather than a zero price: "0.00" on a matrix
            # reads as free fuel, which is worse than reading as nothing.
            return WidgetData(
                values={
                    "price": None,
                    "fuel": prices.FUELS.get(fuel, fuel),
                    "station": None,
                    "address": None,
                    "distance": None,
                    "updated": None,
                    "count": 0,
                },
                hint_icon=ICON,
                hint_color="#9aa0a6",
            )

        return WidgetData(
            values={
                "price": best.price,
                "fuel": prices.FUELS.get(fuel, fuel),
                "station": best.town,
                "address": best.address,
                "distance": round(best.distance, 1),
                # Written out here rather than left as a timestamp: a template
                # has no date filter, and the useful question is "is this
                # price from today".
                "updated": best.updated.strftime("%d/%m/%Y") if best.updated else None,
                "count": len(found),
                # How old the price is, so a template can say so. The feed
                # publishes stamps, not guarantees: a station that stopped
                # reporting keeps its last figure and goes on looking cheap.
                "age_days": (
                    (prices.now() - best.updated).days if best.updated else None
                ),
            },
            hint_icon=ICON,
            # The colour said nothing before — green whatever the data. It
            # now says the one thing a price needs qualifying by: its age.
            #
            # A price older than a month is not a price, it is a station that
            # stopped reporting. It is still shown, because it may well be the
            # cheapest and the date is there to be read, but it stops looking
            # like a fresh find.
            hint_color=prices.colour_for_age(best.updated),
        )
