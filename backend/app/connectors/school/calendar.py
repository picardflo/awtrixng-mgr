"""The French school calendar: holidays, public holidays, and A/B weeks.

Holidays come from the Ministry's open data rather than from dates typed in
here: they are published years ahead, differ by académie, and a table copied
into the source would be wrong the moment a new year is announced.

Public holidays are computed instead — they follow a rule, and the dataset does
not carry them. Without them "3 days left" is wrong on the 11th of November.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.errors import AwtrixNgError

log = logging.getLogger(__name__)

ENDPOINT = (
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets"
    "/fr-en-calendrier-scolaire/records"
)

#: The calendar is French, and so are its dates: the dataset stores them in UTC,
#: so a holiday ending "2026-11-01T22:00:00+00:00" ends at midnight on the 2nd
#: in Paris. Reading them as UTC shifts every boundary by a day.
PARIS = ZoneInfo("Europe/Paris")

#: Académies, as the dataset spells them. Listed here so the form works with no
#: network; the dataset remains the authority on their dates.
ACADEMIES: tuple[str, ...] = (
    "Aix-Marseille", "Amiens", "Besançon", "Bordeaux", "Caen", "Clermont-Ferrand",
    "Corse", "Créteil", "Dijon", "Grenoble", "Guadeloupe", "Guyane", "Lille",
    "Limoges", "Lyon", "Martinique", "Mayotte", "Montpellier", "Nancy-Metz",
    "Nantes", "Nice", "Normandie", "Nouvelle Calédonie", "Orléans-Tours", "Paris",
    "Poitiers", "Polynésie", "Reims", "Rennes", "Rouen", "Réunion",
    "Saint Pierre et Miquelon", "Strasbourg", "Toulouse", "Versailles",
    "Wallis et Futuna",
)

#: A pupil's week. Saturday morning exists in a few places; it is not the rule,
#: and a widget that claims six days where there are five is worse than one that
#: claims five where there are six.
SCHOOL_WEEKDAYS = 5


@dataclass(frozen=True, slots=True)
class Period:
    """One holiday period, as local dates.

    `start` is the first day off and `end` the last, both inclusive — which is
    not how the dataset stores it, and the conversion happens once, here.
    """

    name: str
    start: date
    end: date
    school_year: str

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


def easter(year: int) -> date:
    """Easter Sunday, Gregorian. Butcher's algorithm, exact for any year."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = ((h + m - 7 * n + 114) % 31) + 1
    return date(year, month, day)


def public_holidays(year: int) -> dict[date, str]:
    """The eleven French public holidays, fixed ones and Easter's children."""
    sunday = easter(year)
    return {
        date(year, 1, 1): "Jour de l'An",
        sunday + timedelta(days=1): "Lundi de Pâques",
        date(year, 5, 1): "Fête du Travail",
        date(year, 5, 8): "Victoire 1945",
        sunday + timedelta(days=39): "Ascension",
        sunday + timedelta(days=50): "Lundi de Pentecôte",
        date(year, 7, 14): "Fête Nationale",
        date(year, 8, 15): "Assomption",
        date(year, 11, 1): "Toussaint",
        date(year, 11, 11): "Armistice 1918",
        date(year, 12, 25): "Noël",
    }


async def fetch_periods(academie: str, client: httpx.AsyncClient) -> list[Period]:
    """Every holiday period published for an académie, pupils only.

    Teachers go back a day or two earlier; a widget for a pupil must not.
    """
    try:
        response = await client.get(
            ENDPOINT,
            params={
                "where": f'location="{academie}" and population!="Enseignants"',
                "order_by": "start_date",
                "limit": 100,
            },
        )
    except httpx.HTTPError as exc:
        raise AwtrixNgError(
            f"Could not reach the school calendar: {exc or type(exc).__name__}",
            code="school.unreachable",
            params={"reason": str(exc) or type(exc).__name__},
        ) from exc

    if response.status_code >= 400:
        raise AwtrixNgError(
            f"The school calendar refused the request (HTTP {response.status_code}).",
            code="school.http_error",
            params={"status": response.status_code},
        )

    periods = [p for p in map(_period, response.json().get("results", [])) if p]
    if not periods:
        raise AwtrixNgError(
            f"No school calendar published for {academie}.",
            code="school.no_data",
            params={"academie": academie},
        )
    return periods


def _period(record: dict[str, Any]) -> Period | None:
    try:
        start = datetime.fromisoformat(record["start_date"]).astimezone(PARIS)
        end = datetime.fromisoformat(record["end_date"]).astimezone(PARIS)
    except (KeyError, TypeError, ValueError):
        return None
    # Both bounds land on midnight in Paris — the dataset shifts them by two
    # or three hours depending on daylight saving, precisely so they do. The
    # first day off is `start`; `end` is the morning school resumes, so the
    # last day off is the day before.
    #
    # Except for "Pont de l'Ascension", which carries the same instant twice.
    # Read literally that is an empty period, and the Friday would count as a
    # school day. One day is what it means.
    first = start.date()
    return Period(
        name=str(record.get("description") or "Vacances"),
        start=first,
        end=max(end.date() - timedelta(days=1), first),
        school_year=str(record.get("annee_scolaire") or ""),
    )


def rentree_before(periods: list[Period], day: date) -> date | None:
    """The first day of school for the year `day` falls in.

    Taken as the morning after the summer holidays, which is what the dataset
    lets us know without guessing.
    """
    summers = sorted(
        (p for p in periods if "Été" in p.name and p.end < day),
        key=lambda p: p.end,
    )
    return summers[-1].end + timedelta(days=1) if summers else None


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_letter(day: date, rentree: date, *, invert: bool = False) -> str:
    """A or B for the week `day` falls in.

    Counted in whole weeks from the Monday of the rentrée, never by subtracting
    ISO week numbers: 2026 has 53 of them, and S53 → S1 would flip the answer
    every new year.

    The alternation runs through the holidays rather than pausing — checked
    against the published calendars for 2026-2027 and 2027-2028.
    """
    weeks = (monday_of(day) - monday_of(rentree)).days // 7
    letter = "A" if weeks % 2 == 0 else "B"
    if invert:
        letter = "B" if letter == "A" else "A"
    return letter


def holiday_on(periods: list[Period], day: date) -> Period | None:
    return next((p for p in periods if p.covers(day)), None)


def is_school_day(day: date, periods: list[Period]) -> bool:
    if day.weekday() >= SCHOOL_WEEKDAYS:
        return False
    if holiday_on(periods, day):
        return False
    return day not in public_holidays(day.year)


def school_days_of_week(day: date, periods: list[Period]) -> tuple[int, int]:
    """(remaining from today, total in this week).

    Today counts while it lasts, so the bar is full on Monday morning and empty
    once Friday is over.
    """
    monday = monday_of(day)
    week = [monday + timedelta(days=n) for n in range(SCHOOL_WEEKDAYS)]
    total = sum(1 for d in week if is_school_day(d, periods))
    remaining = sum(1 for d in week if d >= day and is_school_day(d, periods))
    return remaining, total


def next_holiday(periods: list[Period], day: date) -> Period | None:
    upcoming = sorted((p for p in periods if p.start > day), key=lambda p: p.start)
    return upcoming[0] if upcoming else None


def today() -> date:
    """The date in Paris, not the container's idea of UTC."""
    return datetime.now(UTC).astimezone(PARIS).date()
