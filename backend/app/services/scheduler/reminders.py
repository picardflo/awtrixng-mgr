"""Deciding when a reminder fires, and sending it.

Separate from the widget pass because nothing is shared: no connector, no
cache, no rotation. A reminder is a notification — it takes the matrix rather
than waiting its turn.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core import language
from app.core.errors import AwtrixNgError
from app.models import Reminder
from app.services.ng.client import NgClient
from app.services.ng.payload import NgNotification, Scroll
from app.widgets import template

log = logging.getLogger(__name__)

#: How late a missed instant may still be delivered. A restart during breakfast
#: should still ring; an outage until noon should not replay the morning.
TOLERANCE = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class Fired:
    reminder_id: int
    at: datetime
    sent_to: list[int]
    failed: list[int]


def local_now() -> datetime:
    """Now, in the machine's timezone.

    Someone who writes 07:30 means half past seven where they live. The
    container carries TZ, so this is the setting they already made.
    """
    return datetime.now().astimezone()


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def fires_this_week(reminder: Reminder, day: date) -> bool:
    """Whether `day`'s week is one of this reminder's.

    Counted in whole weeks from the Monday of the reference week, never by
    subtracting ISO week numbers — some years have 53, and S53 to S1 would
    flip the answer every new year. Same reckoning as the A/B school week, for
    the same reason.
    """
    if reminder.every_weeks <= 1:
        return True
    anchor = reminder.anchor or reminder.created_at.date()
    weeks = (monday_of(day) - monday_of(anchor)).days // 7
    return weeks % reminder.every_weeks == 0


def occurrences(reminder: Reminder, day: date) -> list[datetime]:
    """Every instant this reminder fires on a given day.

    The first one, then the repeats. Empty when the day is not one of its own.
    """
    if reminder.on_date is not None:
        # A single date silences the weekly rhythm entirely: asking for both
        # would be asking two questions at once.
        if day != reminder.on_date:
            return []
    else:
        if day.weekday() not in reminder.days:
            return []
        if not fires_this_week(reminder, day):
            return []

    first = datetime.combine(day, reminder.at).astimezone()
    return [
        first + timedelta(minutes=reminder.repeat_every_minutes * n)
        for n in range(reminder.repeat_count + 1)
    ]


def due(reminder: Reminder, now: datetime) -> datetime | None:
    """The instant to send right now, or None.

    Yesterday is checked too: a repeat starting at 23:55 spills past midnight,
    and dropping it would make the last reminder of the day the unreliable one.

    Only the most recent pending instant is returned. If several went by while
    awtrixng-mgr was down, the clock gets one alert, not five.
    """
    if not reminder.enabled:
        return None

    today = now.date()
    candidates = occurrences(reminder, today - timedelta(days=1)) + occurrences(reminder, today)
    last = reminder.last_fired_at
    pending = [
        instant
        for instant in candidates
        if instant <= now
        and now - instant <= TOLERANCE
        and (last is None or instant > last.astimezone())
    ]
    return max(pending) if pending else None


#: The letter a countdown counts in. French counts in days — *jour* — and
#: English in D-Days; neither reads naturally in the other.
COUNTDOWN = {
    "en": {"before": "D-{days}", "day": "D-DAY", "after": "D+{days}"},
    "fr": {"before": "J-{days}", "day": "JOUR J", "after": "J+{days}"},
}


def countdown_text(remaining: int) -> str:
    """`J-406`, `JOUR J`, `J+3` — or their English equivalents."""
    words = COUNTDOWN.get(language.current(), COUNTDOWN["en"])
    if remaining == 0:
        return words["day"]
    if remaining > 0:
        return words["before"].format(days=remaining)
    return words["after"].format(days=-remaining)


def countdown_values(reminder: Reminder, today: date) -> dict[str, object]:
    """What a message may interpolate.

    Only a countdown offers anything: everything else a reminder says, someone
    typed. `days` is negative once the date is past rather than clamped — "J+3"
    is a fact worth seeing, and hiding it would make a missed deadline look
    like a reached one.
    """
    if reminder.countdown_to is None:
        return {}
    remaining = (reminder.countdown_to - today).days
    return {
        # Already written out, because composing it by hand gets the sign
        # wrong: "J-{{ days }}" reads "J--3" the day after the deadline. The
        # day itself is neither J-0 nor J+0 but the day itself.
        #
        # Translated like any other prose: "J-406" was hard-coded French in an
        # application whose default display language is English.
        "countdown": countdown_text(remaining),
        #: Signed, for a message that wants to phrase it differently.
        "days": remaining,
        "date": reminder.countdown_to.strftime("%d/%m/%Y"),
    }


def payload_for(
    reminder: Reminder, today: date | None = None, *, silent: bool = False
) -> NgNotification:
    """What the display is sent.

    `hold` stays off on purpose: the chosen behaviour is blind repetition, and
    a held notification would sit on the matrix until someone pressed a button
    — which HTTP gives us no way to hear about.
    """
    return NgNotification(
        # The same closed grammar the widgets use, rather than a second one:
        # `{{ days }}` is all a reminder has to interpolate, and an unknown
        # name renders empty instead of raising.
        text=template.for_matrix(
            template.render(
                reminder.message, countdown_values(reminder, today or local_now().date())
            )
        ),
        icon=reminder.icon or None,
        text_color=reminder.color or None,
        # Milliseconds on the wire; the column stays in seconds, which is what
        # someone setting a reminder thinks in.
        duration_ms=reminder.duration_seconds * 1000,
        background_color=reminder.background or None,
        # None rather than a value: the display has its own scroll settings,
        # and sending ours everywhere would freeze it on our opinion.
        scroll=_scroll_for(reminder),
        # The presentation a reminder now shares with a widget. Each was
        # measured on **this** route, not assumed from the other one: a pushed
        # app and a notification are different endpoints, and this firmware
        # answers `{"ok": true}` to things it then ignores.
        font=reminder.font or None,
        text_case=reminder.text_case if reminder.text_case != "inherit" else None,
        icon_mode=reminder.icon_mode or None,
        effect=reminder.effect or None,
        overlay=reminder.overlay or None,
        # Wake the matrix: an alert nobody can see is not an alert.
        wakeup=True,
        hold=False,
        # Dropped at the source rather than by silencing the clock. Turning
        # `soundEnabled` off for the night would mute anything else that
        # buzzes and needs putting back afterwards; leaving the melody out of
        # this one notification is exact, and reversible by definition.
        sound_rtttl=None if silent else (reminder.melody or None),
    )


def _scroll_for(reminder: Reminder) -> Scroll | None:
    """The scroll object, or None when nothing differs from the display's own."""
    fields: dict[str, object] = {}
    if reminder.scroll_mode != "wrap":
        fields["mode"] = reminder.scroll_mode
    if reminder.scroll_speed != 100:
        fields["speed"] = reminder.scroll_speed
    if reminder.scroll_when_fits != "static":
        fields["when_fits"] = reminder.scroll_when_fits
    return Scroll(**fields) if fields else None


