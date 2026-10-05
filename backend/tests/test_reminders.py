"""Reminders.

The risk here is timing, not plumbing: firing twice, firing at the wrong hour,
replaying this morning's alert after an evening restart, or losing the last
reminder of the day because its repeat crosses midnight.
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from app.models import Reminder
from app.services.scheduler import reminders as pass_


def a_reminder(**overrides) -> Reminder:
    fields = {
        "id": 1,
        "name": "Médicament",
        "message": "Medicament",
        "at": time(7, 30),
        "weekdays": "0,1,2,3,4",
        "duration_seconds": 10,
        "repeat_count": 0,
        "repeat_every_minutes": 2,
        "enabled": True,
    }
    fields.update(overrides)
    return Reminder(**fields)


def local(year, month, day, hour, minute, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second).astimezone()


#: 2026-10-05 is a Monday, 2026-10-10 a Saturday.
MONDAY = date(2026, 10, 5)
SATURDAY = date(2026, 10, 10)


# -- When it rings ----------------------------------------------------------


def test_a_weekday_reminder_ignores_the_weekend():
    reminder = a_reminder()
    assert len(pass_.occurrences(reminder, MONDAY)) == 1
    assert pass_.occurrences(reminder, SATURDAY) == []


def test_repeats_are_spaced_as_asked():
    reminder = a_reminder(repeat_count=2, repeat_every_minutes=3)
    moments = pass_.occurrences(reminder, MONDAY)
    assert [m.strftime("%H:%M") for m in moments] == ["07:30", "07:33", "07:36"]


def test_no_repeat_means_one_ring():
    assert len(pass_.occurrences(a_reminder(repeat_count=0), MONDAY)) == 1


# -- Whether it is due now --------------------------------------------------


def test_it_fires_on_the_minute():
    reminder = a_reminder()
    assert pass_.due(reminder, local(2026, 10, 5, 7, 30, 1)) is not None


def test_it_does_not_fire_before():
    assert pass_.due(a_reminder(), local(2026, 10, 5, 7, 29, 59)) is None


def test_it_does_not_fire_twice():
    """The loop ticks every second; without this the clock would be hammered
    for a whole minute."""
    reminder = a_reminder()
    now = local(2026, 10, 5, 7, 30, 1)
    moment = pass_.due(reminder, now)
    assert moment is not None

    reminder.last_fired_at = now
    assert pass_.due(reminder, local(2026, 10, 5, 7, 30, 2)) is None


def test_a_long_outage_is_not_replayed():
    """Restarting at noon must not ring this morning's alert."""
    assert pass_.due(a_reminder(), local(2026, 10, 5, 12, 0)) is None


def test_a_brief_restart_still_delivers():
    """Thirty seconds late is still breakfast."""
    assert pass_.due(a_reminder(), local(2026, 10, 5, 7, 30, 30)) is not None


def test_several_missed_rings_send_one_alert():
    """Down from 07:29 to 07:35 with three repeats: the clock gets the latest,
    not a burst of three."""
    reminder = a_reminder(repeat_count=3, repeat_every_minutes=2)
    moment = pass_.due(reminder, local(2026, 10, 5, 7, 35, 0))
    assert moment is not None
    assert moment.strftime("%H:%M") == "07:34"


def test_a_repeat_crossing_midnight_is_not_lost():
    """23:59 with a repeat belongs to yesterday's schedule once it is past
    midnight — looking only at today would drop it."""
    reminder = a_reminder(at=time(23, 59), repeat_count=1, repeat_every_minutes=2)
    # Monday 23:59 + 2 min = Tuesday 00:01.
    assert pass_.due(reminder, local(2026, 10, 6, 0, 1, 10)) is not None


def test_a_disabled_reminder_never_fires():
    assert pass_.due(a_reminder(enabled=False), local(2026, 10, 5, 7, 30, 1)) is None


# -- What is sent -----------------------------------------------------------


def test_the_payload_wakes_the_matrix_and_does_not_hold():
    """Blind repetition was the chosen behaviour: a held notification would sit
    there until someone pressed a button, and HTTP carries no press back."""
    payload = pass_.payload_for(a_reminder(icon="2536", duration_seconds=15))
    sent = payload.to_json()
    assert sent["text"] == "Medicament"
    assert sent["icon"] == "2536"
    assert sent["durationMs"] == 15_000
    assert sent["wakeup"] is True
    assert sent["hold"] is False


