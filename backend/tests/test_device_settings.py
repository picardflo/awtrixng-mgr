"""The display's own settings: brightness, buzzer volume, rotation, formats.

Nineteen of the forty-two keys NG exposes. The others are left alone on
purpose — see the module docstring of `app/schemas/device_settings.py`.

Every range and enumeration asserted here was read out of the firmware's own
422, on a TC001 running NG 1.1.2, rather than from documentation.
"""

import json

import httpx
import pytest
import respx

from app.schemas.device_settings import DeviceSettings, changes, read

BASE = "http://awtrix.test:80"

#: A real answer from a TC001 on NG 1.1.2, trimmed to what this reads plus a
#: few keys it must leave alone.
LIVE = {
    "autoBrightness": True, "brightness": 13, "soundEnabled": True,
    "buzzerVolume": 20, "appDurationMs": 7000, "autoTransition": True,
    "transitionEffect": "Rain", "transitionDirection": "normal",
    "transitionDurationMs": 400, "uppercase": True, "useCelsius": True,
    "time24h": True, "timeLeadingZero": True, "timeShowSeconds": False,
    "timeSeparatorMode": "pulse", "dateOrder": "dayMonthYear",
    "dateSeparator": "dot", "dateYearMode": "twoDigit",
    "dateShowWeekday": True, "dateMonthNames": False,
    "scroll": {"mode": "wrap", "speed": 100, "gap": 8, "holdMs": 1000},
    # Not ours, and must survive untouched.
    "gamma": 1.899999976, "colorCorrection": None, "saturation": 100,
    "blockNavigation": False, "mp3Volume": 70,
}


@pytest.fixture
def device(client):
    return client.post("/api/devices", json={"name": "D", "host": "awtrix.test"}).json()


#: The brightness floor lives in `/api/v1/system`, not in `/api/v1/settings`.
#: Two routes, and two verbs: PATCH there, PUT here.
SYSTEM = {"minBrightness": 10, "maxBrightness": 220, "wifiSsid": "Home.lan"}


def mock_device(settings=None, system=None):
    respx.get(f"{BASE}/api/v1/settings").mock(
        return_value=httpx.Response(200, json=settings or LIVE)
    )
    respx.get(f"{BASE}/api/v1/system").mock(
        return_value=httpx.Response(200, json=system or SYSTEM)
    )
    respx.put(f"{BASE}/api/v1/system").mock(
        return_value=httpx.Response(200, json=system or SYSTEM)
    )
    # PATCH, measured: PUT and POST both answer 405 on this route.
    return respx.patch(f"{BASE}/api/v1/settings").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )


class TestReading:
    def test_it_maps_the_firmware_keys(self):
        settings = read(LIVE)
        assert settings.brightness == 13
        assert settings.buzzer_volume == 20
        assert settings.transition_ms == 400
        assert settings.transition_effect == "Rain"
        assert settings.date_order == "dayMonthYear"

    def test_milliseconds_become_seconds(self):
        """The firmware counts an app's turn in milliseconds; nobody else
        does, so the form keeps seconds."""
        assert read(LIVE).app_seconds == 7

    def test_the_scroll_speed_is_dug_out_of_its_object(self):
        """NG nests it; AWTRIX 3 had it flat as SSPEED."""
        assert read(LIVE).scroll_speed == 100

    def test_a_missing_key_falls_back_to_the_default(self):
        """A firmware that gains or loses a setting must not take the panel
        down."""
        assert read({"brightness": 42}).buzzer_volume == DeviceSettings().buzzer_volume

    def test_one_bad_value_does_not_lose_the_others(self):
        """A brightness out of range should cost the brightness, not the
        thirteen settings that read fine beside it."""
        settings = read({**LIVE, "brightness": 9999})
        assert settings.buzzer_volume == 20
        assert settings.date_order == "dayMonthYear"
        assert settings.brightness == DeviceSettings().brightness

    def test_an_empty_answer_is_not_a_crash(self):
        assert read({}) == DeviceSettings()


