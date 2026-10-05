"""Widget catalogue, instances, preview and push."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlmodel import select

from app.api.deps import DeviceDep, SessionDep, client_for
from app.connectors import factory, registry
from app.connectors.base import WidgetDescriptor
from app.core.errors import AwtrixNgError
from app.models import ConnectorInstance, Device, HealthStatus, Widget, WidgetTarget, utcnow
from app.schemas.widget import (
    OrderRequest,
    PreviewRequest,
    PreviewResponse,
    ReorderResult,
    WidgetCreate,
    WidgetRead,
    WidgetTargetRead,
    WidgetUpdate,
)
from app.schemas.widget_data import DisplayOptions
from app.services.ng.client import app_name
from app.services.scheduler.loop import scheduler
from app.services.scheduler.runner import run_widget
from app.widgets import template
from app.widgets.renderer import render

log = logging.getLogger(__name__)
router = APIRouter(tags=["widgets"])


def _read(widget: Widget) -> WidgetRead:
    return WidgetRead(
        id=widget.id,
        name=widget.name,
        connector_id=widget.connector_id,
        targets=[
            WidgetTargetRead(
                device_id=target.device_id,
                status=target.status,
                last_error=target.last_error,
                last_error_code=target.last_error_code,
                last_pushed_at=target.last_pushed_at,
            )
            for target in sorted(widget.targets, key=lambda t: t.device_id)
        ],
        widget_type=widget.widget_type,
        config=widget.config or {},
        # Validated, not the raw stored dict: a widget saved before an option
        # existed would otherwise come back without it, and the form would
        # render a checkbox with no state. Every new option gets its default
        # filled in on read.
        display=DisplayOptions.model_validate(widget.display or {}).model_dump(),
        refresh_seconds=widget.refresh_seconds,
        enabled=widget.enabled,
        position=widget.position,
        status=widget.status,
        last_success=widget.last_success,
        last_error=widget.last_error,
        last_error_code=widget.last_error_code,
        app_name=app_name(widget.id),
        last_icon=widget.last_icon,
    )


def get_widget(session: SessionDep, widget_id: Annotated[int, Path()]) -> Widget:
    widget = session.get(Widget, widget_id)
    if widget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget not found.")
    return widget


WidgetDep = Annotated[Widget, Depends(get_widget)]


def _descriptor(widget_type: str) -> WidgetDescriptor:
    descriptor = registry.widget_descriptor(widget_type)
    if descriptor is None:
        raise AwtrixNgError(
            f"Unknown widget type {widget_type!r}.",
            code="widget.unknown_type",
            params={"type": widget_type},
        )
    return descriptor


@router.get("/widget-types", response_model=list[WidgetDescriptor])
def list_widget_types() -> list[WidgetDescriptor]:
    """Every widget every connector offers, with its schema and sample data."""
    return [widget for descriptor in registry.descriptors() for widget in descriptor.widgets]


@router.get("/widgets", response_model=list[WidgetRead])
def list_widgets(session: SessionDep) -> list[WidgetRead]:
    # Rotation order, which is what the list is for.
    widgets = session.exec(select(Widget).order_by(Widget.position, Widget.id)).all()
    return [_read(widget) for widget in widgets]


@router.post("/widgets", response_model=WidgetRead, status_code=status.HTTP_201_CREATED)
def create_widget(payload: WidgetCreate, session: SessionDep) -> WidgetRead:
    _descriptor(payload.widget_type)

    instance = session.get(ConnectorInstance, payload.connector_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found.")
    for device_id in payload.device_ids:
        if session.get(Device, device_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Device {device_id} not found.")

    # "weather.current" only makes sense on a "weather" connector.
    if payload.widget_type.split(".", 1)[0] != instance.type:
        raise AwtrixNgError(
            f"Widget {payload.widget_type!r} does not belong to connector "
            f"type {instance.type!r}.",
            code="widget.wrong_connector",
            params={"widget_type": payload.widget_type, "connector_type": instance.type},
        )

    # New widgets land at the end of the rotation.
    last = session.exec(select(Widget).order_by(Widget.position.desc())).first()

    widget = Widget(
        name=payload.name,
        connector_id=payload.connector_id,
        position=(last.position + 1) if last else 0,
        widget_type=payload.widget_type,
        config=payload.config,
        display=payload.display.model_dump(),
        refresh_seconds=payload.refresh_seconds,
        enabled=payload.enabled,
    )
    session.add(widget)
    session.commit()
    session.refresh(widget)

    for device_id in dict.fromkeys(payload.device_ids):
        session.add(WidgetTarget(widget_id=widget.id, device_id=device_id))
    session.commit()
    session.refresh(widget)
    scheduler.run_now(widget.id)
    log.info("widget %s created (%s)", widget.name, widget.widget_type)
    return _read(widget)


@router.get("/widgets/{widget_id}", response_model=WidgetRead)
def get_one(widget: WidgetDep) -> WidgetRead:
    return _read(widget)


@router.patch("/widgets/{widget_id}", response_model=WidgetRead)
def update_widget(payload: WidgetUpdate, widget: WidgetDep, session: SessionDep) -> WidgetRead:
    data = payload.model_dump(exclude_unset=True)
    if "display" in data and data["display"] is not None:
        data["display"] = payload.display.model_dump()

    device_ids = data.pop("device_ids", None)

    # Both leave an app behind on a matrix that no longer owns it: disabling
    # the widget, and dropping a display from its targets. Reconciling right
    # away clears it instead of waiting two minutes for the scheduled pass.
    leaves_an_app_behind = data.get("enabled") is False
    if device_ids is not None:
        wanted = set(device_ids)
        current = set(widget.device_ids)
        if current - wanted:
            leaves_an_app_behind = True
        for device_id in wanted - current:
            if session.get(Device, device_id) is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"Device {device_id} not found."
                )
            session.add(WidgetTarget(widget_id=widget.id, device_id=device_id))
        for target in list(widget.targets):
            if target.device_id not in wanted:
                session.delete(target)

    for key, value in data.items():
        setattr(widget, key, value)
    widget.updated_at = utcnow()
    session.add(widget)
    session.commit()
    session.refresh(widget)

    if leaves_an_app_behind:
        scheduler.reconcile_soon()
    # Edits should show on the matrix now, not at the next interval.
    scheduler.run_now(widget.id)
    return _read(widget)


@router.delete("/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(widget: WidgetDep, session: SessionDep) -> None:
    """Removes the Custom App from the device as well.

    Skipping this would leave an orphan app on the matrix that awtrixng-mgr no
    longer knows about.
    """
    for device_id in widget.device_ids:
        device = session.get(Device, device_id)
        if device is None:
            continue
        client = client_for(device)
        try:
            await client.delete_app(app_name(widget.id))
        except AwtrixNgError as exc:
            # An offline display must not block the deletion; the reconciler
            # clears the orphan when it comes back.
            log.warning(
                "could not remove %s from device %s: %s", widget.name, device_id, exc.message
            )
        finally:
            await client.aclose()

    scheduler.forget(widget.id)
    session.delete(widget)
    session.commit()
    log.info("widget %s deleted", widget.name)


@router.post("/widgets/preview", response_model=PreviewResponse)
async def preview(payload: PreviewRequest, session: SessionDep) -> PreviewResponse:
    """Render a widget without saving it — the heart of the builder (§11).

    Falls back to the widget's sample data when no connector is given or when
    the live call fails, so editing never stalls on an unreachable service.
    """
    descriptor = _descriptor(payload.widget_type)
    owner = registry.owner(payload.widget_type)
    # Not descriptor.sample_data: that one froze its prose in English when the
    # module was imported.
    data = (
        owner.localised_sample(payload.widget_type)
        if owner
        else descriptor.sample_data
    )
    sample = True
    warning = warning_code = None

    if payload.connector_id is not None:
        instance = session.get(ConnectorInstance, payload.connector_id)
        if instance is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found.")
        connector = factory.build(instance, session)
        try:
            data = await connector.fetch(payload.widget_type, payload.config)
            sample = False
        except AwtrixNgError as exc:
            warning, warning_code = exc.message, exc.code
        finally:
            await connector.aclose()

    rendered = render(data, payload.display)
    return PreviewResponse(
        payload=rendered.to_json() if rendered else None,
        text=template.render(payload.display.text, data.values),
        data=data,
        sample=sample,
        warning=warning,
        warning_code=warning_code,
    )


@router.post("/widgets/{widget_id}/refresh", response_model=WidgetRead)
async def refresh_widget(widget: WidgetDep, session: SessionDep) -> WidgetRead:
    """Collect and push right now, on every display, bypassing the schedule."""
    instance = session.get(ConnectorInstance, widget.connector_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found.")

    clients: dict[int, object] = {}
    for device_id in widget.device_ids:
        device = session.get(Device, device_id)
        if device is not None:
            clients[device_id] = client_for(device)

    connector = factory.build(instance, session)
    try:
        outcome = await run_widget(widget, connector, clients, scheduler.cache)
    finally:
        await connector.aclose()
        for client in clients.values():
            await client.aclose()

    if outcome.collected:
        widget.status = HealthStatus.HEALTHY
        widget.last_success = utcnow()
        widget.last_error = widget.last_error_code = None
        widget.consecutive_failures = 0
    else:
        widget.consecutive_failures += 1
        widget.status = HealthStatus.ERROR
        if outcome.error is not None:
            widget.last_error = outcome.error.message
            widget.last_error_code = outcome.error.code

    for result in outcome.targets:
        target = session.get(WidgetTarget, (widget.id, result.device_id))
        if target is None:
            continue
        if result.ok:
            target.status = HealthStatus.HEALTHY
            target.last_error = target.last_error_code = None
            target.consecutive_failures = 0
            if not result.removed:
                target.last_pushed_at = utcnow()
        else:
            target.consecutive_failures += 1
            target.status = HealthStatus.ERROR
            if result.error is not None:
                target.last_error = result.error.message
                target.last_error_code = result.error.code
        session.add(target)

    widget.updated_at = utcnow()
    session.add(widget)
    session.commit()
    session.refresh(widget)
    return _read(widget)


@router.post("/widgets/{widget_id}/push", response_model=WidgetRead)
async def push_widget(widget: WidgetDep, session: SessionDep) -> WidgetRead:
    """Alias of refresh, named after the "Send Preview to AWTRIX" button."""
    return await refresh_widget(widget, session)


@router.post("/widgets/order", response_model=list[WidgetRead])
def set_order(payload: OrderRequest, session: SessionDep) -> list[WidgetRead]:
    """Set the rotation order.

    Cheap: it only writes positions. The displays keep their current order
    until POST /api/devices/{id}/reorder is called, because rebuilding a
    rotation means blanking it for a few seconds.
    """
    widgets = {
        widget.id: widget for widget in session.exec(select(Widget)).all()
    }
    unknown = [wid for wid in payload.widget_ids if wid not in widgets]
    if unknown:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown widgets: {unknown}")

    for position, widget_id in enumerate(payload.widget_ids):
        widget = widgets[widget_id]
        widget.position = position
        widget.updated_at = utcnow()
        session.add(widget)
    session.commit()

    ordered = session.exec(select(Widget).order_by(Widget.position, Widget.id)).all()
    return [_read(widget) for widget in ordered]


@router.post("/devices/{device_id}/reorder", response_model=ReorderResult)
async def reorder_device(device: DeviceDep) -> ReorderResult:
    """Rebuild this display's rotation in position order.

    AWTRIX keeps an app where it first landed, and its `pos` key is
    inoperative on v0.98 (measured), so every managed app is removed and
    republished. The matrix shows only its native apps for a few seconds —
    which is why this is an explicit action and not something the scheduler
    decides to do.
    """
    pushed = await scheduler.reorder(device.id)
    return ReorderResult(ok=True, pushed=pushed)