def test_accents_are_stripped_like_everywhere_else():
    payload = pass_.payload_for(a_reminder(message="Médicament à prendre"))
    assert payload.to_json()["text"] == "Medicament a prendre"


def test_a_melody_travels_inline():
    """RTTTL rather than a file: nothing to upload onto the clock."""
    melody = "alert:d=4,o=5,b=120:c,e,g"
    assert pass_.payload_for(a_reminder(melody=melody)).to_json()["soundRtttl"] == melody


def test_no_melody_sends_no_rtttl_at_all():
    assert "soundRtttl" not in pass_.payload_for(a_reminder()).to_json()


@pytest.mark.asyncio
async def test_the_icon_is_installed_before_the_alert_is_sent():
    """The defect this shipped with: a display draws only icons it already
    holds, and reminders went out without installing theirs — so the matrix
    showed text where an icon had been chosen."""
    order: list[str] = []

    class Clock:
        async def ensure_icon(self, icon):
            order.append(f"install:{icon}")
            return True

        async def notify(self, payload):
            order.append("notify")

    await pass_.send(
        a_reminder(icon="44689"), {1: Clock()}, local(2026, 10, 5, 7, 30)
    )
    assert order == ["install:44689", "notify"]


@pytest.mark.asyncio
async def test_an_icon_that_cannot_be_installed_does_not_drop_the_alert():
    """A reminder without its icon still beats no reminder at all."""
    sent: list[str] = []

    class Clock:
        async def ensure_icon(self, icon):
            from app.core.errors import AwtrixNgError

            raise AwtrixNgError("gallery down", code="icons.download_failed")

        async def notify(self, payload):
            sent.append("notify")

    fired = await pass_.send(
        a_reminder(icon="44689"), {1: Clock()}, local(2026, 10, 5, 7, 30)
    )
    assert sent == ["notify"]
    assert fired.sent_to == [1]


@pytest.mark.asyncio
async def test_no_icon_means_no_install_call():
    class Clock:
        async def ensure_icon(self, icon):
            raise AssertionError("nothing to install")

        async def notify(self, payload):
            return None

    fired = await pass_.send(a_reminder(), {1: Clock()}, local(2026, 10, 5, 7, 30))
    assert fired.sent_to == [1]


@pytest.mark.asyncio
async def test_one_unreachable_display_does_not_stop_the_others():
    """A reminder on two clocks must still reach the one that answers."""

    class Ok:
        async def ensure_icon(self, icon):
            return True

        async def notify(self, payload):
            return None

    class Broken:
        async def ensure_icon(self, icon):
            return True

        async def notify(self, payload):
            from app.core.errors import AwtrixNgError

            raise AwtrixNgError("asleep", code="device.unreachable")

    fired = await pass_.send(
        a_reminder(), {1: Broken(), 2: Ok()}, local(2026, 10, 5, 7, 30)
    )
    assert fired.sent_to == [2]
    assert fired.failed == [1]


# -- Through the API --------------------------------------------------------


