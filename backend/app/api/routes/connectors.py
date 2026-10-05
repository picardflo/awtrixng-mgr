"""Connector catalogue and configured instances."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlmodel import select

from app.api.deps import SessionDep
from app.connectors import factory, registry
from app.connectors.base import ConnectorDescriptor, ConnectorTestResult
from app.core.crypto import encrypt
from app.core.errors import AwtrixNgError
from app.models import ConnectorInstance, HealthStatus, utcnow
from app.schemas.connector import ConnectorCreate, ConnectorRead, ConnectorUpdate
from app.schemas.fields import Option

log = logging.getLogger(__name__)
router = APIRouter(tags=["connectors"])


def _read(instance: ConnectorInstance) -> ConnectorRead:
    return ConnectorRead(
        id=instance.id,
        type=instance.type,
        name=instance.name,
        config=instance.config or {},
        secrets_set=sorted(instance.secrets or {}),
        enabled=instance.enabled,
        status=instance.status,
        last_success=instance.last_success,
        last_error=instance.last_error,
        last_error_code=instance.last_error_code,
        consecutive_failures=instance.consecutive_failures,
    )


def get_instance(
    session: SessionDep, connector_id: Annotated[int, Path()]
) -> ConnectorInstance:
    instance = session.get(ConnectorInstance, connector_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found.")
    return instance


InstanceDep = Annotated[ConnectorInstance, Depends(get_instance)]


@router.get("/connector-types", response_model=list[ConnectorDescriptor])
def list_types() -> list[ConnectorDescriptor]:
    """The catalogue: config schema and widget schemas for every connector.

    This is what lets the frontend build every form without knowing any
    connector (§10).
    """
    return registry.descriptors()


@router.get("/connectors", response_model=list[ConnectorRead])
def list_connectors(session: SessionDep) -> list[ConnectorRead]:
    instances = session.exec(select(ConnectorInstance).order_by(ConnectorInstance.id)).all()
    return [_read(instance) for instance in instances]


@router.post("/connectors", response_model=ConnectorRead, status_code=status.HTTP_201_CREATED)
def create_connector(payload: ConnectorCreate, session: SessionDep) -> ConnectorRead:
    if registry.get(payload.type) is None:
        raise AwtrixNgError(
            f"Unknown connector type {payload.type!r}.",
            code="connector.unknown_type",
            params={"type": payload.type},
        )

    instance = ConnectorInstance(
        type=payload.type,
        name=payload.name,
        config=payload.config,
        secrets={name: encrypt(value) for name, value in payload.secrets.items() if value},
        enabled=payload.enabled,
    )
    session.add(instance)
    session.commit()
    session.refresh(instance)
    log.info("connector %s created (%s)", instance.name, instance.type)
    return _read(instance)


@router.get("/connectors/{connector_id}", response_model=ConnectorRead)
def get_connector(instance: InstanceDep) -> ConnectorRead:
    return _read(instance)


@router.patch("/connectors/{connector_id}", response_model=ConnectorRead)
def update_connector(
    payload: ConnectorUpdate, instance: InstanceDep, session: SessionDep
) -> ConnectorRead:
    data = payload.model_dump(exclude_unset=True)
    secrets = data.pop("secrets", None)
    for key, value in data.items():
        setattr(instance, key, value)

    if secrets is not None:
        # Only the keys sent are touched; "" clears one, so a field can be
        # removed without re-sending the others.
        current = dict(instance.secrets or {})
        for name, value in secrets.items():
            if value:
                current[name] = encrypt(value)
            else:
                current.pop(name, None)
        instance.secrets = current

    # Bumping this is what makes the scheduler rebuild the connector and drop
    # its cached responses on the next tick.
    instance.updated_at = utcnow()
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return _read(instance)


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(instance: InstanceDep, session: SessionDep) -> None:
    session.delete(instance)
    session.commit()
    log.info("connector %s deleted", instance.name)


@router.post("/connectors/{connector_id}/test", response_model=ConnectorTestResult)
async def test_connector(instance: InstanceDep, session: SessionDep) -> ConnectorTestResult:
    """Never raises: an unreachable service is a state, not an API failure."""
    connector = factory.build(instance, session)
    try:
        result = await connector.test_connection()
    except AwtrixNgError as exc:
        instance.status = HealthStatus.ERROR
        instance.last_error = exc.message
        instance.last_error_code = exc.code
        instance.consecutive_failures += 1
        session.add(instance)
        session.commit()
        return ConnectorTestResult(
            ok=False, message=exc.message, code=exc.code, params=exc.params
        )
    finally:
        await connector.aclose()

    instance.status = HealthStatus.HEALTHY
    instance.last_success = utcnow()
    instance.last_error = None
    instance.last_error_code = None
    instance.consecutive_failures = 0
    session.add(instance)
    session.commit()
    return result


@router.get("/connectors/{connector_id}/discover", response_model=list[Option])
async def discover(
    instance: InstanceDep,
    session: SessionDep,
    source: Annotated[str, Query()],
    query: Annotated[str | None, Query()] = None,
) -> list[Option]:
    """Options for a remote_select field, e.g. the hosts of a Zabbix server."""
    connector = factory.build(instance, session)
    try:
        return await connector.discover(source, query, {})
    finally:
        await connector.aclose()
