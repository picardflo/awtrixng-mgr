"""Exporting and restoring the configuration.

Without this, a lost `/data/awtrixng.db` means retyping every template, icon,
colour and position by hand.
"""

import logging

from fastapi import APIRouter, status
from sqlmodel import select

from app import __version__
from app.api.deps import SessionDep
from app.core.crypto import decrypt, encrypt
from app.core.errors import AwtrixNgError
from app.models import (
    ConnectorInstance,
    Device,
    Reminder,
    ReminderTarget,
    Widget,
    WidgetTarget,
)
from app.schemas.backup import (
    FORMAT_VERSION,
    Backup,
    BackupConnector,
    BackupDevice,
    BackupReminder,
    BackupSummary,
    BackupWidget,
    RestoreResult,
)
from app.services.scheduler.loop import scheduler

log = logging.getLogger(__name__)
router = APIRouter(tags=["backup"])


def _targets_by_address(session: SessionDep) -> dict[int, list[tuple[str, int]]]:
    """Where each reminder currently rings, addressed rather than numbered.

    Ids do not survive a restore — every display is deleted and recreated —
    but a clock keeps its host and port, which is what makes a reminder
    re-attachable afterwards.
    """
    found: dict[int, list[tuple[str, int]]] = {}
    for reminder in session.exec(select(Reminder)).all():
        addresses = []
        for target in reminder.targets:
            device = session.get(Device, target.device_id)
            if device is not None:
                addresses.append((device.host, device.port))
        if addresses:
            found[reminder.id] = addresses
    return found


def _count_secrets(backup: Backup) -> int:
    return sum(len(connector.secrets) for connector in backup.connectors) + sum(
        1 for device in backup.devices if device.password
    )


@router.get("/backup", response_model=Backup)
def export_configuration(session: SessionDep) -> Backup:
    """The whole configuration, **credentials included, in clear text**.

    They are re-encrypted on restore with the receiving installation's key. The
    file therefore has to be kept like a credential: it says so in its own
    first field, and the export button says so before downloading.

    Note the consequence: this is the one endpoint that returns a secret. On a
    LAN-only deployment without authentication (ADR-010), anyone who can reach
    awtrixng-mgr can read them.
    """
    devices = list(session.exec(select(Device).order_by(Device.id)).all())
    connectors = list(
        session.exec(select(ConnectorInstance).order_by(ConnectorInstance.id)).all()
    )
    widgets = list(
        session.exec(select(Widget).order_by(Widget.position, Widget.id)).all()
    )
    reminders = list(session.exec(select(Reminder).order_by(Reminder.id)).all())

    return Backup(
        app_version=__version__,
        devices=[
            BackupDevice(
                ref=device.id,
                name=device.name,
                host=device.host,
                port=device.port,
                username=device.username,
                password=decrypt(device.password_enc) if device.password_enc else None,
                enabled=device.enabled,
            )
            for device in devices
        ],
        connectors=[
            BackupConnector(
                ref=instance.id,
                type=instance.type,
                name=instance.name,
                config=instance.config or {},
                secrets={
                    name: decrypt(token)
                    for name, token in sorted((instance.secrets or {}).items())
                },
                enabled=instance.enabled,
            )
            for instance in connectors
        ],
        widgets=[
            BackupWidget(
                name=widget.name,
                connector=widget.connector_id,
                devices=widget.device_ids,
                widget_type=widget.widget_type,
                config=widget.config or {},
                display=widget.display or {},
                refresh_seconds=widget.refresh_seconds,
                position=widget.position,
                enabled=widget.enabled,
            )
            for widget in widgets
        ],
        reminders=[
            BackupReminder(
                name=reminder.name,
                message=reminder.message,
                devices=reminder.device_ids,
                icon=reminder.icon,
                color=reminder.color,
                at=reminder.at,
                days=reminder.days,
                every_weeks=reminder.every_weeks,
                anchor=reminder.anchor,
                on_date=reminder.on_date,
                countdown_to=reminder.countdown_to,
                duration_seconds=reminder.duration_seconds,
                repeat_count=reminder.repeat_count,
                repeat_every_minutes=reminder.repeat_every_minutes,
                melody=reminder.melody,
                rings_at_night=reminder.rings_at_night,
                enabled=reminder.enabled,
                background=reminder.background,
                effect=reminder.effect,
                overlay=reminder.overlay,
                icon_mode=reminder.icon_mode,
                text_case=reminder.text_case,
                font=reminder.font,
                scroll_mode=reminder.scroll_mode,
                scroll_speed=reminder.scroll_speed,
                scroll_when_fits=reminder.scroll_when_fits,
            )
            for reminder in reminders
        ],
    )


