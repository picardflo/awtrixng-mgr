"""Open-Meteo connector.

Parsing is tested against a frozen fixture and collection against a mocked
transport: no test here touches the network (§23).
"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.connectors.weather import WeatherConnector, wmo
from app.core.errors import ConnectorError

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "open_meteo_current.json").read_text()
)
CONFIG = {"place": {"name": "Paris", "latitude": 48.8566, "longitude": 2.3522}}
#: Shape used before the place search replaced the two number fields.
LEGACY_CONFIG = {"latitude": 48.8566, "longitude": 2.3522}


@pytest.fixture
def connector():
    return WeatherConnector(CONFIG, {})


class TestProjection:
    """project() is pure: no network, no clock, no device."""

    def test_current_weather_values(self, connector):
        data = connector.project("weather.current", CONFIG, FIXTURE)
        assert data.values["temp"] == 21.5
        assert data.values["feels_like"] == 21.6
        assert data.values["humidity"] == 66
        assert data.values["wind"] == 10.6
        assert data.values["condition"] == "Overcast"
        assert data.values["condition_code"] == "overcast"
        assert data.values["is_day"] is False

    def test_current_weather_colours_by_temperature(self, connector):
        data = connector.project("weather.current", CONFIG, FIXTURE)
        # 21.5 °C sits between the mild and warm anchors, so it is a blend of
        # the two rather than either one.
        assert data.hint_color == wmo.colour_for_temperature(21.5)
        assert data.hint_color not in ("#3ddc84", "#f5a524")

    def test_rain_values(self, connector):
        data = connector.project("weather.rain", CONFIG, FIXTURE)
        assert data.values["probability"] == 2
        assert data.values["precipitation"] == 0.0
        assert data.progress == 2

    def test_missing_current_block_does_not_raise(self, connector):
        data = connector.project("weather.current", CONFIG, {})
        assert data.values["temp"] is None
        assert data.values["condition_code"] == "unknown"

    def test_every_declared_variable_is_produced(self, connector):
        """The template editor lists these: they must be real."""
        for widget in connector.descriptor.widgets:
            produced = set(connector.project(widget.type, CONFIG, FIXTURE).values)
            declared = {variable.name for variable in widget.variables}
            assert declared <= produced, f"{widget.type} promises {declared - produced}"

    def test_the_only_thing_produced_and_not_listed_is_an_identifier(self, connector):
        """Declared is now a *subset* of produced, on purpose.

        The `*_code` values drive the icon and the colour and are compared by
        the tests, so the data keeps them. They are no longer offered in the
        editor: the template engine has no comparison — no `if`, no `==`, see
        ADR-006 — so there is nothing a template could do with one except
        print it, which is what someone did by accident. They still resolve if
        typed, so an existing template keeps working.
        """
        for widget in connector.descriptor.widgets:
            produced = set(connector.project(widget.type, CONFIG, FIXTURE).values)
            declared = {variable.name for variable in widget.variables}
            for extra in produced - declared:
                assert extra.endswith("_code"), f"{widget.type} hides {extra}"

    def test_sample_data_matches_the_real_shape(self, connector):
        """sample_data drives the preview before any service is reachable, so a
        drift here would show the user keys that do not exist."""
        for widget in connector.descriptor.widgets:
            real = set(connector.project(widget.type, CONFIG, FIXTURE).values)
            assert set(widget.sample_data.values) == real


class TestCache:
    def test_both_widgets_share_one_upstream_call(self, connector):
        current, _ = connector.request_key("weather.current", CONFIG)
        rain, _ = connector.request_key("weather.rain", CONFIG)
        assert current == rain

    def test_different_places_do_not_share(self, connector):
        elsewhere = WeatherConnector({"place": {"latitude": 0, "longitude": 0}}, {})
        assert elsewhere.request_key("weather.current", {})[0] != (
            connector.request_key("weather.current", {})[0]
        )

    def test_two_connectors_on_the_same_place_share_one_call(self):
        """Keyed on coordinates, not on the connector id."""
        first = WeatherConnector(CONFIG, {})
        second = WeatherConnector(dict(CONFIG), {})
        assert first.request_key("weather.current", {})[0] == (
            second.request_key("weather.current", {})[0]
        )

    def test_ttl_matches_the_upstream_refresh_rate(self, connector):
        """Open-Meteo refreshes every 15 min; §6 asks for 10."""
        assert connector.request_key("weather.current", CONFIG)[1] == 600


class TestCollection:
    @respx.mock
    async def test_sends_the_documented_parameters(self, connector):
        route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=FIXTURE)
        )
        await connector.collect("weather.current", CONFIG)

        params = route.calls.last.request.url.params
        assert params["latitude"] == "48.8566"
        assert params["timezone"] == "auto"
        assert "precipitation_probability" in params["current"]

    @respx.mock
    async def test_400_surfaces_the_api_reason(self, connector):
        """Open-Meteo explains itself in the body; the status alone says nothing."""
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(
                400, json={"error": True, "reason": "Latitude must be in range"}
            )
        )
        with pytest.raises(ConnectorError, match="Latitude must be in range"):
            await connector.collect("weather.current", CONFIG)

    @respx.mock
    async def test_network_failure_is_a_connector_error(self, connector):
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            side_effect=httpx.ConnectTimeout("")
        )
        with pytest.raises(ConnectorError) as caught:
            await connector.collect("weather.current", CONFIG)
        assert caught.value.code == "weather.unreachable"
        assert caught.value.params["reason"] == "ConnectTimeout"

    async def test_missing_place_is_explained(self):
        with pytest.raises(ConnectorError, match="Pick a place"):
            await WeatherConnector({}, {}).collect("weather.current", {})

    def test_a_connector_configured_before_the_place_search_still_works(self):
        """Top-level latitude/longitude predate the place field; dropping them
        would silently break an existing installation."""
        legacy = WeatherConnector(LEGACY_CONFIG, {})
        assert legacy.request_key("weather.current", {})[0] == "weather:48.8566,2.3522"


class TestWmo:
    @pytest.mark.parametrize(
        ("code", "slug"),
        [(0, "clear"), (3, "overcast"), (61, "rain_slight"), (95, "thunderstorm")],
    )
    def test_known_codes(self, code, slug):
        assert wmo.describe(code)[0] == slug

    @pytest.mark.parametrize("code", [None, 7, -1, "x", 999])
    def test_unknown_codes_never_raise(self, code):
        assert wmo.describe(code) == ("unknown", "Unknown")

    @pytest.mark.parametrize(
        ("celsius", "colour"),
        [(-10, "#7ec8ff"), (5, "#4aa8ff"), (15, "#3ddc84"), (24, "#f5a524"), (34, "#f4526b")],
    )
    def test_each_anchor_renders_exactly(self, celsius, colour):
        """The five colours this project has always used, unchanged. Only
        what happens between them is new."""
        assert wmo.colour_for_temperature(celsius) == colour

    @pytest.mark.parametrize("celsius", [-40, -11, -10])
    def test_below_the_first_anchor_the_colour_holds(self, celsius):
        """There is no sensible blue beyond pale blue."""
        assert wmo.colour_for_temperature(celsius) == "#7ec8ff"

    @pytest.mark.parametrize("celsius", [34, 45, 60])
    def test_above_the_last_anchor_the_colour_holds(self, celsius):
        assert wmo.colour_for_temperature(celsius) == "#f4526b"

    def test_half_a_degree_no_longer_changes_the_weather(self):
        """The defect bands had: 19.5 was green and 20.5 was amber, so the
        same afternoon looked like two different days."""
        cool = wmo.colour_for_temperature(19.5)
        warm = wmo.colour_for_temperature(20.5)
        assert cool != warm
        assert max(
            abs(int(cool[i : i + 2], 16) - int(warm[i : i + 2], 16)) for i in (1, 3, 5)
        ) < 30

    def test_eight_degrees_apart_no_longer_look_identical(self):
        """The other defect: -8 °C and 0 °C were the same pale blue."""
        assert wmo.colour_for_temperature(-8) != wmo.colour_for_temperature(0)

    def test_the_scale_is_continuous(self):
        """The property bands lacked, stated as a number: walked half a degree
        at a time, no channel ever jumps.

        Not monotonic — a pale blue holds more red than a saturated one, so no
        single channel climbs all the way. Continuity is what was missing, and
        continuity is what this pins.
        """
        steps = [wmo.colour_for_temperature(t / 2) for t in range(-24, 70)]
        worst = max(
            abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16))
            for a, b in zip(steps, steps[1:], strict=False)
            for i in (1, 3, 5)
        )
        assert worst <= 12, f"a half-degree moved a channel by {worst}"

    def test_no_temperature_means_no_colour(self):
        assert wmo.colour_for_temperature(None) is None


def test_connector_needs_no_credentials():
    """The point of starting with Open-Meteo (§29 phase 4)."""
    assert WeatherConnector.descriptor.requires_credentials is False
    assert not any(f.type == "secret" for f in WeatherConnector.descriptor.config_schema)


class TestConfigurationSource:
    """The place lives on the connector, not on the widget.

    Reading it from the widget config silently produced an empty preview, so
    the distinction is pinned down here.
    """

    def test_coordinates_come_from_the_connector(self, connector):
        key, _ = connector.request_key("weather.current", {})
        assert key == "weather:48.8566,2.3522"

    @respx.mock
    async def test_collect_ignores_the_widget_config(self, connector):
        route = respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=FIXTURE)
        )
        await connector.collect("weather.current", {"latitude": 0, "longitude": 0})
        assert route.calls.last.request.url.params["latitude"] == "48.8566"


class TestTheRainColourFollowsTheIcon:
    """The icon branched on the probability and the colour never did.

    At 0 % the widget drew a sun in bright blue — contradicting both its own
    icon and the number printed beside it. The two answer the same question,
    so they must branch at the same place; this is what says so.
    """

    #: Codes that are already precipitating, and codes that are not.
    WET = (51, 61, 71, 95)
    DRY_SKY = (0, 1, 2, 3, 45)

    def colour(self, code: int, probability: float | None) -> str:
        return wmo.colour_for_precipitation(code, probability)

    def icon_says_rain(self, code: int, probability: float | None) -> bool:
        icon = wmo.precipitation_icon(code, probability, is_day=True)
        return int(icon) in wmo.PRECIPITATION_ICONS

    @pytest.mark.parametrize("code", DRY_SKY)
    @pytest.mark.parametrize("probability", [0, 10, 49, 50, 80, 100])
    def test_they_agree_on_every_combination(self, code: int, probability: int):
        """The property, not the table: whenever the icon shows precipitation
        the colour must be wet, and whenever it does not the colour must be
        dry. Either side gaining a case keeps them in step or fails here."""
        wet_colour = self.colour(code, probability) in (wmo.LIKELY, wmo.FALLING)
        assert wet_colour == self.icon_says_rain(code, probability)

    @pytest.mark.parametrize("code", WET)
    def test_already_falling_is_its_own_shade(self, code: int):
        """Deeper than "likely": it is not a forecast any more."""
        assert self.colour(code, 0) == wmo.FALLING
        assert self.icon_says_rain(code, 0)

    def test_a_clear_sky_at_zero_is_not_bright_blue(self):
        """The regression, stated as what someone saw."""
        assert self.colour(0, 0) == wmo.DRY

    def test_the_threshold_is_the_icon_s_own(self):
        """One number, not two that drift apart."""
        assert self.colour(3, wmo.LIKELY_PERCENT - 1) == wmo.DRY
        assert self.colour(3, wmo.LIKELY_PERCENT) == wmo.LIKELY

    def test_an_unknown_probability_reads_as_dry(self):
        assert self.colour(3, None) == wmo.DRY
