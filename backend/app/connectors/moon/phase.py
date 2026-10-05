"""Where the Moon is in its cycle, computed rather than fetched.

There is no API behind this widget, and that is the point: the phase depends
only on the date, so it cannot fail, cannot be rate-limited, and works with the
network down.

The usual shortcut — days since a known new moon, modulo 29.53 — is wrong by up
to half a day, because the Moon's orbit is an ellipse and it does not move at a
constant rate. Half a day is exactly enough to name the wrong phase near a
quarter, which is when someone looks. So the Sun and Moon longitudes are
computed from the abridged series in Meeus, *Astronomical Algorithms*
(ch. 25 and 47): about fifty lines, and accurate to a few tenths of a degree —
far more than a name and a percentage need.
"""

import math
from datetime import UTC, datetime

from app.core import language

#: Mean length of a lunation, in days. Used to turn an angle into a duration,
#: never to advance the phase itself.
SYNODIC_MONTH = 29.530588853

#: The eight principal phases, in the order the Moon passes through them,
#: each centred on a multiple of 45° of elongation.
#: slug -> label, per language. The slug never changes: it is what a template
#: compares against.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "new": "Nouvelle lune",
        "waxing_crescent": "Premier croissant",
        "first_quarter": "Premier quartier",
        "waxing_gibbous": "Lune gibbeuse croissante",
        "full": "Pleine lune",
        "waning_gibbous": "Lune gibbeuse décroissante",
        "last_quarter": "Dernier quartier",
        "waning_crescent": "Dernier croissant",
    },
}

PHASES: tuple[tuple[str, str], ...] = (
    ("new", "New Moon"),
    ("waxing_crescent", "Waxing Crescent"),
    ("first_quarter", "First Quarter"),
    ("waxing_gibbous", "Waxing Gibbous"),
    ("full", "Full Moon"),
    ("waning_gibbous", "Waning Gibbous"),
    ("last_quarter", "Last Quarter"),
    ("waning_crescent", "Waning Crescent"),
)


def _julian_day(moment: datetime) -> float:
    """Julian Day of an instant. Gregorian calendar only, which is all we need."""
    moment = moment.astimezone(UTC)
    year, month = moment.year, moment.month
    day = (
        moment.day
        + (moment.hour + (moment.minute + moment.second / 60) / 60) / 24
    )
    if month <= 2:
        year, month = year - 1, month + 12
    a = year // 100
    b = 2 - a + a // 4
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day
        + b
        - 1524.5
    )


def _centuries(julian_day: float) -> float:
    """Julian centuries since J2000.0."""
    return (julian_day - 2451545.0) / 36525.0


def _sun_longitude(t: float) -> float:
    """Apparent geometric longitude of the Sun, degrees (Meeus ch. 25)."""
    mean = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    anomaly = math.radians(357.52911 + 35999.05029 * t - 0.0001537 * t * t)
    centre = (
        (1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(anomaly)
        + (0.019993 - 0.000101 * t) * math.sin(2 * anomaly)
        + 0.000289 * math.sin(3 * anomaly)
    )
    return (mean + centre) % 360.0


def _moon_longitude(t: float) -> float:
    """Apparent longitude of the Moon, degrees (Meeus ch. 47, principal terms).

    Sixteen terms out of sixty: the ones left out move the result by less than
    a hundredth of a degree, which no phase name and no whole percentage can
    notice.
    """
    mean = 218.3164477 + 481267.88123421 * t - 0.0015786 * t * t
    elongation = math.radians(297.8501921 + 445267.1114034 * t - 0.0018819 * t * t)
    sun_anomaly = math.radians(357.5291092 + 35999.0502909 * t)
    moon_anomaly = math.radians(134.9633964 + 477198.8675055 * t + 0.0087414 * t * t)
    argument = math.radians(93.2720950 + 483202.0175233 * t - 0.0036539 * t * t)

    d, m, mp, f = elongation, sun_anomaly, moon_anomaly, argument
    correction = (
        6.288774 * math.sin(mp)
        + 1.274027 * math.sin(2 * d - mp)
        + 0.658314 * math.sin(2 * d)
        + 0.213618 * math.sin(2 * mp)
        - 0.185116 * math.sin(m)
        - 0.114332 * math.sin(2 * f)
        + 0.058793 * math.sin(2 * d - 2 * mp)
        + 0.057066 * math.sin(2 * d - m - mp)
        + 0.053322 * math.sin(2 * d + mp)
        + 0.045758 * math.sin(2 * d - m)
        - 0.040923 * math.sin(m - mp)
        - 0.034720 * math.sin(d)
        - 0.030383 * math.sin(m + mp)
        + 0.015327 * math.sin(2 * d - 2 * f)
        - 0.012528 * math.sin(mp + 2 * f)
        + 0.010980 * math.sin(mp - 2 * f)
    )
    return (mean + correction) % 360.0


def elongation(moment: datetime) -> float:
    """Angle from the Sun to the Moon along the ecliptic, 0–360°.

    0° is new, 90° first quarter, 180° full, 270° last quarter. Everything
    else here is derived from this one number.
    """
    t = _centuries(_julian_day(moment))
    return (_moon_longitude(t) - _sun_longitude(t)) % 360.0


def illumination(moment: datetime) -> float:
    """Lit fraction of the visible disc, 0–100."""
    return (1 - math.cos(math.radians(elongation(moment)))) / 2 * 100


def age(moment: datetime) -> float:
    """Days since the last new moon."""
    return elongation(moment) / 360.0 * SYNODIC_MONTH


def phase(moment: datetime) -> tuple[str, str]:
    """The principal phase, as (stable slug, name in the display language).

    The eight sectors are centred on their principal points, so "Full Moon"
    spans 22.5° either side of opposition rather than starting there — which is
    how the names are used in practice.
    """
    slug, english = PHASES[int((elongation(moment) + 22.5) % 360.0 // 45.0)]
    return slug, language.localise(TRANSLATIONS, slug, english)


def days_until(moment: datetime, target_elongation: float) -> float:
    """Days until the Moon next reaches a given elongation.

    Derived from the mean lunation rather than solved exactly: a tenth of a day
    on "full moon in 6 days" is not worth a Newton iteration.
    """
    ahead = (target_elongation - elongation(moment)) % 360.0
    return ahead / 360.0 * SYNODIC_MONTH
