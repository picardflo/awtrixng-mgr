"""Sunrise and sunset, from the same Open-Meteo call as the weather.

Not a connector of its own: Open-Meteo returns `sunrise`, `sunset` and
`daylight_duration` from the endpoint the weather widgets already hit, for the
coordinates they already carry. A second connector would mean a second place
to configure, a second cache entry and a second request for data arriving in
the first one.

What this module settles is the awkward part — *which* of the two is next.
After today's sunset the answer is tomorrow's sunrise, so the request asks for
two days and the choice walks them in order.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

#: A sun climbing over the horizon, and the same sun going down — nine frames
#: each, one the mirror of the other.
#:
#: 2653 and 2654 came first and were dropped: four frames, half of them nearly
#: black. Across a room that reads as nothing at all. These two fill the frame
#: and the motion is what carries the meaning.
#:
#: Both are plain yellow, so the colour is not sampled from them as it is for
#: the air quality icons. Here the *shape* says which event it is and the
#: colour reinforces it — yellow at dawn, orange at dusk.
ICON_SUNRISE = 11949
ICON_SUNSET = 12061

#: What each slug reads as in English. The slug itself never changes, so a
#: template can compare against it whatever the interface language.
ENGLISH = {"sunrise": "Sunrise", "sunset": "Sunset"}

#: One is the day starting, the other the day ending, and the matrix has no
#: room to spell that out. A bright yellow against a deep orange reads at a
#: glance on eight pixels, where two shades of amber would not.
COLOURS = {"sunrise": "#ffd93d", "sunset": "#ff7043"}

#: Prose only.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {"sunrise": "Lever", "sunset": "Coucher"},
}


@dataclass(frozen=True, slots=True)
class Event:
    """One sunrise or sunset, in the place's own local time."""

    #: "sunrise" or "sunset". Never translated.
    code: str
    at: datetime

    @property
    def icon(self) -> int:
        return ICON_SUNRISE if self.code == "sunrise" else ICON_SUNSET


def _parse(stamp: Any) -> datetime | None:
    """Open-Meteo writes local time with no offset: "2026-10-03T07:54"."""
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def local_now(raw: dict[str, Any], utc_now: datetime) -> datetime:
    """Now, as a clock in that place would read it.

    The times in the response carry no offset, so comparing them against this
    machine's clock would be wrong for anywhere but here. `utc_offset_seconds`
    is what makes the comparison honest — and it already accounts for summer
    time, which is why nothing here does arithmetic on months.
    """
    offset = raw.get("utc_offset_seconds")
    seconds = offset if isinstance(offset, int | float) else 0
    return utc_now.replace(tzinfo=None) + timedelta(seconds=float(seconds))


def events(raw: dict[str, Any]) -> list[Event]:
    """Every sunrise and sunset in the response, in order."""
    daily = raw.get("daily") or {}
    found: list[Event] = []
    for code in ("sunrise", "sunset"):
        for stamp in daily.get(code) or []:
            moment = _parse(stamp)
            if moment is not None:
                found.append(Event(code=code, at=moment))
    return sorted(found, key=lambda event: event.at)


def next_event(raw: dict[str, Any], utc_now: datetime) -> Event | None:
    """The next one to happen, or None if the response says nothing useful."""
    now = local_now(raw, utc_now)
    return next((event for event in events(raw) if event.at > now), None)


def today(raw: dict[str, Any], utc_now: datetime) -> tuple[datetime | None, datetime | None]:
    """Today's sunrise and sunset, by the date the place is living.

    Indexing `[0]` would be wrong just after midnight UTC for anywhere east of
    it, which is the kind of error that shows up for one hour a day and is
    never reproduced on purpose.
    """
    daily = raw.get("daily") or {}
    dates = daily.get("time") or []
    here = local_now(raw, utc_now).date()
    try:
        index = next(i for i, day in enumerate(dates) if day == here.isoformat())
    except StopIteration:
        index = 0

    def at(code: str) -> datetime | None:
        values = daily.get(code) or []
        return _parse(values[index]) if index < len(values) else None

    return at("sunrise"), at("sunset")


def daylight_elapsed(
    sunrise: datetime | None, sunset: datetime | None, now: datetime
) -> int | None:
    """How much of the daylight has gone, as a percentage.

    Drives the progress bar. Undefined before sunrise and after sunset — a bar
    at 0 % or 100 % all night would be read as a measurement rather than as
    "not applicable", so the widget shows none.
    """
    if sunrise is None or sunset is None or not sunrise < now < sunset:
        return None
    span = (sunset - sunrise).total_seconds()
    if span <= 0:
        return None
    return max(0, min(100, round((now - sunrise).total_seconds() / span * 100)))
