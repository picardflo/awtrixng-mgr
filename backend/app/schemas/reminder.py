"""Shapes for the reminder API."""

from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator

from app.schemas.matrix_text import MatrixText, ScrollMode, ScrollWhenFits
from app.services.ng.payload import Font, IconMode, TextCase

#: Monday is 0, as everywhere else in Python.
WEEKDAYS = range(7)


class ReminderBase(MatrixText):
    """A reminder, as the API takes and gives it.

    It inherits its presentation from `MatrixText`, the same declaration the
    widgets use. Everything below is what makes it a reminder rather than a
    widget: a time, a rhythm, a melody.
    """

    name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    icon: str | None = None
    color: str | None = None
    at: time
    #: Days it fires on. Empty would be a reminder that never rings, which is
    #: a mistake rather than an intention.
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1)
    #: 1 = every week. Above that, `anchor` says which weeks.
    every_weeks: int = Field(default=1, ge=1, le=8)
    anchor: date | None = None
    #: Set, it rings that day only and `days`/`every_weeks` are ignored.
    on_date: date | None = None
    #: Set, the message may use {{ countdown }}, {{ days }} and {{ date }}.
    countdown_to: date | None = None
    duration_seconds: int = Field(default=10, ge=1, le=120)
    repeat_count: int = Field(default=0, ge=0, le=10)
    repeat_every_minutes: int = Field(default=2, ge=1, le=60)
    melody: str | None = None
    #: Keeps its melody inside the display's quiet hours. Off by default,
    #: because that is what quiet hours have to mean.
    rings_at_night: bool = False
    enabled: bool = True

    @field_validator("days")
    @classmethod
    def _real_days(cls, value: list[int]) -> list[int]:
        unknown = sorted(set(value) - set(WEEKDAYS))
        if unknown:
            raise ValueError(f"not days of the week: {unknown}")
        return sorted(set(value))


class ReminderCreate(ReminderBase):
    device_ids: list[int] = Field(default_factory=list)


class ReminderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    message: str | None = Field(default=None, min_length=1)
    icon: str | None = None
    color: str | None = None
    at: time | None = None
    days: list[int] | None = None
    every_weeks: int | None = Field(default=None, ge=1, le=8)
    anchor: date | None = None
    on_date: date | None = None
    countdown_to: date | None = None
    duration_seconds: int | None = Field(default=None, ge=1, le=120)
    # The presentation options, each nullable so a PATCH can leave it alone.
    # Listed rather than inherited: `MatrixText` carries defaults, and a
    # default in a PATCH body overwrites a choice the user made.
    background: str | None = None
    effect: str | None = None
    overlay: str | None = None
    icon_mode: IconMode | None = None
    text_case: TextCase | None = None
    font: Font | None = None
    scroll_mode: ScrollMode | None = None
    scroll_speed: int | None = Field(default=None, ge=0, le=500)
    scroll_when_fits: ScrollWhenFits | None = None
    repeat_count: int | None = Field(default=None, ge=0, le=10)
    repeat_every_minutes: int | None = Field(default=None, ge=1, le=60)
    melody: str | None = None
    rings_at_night: bool | None = None
    enabled: bool | None = None
    device_ids: list[int] | None = None


class ReminderRead(ReminderBase):
    id: int
    device_ids: list[int]
    last_fired_at: datetime | None
    #: When it will next ring, so the list answers the obvious question
    #: without anyone counting on their fingers.
    next_at: datetime | None


class FireResult(BaseModel):
    ok: bool
    message: str
    code: str
    params: dict = Field(default_factory=dict)
