"""The display connector: an AWTRIX read as a data source.

Its whole point is that an indoor reading stops being mistaken for an outdoor
one — so the icon, the colour and the unit are part of the contract, not
decoration.
"""

import httpx
import pytest
import respx

from app.connectors.device import METRICS, RESOLVED, DeviceConnector
from app.core.errors import ConnectorError

STATS_URL = "http://awtrix.test:80/api/stats"
STATS = {
    "temp": 27, "hum": 48, "bat": 84, "lux": 10, "bri": 32,
    "wifi_signal": -52, "uptime": 31235, "version": "0.98",
}
TARGET = {"id": 1, "name": "Office", "host": "awtrix.test", "port": 80,
          "username": None, "password": None}


@pytest.fixture
def connector():
    return DeviceConnector({"device_id": 1, RESOLVED: TARGET}, {})


class TestProjection:
    @pytest.mark.parametrize(
        ("metric", "value", "unit"),
        [
            ("temperature", 27, "°C"),
            ("humidity", 48, "%"),
            ("battery", 84, "%"),
            ("illuminance", 10, "lx"),
            ("signal", -52, "dBm"),
            ("uptime", 31235, "s"),
        ],
    )
    def test_each_reading(self, connector, metric, value, unit):
        data = connector.project("device.metric", {"metric": metric}, STATS)
        assert data.values["value"] == value
        assert data.values["unit"] == unit

    def test_the_display_name_is_available_to_templates(self, connector):
        data = connector.project("device.metric", {"metric": "temperature"}, STATS)
        assert data.values["device"] == "Office"

    def test_an_unknown_reading_falls_back_rather_than_raising(self, connector):
        data = connector.project("device.metric", {"metric": "nonsense"}, STATS)
        assert data.values["metric"] == "temperature"

    def test_a_missing_sensor_is_empty_not_an_error(self, connector):
        """Not every AWTRIX has every sensor; the widget simply hides."""
        data = connector.project("device.metric", {"metric": "humidity"}, {"temp": 20})
        assert data.status == "empty"
        assert data.values["value"] is None

    def test_declared_variables_match_what_is_produced(self, connector):
        widget = connector.descriptor.widgets[0]
        produced = set(connector.project("device.metric", {}, STATS).values)
        assert {variable.name for variable in widget.variables} == produced

    def test_sample_data_matches_the_real_shape(self, connector):
        widget = connector.descriptor.widgets[0]
        assert set(widget.sample_data.values) == set(
            connector.project("device.metric", {}, STATS).values
        )


class TestPresentation:
    def test_percentage_readings_feed_a_progress_bar(self, connector):
        assert connector.project("device.metric", {"metric": "battery"}, STATS).progress == 84

    def test_others_do_not(self, connector):
        assert connector.project("device.metric", {"metric": "signal"}, STATS).progress is None

    @pytest.mark.parametrize(
        ("battery", "colour"),
        [(10, "#f4526b"), (35, "#f5a524"), (84, "#3ddc84")],
    )
    def test_battery_colour_warns(self, connector, battery, colour):
        data = connector.project("device.metric", {"metric": "battery"}, STATS | {"bat": battery})
        assert data.hint_color == colour

    @pytest.mark.parametrize(
        ("signal", "colour"),
        [(-40, "#3ddc84"), (-60, "#f5a524"), (-80, "#f4526b")],
    )
    def test_signal_colour_warns(self, connector, signal, colour):
        data = connector.project(
            "device.metric", {"metric": "signal"}, STATS | {"wifi_signal": signal}
        )
        assert data.hint_color == colour

    def test_temperature_uses_the_same_bands_as_the_weather(self, connector):
        """A temperature must read the same way whatever produced it."""
        from app.connectors.weather import wmo

        data = connector.project("device.metric", {"metric": "temperature"}, STATS)
        assert data.hint_color == wmo.colour_for_temperature(27)

    def test_every_reading_has_its_own_icon(self, connector):
        icons = {
            connector.project("device.metric", {"metric": m.key}, STATS).hint_icon
            for m in METRICS
        }
        assert len(icons) == len(METRICS), "two readings share an icon"