async def send(
    reminder: Reminder,
    clients: dict[int, NgClient],
    at: datetime,
    *,
    silent_on: frozenset[int] = frozenset(),
) -> Fired:
    """Push the notification to every display, never raising.

    One unreachable clock must not stop the others: a reminder that fires on
    two displays and finds one asleep should still reach the other.

    `silent_on` names the displays whose quiet window is open. The decision
    is per display, not per reminder: the same alert can ring in the kitchen
    and stay quiet in the bedroom.
    """
    loud = payload_for(reminder)
    quiet = payload_for(reminder, silent=True) if reminder.melody else loud
    sent: list[int] = []
    failed: list[int] = []

    for device_id, client in clients.items():
        payload = quiet if device_id in silent_on else loud
        try:
            # The display only draws icons it already holds. Widgets have done
            # this since the start; reminders went out without it and showed
            # text where an icon was asked for.
            #
            # A failed install must not drop the alert: a reminder without its
            # icon still beats no reminder at all.
            if payload.icon:
                try:
                    await client.ensure_icon(payload.icon)
                except AwtrixNgError as exc:
                    log.warning(
                        "reminder %s: icon %s unavailable (%s)",
                        reminder.name,
                        payload.icon,
                        exc.message,
                    )

            # Light the panel, because the firmware will not.
            #
            # Notifications carry `wakeup`, and measured on NG 1.1.2 that key
            # is accepted and does nothing: with the panel off the firmware
            # composes the frame — 36 pixels lit — and leaves `power` false.
            # The alert is heard and never seen. Brightness at zero behaves the
            # same, with or without the key.
            #
            # So the application does it. Florian's call, 5 October 2026:
            # switch on, and *stay* on. Restoring the previous state would hide
            # the alert at the moment it matters — a 06:30 alarm that fades
            # after ten seconds wakes nobody.
            #
            # Written unconditionally rather than read-then-write: one request
            # instead of two, and it is idempotent (measured: `power: true` on
            # a lit panel answers ok and changes nothing).
            try:
                await client.set_power(True)
            except AwtrixNgError as exc:
                # Same rule as the icon: never drop the alert for this.
                log.warning(
                    "reminder %s: could not light device %s (%s)",
                    reminder.name,
                    device_id,
                    exc.message,
                )

            await client.notify(payload)
            sent.append(device_id)
        except AwtrixNgError as exc:
            failed.append(device_id)
            log.warning(
                "reminder %s could not reach device %s: %s",
                reminder.name,
                device_id,
                exc.message,
            )

    log.info("reminder %s fired on %d display(s)", reminder.name, len(sent))
    return Fired(reminder.id or 0, at, sent, failed)
