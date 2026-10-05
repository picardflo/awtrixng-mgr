"""AWTRIX display management."""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.deps import DeviceDep, SessionDep, client_for
from app.core.crypto import encrypt
from app.core.errors import AwtrixNgError
from app.models import Device, HealthStatus, utcnow
from app.schemas.bedroom import BedroomMode
from app.schemas.device import (
    DeviceCreate,
    DeviceRead,
    DeviceTestResult,
    DeviceUpdate,
    NotifyRequest,
)
from app.schemas.device_settings import (
    DeviceSettings,
    DeviceSettingsResult,
    changes,
    read,
)
from app.services.ng.payload import NgNotification
from app.services.scheduler.loop import scheduler

log = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["devices"])


def _read(device: Device) -> DeviceRead:
    return DeviceRead(
        id=device.id,
        name=device.name,
        host=device.host,
        port=device.port,
        username=device.username,
        has_password=bool(device.password_enc),
        enabled=device.enabled,
        firmware=device.firmware,
        uid=device.uid,
        status=device.status,
        last_seen=device.last_seen,
        last_error=device.last_error,
        last_error_code=device.last_error_code,
    )


def _record_failure(device: Device, exc: AwtrixNgError, session: SessionDep) -> None:
    device.status = HealthStatus.ERROR
    device.last_error = exc.message
    device.last_error_code = exc.code
    device.updated_at = utcnow()
    session.add(device)
    session.commit()


async def _probe(device: Device, session: SessionDep) -> DeviceTestResult:
    """Read GET /api/v1/device and refresh our view of it.

    Never raises: an unreachable display is a normal state, not an API
    failure.
    """
    client = client_for(device)
    try:
        stats = await client.get_device()
    except AwtrixNgError as exc:
        _record_failure(device, exc, session)
        log.warning("device %s unreachable: %s", device.name, exc.message)
        return DeviceTestResult(
            ok=False, message=exc.message, code=exc.code, params=exc.params
        )
    finally:
        await client.aclose()

    device.firmware = stats.version
    device.uid = stats.uid
    device.status = HealthStatus.HEALTHY
    device.last_seen = utcnow()
    device.last_error = None
    device.last_error_code = None
    device.updated_at = utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)

    return DeviceTestResult(
        ok=True,
        message=f"AWTRIX 3 detected, firmware {stats.version}.",
        code="device.detected",
        params={"firmware": stats.version},
        firmware=stats.version,
        uid=stats.uid,
        stats=stats,
    )


@router.get("", response_model=list[DeviceRead])
def list_devices(session: SessionDep) -> list[DeviceRead]:
    devices = session.exec(select(Device).order_by(Device.id)).all()
    return [_read(d) for d in devices]


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, session: SessionDep) -> DeviceRead:
    device = Device(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password_enc=encrypt(payload.password) if payload.password else None,
        enabled=payload.enabled,
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    log.info("device %s created (%s)", device.name, device.base_url)
    return _read(device)


@router.get("/{device_id}", response_model=DeviceRead)
def get_one(device: DeviceDep) -> DeviceRead:
    return _read(device)


@router.patch("/{device_id}", response_model=DeviceRead)
def update_device(payload: DeviceUpdate, device: DeviceDep, session: SessionDep) -> DeviceRead:
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for key, value in data.items():
        setattr(device, key, value)
    if password is not None:
        # "" clears the password, any other value replaces it.
        device.password_enc = encrypt(password) if password else None
    device.updated_at = utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)
    return _read(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device: DeviceDep, session: SessionDep) -> None:
    session.delete(device)
    session.commit()
    log.info("device %s deleted", device.name)


@router.post("/{device_id}/test", response_model=DeviceTestResult)
async def test_device(device: DeviceDep, session: SessionDep) -> DeviceTestResult:
    return await _probe(device, session)


@router.post("/{device_id}/notify", response_model=DeviceTestResult)
async def send_notification(
    payload: NotifyRequest, device: DeviceDep, session: SessionDep
) -> DeviceTestResult:
    client = client_for(device)
    try:
        await client.notify(
            NgNotification(
                text=payload.text,
                icon=payload.icon,
                text_color=payload.color,
                duration_ms=payload.duration * 1000,
                overlay=payload.overlay or None,
                sound_rtttl=payload.melody or None,
                wakeup=payload.wakeup or None,
            )
        )
    except AwtrixNgError as exc:
        _record_failure(device, exc, session)
        return DeviceTestResult(
            ok=False, message=exc.message, code=exc.code, params=exc.params
        )
    finally:
        await client.aclose()
    return DeviceTestResult(
        ok=True, message="Notification sent.", code="device.notification_sent"
    )


