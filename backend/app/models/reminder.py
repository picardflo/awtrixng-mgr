"""A reminder: a message at a time, on one or more displays.

Not a widget, and deliberately so. A widget is collected on an interval and
takes its turn in the rotation; a reminder has nothing upstream, fires at a
clock time, and must interrupt rather than wait — which is what /api/notify is
for. Forcing it into the widget model would have meant a widget with no
connector, outside the rotation, whose refresh is an hour of the day: three
exceptions, which is the sign of a different thing.
"""

from datetime import date, datetime, time

from sqlmodel import Field, Relationship, SQLModel

from app.models.base import utcnow


class ReminderTarget(SQLModel, table=True):
    """One display a reminder fires on.

    A link table rather than a list of ids in a column: deleting a display must
    not leave a reminder pointing at nothing. No state here — a notification is
    sent and forgotten, there is nothing to reconcile.
    """

    __tablename__ = "reminder_target"

    reminder_id: int = Field(
        foreign_key="reminder.id", ondelete="CASCADE", primary_key=True
    )
    device_id: int = Field(
        foreign_key="device.id", ondelete="CASCADE", primary_key=True
    )

    reminder: "Reminder" = Relationship(back_populates="targets")


class Reminder(SQLModel, table=True):
    __tablename__ = "reminder"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    #: What the matrix shows. Accents are stripped on the way out, like any
    #: other text (the firmware font has none).
    message: str

    #: LaMetric id or a file already on the device. Animated is the point here:
    #: an alert that moves is seen from across a room.
    icon: str | None = None
    color: str | None = None

    #: Local time, in the container's timezone. Someone who says 07:30 means
    #: half past seven where they live, not UTC.
    at: time

    #: 1 = every week, 2 = every other week, and so on. Paired with `anchor`,
    #: which names a week it does fire on — without it, "every other week"
    #: would be a question with two answers.
    every_weeks: int = Field(default=1, ge=1, le=8)

    #: Any day of a week the reminder fires on. Only the week matters; the day
    #: within it is ignored.
    anchor: date | None = None

    #: A single date instead of a weekly rhythm — a car service, an
    #: appointment. Set, it replaces `weekdays` and `every_weeks` entirely: the
    #: reminder rings that day and never again.
    on_date: date | None = None

    #: Target of a countdown. Set, the message may use `{{ days }}`, which is
    #: how many days remain. The reminder keeps its own schedule: what changes
    #: is what it says, not when it says it.
    countdown_to: date | None = None

    #: Days it fires on, Monday = 0, as a sorted list of integers.
    #: Stored as text because SQLite has no array and a seven-slot bitmask
    #: would be unreadable in a backup file.
    weekdays: str = Field(default="0,1,2,3,4")

    #: Seconds the notification stays up.
    duration_seconds: int = Field(default=10, ge=1, le=120)

    #: The presentation options a widget offers, minus those that make no
    #: sense here: a reminder has no data, so no progress bar, no weekday
    #: segments and nothing to hide when a service returns nothing.
    #:
    #: The rest is now the **same list**, declared once in
    #: `app/schemas/matrix_text.py` and measured on the notification route as
    #: well as on the pushed-app one. It used to be three options against a
    #: widget's ten, and nobody could say why the font was among the seven
    #: missing.
    #:
    #: `center` and `rainbow` were here on AWTRIX 3 and are gone: NG has no
    #: centring key at all, and `palette` colours effects rather than text —
    #: both measured on hardware. Offering a control the firmware ignores is
    #: how someone spends an evening wondering why nothing changes.
    #:
    #: `no_scroll` became `scroll_mode="static"`, which is the firmware's own
    #: word for the same thing.
    scroll_mode: str = Field(default="wrap")
    scroll_speed: int = Field(default=100, ge=0, le=500)
    #: What the text does when it *does* fit — "static" or "scroll".
    scroll_when_fits: str = Field(default="static")
    background: str | None = None
    #: An animation behind the text. Some fill the panel; see `MatrixText`.
    effect: str | None = None
    #: Weather drawn over the text. Nothing proposes one for a reminder, so
    #: None here means none, full stop.
    overlay: str | None = None
    #: "fixed", "pushOnce" or "push" — what the icon does while text scrolls.
    icon_mode: str = Field(default="fixed")
    #: "inherit", "upper" or "asTyped". A stock display shows capitals, so
    #: "Ritaline" arrives as "RITALINE" unless this says otherwise.
    text_case: str = Field(default="inherit")
    #: "small" or "large". Five rows or seven — and no extra width either way,
    #: so a message that scrolls in one scrolls in the other.
    font: str = Field(default="small")

    #: Blind repetition: it fires again every `repeat_every_minutes`, this many
    #: extra times. awtrixng-mgr cannot know whether anyone saw it — HTTP carries
    #: no button press back — so it repeats without asking.
    repeat_count: int = Field(default=0, ge=0, le=10)
    repeat_every_minutes: int = Field(default=2, ge=1, le=60)

    #: Whether this one still rings while the display is in quiet hours.
    #:
    #: Off by default, because that is what "quiet hours" has to mean. On for
    #: the alarm that exists in order to wake someone: a 06:30 wake-up inside
    #: a 22:00–07:00 window would otherwise be silent, and that is the kind of
    #: silence noticed only on the morning it mattered.
    rings_at_night: bool = False

    #: An RTTTL melody, played inline — nothing to upload. Silent on a clock
    #: with no buzzer, which the Ulanzi ships without.
    melody: str | None = None

    enabled: bool = True

    #: The last instant actually sent, so a restart does not re-fire this
    #: morning's alert and a missed window is not replayed hours later.
    last_fired_at: datetime | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    targets: list[ReminderTarget] = Relationship(
        back_populates="reminder", cascade_delete=True
    )

    @property
    def device_ids(self) -> list[int]:
        return [target.device_id for target in self.targets]

    @property
    def days(self) -> list[int]:
        return sorted(
            {int(part) for part in self.weekdays.split(",") if part.strip().isdigit()}
        )
