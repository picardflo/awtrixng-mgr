"""Fuel prices.

The upstream feed is never called here: `RESPONSE` is a trimmed real answer
for Les Essarts-le-Roi, so the arithmetic and the filtering are pinned without
depending on what the pumps charge today.
"""

from datetime import datetime

import httpx
import pytest

from app.connectors.fuel import prices
from app.connectors.fuel.connector import FuelConnector
from app.core.errors import ConnectorError

HOME = (48.7167, 1.9)

#: Four stations, shaped like the real records: a null price means the station
#: does not sell that fuel, and `geom` is what distance is measured from.
RESPONSE = {
    "total_count": 4,
    "results": [
        {
            "id": 1,
            "ville": "Les Essarts-le-Roi",
            "adresse": "37 RN 10",
            "cp": "78690",
            "geom": {"lat": 48.7260, "lon": 1.8930},
            "e10_prix": 1.99,
            "e10_maj": "2026-10-03T00:01:00+00:00",
            "sp98_prix": None,
            "sp98_maj": None,
        },
        {
            "id": 2,
            "ville": "Le Perray-en-Yvelines",
            "adresse": "2 RUE DE CHARTRES",
            "cp": "78610",
            "geom": {"lat": 48.7050, "lon": 1.8560},
            # Cheaper, but further: the tie-break only applies on equal price.
            "e10_prix": 1.95,
            "e10_maj": "2026-10-02T08:06:51+00:00",
            "sp98_prix": 2.05,
            "sp98_maj": "2026-10-02T08:06:51+00:00",
        },
        {
            "id": 3,
            "ville": "Coignières",
            "adresse": "222 RN 10",
            "cp": "78310",
            "geom": {"lat": 48.7530, "lon": 1.9230},
            # Same price as station 1, but twice as far away.
            "e10_prix": 1.99,
            "e10_maj": "2026-10-03T00:01:00+00:00",
            "sp98_prix": 2.01,
            "sp98_maj": "2026-10-03T00:01:00+00:00",
        },
        {
            "id": 4,
            "ville": "Auffargis",
            "adresse": "RN 306",
            "cp": "78610",
            "geom": {"lat": 48.7000, "lon": 1.8880},
            "e10_prix": None,
            "e10_maj": None,
            "sp98_prix": None,
            "sp98_maj": None,
        },
    ],
}


class TestWhichColumnsAreAsked:
    def test_only_the_fuels_a_service_tracks(self):
        asked = prices.columns(("e10", "sp98"))
        assert "e10_prix" in asked and "sp98_maj" in asked
        assert not any(column.startswith("gazole") for column in asked)

    def test_an_unknown_slug_is_dropped_rather_than_sent_upstream(self):
        """Otherwise a stale configuration asks for a column that does not
        exist and the whole request is refused — every widget of the service
        going dark over one bad value."""
        assert not any("klingon" in column for column in prices.columns(("e10", "klingon")))

    def test_where_the_station_is_is_always_asked_for(self):
        """Without `geom` there is no distance, and without `ville` the matrix
        has nothing to name. Neither depends on which fuel is tracked."""
        asked = prices.columns(("e10",))
        for column in ("geom", "ville", "adresse", "cp"):
            assert column in asked, column


class TestDistance:
    def test_a_known_pair(self):
        """Paris to Lyon is about 392 km as the crow flies."""
        km = prices.haversine(48.8566, 2.3522, 45.7640, 4.8357)
        assert 390 < km < 395

    def test_the_same_point_is_zero(self):
        assert prices.haversine(48.7, 1.9, 48.7, 1.9) == pytest.approx(0, abs=1e-9)


