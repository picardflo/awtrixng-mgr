"""Quiet hours: a window where reminders ring without their melody.

**It used to dim the display too.** That was its reason to exist on AWTRIX 3,
whose automatic brightness clamped at 2 — too bright for a bedroom, and the
floor could not be changed. So the window turned the sensor off, forced a
lower level, remembered what it had overwritten, and restored it at dawn.

NG makes `minBrightness` a setting. Measured on a TC001 in a dark room: the
panel sits exactly on that floor, and lowering it from 10 took the live
brightness down with it, 10 → 9 → 8. One setting replaces the schedule, the
saved state and the restore — and reads the room rather than the clock, so it
dims when someone actually goes to bed.

What is tested here is therefore the half a light sensor cannot do.
"""

from datetime import time

import pytest

from app.services.ng import quiet


@pytest.fixture
def device(client):
    return client.post("/api/devices", json={"name": "D", "host": "awtrix.test"}).json()


class TestTheWindow:
    """Written for 22:00→07:00, because that is what someone configures."""

    EVENING, MORNING = time(22, 0), time(7, 0)

    @pytest.mark.parametrize(
        ("hour", "expected"),
        [(21, False), (22, True), (23, True), (0, True), (3, True),
         (6, True), (7, False), (8, False), (12, False)],
    )
    def test_crossing_midnight(self, hour: int, expected: bool):
        assert quiet.is_quiet(self.EVENING, self.MORNING, time(hour, 0)) is expected

    def test_a_window_inside_one_day(self):
        """13:00→14:00 is a nap, and must not be read as its complement."""
        assert quiet.is_quiet(time(13), time(14), time(13, 30)) is True
        assert quiet.is_quiet(time(13), time(14), time(23, 0)) is False

    def test_the_start_is_inside_and_the_end_is_not(self):
        """How "22:00 to 07:00" reads to a person."""
        assert quiet.is_quiet(self.EVENING, self.MORNING, time(22, 0)) is True
        assert quiet.is_quiet(self.EVENING, self.MORNING, time(7, 0)) is False

    def test_equal_bounds_mean_nothing_rather_than_everything(self):
        """Refused by validation, and answered here rather than left to depend
        on which comparison runs first."""
        assert quiet.is_quiet(time(22), time(22), time(23)) is False


class TestTheRoute:
    def test_it_is_off_by_default(self, client, device):
        body = client.get(f"/api/devices/{device['id']}/quiet-hours").json()
        assert body["enabled"] is False

    def test_setting_it_keeps_what_was_sent(self, client, device):
        body = client.put(
            f"/api/devices/{device['id']}/quiet-hours",
            json={"enabled": True, "start": "22:00:00", "end": "07:00:00"},
        ).json()
        assert body["enabled"] is True
        assert body["start"] == "22:00:00"
        assert body["end"] == "07:00:00"

    def test_equal_bounds_are_refused(self, client, device):
        """Rather than stored and left to mean never, or always."""
        answer = client.put(
            f"/api/devices/{device['id']}/quiet-hours",
            json={"enabled": True, "start": "22:00:00", "end": "22:00:00"},
        )
        assert answer.status_code == 422

    def test_there_is_no_brightness_to_set_any_more(self, client, device):
        """Pinned so it is not quietly put back.

        A brightness here would be a second place to set one, disagreeing with
        the display's own `minBrightness` — and the whole point of the split is
        that there is one place now.
        """
        answer = client.put(
            f"/api/devices/{device['id']}/quiet-hours",
            json={"enabled": True, "start": "22:00:00", "end": "07:00:00", "brightness": 3},
        )
        assert answer.status_code == 200
        assert "brightness" not in answer.json()

    def test_nothing_at_all_is_written_to_the_display(self, client, device):
        """Not "nothing yet", nothing ever.

        The window dims nothing, so it changes no setting; and NG has no
        schedule to hand it to — probed, `/schedules`, `/automations`,
        `/timers`, `/alarms`, `/cron` and `/dnd` all answer 404. So no state
        reaches the clock, which means none can be left behind when this
        application stops.
        """
        import httpx
        import respx

        with respx.mock:
            read = respx.get("http://awtrix.test:80/api/v1/settings").mock(
                return_value=httpx.Response(200, json={})
            )
            write = respx.patch("http://awtrix.test:80/api/v1/settings").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
            client.put(
                f"/api/devices/{device['id']}/quiet-hours",
                json={"enabled": True, "start": "22:00:00", "end": "07:00:00"},
            )
            assert write.call_count == 0
            assert read.call_count == 0


class TestARingingReminder:
    """A melody inside the quiet window — the whole of what is left.

    The window used to silence the clock itself, which stopped anything that
    buzzes and left an alarm — the one reminder that exists in order to wake
    someone — with no way through. The melody is dropped at the source
    instead, per display, and one reminder can be marked to keep it.
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

    def test_a_quiet_display_loses_the_melody(self):
        from app.services.scheduler import reminders as pass_

        quiet = pass_.payload_for(self.reminder(), silent=True).to_json()
        assert "soundRtttl" not in quiet
        # Everything else still travels: it appears, it simply makes no sound.
        assert quiet["text"] == "DEBOUT"

    def test_a_display_outside_the_window_keeps_it(self):
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
