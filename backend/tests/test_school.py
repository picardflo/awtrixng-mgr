"""The school week.

Every expectation here was read off the two official calendars Florian
supplied, or confirmed against his daughter's own timetable — not produced by
this code and then frozen.
"""

from datetime import date, timedelta

import pytest

from app.connectors.school import calendar as cal
from app.connectors.school.connector import SchoolConnector

#: Zone C / Versailles, from the Ministry's dataset.
RENTREE_2026 = date(2026, 9, 1)   # Tuesday, ISO week 36
RENTREE_2027 = date(2027, 9, 2)   # Thursday, ISO week 35


def holidays(*spans: tuple[str, str, str]) -> list[cal.Period]:
    return [
        cal.Period(name=n, start=date.fromisoformat(a), end=date.fromisoformat(b),
                   school_year="2026-2027")
        for n, a, b in spans
    ]


TOUSSAINT = holidays(
    ("Vacances d'Été", "2026-07-04", "2026-08-31"),
    ("Vacances de la Toussaint", "2026-10-17", "2026-11-01"),
)


# -- Easter, and what hangs off it ------------------------------------------


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2026, "2026-04-05"), (2027, "2027-03-28"), (2028, "2028-04-16")],
)
def test_easter(year, expected):
    assert cal.easter(year) == date.fromisoformat(expected)


@pytest.mark.parametrize(
    ("day", "name"),
    [
        ("2027-03-29", "Lundi de Pâques"),
        ("2027-05-06", "Ascension"),
        ("2027-05-17", "Lundi de Pentecôte"),
        ("2028-04-17", "Lundi de Pâques"),
        ("2028-05-25", "Ascension"),
        ("2028-06-05", "Lundi de Pentecôte"),
    ],
)
def test_the_moving_public_holidays_match_the_printed_calendars(day, name):
    assert cal.public_holidays(int(day[:4]))[date.fromisoformat(day)] == name


def test_there_are_eleven_of_them():
    assert len(cal.public_holidays(2027)) == 11


# -- A and B ----------------------------------------------------------------


def test_the_first_week_back_is_A():
    """Both printed calendars mark it A, in years whose ISO parity differs —
    which is exactly why the rule cannot be "even weeks are A"."""
    assert cal.week_letter(RENTREE_2026, RENTREE_2026) == "A"
    assert cal.week_letter(RENTREE_2027, RENTREE_2027) == "A"
    assert RENTREE_2026.isocalendar().week % 2 != RENTREE_2027.isocalendar().week % 2


def test_iso_parity_would_have_been_wrong():
    """Guards the reasoning, not just the result."""
    naive = "A" if RENTREE_2027.isocalendar().week % 2 == 0 else "B"
    assert naive != cal.week_letter(RENTREE_2027, RENTREE_2027)


@pytest.mark.parametrize(
    ("day", "letter"),
    [
        ("2026-09-30", "A"),  # confirmed on her own timetable
        ("2026-10-02", "A"),
        ("2026-10-05", "B"),
        ("2026-10-12", "A"),
        ("2026-10-19", "B"),
        ("2026-11-02", "B"),  # back from the holidays: the count never paused
        ("2026-11-09", "A"),
    ],
)
def test_the_letters_follow_the_printed_calendar(day, letter):
    assert cal.week_letter(date.fromisoformat(day), RENTREE_2026) == letter


def test_the_alternation_survives_the_new_year():
    """2026 has 53 ISO weeks: subtracting week numbers would flip the answer
    on the 1st of January."""
    assert cal.week_letter(date(2026, 12, 28), RENTREE_2026) == "B"
    assert cal.week_letter(date(2027, 1, 4), RENTREE_2026) == "A"
    assert cal.week_letter(date(2027, 1, 11), RENTREE_2026) == "B"


def test_every_day_of_a_week_gets_the_same_letter():
    monday = date(2026, 10, 5)
    letters = {
        cal.week_letter(monday + timedelta(days=n), RENTREE_2026) for n in range(7)
    }
    assert letters == {"B"}


def test_swapping_is_a_straight_swap():
    for offset in range(0, 40, 3):
        day = RENTREE_2026 + timedelta(days=offset)
        assert cal.week_letter(day, RENTREE_2026, invert=True) != cal.week_letter(
            day, RENTREE_2026
        )


# -- Days left --------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "left", "total"),
    [
        ("2026-09-28", 5, 5),  # Monday
        ("2026-09-30", 3, 5),  # Wednesday
        ("2026-10-02", 1, 5),  # Friday
        ("2026-10-03", 0, 5),  # Saturday
        ("2026-10-19", 0, 0),  # holidays
    ],
)
def test_the_week_drains(day, left, total):
    assert cal.school_days_of_week(date.fromisoformat(day), TOUSSAINT) == (left, total)


def test_a_public_holiday_shortens_the_week():
    """11 November 2026 is a Wednesday: four school days, not five."""
    assert cal.school_days_of_week(date(2026, 11, 9), TOUSSAINT) == (4, 4)
    assert cal.school_days_of_week(date(2026, 11, 11), TOUSSAINT) == (2, 4)


# -- What the widget says ---------------------------------------------------