class TestWhichStationsSellIt:
    def test_a_null_price_is_not_a_station(self):
        """Station 4 sells neither, station 1 has no SP98."""
        towns = [s.town for s in prices.stations(RESPONSE, "sp98", *HOME)]
        assert "Auffargis" not in towns
        assert "Les Essarts-le-Roi" not in towns

    def test_they_come_back_nearest_first(self):
        found = prices.stations(RESPONSE, "e10", *HOME)
        assert [round(s.distance, 1) for s in found] == sorted(
            round(s.distance, 1) for s in found
        )

    def test_the_date_is_parsed(self):
        first = prices.stations(RESPONSE, "e10", *HOME)[0]
        assert first.updated == datetime.fromisoformat("2026-10-03T00:01:00+00:00")

    def test_a_record_without_coordinates_is_skipped_not_fatal(self):
        broken = {"results": [{"ville": "X", "e10_prix": 1.5, "geom": None}]}
        assert prices.stations(broken, "e10", *HOME) == []

    def test_an_empty_response_gives_an_empty_list(self):
        assert prices.stations({}, "e10", *HOME) == []


class TestCheapest:
    def test_it_is_the_lowest_price_not_the_nearest(self):
        best = prices.cheapest(prices.stations(RESPONSE, "e10", *HOME))
        assert best.town == "Le Perray-en-Yvelines"
        assert best.price == 1.95

    def test_an_equal_price_goes_to_the_nearer_one(self):
        """Stations 1 and 3 both charge 1.99. Driving twice as far to pay the
        same is the one case where the tie-break earns its keep."""
        without_the_cheapest = {
            "results": [r for r in RESPONSE["results"] if r["id"] != 2]
        }
        best = prices.cheapest(prices.stations(without_the_cheapest, "e10", *HOME))
        assert best.town == "Les Essarts-le-Roi"

    def test_nothing_is_not_a_crash(self):
        assert prices.cheapest([]) is None


class TestTheConnector:
    def connector(self, **config) -> FuelConnector:
        return FuelConnector(
            config={
                "place": {"latitude": HOME[0], "longitude": HOME[1], "name": "Chez moi"},
                **config,
            },
            secrets={},
        )

    def test_the_widget_reports_the_cheapest_and_where(self):
        values = self.connector(fuels=["e10"]).project(
            "fuel.cheapest", {"fuel": "e10"}, RESPONSE
        ).values
        assert values["price"] == 1.95
        assert values["station"] == "Le Perray-en-Yvelines"
        assert values["fuel"] == "SP95-E10"
        assert values["count"] == 3
        assert values["updated"] == "02/10/2026"

    def test_no_station_shows_nothing_rather_than_zero(self):
        """"0.00" on a matrix reads as free fuel."""
        values = self.connector(fuels=["gplc"]).project(
            "fuel.cheapest", {"fuel": "gplc"}, RESPONSE
        ).values
        assert values["price"] is None
        assert values["count"] == 0
        # The fuel is still named, so the widget says *what* it found none of.
        assert values["fuel"] == "GPLc"

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            (["e10", "sp98"], ("e10", "sp98")),
            # Catalogue order, not the order they were clicked in.
            (["sp98", "e10"], ("e10", "sp98")),
            (["e10", "klingon"], ("e10",)),
            # Falling back beats fetching no column at all: a service that
            # silently returns nothing is harder to diagnose.
            ([], prices.DEFAULT_FUELS),
            (None, prices.DEFAULT_FUELS),
        ],
    )
    def test_which_fuels_a_service_tracks(self, configured, expected):
        assert self.connector(fuels=configured)._fuels() == expected

    @pytest.mark.asyncio
    async def test_the_widget_form_offers_exactly_those(self):
        """Unchecking gazole on the service must remove it from the widget
        form, or someone builds a widget that is silently empty forever."""
        options = await self.connector(fuels=["e10", "sp98"]).discover("fuels", None, {})
        assert [o.value for o in options] == ["e10", "sp98"]
        assert [o.label for o in options] == ["SP95-E10", "SP98"]

    @pytest.mark.asyncio
    async def test_an_unknown_source_offers_nothing(self):
        assert await self.connector().discover("planets", None, {}) == []

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [(10, 10), ("25", 25), (0, 1), (500, 50), ("", 10), (None, 10)],
    )
    def test_the_radius_is_clamped_rather_than_refused(self, configured, expected):
        assert self.connector(radius=configured)._radius() == expected

    def test_a_service_with_no_place_says_so(self):
        connector = FuelConnector(config={}, secrets={})
        with pytest.raises(ConnectorError) as raised:
            connector.request_key("fuel.cheapest", {})
        assert raised.value.code == "fuel.no_place"

    def test_every_widget_of_a_service_shares_one_call(self):
        """The columns are asked for once, up front: two widgets on the same
        service must not mean two requests."""
        connector = self.connector(fuels=["e10", "sp98"])
        first, _ = connector.request_key("fuel.cheapest", {"fuel": "e10"})
        second, _ = connector.request_key("fuel.cheapest", {"fuel": "sp98"})
        assert first == second

    def test_changing_the_tracked_fuels_changes_the_key(self):
        """Otherwise the cached response is reused without the new column, and
        the new widget stays empty for an hour."""
        one, _ = self.connector(fuels=["e10"]).request_key("fuel.cheapest", {})
        two, _ = self.connector(fuels=["e10", "sp98"]).request_key("fuel.cheapest", {})
        assert one != two