class TestWhatGetsSent:
    def test_only_what_differs(self):
        current = read(LIVE)
        wanted = current.model_copy(update={"brightness": 60, "buzzer_volume": 25})
        assert changes(current, wanted) == {"brightness": 60, "buzzerVolume": 25}

    def test_nothing_when_nothing_differs(self):
        current = read(LIVE)
        assert changes(current, current) == {}

    def test_it_speaks_the_firmware_s_own_names(self):
        current = read(LIVE)
        wanted = current.model_copy(update={"date_show_weekday": False})
        assert changes(current, wanted) == {"dateShowWeekday": False}

    def test_seconds_go_back_out_as_milliseconds(self):
        current = read(LIVE)
        wanted = current.model_copy(update={"app_seconds": 12})
        assert changes(current, wanted) == {"appDurationMs": 12000}

    def test_the_scroll_speed_goes_back_into_its_object(self):
        current = read(LIVE)
        wanted = current.model_copy(update={"scroll_speed": 60})
        assert changes(current, wanted) == {"scroll": {"speed": 60}}

    def test_an_awtrix3_key_is_never_produced(self):
        """Each of these answers `unknown field` on a real display."""
        current = read(LIVE)
        wanted = current.model_copy(
            update={"brightness": 1, "buzzer_volume": 1, "app_seconds": 1, "scroll_speed": 1}
        )
        produced = set(changes(current, wanted))
        assert produced.isdisjoint({"BRI", "VOL", "ATIME", "SSPEED", "TEFF", "TFORMAT"})


class TestTheRanges:
    """Read off the device, which answers "out of range" by name."""

    @pytest.mark.parametrize(
        ("field", "bad"),
        [
            ("brightness", 256),      # measured: 255 accepted, 256 refused
            ("brightness", -1),
            ("buzzer_volume", 101),   # measured: 100 accepted, 101 refused.
            ("buzzer_volume", -1),    # AWTRIX 3's was 0-30 and read as a percentage
            ("app_seconds", 0),
            ("scroll_speed", 501),
        ],
    )
    def test_out_of_range_is_refused(self, field: str, bad: int):
        with pytest.raises(ValueError):
            DeviceSettings(**{field: bad})

    @pytest.mark.parametrize(
        ("field", "bad"),
        [
            ("date_order", "yearDayMonth"),
            ("date_separator", "comma"),
            ("date_year", "threeDigit"),
            ("time_separator", "flash"),
            ("transition_direction", "sideways"),
        ],
    )
    def test_an_invented_enum_value_is_refused(self, field: str, bad: str):
        """The firmware lists its own vocabulary in the 422 — `must be one of:
        dayMonthYear monthDayYear yearMonthDay`. These are transcriptions of
        that, so a typo is caught by the form rather than by the display."""
        with pytest.raises(ValueError):
            DeviceSettings(**{field: bad})

    def test_the_measured_values_are_accepted(self):
        assert DeviceSettings(date_order="monthDayYear").date_order == "monthDayYear"
        assert DeviceSettings(time_separator="steady").time_separator == "steady"


