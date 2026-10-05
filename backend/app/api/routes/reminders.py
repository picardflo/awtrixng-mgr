"""Reminders: a message at a time, on one or more displays.

Not under /widgets on purpose — a reminder has no connector, no rotation and
no refresh interval. See `app/models/reminder.py` for why it is its own thing.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlmodel import select

from app.api.deps import SessionDep, client_for
from app.core.errors import AwtrixNgError
from app.models import Device, Reminder, ReminderTarget, utcnow
from app.schemas.reminder import (
    FireResult,
    ReminderCreate,
    ReminderRead,
    ReminderUpdate,
)
from app.services.scheduler import reminders as pass_

log = logging.getLogger(__name__)
router = APIRouter(tags=["reminders"])

#: How far ahead to look for the next ring. Wide enough for the longest cycle
#: a reminder can have, plus the week it sits in.
HORIZON_DAYS = 8 * 7 + 7


def _next_at(reminder: Reminder, now: datetime) -> datetime | None:
    if not reminder.enabled:
        return None
    if reminder.on_date is not None:
        # A car service booked for next spring is further out than the rolling
        # horizon, and answering "never" about a date the user just typed in
        # would read as a bug. One date, one lookup.
        upcoming = [m for m in pass_.occurrences(reminder, reminder.on_date) if m > now]
        return min(upcoming) if upcoming else None
    for offset in range(HORIZON_DAYS):
        day = now.date() + timedelta(days=offset)
        upcoming = [m for m in pass_.occurrences(reminder, day) if m > now]
        if upcoming:
            return min(upcoming)
    return None


def _read(reminder: Reminder) -> ReminderRead:
    return ReminderRead(
        id=reminder.id or 0,
        name=reminder.name,
        message=reminder.message,
        icon=reminder.icon,
        color=reminder.color,
        at=reminder.at,
        days=reminder.days,
        every_weeks=reminder.every_weeks,
        anchor=reminder.anchor,
        on_date=reminder.on_date,
        countdown_to=reminder.countdown_to,
        duration_seconds=reminder.duration_seconds,
        scroll_mode=reminder.scroll_mode,
        scroll_speed=reminder.scroll_speed,
        background=reminder.background,
        repeat_count=reminder.repeat_count,
        repeat_every_minutes=reminder.repeat_every_minutes,
        melody=reminder.melody,
        rings_at_night=reminder.rings_at_night,
        enabled=reminder.enabled,
        device_ids=reminder.device_ids,
        last_fired_at=reminder.last_fired_at,
        next_at=_next_at(reminder, pass_.local_now()),
    )


def _targets(session: SessionDep, reminder: Reminder, device_ids: list[int]) -> None:
    """Point a reminder at exactly these displays.

    An unknown id is refused rather than ignored: a reminder silently firing on
    fewer clocks than asked is the kind of thing nobody notices until the
    morning it mattered.
    """
    wanted = sorted(set(device_ids))
    for device_id in wanted:
        if session.get(Device, device_id) is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Display {device_id} does not exist."
            )

    reminder.targets = [
        ReminderTarget(reminder_id=reminder.id, device_id=device_id)
        for device_id in wanted
    ]


@router.get("/reminders", response_model=list[ReminderRead])
def list_reminders(session: SessionDep) -> list[ReminderRead]:
    rows = session.exec(select(Reminder).order_by(Reminder.at, Reminder.id)).all()
    return [_read(reminder) for reminder in rows]


@router.post("/reminders", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
def create_reminder(payload: ReminderCreate, session: SessionDep) -> ReminderRead:
    reminder = Reminder(
        name=payload.name,
        message=payload.message,
        icon=payload.icon,
        color=payload.color,
        at=payload.at,
        weekdays=",".join(str(d) for d in payload.days),
        every_weeks=payload.every_weeks,
        # Defaulting to today makes "every other week" start now, which is
        # what someone setting it today means.
        anchor=payload.anchor or pass_.local_now().date(),
        on_date=payload.on_date,
        countdown_to=payload.countdown_to,
        duration_seconds=payload.duration_seconds,
        scroll_mode=payload.scroll_mode,
        scroll_speed=payload.scroll_speed,
        background=payload.background,
        repeat_count=payload.repeat_count,
        repeat_every_minutes=payload.repeat_every_minutes,
        melody=payload.melody,
        rings_at_night=payload.rings_at_night,
        enabled=payload.enabled,
    )
    session.add(reminder)
    session.flush()
    _targets(session, reminder, payload.device_ids)
    session.commit()
    session.refresh(reminder)
    log.info("reminder %s created for %s", reminder.name, reminder.at)
    return _read(reminder)


@router.get("/reminders/{reminder_id}", response_model=ReminderRead)
def get_one(reminder_id: Annotated[int, Path(ge=1)], session: SessionDep) -> ReminderRead:
    return _read(_get(session, reminder_id))


@router.patch("/reminders/{reminder_id}", response_model=ReminderRead)
def update_reminder(
    reminder_id: Annotated[int, Path(ge=1)],
    payload: ReminderUpdate,
    session: SessionDep,
) -> ReminderRead:
    reminder = _get(session, reminder_id)
    fields = payload.model_dump(exclude_unset=True)
    device_ids = fields.pop("device_ids", None)

    if "days" in fields:
        days = sorted(set(fields.pop("days") or []))
        if not days:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A reminder with no day would never ring.",
            )
        reminder.weekdays = ",".join(str(d) for d in days)

    for key, value in fields.items():
        setattr(reminder, key, value)

    if device_ids is not None:
        _targets(session, reminder, device_ids)

    reminder.updated_at = utcnow()
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return _read(reminder)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(
    reminder_id: Annotated[int, Path(ge=1)], session: SessionDep
) -> None:
    reminder = _get(session, reminder_id)
    session.delete(reminder)
    session.commit()
    log.info("reminder %s deleted", reminder.name)


@router.post("/reminders/{reminder_id}/fire", response_model=FireResult)
async def fire_now(
    reminder_id: Annotated[int, Path(ge=1)], session: SessionDep
) -> FireResult:
    """Ring it immediately, to see and hear what it does.

    Does not touch `last_fired_at`: trying a reminder at ten past seven must
    not cancel the real one at half past.
    """
    reminder = _get(session, reminder_id)
    clients = {}
    for device_id in reminder.device_ids:
        device = session.get(Device, device_id)
        if device is not None and device.enabled:
            clients[device_id] = client_for(device)

    if not clients:
        return FireResult(
            ok=False,
            message="No display to ring on.",
            code="reminder.no_display",
        )

    try:
        fired = await pass_.send(reminder, clients, pass_.local_now())
    except AwtrixNgError as exc:
        return FireResult(ok=False, message=exc.message, code=exc.code, params=exc.params)
    finally:
        for client in clients.values():
            await client.aclose()

    if not fired.sent_to:
        return FireResult(
            ok=False,
            message="No display could be reached.",
            code="reminder.unreachable",
        )

    return FireResult(
        ok=True,
        message=f"Sent to {len(fired.sent_to)} display(s).",
        code="reminder.fired",
        params={"count": len(fired.sent_to)},
    )


def _get(session: SessionDep, reminder_id: int) -> Reminder:
    reminder = session.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found.")
    return reminder