class TestTheRequestItself:
    """The HTTP layer, with the upstream mocked rather than called."""

    URL = prices.ENDPOINT

    @pytest.mark.asyncio
    async def test_the_radius_and_the_point_reach_the_query(self, respx_mock):
        route = respx_mock.get(self.URL).respond(json={"results": [], "total_count": 0})
        async with httpx.AsyncClient() as client:
            await prices.fetch(client, 48.7167, 1.9, 15, ("e10",))

        query = route.calls.last.request.url.params
        # Longitude first inside POINT(): the opposite order silently returns
        # stations in the wrong hemisphere rather than an error.
        assert "POINT(1.9 48.7167)" in query["where"]
        assert "15km" in query["where"]
        assert "e10_prix" in query["select"]

    @pytest.mark.asyncio
    async def test_an_unreachable_service_is_a_connector_error(self, respx_mock):
        respx_mock.get(self.URL).mock(side_effect=httpx.ConnectError("no route"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(ConnectorError) as raised:
                await prices.fetch(client, 48.7, 1.9, 10, ("e10",))
        assert raised.value.code == "fuel.unreachable"

    @pytest.mark.asyncio
    async def test_a_refusal_carries_what_upstream_said(self, respx_mock):
        respx_mock.get(self.URL).respond(400, json={"message": "unknown field klingon_prix"})
        async with httpx.AsyncClient() as client:
            with pytest.raises(ConnectorError) as raised:
                await prices.fetch(client, 48.7, 1.9, 10, ("e10",))
        assert raised.value.code == "fuel.rejected"
        assert "klingon" in raised.value.params["reason"]

    @pytest.mark.asyncio
    async def test_a_non_json_answer_does_not_raise_a_value_error(self, respx_mock):
        """A captive portal or a proxy error page. The widget must degrade,
        not crash the scheduler."""
        respx_mock.get(self.URL).respond(200, text="<html>nope</html>")
        async with httpx.AsyncClient() as client:
            with pytest.raises(ConnectorError) as raised:
                await prices.fetch(client, 48.7, 1.9, 10, ("e10",))
        assert raised.value.code == "fuel.bad_response"


class TestDenseAreas:
    """One page of a hundred was enough for a village and wrong elsewhere.

    Measured against the real feed: 10 km around Châtelet holds 141 stations,
    50 km holds 789. The feed returns them in no particular order, so a single
    page gave an arbitrary hundred and the cheapest could simply not be in the
    answer — silently. Every test here mocked a village until now.
    """

    URL = prices.ENDPOINT

    @pytest.mark.asyncio
    async def test_every_station_is_collected_not_just_the_first_page(self, respx_mock):
        total = 141
        respx_mock.get(self.URL).mock(side_effect=self._answer(total))
        async with httpx.AsyncClient() as client:
            raw = await prices.fetch(client, 48.8584, 2.3470, 10, ("e10",))
        assert len(raw["results"]) == total
        assert raw["total_count"] == total

    @pytest.mark.asyncio
    async def test_the_cheapest_past_the_first_page_is_found(self, respx_mock):
        """The failure this guards against, stated as a price rather than a
        count: the bug showed up as a widget quietly naming the wrong pump."""
        total = 141
        respx_mock.get(self.URL).mock(side_effect=self._answer(total))
        async with httpx.AsyncClient() as client:
            raw = await prices.fetch(client, 48.8584, 2.3470, 10, ("e10",))
        best = prices.cheapest(prices.stations(raw, "e10", 48.8584, 2.3470))
        assert best.price == 1.80

    @pytest.mark.asyncio
    async def test_a_village_still_costs_one_request(self, respx_mock):
        """Paging must not turn fifteen stations into several round trips."""
        route = respx_mock.get(self.URL).mock(side_effect=self._answer(15))
        async with httpx.AsyncClient() as client:
            await prices.fetch(client, 48.7167, 1.9, 10, ("e10",))
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_it_stops_at_the_cap(self, respx_mock):
        """A guard against an endless feed, not against a city."""
        respx_mock.get(self.URL).mock(side_effect=self._answer(5000))
        async with httpx.AsyncClient() as client:
            raw = await prices.fetch(client, 48.8584, 2.3470, 50, ("e10",))
        assert len(raw["results"]) == prices.MAX_STATIONS

    @pytest.mark.asyncio
    async def test_the_request_asks_for_them_nearest_first(self, respx_mock):
        """Ordering is what makes the cap honest: the nearest thousand is an
        answer, an arbitrary hundred is a coin toss."""
        route = respx_mock.get(self.URL).mock(side_effect=self._answer(10))
        async with httpx.AsyncClient() as client:
            await prices.fetch(client, 48.8584, 2.3470, 10, ("e10",))
        order = route.calls.last.request.url.params["order_by"]
        assert order.startswith("distance(geom,")
        assert "POINT(2.347 48.8584)" in order

    @staticmethod
    def _answer(total: int):
        def answer(request: httpx.Request) -> httpx.Response:
            offset = int(request.url.params.get("offset", 0))
            limit = int(request.url.params.get("limit", prices.PAGE_SIZE))
            rows = [
                {
                    "id": n,
                    "ville": f"Ville {n}",
                    "adresse": "rue",
                    "cp": "75001",
                    "geom": {"lat": 48.85 + n / 10000, "lon": 2.35},
                    "e10_prix": 1.80 if n == total - 1 else 2.10,
                    "e10_maj": "2026-10-03T00:01:00+00:00",
                }
                for n in range(offset, min(offset + limit, total))
            ]
            return httpx.Response(200, json={"total_count": total, "results": rows})

        return answer


class TestTheFormOffersTheExclusion:
    """The field existed in the connector's code and not in its schema.

    A `str.replace` that matched nothing, and nothing said so: the filtering
    worked, `_excluded()` worked, the tests passed — and the form had no way
    to set it. Found by looking at a screenshot.
    """

    def descriptor(self):
        from app.connectors import registry

        registry.load_all()
        return next(d for d in registry.descriptors() if d.id == "fuel")

    def test_the_service_form_has_a_station_field(self):
        names = [field.name for field in self.descriptor().config_schema]
        assert "excluded_stations" in names

    def test_it_is_fed_by_discover(self):
        field = next(
            f for f in self.descriptor().config_schema if f.name == "excluded_stations"
        )
        assert field.type == "remote_multiselect"
        assert field.source == "stations"

    def test_every_configurable_value_is_reachable_from_the_form(self):
        """Generic on purpose. A connector reading a key its schema never
        offers is a setting nobody can set."""
        schema = {field.name for field in self.descriptor().config_schema}
        for key in ("place", "radius", "fuels", "excluded_stations"):
            assert key in schema, f"{key} is read by the connector but absent from its form"
