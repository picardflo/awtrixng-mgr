"""Sunrise and sunset.

The arithmetic is small but every piece of it has a way of being wrong for an
hour a day, or for half the year, or everywhere but here — so each is pinned.
"""

from datetime import UTC, datetime

import pytest

from app.connectors.weather import sun

#: A real Open-Meteo answer for Rambouillet, trimmed. Two days, because
#: that is what makes "next" answerable after the sun has gone down.
PARIS = {
    "utc_offset_seconds": 7200,
    "timezone": "Europe/Paris",
    "daily": {
        "time": ["2026-10-03", "2026-10-04"],
        "sunrise": ["2026-10-03T07:54", "2026-10-04T07:56"],
        "sunset": ["2026-10-03T19:27", "2026-10-04T19:25"],
        "daylight_duration": [41583.97, 41371.39],
    },
}


def utc(hour: int, minute: int = 0, day: int = 3) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


class TestWhatTimeItIsThere:
    def test_the_offset_is_applied(self):
        """09:00 UTC is 11:00 in Paris in October."""
        assert sun.local_now(PARIS, utc(9)) == datetime(2026, 10, 3, 11, 0)

    def test_a_response_without_an_offset_is_read_as_utc(self):
        """Rather than raising. A missing field should degrade, not break a
        widget that was working this morning."""
        assert sun.local_now({}, utc(9)) == datetime(2026, 10, 3, 9, 0)


class TestWhichComesNext:
    @pytest.mark.parametrize(
        ("at", "code", "when"),
        [
            # 04:00 UTC = 06:00 local, before sunrise.
            (utc(4), "sunrise", "2026-10-03T07:54"),
            # 10:00 UTC = 12:00 local, between the two.
            (utc(10), "sunset", "2026-10-03T19:27"),
            # 19:00 UTC = 21:00 local: today is done, so it is tomorrow's
            # sunrise. This is the case a single-day request cannot answer.
            (utc(19), "sunrise", "2026-10-04T07:56"),
        ],
    )
    def test_each_part_of_the_day(self, at: datetime, code: str, when: str):
        event = sun.next_event(PARIS, at)
        assert event is not None
        assert event.code == code
        assert event.at == datetime.fromisoformat(when)

    def test_the_icon_follows_the_event(self):
        assert sun.next_event(PARIS, utc(4)).icon == sun.ICON_SUNRISE
        assert sun.next_event(PARIS, utc(10)).icon == sun.ICON_SUNSET

    def test_nothing_left_in_the_response_is_not_a_crash(self):
        """Past the end of the forecast. A widget shows no time rather than
        falling over."""
        assert sun.next_event(PARIS, utc(23, 0, day=5)) is None

    def test_an_empty_response_is_not_a_crash(self):
        assert sun.next_event({}, utc(10)) is None


class TestTodaysPair:
    def test_it_reads_the_day_the_place_is_living(self):
        """At 23:00 UTC it is already the 4th in Paris, so "today" is the 4th.

        Taking `[0]` would answer with the 3rd for that hour every night — the
        kind of error nobody reproduces on purpose.
        """
        sunrise, sunset = sun.today(PARIS, utc(23))
        assert sunrise == datetime(2026, 10, 4, 7, 56)
        assert sunset == datetime(2026, 10, 4, 19, 25)

    def test_an_ordinary_hour(self):
        sunrise, sunset = sun.today(PARIS, utc(10))
        assert sunrise == datetime(2026, 10, 3, 7, 54)
        assert sunset == datetime(2026, 10, 3, 19, 27)

    def test_a_date_outside_the_response_falls_back_to_the_first(self):
        sunrise, _ = sun.today(PARIS, utc(10, 0, day=9))
        assert sunrise == datetime(2026, 10, 3, 7, 54)


class TestHowMuchDaylightHasGone:
    SUNRISE = datetime(2026, 10, 3, 8, 0)
    SUNSET = datetime(2026, 10, 3, 20, 0)

    def test_halfway(self):
        assert sun.daylight_elapsed(self.SUNRISE, self.SUNSET, datetime(2026, 10, 3, 14, 0)) == 50

    def test_a_quarter_in(self):
        assert sun.daylight_elapsed(self.SUNRISE, self.SUNSET, datetime(2026, 10, 3, 11, 0)) == 25

    @pytest.mark.parametrize("hour", [6, 7, 21, 23])
    def test_outside_daylight_there_is_no_bar_at_all(self, hour: int):
        """Not 0 and not 100: a bar pinned at either end all night reads as a
        measurement rather than as "this does not apply"."""
        moment = datetime(2026, 10, 3, hour, 0)
        assert sun.daylight_elapsed(self.SUNRISE, self.SUNSET, moment) is None

    def test_a_missing_end_gives_nothing(self):
        assert sun.daylight_elapsed(None, self.SUNSET, datetime(2026, 10, 3, 14, 0)) is None

    def test_a_polar_day_does_not_divide_by_zero(self):
        """Above the Arctic circle Open-Meteo can return the same instant
        twice. The widget shows no bar instead of raising."""
        same = datetime(2026, 6, 21, 0, 0)
        assert sun.daylight_elapsed(same, same, same) is None


