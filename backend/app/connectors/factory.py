"""Turning a stored configuration into a live connector."""

from typing import Any

from sqlmodel import Session

from app.connectors.base import Connector
from app.connectors.registry import get as get_connector_type
from app.core.crypto import decrypt
from app.core.errors import AwtrixNgError
from app.models import ConnectorInstance, Device

#: Where a resolved display is parked in the configuration.
#:
#: A connector has no database access — that is what keeps it testable without
#: one — so a `device` field holds only an id. The factory looks it up and
#: leaves the host, port and credentials here. One display per connector is
#: enough for anything built so far.
RESOLVED_DEVICE = "_resolved_device"


def _device_field(connector_type: type[Connector]) -> str | None:
    return next(
        (
            field.name
            for field in connector_type.descriptor.config_schema
            if field.type == "device"
        ),
        None,
    )


def _resolve(config: dict[str, Any], device: Device) -> dict[str, Any]:
    return config | {
        RESOLVED_DEVICE: {
            "id": device.id,
            "name": device.name,
            "host": device.host,
            "port": device.port,
            "username": device.username,
            "password": decrypt(device.password_enc) if device.password_enc else None,
        }
    }


def build(instance: ConnectorInstance, session: Session | None = None) -> Connector:
    """Instantiate a configured connector, decrypting its secrets.

    `session` is only needed by connectors that reference a display; without
    one they raise a plain "pick a display" error rather than misbehave.
    """
    connector_type = get_connector_type(instance.type)
    if connector_type is None:
        raise AwtrixNgError(
            f"Unknown connector type {instance.type!r}.",
            code="connector.unknown_type",
            params={"type": instance.type},
        )

    config = dict(instance.config or {})
    field = _device_field(connector_type)
    if field and session is not None:
        device = session.get(Device, config.get(field)) if config.get(field) else None
        if device is not None:
            config = _resolve(config, device)

    secrets = {name: decrypt(token) for name, token in (instance.secrets or {}).items()}
    return connector_type(config, secrets)


def fingerprint(instance: ConnectorInstance, session: Session | None = None) -> tuple:
    """Identifies a built connector, for caching it between scheduler passes.

    It includes the referenced display's own timestamp: changing a display's
    hostname must take effect on the next pass, not at the next restart.
    """
    stamp: Any = None
    connector_type = get_connector_type(instance.type)
    if connector_type is not None and session is not None:
        field = _device_field(connector_type)
        if field and (instance.config or {}).get(field):
            device = session.get(Device, instance.config[field])
            stamp = device.updated_at if device else None
    return instance.id, instance.updated_at, stamp
