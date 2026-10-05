"""Bedroom mode, as the API shows it.

Stored by awtrixng-mgr, not by the display: the firmware has no notion of a
schedule. Saving therefore writes nothing to the clock — the scheduler opens
and closes the window on its own pass, within a second of the change.
"""

from datetime import time

from pydantic import BaseModel, Field, model_validator


class BedroomMode(BaseModel):
    enabled: bool = False
    #: Local time, and the window may cross midnight — 22:00 to 07:00 is the
    #: case anyone actually configures.
    start: time = time(22, 0)
    end: time = time(7, 0)
    #: 0–255, like the firmware's own. Low rather than off: a clock nobody can
    #: read at night is a clock that is off, and there is a power button for
    #: that.
    #:
    #: The default is **1**, not 2, and the reason is measured. The firmware's
    #: automatic brightness clamps at `MIN_BRIGHTNESS = 2`, so in a dark room
    #: it already sits there on its own — a window set to 2 replaces 2 with 2
    #: and nobody sees anything happen. Only manual brightness goes lower,
    #: which is what makes the window visible at all.
    brightness: int = Field(default=1, ge=0, le=255)

    #: True while the window is applied. Read-only — the scheduler owns it.
    active: bool = False

    @model_validator(mode="after")
    def _a_window_needs_two_ends(self) -> "BedroomMode":
        if self.enabled and self.start == self.end:
            # Equal bounds mean either "never" or "always" depending on which
            # comparison runs first. Refused rather than guessed.
            raise ValueError("start and end must differ")
        return self
