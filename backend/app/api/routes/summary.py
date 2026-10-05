"""One scalar per thing worth watching, for a dashboard.

Written for tools like Homepage, which read a JSON document and map fields to
labels. They cannot count the items of an array, so `/api/devices` is useless
to them however well it serves the interface: what a dashboard needs is
`displays_online: 2`, not a list to reason about.

Readable with the session, or with the read-only token — and that token opens
this and nothing else.
"""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app import __version__
from app.api.deps import SessionDep
from app.models import Device, HealthStatus, Reminder, Widget
from app.services.scheduler import reminders as reminder_pass

router = APIRouter(tags=["summary"])


class Summary(BaseModel):
    status: str
    version: str

    displays_online: int
    displays_total: int

    widgets_active: int
    widgets_total: int

    reminders_active: int
    #: The next one to ring, across every reminder. Null when none will.
    next_reminder: str | None = None
    next_reminder_at: datetime | None = None


@router.get("/summary", response_model=Summary)
def summary(session: SessionDep) -> Summary:
    devices = list(session.exec(select(Device)).all())
    widgets = list(session.exec(select(Widget)).all())
    reminders = list(session.exec(select(Reminder).where(Reminder.enabled)).all())

    soonest: tuple[datetime, str] | None = None
    now = reminder_pass.local_now()
    for reminder in reminders:
        moment = _next_ring(reminder, now)
        if moment is not None and (soonest is None or moment < soonest[0]):
            soonest = (moment, reminder.name)

    return Summary(
        status="ok",
        version=__version__,
        displays_online=sum(
            1 for d in devices if d.enabled and d.status == HealthStatus.HEALTHY
        ),
        displays_total=len(devices),
        widgets_active=sum(1 for w in widgets if w.enabled),
        widgets_total=len(widgets),
        reminders_active=len(reminders),
        next_reminder=soonest[1] if soonest else None,
        next_reminder_at=soonest[0] if soonest else None,
    )


def _next_ring(reminder: Reminder, now: datetime) -> datetime | None:
    """The reminder's next instant, or None within the horizon.

    Looked for day by day rather than computed: a reminder may fire one week in
    eight, and an expression closed over that is harder to trust than a loop
    over eight weeks of days.
    """
    from datetime import timedelta

    for offset in range(8 * 7 + 7):
        day = now.date() + timedelta(days=offset)
        upcoming = [m for m in reminder_pass.occurrences(reminder, day) if m > now]
        if upcoming:
            return min(upcoming)
    return None
