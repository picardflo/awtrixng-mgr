"""Routes the frontend depends on, and that had no test at all.

Found by listing the declared routes and grepping the test suite for each: nine
had none, including /widgets/preview — the heart of the builder.
"""

import httpx
import pytest
import respx

DEVICE = "http://awtrix.test:80"
FORECAST = "https://api.open-meteo.com/v1/forecast"
STATS = {"version": "1.1.2", "uid": "b0cbd8a1b560", "batteryPercent": 80, "temperature": 21}
CURRENT = {"current": {"temperature_2m": 19.0, "relative_humidity_2m": 60,
                       "weather_code": 3, "is_day": 1, "wind_speed_10m": 9.0,
                       "precipitation": 0.0, "precipitation_probability": 40,
                       "apparent_temperature": 18.0}}


def setup(client):
    device = client.post(
        "/api/devices", json={"name": "D", "host": "awtrix.test"}
    ).json()
    connector = client.post(
        "/api/connectors",
        json={"type": "weather", "name": "W",
              "config": {"place": {"name": "P", "latitude": 1, "longitude": 2}}},
    ).json()
    return device, connector


#: Matching on the path rather than the whole URL: NG puts an app's name in
#: the path, where AWTRIX 3 put it in a query string.
DEVICE_HOST = "awtrix.test"
PUSH_PATH = r"^/api/v1/apps/pushed/[^/]+$"
DELETE_PATH = r"^/api/v1/apps/[^/]+$"


def mock_awtrix():
    respx.get(f"{DEVICE}/api/v1/device").mock(return_value=httpx.Response(200, json=STATS))
    respx.get(f"{DEVICE}/api/v1/apps").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{DEVICE}/api/v1/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    respx.post(f"{DEVICE}/api/v1/files").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.get(url__startswith="https://developer.lametric.com/content").mock(
        return_value=httpx.Response(200, content=b"GIF89a",
                                    headers={"content-type": "image/gif"})
    )
    respx.route(method="DELETE", host=DEVICE_HOST, path__regex=DELETE_PATH).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    return respx.route(method="PUT", host=DEVICE_HOST, path__regex=PUSH_PATH).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )


class TestCatalogue:
    """Everything the frontend builds its forms from."""

    def test_connector_types_expose_their_schema(self, client):
        types = {t["id"]: t for t in client.get("/api/connector-types").json()}
        assert "weather" in types and "device" in types
        assert [f["name"] for f in types["weather"]["config_schema"]] == ["place"]

    def test_widget_types_expose_sample_data_and_variables(self, client):
        types = {t["type"]: t for t in client.get("/api/widget-types").json()}
        current = types["weather.current"]
        assert current["variables"], "the template editor lists these"
        assert current["sample_data"]["values"], "the preview needs these"
        assert current["default_display"]["text"]

    def test_every_widget_type_belongs_to_a_listed_connector(self, client):
        connectors = {t["id"] for t in client.get("/api/connector-types").json()}
        for widget in client.get("/api/widget-types").json():
            assert widget["type"].split(".", 1)[0] in connectors


class TestPreview:
    def test_sample_data_needs_no_connector(self, client):
        """What makes the builder usable before a service is configured."""
        result = client.post(
            "/api/widgets/preview",
            json={"widget_type": "weather.current",
                  "display": {"text": "{{ temp | round }}°"}},
        ).json()
        assert result["sample"] is True
        assert result["text"] == "18°"
        assert result["payload"]["text"] == "18°"

    @respx.mock
    def test_a_connector_gives_live_data(self, client):
        _, connector = setup(client)
        respx.get(FORECAST).mock(return_value=httpx.Response(200, json=CURRENT))

        result = client.post(
            "/api/widgets/preview",
            json={"widget_type": "weather.current", "connector_id": connector["id"],
                  "display": {"text": "{{ temp | round }}°"}},
        ).json()

        assert result["sample"] is False
        assert result["text"] == "19°"

    @respx.mock
    def test_an_unreachable_service_falls_back_and_says_so(self, client):
        """Editing must never stall on a service being down."""
        _, connector = setup(client)
        respx.get(FORECAST).mock(side_effect=httpx.ConnectTimeout(""))

        result = client.post(
            "/api/widgets/preview",
            json={"widget_type": "weather.current", "connector_id": connector["id"],
                  "display": {"text": "{{ temp | round }}°"}},
        ).json()

        assert result["sample"] is True
        assert result["warning_code"] == "weather.unreachable"

    def test_an_unknown_widget_type_is_refused(self, client):
        assert client.post(
            "/api/widgets/preview",
            json={"widget_type": "nope.nope", "display": {"text": "x"}},
        ).status_code == 400

    def test_hidden_when_the_service_reports_nothing(self, client):
        """A null payload means the app is removed, not that it renders empty."""
        result = client.post(
            "/api/widgets/preview",
            json={"widget_type": "device.metric", "display": {"text": "{{ value }}"}},
        ).json()
        assert result["payload"] is not None  # sample data is not empty