def test_a_school_day(monkeypatch):
    monkeypatch.setenv("AWTRIXNG_LANGUAGE", "fr")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        data = SchoolConnector._describe(date(2026, 9, 30), TOUSSAINT, invert=False)
        assert data.values["summary"] == "Semaine A"
        assert data.values["week"] == "A"
        assert data.values["holiday"] is False
        assert data.progress == 60
    finally:
        get_settings.cache_clear()


def test_a_holiday_counts_down_to_the_morning_school_resumes(monkeypatch):
    monkeypatch.setenv("AWTRIXNG_LANGUAGE", "fr")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        data = SchoolConnector._describe(date(2026, 10, 19), TOUSSAINT, invert=False)
        assert data.values["holiday"] is True
        assert data.values["holiday_name"] == "Vacances de la Toussaint"
        # Last day off is 1 November, back on the 2nd: fourteen days away.
        assert "J-14" in data.values["summary"]
        assert data.progress == 0
    finally:
        get_settings.cache_clear()


def test_the_end_of_a_period_is_the_last_day_off_not_the_morning_back():
    """The dataset stores midnight of the return; read as UTC it lands a day
    early and school would appear to start on a Sunday."""
    period = cal._period(
        {
            "description": "Vacances de la Toussaint",
            "start_date": "2026-10-16T22:00:00+00:00",
            "end_date": "2026-11-01T23:00:00+00:00",
            "annee_scolaire": "2026-2027",
        }
    )
    assert period is not None
    assert period.start == date(2026, 10, 17)
    assert period.end == date(2026, 11, 1)
    assert not period.covers(date(2026, 11, 2))


def test_the_ascension_bridge_is_one_day_not_none():
    """The dataset gives it the same instant twice. Taken literally the period
    is empty and the Friday counts as a school day, which it is not."""
    period = cal._period(
        {
            "description": "Pont de l'Ascension",
            "start_date": "2027-05-06T22:00:00+00:00",
            "end_date": "2027-05-06T22:00:00+00:00",
            "annee_scolaire": "2026-2027",
        }
    )
    assert period is not None
    assert period.start == period.end == date(2027, 5, 7)
    assert period.covers(date(2027, 5, 7))
    assert not period.covers(date(2027, 5, 10))


def test_the_ascension_week_is_two_days_long():
    """Thursday is the public holiday, Friday the bridge: back on Monday 10,
    as the printed calendar says."""
    periods = holidays(("Vacances d'Été", "2026-07-04", "2026-08-31")) + [
        cal.Period("Pont de l'Ascension", date(2027, 5, 7), date(2027, 5, 7), "2026-2027")
    ]
    assert cal.school_days_of_week(date(2027, 5, 3), periods) == (3, 3)
    assert not cal.is_school_day(date(2027, 5, 6), periods)  # Ascension
    assert not cal.is_school_day(date(2027, 5, 7), periods)  # pont


def test_a_malformed_record_is_skipped_not_fatal():
    assert cal._period({"description": "x"}) is None
    assert cal._period({"start_date": "pas une date", "end_date": "non plus"}) is None


class TestTheWeekHasItsOwnColour:
    """The letter is the one fact the widget exists to give.

    A colour is read before a word is, which matters for someone glancing at a
    clock while putting a coat on. Holidays need a third anyway: there is then
    neither an A nor a B, and `week_letter` keeps counting through them.
    """

    def test_a_and_b_differ(self):
        from app.connectors.school.connector import colour_for

        assert colour_for("A", holiday=False) != colour_for("B", holiday=False)

    def test_holidays_win_over_the_letter(self):
        from app.connectors.school.connector import colour_for

        assert colour_for("A", holiday=True) == colour_for("B", holiday=True)

    def test_the_three_are_distinct(self):
        """Two neighbouring shades are one shade at eight pixels."""
        from app.connectors.school import connector

        assert len({connector.COLOUR_A, connector.COLOUR_B, connector.COLOUR_HOLIDAY}) == 3

    def test_an_unknown_letter_does_not_crash(self):
        """Before the first rentrée of a calendar there is no letter yet."""
        from app.connectors.school.connector import colour_for

        assert colour_for("", holiday=False)

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            # Alternating weeks, read from the widget itself rather than from
            # the colour table: this is what reaches the matrix.
            (date(2026, 10, 5), "B"),
            (date(2026, 10, 12), "A"),
            (date(2026, 11, 2), "B"),
        ],
    )
    def test_the_colour_follows_the_letter_the_widget_shows(self, day, expected):
        from app.connectors.school.connector import colour_for

        data = SchoolConnector._describe(day, TOUSSAINT, invert=False)
        assert data.values["week"] == expected
        assert data.hint_color == colour_for(expected, holiday=False)


def test_the_letter_matches_a_week_someone_actually_lived():
    """Ground truth, not a fixture invented to make the code pass.

    On 5 October 2026 Florian said his school was in week B. The rentrée that
    year was Tuesday 1 September, whose Monday is 31 August; five whole weeks
    separate it from the Monday of 5 October, and an odd count is B.

    It is worth a test of its own because every other assertion here checks
    the arithmetic against itself. This one checks it against a school.
    """
    from datetime import date

    from app.connectors.school import calendar as cal

    rentree = date(2026, 9, 1)
    today = date(2026, 10, 5)

    assert (cal.monday_of(today) - cal.monday_of(rentree)).days // 7 == 5
    assert cal.week_letter(today, rentree) == "B"
    # The option exists for schools that count the other way round.
    assert cal.week_letter(today, rentree, invert=True) == "A"
