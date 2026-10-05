"""Bedroom mode: a window where a display is dimmed and silent.

The firmware has nothing like it — its only brightness controls are a manual
level, one driven by the light sensor, and a deep sleep that turns the matrix
off. Checked across the whole official documentation before writing a line.
"""

from datetime import time

import httpx
import pytest
import respx

from app.services.ng import night

BASE = "http://awtrix.test:80"

#: What the display is set to during the day, as the firmware reports it.
DAY = {"brightness": 120, "autoBrightness": True, "soundEnabled": True}


class TestTheWindow:
    """Written for 22:00→07:00, because that is what someone configures."""

    EVENING, MORNING = time(22, 0), time(7, 0)

    @pytest.mark.parametrize(
        ("hour", "expected"),
        [(21, False), (22, True), (23, True), (0, True), (3, True),
         (6, True), (7, False), (8, False), (12, False)],
    )
    def test_crossing_midnight(self, hour: int, expected: bool):
        assert night.is_night(self.EVENING, self.MORNING, time(hour, 0)) is expected

    def test_a_window_inside_one_day(self):
        """13:00→14:00 is a nap, and must not be read as its complement."""
        assert night.is_night(time(13), time(14), time(13, 30)) is True
        assert night.is_night(time(13), time(14), time(23, 0)) is False

    def test_the_start_is_inside_and_the_end_is_not(self):
        """How "22:00 to 07:00" reads to a person."""
        assert night.is_night(self.EVENING, self.MORNING, time(22, 0)) is True
        assert night.is_night(self.EVENING, self.MORNING, time(7, 0)) is False

    def test_equal_bounds_mean_nothing_rather_than_everything(self):
        """Refused by validation, and answered here rather than left to depend
        on which comparison runs first."""
        assert night.is_night(time(22), time(22), time(23)) is False


class TestWhatIsWritten:
    def test_the_light_sensor_is_always_turned_off(self):
        """A dim level under an active sensor lasts about a second."""
        assert night.night_settings(2, mute=True)["autoBrightness"] is False

    def test_it_dims_without_touching_the_volume(self):
        assert night.night_settings(2) == {"brightness": 2, "autoBrightness": False}

    def test_the_volume_is_left_alone_when_not_muting(self):
        assert "soundEnabled" not in night.night_settings(2, mute=False)

    def test_what_is_saved_round_trips(self):
        saved = night.Saved.from_settings(DAY)
        assert saved.to_settings() == {
            "brightness": 120,
            "autoBrightness": True,
            "soundEnabled": True,
        }

    def test_a_display_that_reports_nothing_still_gives_a_usable_default(self):
        """Restoring to zero brightness would leave a dark clock at seven."""
        assert night.Saved.from_settings({}).brightness > 0


@pytest.fixture
def device(client):
    return client.post("/api/devices", json={"name": "D", "host": "awtrix.test"}).json()


def mock_device(settings=None):
    respx.get(f"{BASE}/api/v1/settings").mock(
        return_value=httpx.Response(200, json=settings or DAY)
    )
    return respx.patch(f"{BASE}/api/v1/settings").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )


class TestTheRoute:
    def test_it_is_off_by_default(self, client, device):
        body = client.get(f"/api/devices/{device['id']}/bedroom").json()
        assert body["enabled"] is False
        assert body["active"] is False

    def test_setting_it_keeps_what_was_sent(self, client, device):
        body = client.put(
            f"/api/devices/{device['id']}/bedroom",
            json={"enabled": True, "start": "22:00:00", "end": "07:00:00", "brightness": 3},
        ).json()
        assert body["enabled"] is True
        assert body["brightness"] == 3
        assert body["start"] == "22:00:00"

    def test_equal_bounds_are_refused(self, client, device):
        """Rather than stored and left to mean never, or always."""
        answer = client.put(
            f"/api/devices/{device['id']}/bedroom",
            json={"enabled": True, "start": "22:00:00", "end": "22:00:00", "brightness": 2},
        )
        assert answer.status_code == 422

    def test_a_brightness_out_of_range_is_refused(self, client, device):
        answer = client.put(
            f"/api/devices/{device['id']}/bedroom",
            json={"enabled": True, "start": "22:00:00", "end": "07:00:00", "brightness": 300},
        )
        assert answer.status_code == 422

    def test_saving_writes_nothing_to_the_display(self, client, device):
        """The firmware has no schedule: awtrixng-mgr keeps it, and the pass
        applies it. A write here would dim the clock at three in the
        afternoon."""
        with respx.mock:
            write = mock_device()
            client.put(
                f"/api/devices/{device['id']}/bedroom",
                json={"enabled": True, "start": "22:00:00", "end": "07:00:00", "brightness": 2},
            )
            assert write.call_count == 0


