"""Air quality and UV.

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

    def test_the_two_share_one_call(self):
        """A different host from the forecast, but one request between them:
        two widgets must not mean two round trips."""
        connector = self.connector()
        keys = {connector.request_key(t, {})[0] for t in ("weather.air", "weather.uv")}
        assert len(keys) == 1
        assert keys.pop().startswith("air:")

    def test_the_pollen_widget_is_gone(self):
        """Removed on 5 October 2026, Florian's call: "il ne m'apporte pas
        grand chose".

        It was also the one reading in the project with no ceiling to draw a
        bar against — a count of grains per cubic metre says little without a
        scale beside it, and the scale does not exist. Pinned so it is not
        quietly restored with the data still in the response.
        """
        from app.connectors import registry

        registry.load_all()
        assert registry.widget_descriptor("weather.pollen") is None

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


def test_a_withdrawn_widget_type_is_refused_not_defaulted():
    """Removing a widget must not turn its instances into something else.

    The weather connector matches each type by name and ends on the current
    weather. A `weather.pollen` widget surviving in a running installation
    would therefore have fallen through to that last branch and become a
    temperature widget — silently, with a plausible number on the matrix and
    nothing anywhere to say it was the wrong one.

    Found while removing pollen on 5 October 2026, with instances of it
    possibly already configured.
    """
    from app.connectors import registry
    from app.connectors.factory import build
    from app.core.errors import ConnectorError
    from app.models import ConnectorInstance

    registry.load_all()
    connector = build(
        ConnectorInstance(
            id=1,
            type="weather",
            name="M",
            config={"place": {"name": "P", "latitude": 48.85, "longitude": 2.35}},
            secrets={},
        )
    )
    raw = {"current": {"temperature_2m": 20, "weather_code": 2, "is_day": 1}}

    assert connector.project("weather.current", {}, raw).values["temp"] == 20
    for withdrawn in ("weather.pollen", "weather.whatever"):
        with pytest.raises(ConnectorError, match="no longer offers"):
            connector.project(withdrawn, {}, raw)