def test_the_api_round_trip(client):
    device = client.post(
        "/api/devices", json={"name": "Bureau", "host": "127.0.0.1", "port": 9101}
    ).json()

    created = client.post(
        "/api/reminders",
        json={
            "name": "Médicament",
            "message": "Medicament",
            "at": "07:30:00",
            "days": [0, 1, 2, 3, 4],
            "repeat_count": 2,
            "device_ids": [device["id"]],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["days"] == [0, 1, 2, 3, 4]
    assert body["device_ids"] == [device["id"]]
    assert body["next_at"] is not None

    assert client.get("/api/reminders").json()[0]["id"] == body["id"]
    assert client.delete(f"/api/reminders/{body['id']}").status_code == 204
    assert client.get("/api/reminders").json() == []


def test_a_reminder_that_could_never_ring_is_refused(client):
    for days in ([], [9]):
        response = client.post(
            "/api/reminders",
            json={"name": "x", "message": "y", "at": "08:00:00", "days": days},
        )
        assert response.status_code == 422, days


def test_an_unknown_display_is_refused_not_ignored(client):
    """Silently firing on fewer clocks than asked is the kind of thing nobody
    notices until the morning it mattered."""
    response = client.post(
        "/api/reminders",
        json={"name": "x", "message": "y", "at": "08:00:00", "device_ids": [999]},
    )
    assert response.status_code == 404


def test_deleting_a_display_takes_its_targets_with_it(client):
    device = client.post(
        "/api/devices", json={"name": "Salon", "host": "127.0.0.1", "port": 9102}
    ).json()
    reminder = client.post(
        "/api/reminders",
        json={
            "name": "x",
            "message": "y",
            "at": "08:00:00",
            "device_ids": [device["id"]],
        },
    ).json()

    assert client.delete(f"/api/devices/{device['id']}").status_code == 204
    assert client.get(f"/api/reminders/{reminder['id']}").json()["device_ids"] == []


def test_next_at_is_empty_when_disabled(client):
    reminder = client.post(
        "/api/reminders",
        json={"name": "x", "message": "y", "at": "08:00:00", "enabled": False},
    ).json()
    assert reminder["next_at"] is None


class TestDisplayOptions:
    """The options a widget offers, on a reminder.

    An oversight, not a technical limit: the firmware takes them all on a
    notification. The ones a reminder cannot use are absent on purpose — it
    carries no data, so no progress bar and nothing to hide when a service
    returns none.
    """

    def test_they_reach_the_payload(self):
        payload = pass_.payload_for(
            a_reminder(
                scroll_mode="static",
                scroll_speed=40,
                background="#101010",
            )
        ).to_json()
        assert payload["scroll"] == {"mode": "static", "speed": 40}
        assert payload["backgroundColor"] == "#101010"

    def test_the_defaults_leave_the_firmware_alone(self):
        """Sending an explicit value everywhere would freeze the clock on our
        opinion rather than its own settings."""
        payload = pass_.payload_for(a_reminder()).to_json()
        for key in ("scroll", "backgroundColor"):
            assert key not in payload, key

    def test_the_options_awtrix3_had_and_ng_does_not_are_gone(self):
        """`center` and `rainbow` were offered on the previous project.
        Measured on NG: there is no centring key, and `palette` colours
        effects rather than text. A control the firmware ignores is worse
        than no control — it is an evening spent wondering why nothing
        changes."""
        from app.models import Reminder

        for dead in ("center", "rainbow", "no_scroll"):
            assert dead not in Reminder.model_fields

    def test_the_api_round_trips_them(self, client):
        device = client.post(
            "/api/devices", json={"name": "Bureau", "host": "127.0.0.1"}
        ).json()
        created = client.post(
            "/api/reminders",
            json={
                "name": "x",
                "message": "y",
                "at": "08:00:00",
                "device_ids": [device["id"]],
                "scroll_mode": "static",
                "scroll_speed": 40,
                "background": "#101010",
            },
        ).json()
        assert created["scroll_mode"] == "static"
        assert created["scroll_speed"] == 40
        assert created["background"] == "#101010"

        updated = client.patch(
            f"/api/reminders/{created['id']}", json={"scroll_mode": "bounce"}
        ).json()
        assert updated["scroll_mode"] == "bounce"
        assert updated["scroll_speed"] == 40, "an unrelated field moved"


class TestEveryNWeeks:
    """Fortnightly reminders — Florian's bins: black every week, blue every
    other one."""

    @staticmethod
    def fortnightly(**overrides) -> Reminder:
        fields = {"every_weeks": 2, "anchor": date(2026, 10, 5), "weekdays": "6"}
        fields.update(overrides)
        return a_reminder(**fields)

    def test_every_week_is_the_default(self):
        reminder = a_reminder()
        assert reminder.every_weeks == 1
        for offset in range(0, 28, 7):
            assert pass_.fires_this_week(reminder, MONDAY + timedelta(days=offset))

    def test_one_week_in_two(self):
        reminder = self.fortnightly()
        weeks = [
            pass_.fires_this_week(reminder, date(2026, 10, 5) + timedelta(days=7 * n))
            for n in range(6)
        ]
        assert weeks == [True, False, True, False, True, False]

    def test_one_week_in_three(self):
        reminder = self.fortnightly(every_weeks=3)
        weeks = [
            pass_.fires_this_week(reminder, date(2026, 10, 5) + timedelta(days=7 * n))
            for n in range(6)
        ]
        assert weeks == [True, False, False, True, False, False]

    def test_the_whole_week_counts_not_just_the_anchor_day(self):
        """The anchor names a week, not a day: any day of it should agree."""
        reminder = self.fortnightly()
        for offset in range(7):
            assert pass_.fires_this_week(reminder, date(2026, 10, 5) + timedelta(days=offset))

    def test_it_survives_the_new_year(self):
        """2026 has 53 ISO weeks; subtracting week numbers would flip the
        answer on the 1st of January. Same lesson as the A/B school week."""
        reminder = self.fortnightly(anchor=date(2026, 12, 21))
        assert pass_.fires_this_week(reminder, date(2026, 12, 21))
        assert not pass_.fires_this_week(reminder, date(2026, 12, 28))
        assert pass_.fires_this_week(reminder, date(2027, 1, 4))
        assert not pass_.fires_this_week(reminder, date(2027, 1, 11))

    def test_an_off_week_produces_no_occurrence_at_all(self):
        reminder = self.fortnightly(at=time(19, 45))
        on = date(2026, 10, 11)   # Sunday of the anchor week
        off = date(2026, 10, 18)  # the Sunday after
        assert len(pass_.occurrences(reminder, on)) == 1
        assert pass_.occurrences(reminder, off) == []

    def test_a_missing_anchor_falls_back_to_the_creation_week(self):
        """Rather than refusing: a reminder created today and set to every
        other week plainly means starting this week."""
        reminder = self.fortnightly(anchor=None)
        reminder.created_at = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
        assert pass_.fires_this_week(reminder, date(2026, 10, 5))
        assert not pass_.fires_this_week(reminder, date(2026, 10, 12))

    def test_the_api_keeps_the_cycle(self, client):
        device = client.post(
            "/api/devices", json={"name": "Salon", "host": "127.0.0.1"}
        ).json()
        created = client.post(
            "/api/reminders",
            json={
                "name": "Papiers",
                "message": "Papiers",
                "at": "19:45:00",
                "days": [6],
                "every_weeks": 2,
                "anchor": "2026-10-11",
                "device_ids": [device["id"]],
            },
        ).json()
        assert created["every_weeks"] == 2
        assert created["anchor"] == "2026-10-11"
        # The next ring must be a Sunday of an on-week, never the one between.
        assert created["next_at"] is not None

    def test_an_anchor_is_set_even_when_none_is_given(self, client):
        """Stored rather than left null, so the cycle cannot shift later if the
        fallback ever changes."""
        created = client.post(
            "/api/reminders",
            json={"name": "x", "message": "y", "at": "08:00:00", "every_weeks": 2},
        ).json()
        assert created["anchor"] is not None


class TestASingleDate:
    """`on_date`: a car service, an appointment — once, then never."""

    def one_off(self, **kwargs) -> Reminder:
        return Reminder(
            name="Entretien",
            message="ENTRETIEN VOITURE",
            at=time(9, 0),
            on_date=date(2026, 11, 15),
            **{"weekdays": "0,1,2,3,4,5,6", **kwargs},
        )

    def test_it_rings_on_that_day(self):
        assert pass_.occurrences(self.one_off(), date(2026, 11, 15))

    def test_it_is_silent_every_other_day(self):
        for day in (date(2026, 11, 14), date(2026, 11, 16), date(2027, 11, 15)):
            assert not pass_.occurrences(self.one_off(), day), day

    def test_the_weekly_rhythm_no_longer_applies(self):
        """15/11/2026 is a Sunday, and the reminder is set to weekdays only.

        A date someone typed in beats a weekday list they left at its default,
        otherwise the reminder silently does nothing on the one day it exists
        for.
        """
        sunday = date(2026, 11, 15)
        assert sunday.weekday() == 6
        assert pass_.occurrences(self.one_off(weekdays="0,1,2,3,4"), sunday)

    def test_every_n_weeks_no_longer_applies(self):
        """Same reasoning for the A/B-week cycle."""
        assert pass_.occurrences(
            self.one_off(every_weeks=2, anchor=date(2026, 11, 9)), date(2026, 11, 15)
        )


class TestCountdown:
    """`countdown_to`: the message changes, the schedule does not.

    Written in French throughout, so the language is pinned rather than
    inherited: the default is English, and "J-406" was hard-coded until an
    English installation showed it.
    """

    @pytest.fixture(autouse=True)
    def _speaking_french(self, monkeypatch):
        from app.core import language

        monkeypatch.setattr(language, "_chosen", "fr")

    def loan(self, message: str = "PRET {{ countdown }}") -> Reminder:
        return Reminder(
            name="Prêt",
            message=message,
            at=time(8, 0),
            weekdays="0,1,2,3,4,5,6",
            countdown_to=date(2027, 11, 15),
        )

    def text(self, reminder: Reminder, today: date) -> str:
        return pass_.payload_for(reminder, today).to_json()["text"]

    def test_it_counts_down(self):
        assert self.text(self.loan(), date(2027, 11, 14)) == "PRET J-1"
        assert self.text(self.loan(), date(2027, 10, 15)) == "PRET J-31"

    def test_the_day_itself_is_neither_minus_nor_plus_zero(self):
        assert self.text(self.loan(), date(2027, 11, 15)) == "PRET JOUR J"

    def test_overdue_counts_up_rather_than_going_negative(self):
        """"J--3" is what composing it by hand produces. A missed deadline has
        to look different from a reached one."""
        assert self.text(self.loan(), date(2027, 11, 18)) == "PRET J+3"

    def test_the_raw_number_is_signed(self):
        assert self.text(self.loan("{{ days }}"), date(2027, 11, 18)) == "-3"

    def test_the_date_is_written_the_french_way(self):
        assert self.text(self.loan("{{ date }}"), date(2026, 1, 1)) == "15/11/2027"

    def test_a_reminder_without_a_target_interpolates_nothing(self):
        """Not the literal braces, and not a crash: empty. An ordinary message
        that happens to contain {{ }} must not start showing a date."""
        plain = Reminder(
            name="Réveil", message="DEBOUT {{ countdown }}", at=time(7, 0), weekdays="0"
        )
        assert self.text(plain, date(2026, 1, 1)) == "DEBOUT "

    def test_the_schedule_is_untouched(self):
        """A countdown is about what it says, not when it says it."""
        weekdays_only = self.loan()
        weekdays_only.weekdays = "0,1,2,3,4"
        assert not pass_.occurrences(weekdays_only, date(2027, 11, 13))
        assert pass_.occurrences(weekdays_only, date(2027, 11, 12))

    def test_accents_still_go_before_the_matrix(self):
        """The countdown runs through the same hardware boundary as any text."""
        assert self.text(self.loan("ECHEANCE {{ countdown }}"), date(2027, 11, 15)) == (
            "ECHEANCE JOUR J"
        )


class TestThePreviewAgrees:
    """One rule, two implementations, one table.

    The reminder form computes the countdown in TypeScript so the preview can
    show it without a round trip. `countdown.test.ts` reads this same file.
    Either side drifting fails here.
    """

    CASES = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "frontend/src/features/reminders/countdown-cases.json"
        ).read_text()
    )

    def test_the_table_is_not_empty(self):
        """A fixture that silently became empty would make every case below
        vacuously pass."""
        assert len(self.CASES["cases"]) >= 5

    @pytest.mark.parametrize("language", ["en", "fr"])
    @pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["today"])
    def test_each_case(self, case: dict, language: str, monkeypatch):
        reminder = Reminder(
            name="Prêt",
            message="PRET {{ countdown }}",
            at=time(8, 0),
            weekdays="0,1,2,3,4,5,6",
            countdown_to=date.fromisoformat(self.CASES["target"]),
        )
        from app.core import language as lang

        monkeypatch.setattr(lang, "_chosen", language)
        today = date.fromisoformat(case["today"])
        values = pass_.countdown_values(reminder, today)

        assert values["countdown"] == case[language]
        assert values["days"] == case["days"]
        assert pass_.payload_for(reminder, today).to_json()["text"] == (
            f"PRET {case[language]}"
        )