@router.post("/backup/inspect", response_model=BackupSummary)
def inspect_backup(backup: Backup, session: SessionDep) -> BackupSummary:
    """What a file holds, without touching anything.

    Restoring replaces everything, so seeing the file's contents first is what
    stops the wrong file from wiping a working configuration.
    """
    if backup.format > FORMAT_VERSION:
        return BackupSummary(
            ok=False,
            message=(
                f"This file was written by a newer awtrixng-mgr (format "
                f"{backup.format}, this one reads {FORMAT_VERSION})."
            ),
            code="backup.format_too_new",
        )

    return BackupSummary(
        ok=True,
        message="File read.",
        code="backup.readable",
        exported_at=backup.exported_at,
        app_version=backup.app_version or None,
        devices=len(backup.devices),
        connectors=len(backup.connectors),
        widgets=len(backup.widgets),
        # None, not 0: a file that predates format 2 says nothing about
        # reminders, and printing a zero would read as "this backup has none".
        reminders=None if backup.reminders is None else len(backup.reminders),
        secrets=_count_secrets(backup),
    )


@router.post("/backup/restore", response_model=RestoreResult)
def restore_configuration(backup: Backup, session: SessionDep) -> RestoreResult:
    """Replace the configuration with the file's.

    Replaces rather than merges: "restore" has to mean "look like the backup".
    Merging would invite duplicates nobody asked for.

    Everything happens in one transaction: a malformed file leaves the previous
    configuration untouched rather than half-replaced.
    """
    if backup.format > FORMAT_VERSION:
        raise AwtrixNgError(
            f"This file was written by a newer awtrixng-mgr (format {backup.format}).",
            code="backup.format_too_new",
            params={"format": backup.format},
        )

    try:
        # Where each surviving reminder rings, by host and port rather than by
        # id. Deleting the displays below takes `reminder_target` with it —
        # ON DELETE CASCADE, and the pragma is on at runtime — so a reminder
        # kept from an older file would come back ringing on nothing at all.
        # That is what version 1 did, silently: three reminders, three empty
        # target lists, and a result saying "Configuration restored".
        #
        # Matching on the address is what makes it work in the ordinary case:
        # the "Bureau" deleted and the "Bureau" recreated are the same clock.
        rings_on = _targets_by_address(session)

        for widget in session.exec(select(Widget)).all():
            session.delete(widget)
        for instance in session.exec(select(ConnectorInstance)).all():
            session.delete(instance)
        if backup.reminders is not None:
            # Replaced, like everything else. Only a file that carries the
            # section may clear it.
            for reminder in session.exec(select(Reminder)).all():
                session.delete(reminder)
        for device in session.exec(select(Device)).all():
            session.delete(device)
        session.flush()

        # File-local refs become database ids.
        devices: dict[int, int] = {}
        for entry in backup.devices:
            device = Device(
                name=entry.name,
                host=entry.host,
                port=entry.port,
                username=entry.username,
                # Re-encrypted with *this* installation's key.
                password_enc=encrypt(entry.password) if entry.password else None,
                enabled=entry.enabled,
            )
            session.add(device)
            session.flush()
            devices[entry.ref] = device.id

        connectors: dict[int, int] = {}
        for entry in backup.connectors:
            instance = ConnectorInstance(
                type=entry.type,
                name=entry.name,
                config=entry.config,
                secrets={
                    name: encrypt(value) for name, value in entry.secrets.items() if value
                },
                enabled=entry.enabled,
            )
            session.add(instance)
            session.flush()
            connectors[entry.ref] = instance.id

        kept = 0
        for entry in backup.widgets:
            if entry.connector not in connectors:
                log.warning("widget %s references an unknown service, skipped", entry.name)
                continue
            widget = Widget(
                name=entry.name,
                connector_id=connectors[entry.connector],
                widget_type=entry.widget_type,
                config=entry.config,
                display=entry.display,
                refresh_seconds=entry.refresh_seconds,
                position=entry.position,
                enabled=entry.enabled,
            )
            session.add(widget)
            session.flush()
            # A file listing the same display twice would violate the target
            # primary key; tolerating it beats refusing the whole restore.
            for ref in dict.fromkeys(entry.devices):
                if ref in devices:
                    session.add(
                        WidgetTarget(widget_id=widget.id, device_id=devices[ref])
                    )
            kept += 1

        # -- Reminders ------------------------------------------------------
        by_address = {
            (entry.host, entry.port): devices[entry.ref]
            for entry in backup.devices
            if entry.ref in devices
        }

        restored = 0
        for entry in backup.reminders or []:
            reminder = Reminder(
                name=entry.name,
                message=entry.message,
                icon=entry.icon,
                color=entry.color,
                at=entry.at,
                weekdays=",".join(str(day) for day in sorted(set(entry.days))),
                every_weeks=entry.every_weeks,
                anchor=entry.anchor,
                on_date=entry.on_date,
                countdown_to=entry.countdown_to,
                duration_seconds=entry.duration_seconds,
                repeat_count=entry.repeat_count,
                repeat_every_minutes=entry.repeat_every_minutes,
                melody=entry.melody,
                rings_at_night=entry.rings_at_night,
                enabled=entry.enabled,
                background=entry.background,
                effect=entry.effect,
                overlay=entry.overlay,
                icon_mode=entry.icon_mode,
                text_case=entry.text_case,
                font=entry.font,
                scroll_mode=entry.scroll_mode,
                scroll_speed=entry.scroll_speed,
                scroll_when_fits=entry.scroll_when_fits,
            )
            session.add(reminder)
            session.flush()
            for ref in dict.fromkeys(entry.devices):
                if ref in devices:
                    session.add(
                        ReminderTarget(reminder_id=reminder.id, device_id=devices[ref])
                    )
            restored += 1

        # The reminders this installation already had, when the file could not
        # speak about them. Re-attached to the displays that came back at the
        # same address.
        reattached = 0
        if backup.reminders is None:
            for reminder in session.exec(select(Reminder)).all():
                for address in rings_on.get(reminder.id, ()):
                    device_id = by_address.get(address)
                    if device_id is not None:
                        session.add(
                            ReminderTarget(
                                reminder_id=reminder.id, device_id=device_id
                            )
                        )
                reattached += 1

        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        log.exception("restore failed")
        raise AwtrixNgError(
            f"The file could not be restored: {exc}", code="backup.restore_failed"
        ) from exc

    # The displays still carry the previous apps; reconciling clears what no
    # longer belongs and republishes the rest.
    scheduler.reconcile_soon()
    log.info(
        "restored %d device(s), %d service(s), %d widget(s), %d reminder(s)"
        "%s",
        len(devices), len(connectors), kept, restored,
        f", kept {reattached} from before" if reattached else "",
    )

    return RestoreResult(
        ok=True,
        message="Configuration restored.",
        code="backup.restored",
        devices=len(devices),
        connectors=len(connectors),
        widgets=kept,
        reminders=restored,
        reminders_kept=reattached,
        secrets=_count_secrets(backup),
    )


@router.get("/backup/format", status_code=status.HTTP_200_OK)
def backup_format() -> dict[str, int]:
    """The format this installation writes and reads."""
    return {"format": FORMAT_VERSION}