class TestTheWidget:
    """The projection, which is where the module above meets the matrix."""

    def connector(self):
        from app.connectors.weather.connector import WeatherConnector

        return WeatherConnector(
            config={"place": {"latitude": 48.6436, "longitude": 1.9}}, secrets={}
        )

    def values(self, raw: dict, monkeypatch, at: datetime) -> dict:
        import app.connectors.weather.connector as module

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return at

        monkeypatch.setattr(module, "datetime", Frozen)
        return dict(self.connector().project("weather.sun", {}, raw).values)

    def test_it_reports_both_times_and_the_next_one(self, monkeypatch):
        values = self.values(PARIS, monkeypatch, utc(10))
        assert values["sunrise"] == "07:54"
        assert values["sunset"] == "19:27"
        assert values["next"] == "19:27"
        assert values["event_code"] == "sunset"

    def test_after_dark_it_points_at_tomorrow(self, monkeypatch):
        values = self.values(PARIS, monkeypatch, utc(19))
        assert values["next"] == "07:56"
        assert values["event_code"] == "sunrise"

    def test_daylight_is_seconds_so_the_duration_filter_can_read_it(self, monkeypatch):
        from app.widgets import template

        values = self.values(PARIS, monkeypatch, utc(10))
        assert values["daylight"] == 41583
        assert template.render("{{ daylight | duration }}", values) == "11H33"

    def test_the_bar_tracks_the_day(self, monkeypatch):
        import app.connectors.weather.connector as module

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                # 11:41 UTC = 13:41 local, halfway between 07:54 and 19:27.
                return utc(11, 41)

        monkeypatch.setattr(module, "datetime", Frozen)
        data = self.connector().project("weather.sun", {}, PARIS)
        assert data.progress == 50

    def test_an_empty_response_shows_nothing_rather_than_failing(self, monkeypatch):
        values = self.values({}, monkeypatch, utc(10))
        assert values["next"] is None
        assert values["sunrise"] is None


class TestTheColourSaysWhichEvent:
    """Fixed amber for both, where the weather widget next door has coloured
    itself by value since the beginning.

    Noticed from the other end: someone set a progress bar to the widget's
    colour and asked whether it would still match at sunrise. It would have —
    because nothing changed — and that was the defect.
    """

    def values(self, monkeypatch, at: datetime):
        import app.connectors.weather.connector as module

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return at

        monkeypatch.setattr(module, "datetime", Frozen)
        from app.connectors.weather.connector import WeatherConnector

        connector = WeatherConnector(
            config={"place": {"latitude": 48.6436, "longitude": 1.9}}, secrets={}
        )
        return connector.project("weather.sun", {}, PARIS)

    def test_sunrise_and_sunset_do_not_share_a_colour(self, monkeypatch):
        before_dawn = self.values(monkeypatch, utc(4)).hint_color
        midday = self.values(monkeypatch, utc(10)).hint_color
        assert before_dawn == sun.COLOURS["sunrise"]
        assert midday == sun.COLOURS["sunset"]
        assert before_dawn != midday

    def test_the_colour_matches_the_icon(self, monkeypatch):
        """Both answer "which of the two is next", so they cannot disagree."""
        for at in (utc(4), utc(10), utc(19)):
            data = self.values(monkeypatch, at)
            expected = (
                sun.COLOURS["sunrise"]
                if int(data.hint_icon) == sun.ICON_SUNRISE
                else sun.COLOURS["sunset"]
            )
            assert data.hint_color == expected, at

    def test_a_response_with_nothing_left_still_has_a_colour(self, monkeypatch):
        """No event is not a reason to send no colour: the widget still draws
        a text, and an uncoloured one would be the firmware's white."""
        assert self.values(monkeypatch, utc(23, 0, day=5)).hint_color


class TestTheDaylightBar:
    """The bar was computed from the first version and never switched on.

    `daylight_elapsed` is written, tested, and its own docstring says it
    "drives the progress bar". The projection filled `progress` on every pass.
    And the default display did not set `show_progress`, so the renderer threw
    it away — for the whole life of the previous project.

    Nothing failed. The widget showed a time, which is what it promised, and
    the figure behind the bar was recomputed every fifteen minutes and
    discarded.
    """

    def widget(self):
        from app.connectors import registry

        registry.load_all()
        return registry.widget_descriptor("weather.sun")

    def test_the_bar_is_switched_on(self):
        assert self.widget().default_display.show_progress is True

    def test_a_time_fills_the_panel(self):
        """Five characters in the large font measured at 24 columns of 32 with
        the icon — the bar underneath, untouched."""
        assert self.widget().default_display.font == "large"

    def test_during_the_day_the_bar_shows_how_much_is_left(self):
        from app.widgets.renderer import render

        descriptor = self.widget()
        payload = render(descriptor.sample_data, descriptor.default_display).to_json()
        assert payload["progress"] == 62
        # One palette: the bar takes the colour of the next sun event, and its
        # track a dark wash of the same.
        assert payload["progressColor"] == payload["textColor"]
        assert payload["progressTrackColor"] == "#2e200d"

    def test_at_night_there_is_no_bar_at_all(self):
        """`daylight_elapsed` returns None outside daylight, deliberately: a
        bar sitting at 0 % or 100 % all night reads as a measurement rather
        than as "not applicable"."""
        from app.widgets.renderer import render

        descriptor = self.widget()
        night = descriptor.sample_data.model_copy(update={"progress": None})
        payload = render(night, descriptor.default_display).to_json()
        assert "progress" not in payload
        assert "progressColor" not in payload
        assert "progressTrackColor" not in payload
