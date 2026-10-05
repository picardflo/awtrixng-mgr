"""Quiet hours: a window of the day where reminders ring without a melody.

**This used to dim the display as well.** On AWTRIX 3 that was its reason to
exist: the firmware's automatic brightness clamped at 2, too bright for a
bedroom, and the floor was not adjustable. The window therefore switched the
sensor off, forced a lower level, remembered what it had overwritten, and
restored it at dawn — four columns of state and two settings writes a day.

NG makes `minBrightness` a setting in `/api/v1/system`. Measured on a TC001 in
a dark room: the panel sits exactly on that floor, and lowering it from 10 to
8 took the live brightness down with it, 10 → 9 → 8. One setting replaces the
schedule, the saved state and the restore.

It is also the better answer. Automatic brightness follows the *room*, so it
dims when someone actually goes to bed; a window fixed at 22:00 cannot know
that, and will happily dim a lit room at ten past.

What is left here is the half the light sensor cannot do, because it is a
matter of time rather than of light: a reminder that falls inside the window
goes out without its melody.
"""

from datetime import time


def is_quiet(start: time, end: time, now: time) -> bool:
    """Whether `now` falls inside the window.

    Inclusive at the start, exclusive at the end: 22:00 is already quiet and
    07:00 is already morning, which is how someone reads "22:00 to 07:00".
    """
    if start == end:
        # Refused by validation, and answered here rather than left to mean
        # either "never" or "always" depending on which comparison runs first.
        return False
    if start < end:
        return start <= now < end
    # Crosses midnight: inside means after the start *or* before the end.
    return now >= start or now < end
