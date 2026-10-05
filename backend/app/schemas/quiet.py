"""Quiet hours, as the API shows them.

Stored by awtrixng-mgr, not by the display: NG has no schedule of any kind —
probed, `/schedules`, `/automations`, `/timers`, `/alarms`, `/cron` and `/dnd`
all answer 404. Saving therefore writes nothing to the clock.

The brightness this once carried is gone: `minBrightness` in the display's own
settings does that job now, and does it from the light in the room rather than
from the hour. See `app/services/ng/quiet.py`.
"""

from datetime import time

from pydantic import BaseModel, model_validator


class QuietHours(BaseModel):
    enabled: bool = False
    #: Local time, and the window may cross midnight — 22:00 to 07:00 is the
    #: case anyone actually configures.
    start: time = time(22, 0)
    end: time = time(7, 0)

    @model_validator(mode="after")
    def _a_window_needs_two_ends(self) -> "QuietHours":
        if self.enabled and self.start == self.end:
            # Equal bounds mean either "never" or "always" depending on which
            # comparison runs first. Refused rather than guessed.
            raise ValueError("start and end must differ")
        return self
