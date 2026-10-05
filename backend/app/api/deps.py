"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlmodel import Session

from app.core.crypto import decrypt
from app.db.session import get_session
from app.models import Device
from app.services.ng.client import NgClient
from app.services.ng.transport import HttpTransport

SessionDep = Annotated[Session, Depends(get_session)]


def get_device(session: SessionDep, device_id: Annotated[int, Path()]) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found.")
    return device


DeviceDep = Annotated[Device, Depends(get_device)]


def client_for(device: Device) -> NgClient:
    """Build a client for a device. The caller is responsible for closing it."""
    password = decrypt(device.password_enc) if device.password_enc else None
    transport = HttpTransport(
        device.host, device.port, username=device.username, password=password
    )
    return NgClient(transport)