class TestThePass:
    """What the scheduler actually does at the boundaries."""

    async def run_at(self, monkeypatch, hour: int, minute: int = 0):
        from datetime import datetime

        import app.services.scheduler.loop as loop

        monkeypatch.setattr(
            loop.reminder_pass,
            "local_now",
            lambda: datetime(2026, 10, 4, hour, minute),
        )
        return await loop.scheduler.apply_bedroom_mode()

    def enable(self, client, device, **extra):
        return client.put(
            f"/api/devices/{device['id']}/bedroom",
            json={
                "enabled": True,
                "start": "22:00:00",
                "end": "07:00:00",
                "brightness": 2,
                **extra,
            },
        ).json()

    @respx.mock
    @pytest.mark.asyncio
    async def test_it_dims_at_the_boundary(self, client, device, monkeypatch):
        write = mock_device()
        self.enable(client, device)

        assert await self.run_at(monkeypatch, 22, 0) == [device["id"]]
        import json as _json

        assert _json.loads(write.calls.last.request.content) == {
            "brightness": 2,
            "autoBrightness": False,
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_it_never_touches_the_sound(self, client, device, monkeypatch):
        """Muting the clock silenced anything that buzzes and left an alarm
        that exists to wake someone with no way through. Reminders drop their
        own melody instead, one display at a time."""
        write = mock_device()
        self.enable(client, device)
        await self.run_at(monkeypatch, 22, 0)

        import json as _json

        assert "soundEnabled" not in _json.loads(write.calls.last.request.content)

    @respx.mock
    @pytest.mark.asyncio
    async def test_it_does_nothing_during_the_day(self, client, device, monkeypatch):
        write = mock_device()
        self.enable(client, device)

        assert await self.run_at(monkeypatch, 15, 0) == []
        assert write.call_count == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_the_morning_restores_what_the_evening_found(
        self, client, device, monkeypatch
    ):
        """Not a default: the display goes back to the 120 and the automatic
        brightness it had at ten in the evening."""
        write = mock_device()
        self.enable(client, device)
        await self.run_at(monkeypatch, 22, 0)

        await self.run_at(monkeypatch, 7, 0)
        import json as _json

        assert _json.loads(write.calls.last.request.content) == {
            "brightness": 120, "autoBrightness": True, "soundEnabled": True
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_second_pass_inside_the_window_writes_nothing(
        self, client, device, monkeypatch
    ):
        """A brightness raised by hand at midnight must survive until morning,
        rather than be pushed back down thirty seconds later."""
        write = mock_device()
        self.enable(client, device)
        await self.run_at(monkeypatch, 22, 0)
        before = write.call_count

        assert await self.run_at(monkeypatch, 2, 0) == []
        assert write.call_count == before

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_boundary_missed_while_down_is_caught_up(
        self, client, device, monkeypatch
    ):
        """awtrixng-mgr off at 22:00 and back at 23:30: the window still opens,
        because the pass compares states instead of waiting for an edge."""
        write = mock_device()
        self.enable(client, device)

        assert await self.run_at(monkeypatch, 23, 30) == [device["id"]]
        assert write.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_turning_it_off_mid_window_puts_the_display_back(
        self, client, device, monkeypatch
    ):
        write = mock_device()
        self.enable(client, device)
        await self.run_at(monkeypatch, 23, 0)

        client.put(
            f"/api/devices/{device['id']}/bedroom",
            json={"enabled": False, "start": "22:00:00", "end": "07:00:00", "brightness": 2},
        )
        await self.run_at(monkeypatch, 23, 1)
        import json as _json

        assert _json.loads(write.calls.last.request.content) == {
            "brightness": 120, "autoBrightness": True, "soundEnabled": True
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_unreachable_display_is_retried_not_skipped(
        self, client, device, monkeypatch
    ):
        """A clock rebooting at 22:00 must be dimmed when it comes back, not
        left bright until tomorrow night."""
        respx.get(f"{BASE}/api/v1/settings").mock(side_effect=httpx.ConnectError("no"))
        self.enable(client, device)

        assert await self.run_at(monkeypatch, 22, 0) == []

        respx.get(f"{BASE}/api/v1/settings").mock(
            return_value=httpx.Response(200, json=DAY)
        )
        write = respx.patch(f"{BASE}/api/v1/settings").mock(
            return_value=httpx.Response(200)
        )
        assert await self.run_at(monkeypatch, 22, 1) == [device["id"]]
        assert write.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_display_without_the_mode_is_left_alone(
        self, client, device, monkeypatch
    ):
        write = mock_device()
        assert await self.run_at(monkeypatch, 23, 0) == []
        assert write.call_count == 0


class TestARingingReminder:
    """A melody inside a dimmed window.

    Bedroom mode used to silence the clock entirely, which stopped
    anything that buzzes and left an alarm — the one reminder that exists in
    order to wake someone — with no way through. The melody is now dropped at
    the source, per display, and one reminder can be marked to keep it.
    """

    from datetime import time as _time

    def reminder(self, **extra):
        from datetime import time as t

        from app.models import Reminder

        return Reminder(
            name="Réveil",
            message="DEBOUT",
            at=t(6, 30),
            weekdays="0,1,2,3,4,5,6",
            melody="rappel:d=16,o=6,b=120:c,e,g",
            **extra,
        )

    def test_a_dimmed_display_loses_the_melody(self):
        from app.services.scheduler import reminders as pass_

        quiet = pass_.payload_for(self.reminder(), silent=True).to_json()
        assert "soundRtttl" not in quiet
        # Everything else still travels: it appears, it simply makes no sound.
        assert quiet["text"] == "DEBOUT"

    def test_a_lit_display_keeps_it(self):
        from app.services.scheduler import reminders as pass_

        assert pass_.payload_for(self.reminder()).to_json()["soundRtttl"]

    @pytest.mark.asyncio
    async def test_the_decision_is_per_display(self):
        """The same alert rings in the kitchen and stays quiet in the bedroom:
        one payload for all of them would have to pick one or the other."""
        from unittest.mock import AsyncMock

        from app.services.scheduler import reminders as pass_

        bedroom, kitchen = AsyncMock(), AsyncMock()
        await pass_.send(
            self.reminder(),
            {1: bedroom, 2: kitchen},
            pass_.local_now(),
            silent_on=frozenset({1}),
        )
        assert "soundRtttl" not in bedroom.notify.call_args.args[0].to_json()
        assert kitchen.notify.call_args.args[0].to_json()["soundRtttl"]

    @pytest.mark.asyncio
    async def test_one_marked_to_ring_keeps_it_everywhere(self):
        from unittest.mock import AsyncMock

        from app.services.scheduler import reminders as pass_

        bedroom = AsyncMock()
        # What the loop does with the flag: it sends no silent displays at all.
        await pass_.send(
            self.reminder(rings_at_night=True),
            {1: bedroom},
            pass_.local_now(),
            silent_on=frozenset(),
        )
        assert bedroom.notify.call_args.args[0].to_json()["soundRtttl"]

    def test_a_reminder_without_a_melody_is_unaffected(self):
        from datetime import time as t

        from app.models import Reminder
        from app.services.scheduler import reminders as pass_

        plain = Reminder(name="X", message="X", at=t(6, 30), weekdays="0")
        assert "soundRtttl" not in pass_.payload_for(plain, silent=True).to_json()
        assert "soundRtttl" not in pass_.payload_for(plain).to_json()
