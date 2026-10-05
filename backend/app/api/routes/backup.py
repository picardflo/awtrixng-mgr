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
from app.models import ConnectorInstance, Device, Widget, WidgetTarget
from app.schemas.backup import (
    FORMAT_VERSION,
    Backup,
    BackupConnector,
    BackupDevice,
    BackupSummary,
    BackupWidget,
    RestoreResult,
)
from app.services.scheduler.loop import scheduler

log = logging.getLogger(__name__)
router = APIRouter(tags=["backup"])


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
        for widget in session.exec(select(Widget)).all():
            session.delete(widget)
        for instance in session.exec(select(ConnectorInstance)).all():
            session.delete(instance)
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
    log.info("restored %d device(s), %d service(s), %d widget(s)",
             len(devices), len(connectors), kept)

    return RestoreResult(
        ok=True,
        message="Configuration restored.",
        code="backup.restored",
        devices=len(devices),
        connectors=len(connectors),
        widgets=kept,
        secrets=_count_secrets(backup),
    )


@router.get("/backup/format", status_code=status.HTTP_200_OK)
def backup_format() -> dict[str, int]:
    """The format this installation writes and reads."""
    return {"format": FORMAT_VERSION}
