"""Air quality, UV and pollen.

The thresholds are not invented. The European index comes from Open-Meteo's
own documentation, which states the European Environment Agency's bands as
revised in 2024. The UV scale is the WHO's. The pollen scale is **neither** —
see `pollen_level` — and that is said out loud because someone allergic may
read it.
"""

import httpx
import pytest

from app.connectors.weather import air

#: A real answer for Les Essarts-le-Roi, trimmed.
LIVE = {
    "current": {
        "european_aqi": 30, "pm10": 17.3, "pm2_5": 10.1,
        "nitrogen_dioxide": 7.6, "ozone": 72.0, "sulphur_dioxide": 1.7,
        "uv_index": 3.05, "alder_pollen": 0.0, "birch_pollen": 0.0,
        "grass_pollen": 0.1, "ragweed_pollen": 0.0,
    }
}


class TestTheEuropeanIndex:
    @pytest.mark.parametrize(
        ("value", "code"),
        [(0, "good"), (19.9, "good"), (20, "fair"), (30, "fair"), (39.9, "fair"),
         (40, "moderate"), (60, "poor"), (80, "very_poor"),
         (100, "extremely_poor"), (250, "extremely_poor")],
    )
    def test_the_bands(self, value: float, code: str):
        assert air.aqi_band(value).code == code

    def test_it_is_not_a_scale_out_of_a_hundred(self):
        """Open-Meteo states it plainly: the index is the highest of the five
        pollutant indices and can exceed 100. A bar or a percentage would be
        wrong, which is why neither is offered."""
        assert air.aqi_band(140).code == "extremely_poor"

    def test_every_band_has_its_own_icon_and_colour(self):
        bands = [band for _, band in air.AQI_BANDS] + [air.AQI_WORST]
        assert len({b.icon for b in bands}) == 6
        assert len({b.colour for b in bands}) == 6

    def test_a_missing_reading_lands_on_the_worst(self):
        """Not on "good": an unknown air quality must not look reassuring."""
        assert air.aqi_band(None).code == "extremely_poor"


class TestTheUvScale:
    @pytest.mark.parametrize(
        ("value", "code"),
        [(0, "low"), (2.9, "low"), (3, "moderate"), (5.9, "moderate"),
         (6, "high"), (7.9, "high"), (8, "very_high"), (10.9, "very_high"),
         (11, "extreme"), (14, "extreme")],
    )
    def test_the_who_bands(self, value: float, code: str):
        assert air.uv_band(value).code == code


class TestPollen:
    """No bands here, deliberately.

    Open-Meteo publishes grains per cubic metre and nothing else, and the
    published scales contradict one another. An earlier version invented a
    per-family ladder; it is gone. Someone allergic knows the figure they
    react to, and a word chosen here would have sat between them and it.
    """

    def test_every_species_maps_to_a_field_an_icon_and_a_colour(self):
        for slug, (field, icon, colour) in air.POLLENS.items():
            assert field.endswith("_pollen")
            assert icon
            assert colour.startswith("#")
            assert slug in air.POLLEN_ENGLISH_NAMES

    def test_trees_share_an_icon_and_weeds_do_not(self):
        """What the API itself distinguishes is the plant, so that is what the
        picture follows."""
        assert air.POLLENS["alder"][1] == air.POLLENS["birch"][1]
        assert air.POLLENS["ragweed"][1] != air.POLLENS["grass"][1]

    def test_no_levels_are_offered(self):
        """A guard against putting them back without deciding to."""
        assert not hasattr(air, "pollen_level")
        assert not hasattr(air, "POLLEN_SCALES")


class TestTheWidgets:
    def connector(self):
        from app.connectors.weather.connector import WeatherConnector

        return WeatherConnector(
            config={"place": {"latitude": 48.7167, "longitude": 1.9}}, secrets={}
        )

    def test_air_reports_the_index_and_the_pollutants(self):
        values = self.connector().project("weather.air", {}, LIVE).values
        assert values["aqi"] == 30
        assert values["quality_code"] == "fair"
        assert values["pm2_5"] == 10.1

    def test_the_colour_matches_its_own_icon(self):
        """Sampled from the icons themselves rather than chosen beside them:
        the text can never disagree with the disc it sits next to."""
        data = self.connector().project("weather.air", {}, LIVE)
        band = air.aqi_band(30)
        assert data.hint_icon == str(band.icon)
        assert data.hint_color == band.colour

    def test_uv_reads_the_same_response(self):
        values = self.connector().project("weather.uv", {}, LIVE).values
        assert values["uv"] == 3.05
        assert values["level_code"] == "moderate"

    def test_pollen_follows_the_chosen_species(self):
        connector = self.connector()
        grass = connector.project("weather.pollen", {"species": "grass"}, LIVE)
        birch = connector.project("weather.pollen", {"species": "birch"}, LIVE)
        assert grass.values["species_code"] == "grass"
        assert birch.values["species_code"] == "birch"
        assert grass.hint_icon != birch.hint_icon

    def test_pollen_reports_the_figure_and_nothing_else(self):
        values = self.connector().project("weather.pollen", {"species": "grass"}, LIVE).values
        assert values["grains"] == 0.1
        assert "level" not in values
        assert "level_code" not in values

    def test_pollen_without_a_species_still_works(self):
        values = self.connector().project("weather.pollen", {}, LIVE).values
        assert values["species_code"] == "grass"

    def test_the_three_share_one_call(self):
        """A different host from the forecast, but one request between them:
        three widgets must not mean three round trips."""
        connector = self.connector()
        keys = {
            connector.request_key(t, {})[0]
            for t in ("weather.air", "weather.uv", "weather.pollen")
        }
        assert len(keys) == 1
        assert keys.pop().startswith("air:")

    def test_the_forecast_keeps_its_own(self):
        connector = self.connector()
        assert connector.request_key("weather.current", {})[0] != connector.request_key(
            "weather.air", {}
        )[0]

    def test_an_empty_response_is_not_a_crash(self):
        values = self.connector().project("weather.air", {}, {}).values
        assert values["aqi"] is None


class TestTheRequest:
    @pytest.mark.asyncio
    async def test_it_asks_the_air_quality_host(self, respx_mock):
        route = respx_mock.get(air.ENDPOINT).respond(json=LIVE)
        async with httpx.AsyncClient() as client:
            await air.fetch(client, 48.7167, 1.9)
        params = route.calls.last.request.url.params
        assert "european_aqi" in params["current"]
        assert "grass_pollen" in params["current"]

    @pytest.mark.asyncio
    async def test_unreachable_is_a_connector_error(self, respx_mock):
        respx_mock.get(air.ENDPOINT).mock(side_effect=httpx.ConnectError("no"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(Exception) as raised:
                await air.fetch(client, 48.7, 1.9)
        assert raised.value.code == "air.unreachable"