class TestDeviceActions:
    @respx.mock
    def test_a_test_notification_reaches_the_device(self, client):
        device, _ = setup(client)
        route = respx.post(f"{DEVICE}/api/v1/notifications").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        result = client.post(
            f"/api/devices/{device['id']}/notify", json={"text": "hello"}
        ).json()

        assert result["ok"] and result["code"] == "device.notification_sent"
        assert b'"text":"hello"' in route.calls.last.request.content.replace(b" ", b"")

    @respx.mock
    def test_an_unreachable_device_reports_instead_of_failing(self, client):
        device, _ = setup(client)
        respx.post(f"{DEVICE}/api/v1/notifications").mock(side_effect=httpx.ConnectTimeout(""))
        result = client.post(f"/api/devices/{device['id']}/notify", json={}).json()
        assert result["ok"] is False

    @respx.mock
    def test_the_live_screen_is_returned(self, client):
        device, _ = setup(client)
        pixels = [0] * 256
        # NG wraps the framebuffer in its geometry; AWTRIX 3 sent a bare list.
        respx.get(f"{DEVICE}/api/v1/display/screen").mock(
            return_value=httpx.Response(200, json={"width": 32, "height": 8, "pixels": pixels})
        )
        assert client.get(f"/api/devices/{device['id']}/screen").json() == {
            "pixels": pixels
        }

    @respx.mock
    def test_an_unreachable_screen_is_a_gateway_error(self, client):
        device, _ = setup(client)
        respx.get(f"{DEVICE}/api/v1/display/screen").mock(side_effect=httpx.ConnectTimeout(""))
        assert client.get(f"/api/devices/{device['id']}/screen").status_code == 502


class TestConnectorActions:
    @respx.mock
    def test_testing_a_service_records_its_state(self, client):
        _, connector = setup(client)
        respx.get(FORECAST).mock(return_value=httpx.Response(200, json=CURRENT))

        result = client.post(f"/api/connectors/{connector['id']}/test").json()

        assert result["ok"] and result["code"] == "weather.connected"
        assert client.get(f"/api/connectors/{connector['id']}").json()["status"] == (
            "healthy"
        )

    @respx.mock
    def test_a_failing_service_is_recorded_not_raised(self, client):
        _, connector = setup(client)
        respx.get(FORECAST).mock(side_effect=httpx.ConnectTimeout(""))

        result = client.post(f"/api/connectors/{connector['id']}/test")

        assert result.status_code == 200 and result.json()["ok"] is False
        stored = client.get(f"/api/connectors/{connector['id']}").json()
        assert stored["status"] == "error"
        assert stored["last_error_code"] == "weather.unreachable"

    def test_discover_is_empty_for_a_connector_that_does_not_browse(self, client):
        _, connector = setup(client)
        assert client.get(
            f"/api/connectors/{connector['id']}/discover?source=anything"
        ).json() == []


class TestRefreshAndReorder:
    @respx.mock
    def test_refresh_collects_and_pushes_now(self, client):
        device, connector = setup(client)
        push = mock_awtrix()
        respx.get(FORECAST).mock(return_value=httpx.Response(200, json=CURRENT))
        widget = client.post(
            "/api/widgets",
            json={"name": "W", "connector_id": connector["id"],
                  "device_ids": [device["id"]], "widget_type": "weather.current"},
        ).json()

        result = client.post(f"/api/widgets/{widget['id']}/refresh").json()

        assert result["status"] == "healthy"
        assert result["targets"][0]["last_pushed_at"] is not None
        assert push.called

    @respx.mock
    def test_push_is_an_alias_of_refresh(self, client):
        device, connector = setup(client)
        mock_awtrix()
        respx.get(FORECAST).mock(return_value=httpx.Response(200, json=CURRENT))
        widget = client.post(
            "/api/widgets",
            json={"name": "W", "connector_id": connector["id"],
                  "device_ids": [device["id"]], "widget_type": "weather.current"},
        ).json()
        assert client.post(f"/api/widgets/{widget['id']}/push").json()["status"] == (
            "healthy"
        )

    @respx.mock
    def test_reordering_a_display_reports_how_many_it_republished(self, client):
        device, connector = setup(client)
        mock_awtrix()
        respx.get(FORECAST).mock(return_value=httpx.Response(200, json=CURRENT))
        for name in ("a", "b"):
            client.post(
                "/api/widgets",
                json={"name": name, "connector_id": connector["id"],
                      "device_ids": [device["id"]], "widget_type": "weather.current"},
            )

        result = client.post(f"/api/devices/{device['id']}/reorder").json()
        assert result["ok"] and result["pushed"] == 2


@pytest.mark.parametrize("path", ["/api/connector-types", "/api/widget-types"])
def test_the_catalogue_needs_no_configuration(client, path):
    """A fresh install must be able to show what it offers."""
    assert client.get(path).json()