@router.get("/{device_id}/screen")
async def get_screen(device: DeviceDep) -> dict[str, list[int]]:
    """LiveView: 256 24-bit colours, one per pixel of the 32x8 matrix."""
    client = client_for(device)
    try:
        pixels = await client.get_screen()
    except AwtrixNgError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    finally:
        await client.aclose()
    return {"pixels": pixels}


@router.get("/{device_id}/apps")
async def get_apps(device: DeviceDep) -> list[dict]:
    """Everything the display holds, with its origin.

    Replaces AWTRIX 3's `/api/loop`, which gave names and positions only. The
    origin is the useful part: it says which apps are the firmware's, which
    are ours, and which belong to something else entirely.
    """
    client = client_for(device)
    try:
        # No `by_alias`: the camelCase belongs to the firmware and stops at
        # the client. See app/services/ng/models.py.
        return [app.model_dump() for app in await client.get_apps()]
    except AwtrixNgError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    finally:
        await client.aclose()


@router.get("/{device_id}/display")
async def get_display(device: DeviceDep) -> dict:
    """Panel state: power, brightness, the active overlay.

    `power` is the one that matters and has no AWTRIX 3 equivalent: a display
    whose panel is off still answers `/display/screen` with pixels, so the
    framebuffer cannot tell you whether anything is visible.
    """
    client = client_for(device)
    try:
        return await client.get_display()
    except AwtrixNgError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    finally:
        await client.aclose()


@router.post("/{device_id}/power")
async def set_power(device: DeviceDep, on: bool = True) -> dict:
    """Switch the matrix off or on. New in NG."""
    client = client_for(device)
    try:
        await client.set_power(on)
    except AwtrixNgError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    finally:
        await client.aclose()
    return {"ok": True, "power": on}


def _bedroom(device: Device) -> BedroomMode:
    return BedroomMode(
        enabled=device.night_mode,
        start=device.night_from or BedroomMode().start,
        end=device.night_to or BedroomMode().end,
        brightness=device.night_brightness,
        active=device.night_active,
    )


@router.get("/{device_id}/bedroom", response_model=BedroomMode)
def get_bedroom(device: DeviceDep) -> BedroomMode:
    """The dimmed window this display observes, if any."""
    return _bedroom(device)


@router.put("/{device_id}/bedroom", response_model=BedroomMode)
def set_bedroom(
    payload: BedroomMode, device: DeviceDep, session: SessionDep
) -> BedroomMode:
    """Set the window. Nothing is written to the display here.

    The firmware has no schedule, so awtrixng-mgr keeps it and the scheduler
    applies it on its own pass — within a second of this call, rather than at
    the next half-minute check.
    """
    device.night_mode = payload.enabled
    device.night_from = payload.start
    device.night_to = payload.end
    device.night_brightness = payload.brightness

    # Turning it off mid-window must put the display back, which the pass does
    # by seeing `night_active` disagree with a schedule that no longer applies.
    device.updated_at = utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)

    scheduler.bedroom_soon()
    return _bedroom(device)


@router.get("/{device_id}/settings", response_model=DeviceSettings)
async def get_device_settings(device: DeviceDep) -> DeviceSettings:
    """What the display itself is set to — brightness, volume, rotation."""
    client = client_for(device)
    try:
        return read(await client.get_settings())
    except AwtrixNgError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    finally:
        await client.aclose()


@router.post("/{device_id}/settings", response_model=DeviceSettingsResult)
async def set_device_settings(
    payload: DeviceSettings, device: DeviceDep
) -> DeviceSettingsResult:
    """Change the display's own settings. **No restart**, unlike the built-in
    apps: the firmware applies these immediately.

    Only what differs is sent. Rewriting all fourteen to change one is how a
    setting someone adjusted on the device itself gets quietly reverted by a
    form that was opened before.
    """
    client = client_for(device)
    try:
        current = read(await client.get_settings())
        wanted = changes(current, payload)
        if not wanted:
            return DeviceSettingsResult(
                ok=True,
                message="Nothing to change.",
                code="device_settings.unchanged",
                settings=current,
            )

        await client.update_settings(wanted)
        # Read back rather than trust the payload: the firmware clamps, and a
        # form showing what was asked instead of what took effect is a form
        # that lies.
        applied = read(await client.get_settings())
    except AwtrixNgError as exc:
        return DeviceSettingsResult(
            ok=False, message=exc.message, code=exc.code, settings=payload
        )
    finally:
        await client.aclose()

    return DeviceSettingsResult(
        ok=True,
        message=f"{len(wanted)} setting(s) applied.",
        code="device_settings.applied",
        settings=applied,
        applied=sorted(wanted),
    )