class TestTheRoute:
    @respx.mock
    def test_it_reads_the_display(self, client, device):
        mock_device()
        body = client.get(f"/api/devices/{device['id']}/settings").json()
        assert body["brightness"] == 13
        assert body["buzzer_volume"] == 20

    @respx.mock
    def test_it_writes_only_what_changed(self, client, device):
        write = mock_device()
        current = read(LIVE).model_dump()
        answer = client.post(
            f"/api/devices/{device['id']}/settings",
            json={**current, "brightness": 60},
        ).json()
        assert answer["ok"] is True
        assert answer["applied"] == ["brightness"]
        assert json.loads(write.calls.last.request.content) == {"brightness": 60}

    @respx.mock
    def test_the_settings_it_does_not_manage_are_never_sent(self, client, device):
        """`gamma` and the colour calibration must not travel just because
        they were in the response we read."""
        write = mock_device()
        current = read(LIVE).model_dump()
        client.post(
            f"/api/devices/{device['id']}/settings",
            json={**current, "buzzer_volume": 25},
        )
        sent = json.loads(write.calls.last.request.content)
        assert set(sent) == {"buzzerVolume"}

    @respx.mock
    def test_nothing_to_change_sends_nothing(self, client, device):
        write = mock_device()
        answer = client.post(
            f"/api/devices/{device['id']}/settings", json=read(LIVE).model_dump()
        ).json()
        assert answer["code"] == "device_settings.unchanged"
        assert write.call_count == 0

    @respx.mock
    def test_it_reports_what_took_effect_not_what_was_asked(self, client, device):
        """The firmware clamps. A form showing the request rather than the
        result is a form that lies."""
        respx.get(f"{BASE}/api/v1/settings").mock(
            side_effect=[
                httpx.Response(200, json=LIVE),
                httpx.Response(200, json={**LIVE, "brightness": 255}),
            ]
        )
        respx.get(f"{BASE}/api/v1/system").mock(
            return_value=httpx.Response(200, json=SYSTEM)
        )
        respx.patch(f"{BASE}/api/v1/settings").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        answer = client.post(
            f"/api/devices/{device['id']}/settings",
            json={**read(LIVE).model_dump(), "brightness": 250},
        ).json()
        assert answer["settings"]["brightness"] == 255

    @respx.mock
    def test_an_unreachable_display_is_reported_not_raised(self, client, device):
        respx.get(f"{BASE}/api/v1/settings").mock(side_effect=httpx.ConnectError("no"))
        respx.get(f"{BASE}/api/v1/system").mock(side_effect=httpx.ConnectError("no"))
        answer = client.post(
            f"/api/devices/{device['id']}/settings", json=DeviceSettings().model_dump()
        ).json()
        assert answer["ok"] is False

    @respx.mock
    def test_a_value_out_of_range_never_reaches_the_display(self, client, device):
        write = mock_device()
        answer = client.post(
            f"/api/devices/{device['id']}/settings",
            json={**read(LIVE).model_dump(), "buzzer_volume": 999},
        )
        assert answer.status_code == 422
        assert write.call_count == 0


class TestTheBrightnessFloor:
    """What replaced bedroom mode.

    AWTRIX 3 clamped automatic brightness at 2 and offered no way to change
    it, so dimming a clock at night needed a schedule in the application. NG
    makes it a setting — measured on a TC001 in a dark room, the panel sits
    exactly on `minBrightness`, and lowering it from 10 took the live
    brightness down with it, 10 → 9 → 8.
    """

    def test_it_is_read_from_the_system_route(self):
        settings = read(LIVE, {"minBrightness": 3, "maxBrightness": 180})
        assert settings.min_brightness == 3
        assert settings.max_brightness == 180

    def test_without_the_system_answer_the_defaults_stand(self):
        """A caller that only wants the display settings pays for one request,
        not two."""
        assert read(LIVE).min_brightness == DeviceSettings().min_brightness

    def test_it_is_written_to_the_system_route_not_the_other(self):
        """`minBrightness` posted to `/settings` answers `unknown field` —
        politely, and it would not take effect."""
        from app.schemas.device_settings import system_changes

        current = read(LIVE, {"minBrightness": 10})
        wanted = current.model_copy(update={"min_brightness": 1})
        assert system_changes(current, wanted) == {"minBrightness": 1}
        assert changes(current, wanted) == {}

    @respx.mock
    def test_the_route_sends_it_with_a_put(self, client, device):
        """PUT, where `/settings` takes PATCH. Measured: PATCH on `/system`
        answers 405 naming GET and PUT."""
        mock_device()
        write = respx.put(f"{BASE}/api/v1/system")
        answer = client.post(
            f"/api/devices/{device['id']}/settings",
            json={**read(LIVE, SYSTEM).model_dump(), "min_brightness": 1},
        ).json()
        assert answer["ok"] is True
        assert "minBrightness" in answer["applied"]
        assert json.loads(write.calls.last.request.content) == {"minBrightness": 1}
