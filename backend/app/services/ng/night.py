"""Bedroom mode: a window of the day where a display is dimmed and silent.

**ADR-022 re-judged for NG, and it stands.** The decision to keep the
schedule in the application rested on the firmware having no notion of one.
Checked again against NG 1.1.2's 42 settings: there is still no window, no
schedule, nothing time-based. `autoBrightness`, `brightness`, `soundEnabled`
and `buzzerVolume` are levels, not timetables. So the schedule lives here,
where a loop already runs every second.

What NG *did* give is a better way to silence a display: `soundEnabled` is a
boolean of its own. AWTRIX 3 had only a volume, so muting meant writing zero
and remembering the old number to put back.

Two rules shape the rest of this module:

- **The window may cross midnight**, and 22:00→07:00 is the case someone
  actually configures. Every comparison below is written for that.
- **Automatic brightness has to be suspended** while the window is open. Left
  on, the sensor recomputes the level within seconds and the whole feature
  does nothing in a lit room.
"""

from dataclasses import dataclass
from datetime import time


def is_night(start: time, end: time, now: time) -> bool:
    """Whether `now` falls inside the window.

    Inclusive at the start, exclusive at the end: 22:00 is already night and
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


@dataclass(frozen=True, slots=True)
class Saved:
    """What a display was set to before the window opened.

    Kept so the morning restores what the evening found, rather than some
    default. Persisted on the device row: an awtrixng-mgr restarted at three in
    the morning must still know what to put back at seven.
    """

    brightness: int
    auto_brightness: bool
    sound_enabled: bool

    def to_settings(self) -> dict[str, object]:
        """The firmware's own key names, as PATCH /api/v1/settings takes them.

        Writing AWTRIX 3's `BRI` here costs a 422 naming the field — measured,
        and a good deal friendlier than the silence it used to get.
        """
        return {
            "brightness": self.brightness,
            "autoBrightness": self.auto_brightness,
            "soundEnabled": self.sound_enabled,
        }

    @classmethod
    def from_settings(cls, raw: dict) -> "Saved":
        return cls(
            brightness=int(raw.get("brightness", 80)),
            auto_brightness=bool(raw.get("autoBrightness", True)),
            sound_enabled=bool(raw.get("soundEnabled", True)),
        )

    def to_json(self) -> dict[str, object]:
        return self.to_settings()


def night_settings(brightness: int, *, mute: bool = False) -> dict[str, object]:
    """What to write when the window opens.

    `autoBrightness` goes off with it, always: a dim level under an active
    light sensor lasts about a second.

    **The volume is not touched.** Muting the clock for the night silenced
    anything that buzzes, needed putting back afterwards, and left a reminder
    that exists in order to wake someone — a 06:30 alarm inside a 22:00–07:00
    window — with no way through. Reminders now drop their own melody instead,
    per display, and one of them can be marked to keep it.

    `mute` remains for the tests that pin the old behaviour out. On NG it
    writes `soundEnabled: false`, which is a cleaner statement than AWTRIX 3's
    volume of zero — there is no old number to remember and restore.
    """
    settings: dict[str, object] = {"brightness": brightness, "autoBrightness": False}
    if mute:
        settings["soundEnabled"] = False
    return settings