class TestCollection:
    @respx.mock
    async def test_reads_the_configured_display(self, connector):
        route = respx.get(STATS_URL).mock(return_value=httpx.Response(200, json=STATS))
        assert await connector.collect("device.metric", {}) == STATS
        assert route.called

    def test_every_reading_of_a_display_shares_one_call(self, connector):
        keys = {connector.request_key("device.metric", {"metric": m.key})[0] for m in METRICS}
        assert len(keys) == 1

    def test_two_displays_do_not_share(self, connector):
        other = DeviceConnector(
            {RESOLVED: TARGET | {"host": "other.test", "name": "Living room"}}, {}
        )
        assert other.request_key("device.metric", {})[0] != (
            connector.request_key("device.metric", {})[0]
        )

    async def test_no_display_chosen_is_explained(self):
        with pytest.raises(ConnectorError, match="Pick a display"):
            await DeviceConnector({}, {}).collect("device.metric", {})

    @respx.mock
    async def test_unreachable_display_names_it(self, connector):
        respx.get(STATS_URL).mock(side_effect=httpx.ConnectTimeout(""))
        with pytest.raises(ConnectorError) as caught:
            await connector.collect("device.metric", {})
        assert caught.value.code == "device_connector.unreachable"
        assert caught.value.params["device"] == "Office"

    @respx.mock
    async def test_credentials_are_used_when_the_display_has_some(self):
        secured = DeviceConnector(
            {RESOLVED: TARGET | {"username": "u", "password": "p"}}, {}
        )
        route = respx.get(STATS_URL).mock(return_value=httpx.Response(200, json=STATS))
        await secured.collect("device.metric", {})
        assert "authorization" in route.calls.last.request.headers

    @respx.mock
    async def test_rejected_credentials_are_explained(self, connector):
        respx.get(STATS_URL).mock(return_value=httpx.Response(401))
        with pytest.raises(ConnectorError, match="refused the credentials"):
            await connector.collect("device.metric", {})


def test_connector_needs_no_credentials_of_its_own():
    assert DeviceConnector.descriptor.requires_credentials is False


class TestTheBatteryIcon:
    """One outline said nothing a glance could use.

    The battery is the one reading whose *level* is the whole message, and it
    showed the same picture at 5 % and at 95 %. Four icons drawn as one set
    now fill up with it.
    """

    from app.connectors.device.connector import BY_KEY as _BY_KEY

    BATTERY = _BY_KEY["battery"]

    def icon(self, value):
        from app.connectors.device.connector import _icon

        return _icon(self.BATTERY, value)

    def colour(self, value):
        from app.connectors.device.connector import _colour

        return _colour(self.BATTERY, value)

    @pytest.mark.parametrize(
        ("level", "icon"),
        [(0, "12123"), (19, "12123"), (20, "12124"), (49, "12124"),
         (50, "12125"), (89, "12125"), (90, "12126"), (100, "12126")],
    )
    def test_the_ladder(self, level: int, icon: str):
        assert self.icon(level) == icon

    @pytest.mark.parametrize("level", [0, 10, 19, 20, 35, 49, 50, 70, 89, 90, 100])
    def test_the_icon_and_the_colour_never_disagree(self, level: int):
        """Both branch at 20 and 50. An amber figure beside a green battery
        would be the rain widget's old defect, again — and that one was found
        by looking at a screenshot, not by a test."""
        families = {
            "12123": "#f4526b",
            "12124": "#f5a524",
            "12125": "#3ddc84",
            "12126": "#3ddc84",
        }
        assert families[self.icon(level)] == self.colour(level)

    def test_green_is_split_so_a_glance_can_tell_them_apart(self):
        """55 % and 95 % are both fine, and both green. The picture is what
        separates them."""
        assert self.colour(55) == self.colour(95)
        assert self.icon(55) != self.icon(95)

    def test_a_missing_reading_falls_back_to_the_plain_outline(self):
        """Not every AWTRIX reports a battery, and the widget then hides
        rather than inventing a level."""
        assert self.icon(None) == str(self.BATTERY.icon)

    def test_the_other_readings_keep_their_own(self):
        """Only the battery has a ladder: a humidity of 20 % is not low in the
        way a battery of 20 % is."""
        from app.connectors.device.connector import _icon

        for key in ("humidity", "temperature", "signal", "uptime"):
            metric = self._BY_KEY[key]
            assert _icon(metric, 20) == str(metric.icon)
