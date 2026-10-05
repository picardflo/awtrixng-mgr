"""Connector catalogue.

Registration is by decorator, so adding a connector means adding a module and
importing it below — no core file grows a branch.
"""

from app.connectors.base import Connector, ConnectorDescriptor

_REGISTRY: dict[str, type[Connector]] = {}


def register(connector: type[Connector]) -> type[Connector]:
    identifier = connector.descriptor.id
    if identifier in _REGISTRY:
        raise ValueError(f"connector {identifier!r} is already registered")
    _REGISTRY[identifier] = connector
    return connector


def get(identifier: str) -> type[Connector] | None:
    return _REGISTRY.get(identifier)


def owner(widget_type: str) -> type[Connector] | None:
    """The connector a widget type belongs to, e.g. "weather.current"."""
    return _REGISTRY.get(widget_type.split(".", 1)[0])


def descriptors() -> list[ConnectorDescriptor]:
    return [connector.descriptor for connector in _REGISTRY.values()]


def widget_descriptor(widget_type: str):
    """Look a widget type up across every connector, e.g. "weather.current"."""
    connector_id = widget_type.split(".", 1)[0]
    connector = _REGISTRY.get(connector_id)
    return connector.descriptor.widget(widget_type) if connector else None


def load_all() -> None:
    """Import every connector module so the decorators run.

    Called once at startup. This is the only place that lists them.
    """
    from app.connectors import fuel, moon, school, weather  # noqa: F401
