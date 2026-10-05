"""The connector contract.

A connector collects data. It knows nothing about AWTRIX: not the matrix, not
the JSON keys, not the colours (§32.9, §32.10). Everything it returns goes
through `WidgetData`, which the renderer alone turns into a payload.

Holding this line is what makes adding a connector a local change: no core
file, and no frontend file either, since the forms are generated from
`FormField`.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field

from app.core.http import build_client
from app.schemas.fields import FormField, Option, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData


class ConnectorTestResult(BaseModel):
    """Outcome of "Test connection". Same shape as the device one: an English
    message plus a stable code the UI translates (ADR-012)."""

    ok: bool
    message: str
    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    #: Anything worth showing after a successful test, e.g. a server version.
    details: dict[str, Any] = Field(default_factory=dict)


class WidgetDescriptor(BaseModel):
    """One widget type a connector offers."""

    type: str
    name: str
    description: str
    fields: list[FormField] = Field(default_factory=list)
    #: Documents the keys of WidgetData.values for the template editor.
    variables: list[Variable] = Field(default_factory=list)
    default_display: DisplayOptions = Field(default_factory=DisplayOptions)
    #: Lets the Widget Builder render a preview before any service is
    #: reachable, and lets the renderer be tested without a network.
    sample_data: WidgetData = Field(default_factory=WidgetData)
    default_refresh: int = 60


class ConnectorDescriptor(BaseModel):
    id: str
    name: str
    description: str
    #: Short generic word for the UI icon. Never a brand asset (prior-art §5).
    icon: str = "plug"
    config_schema: list[FormField] = Field(default_factory=list)
    widgets: list[WidgetDescriptor] = Field(default_factory=list)
    #: False for services like Open-Meteo that need no account at all.
    requires_credentials: bool = True

    def widget(self, widget_type: str) -> WidgetDescriptor | None:
        return next((w for w in self.widgets if w.type == widget_type), None)


class Connector(ABC):
    """Base class. One instance per configured service."""

    descriptor: ClassVar[ConnectorDescriptor]

    def __init__(self, config: dict[str, Any], secrets: dict[str, str]) -> None:
        #: The **connector** configuration: the service and how to reach it.
        #: Everywhere below, a `config` argument is the **widget** one instead
        #: — what this particular widget asks of the service. Confusing the two
        #: is easy and silent, so the distinction is stated here once.
        self.config = config
        self.secrets = secrets
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Shared HTTP client, with the outbound guardrails of ADR-009."""
        if self._client is None:
            self._client = build_client(verify=bool(self.config.get("verify_tls", True)))
        return self._client

    @abstractmethod
    async def test_connection(self) -> ConnectorTestResult:
        """Must be side-effect free and return something a human can act on."""

    async def discover(
        self, source: str, query: str | None, context: dict[str, Any]
    ) -> list[Option]:
        """Feed a remote_select field. Optional: not every connector browses."""
        return []

    # -- Collect / project ----------------------------------------------------
    #
    # Fetching is split in two so the cache can work at the level that matters:
    # the *upstream request*. Caching a finished WidgetData would be wrong —
    # three Tautulli widgets share one `get_activity` call but each needs
    # different values out of it.
    #
    #   request_key()  identifies the upstream call, and its TTL
    #   collect()      performs it — the only part that touches the network
    #   project()      maps the raw payload to one widget's data, and is pure

    @classmethod
    def localised_sample(cls, widget_type: str) -> "WidgetData":
        """The widget's sample data, in the display language.

        Descriptors are class attributes, built when the module is imported,
        so any prose in them is frozen — and frozen in English. A preview must
        show the words the matrix will show, so a connector whose sample
        carries prose overrides this.
        """
        descriptor = cls.descriptor.widget(widget_type)
        return descriptor.sample_data if descriptor else WidgetData()

    @abstractmethod
    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        """(cache key, TTL in seconds) for the upstream request.

        Widgets that produce the same key share a single call (§17). The key
        must therefore describe the request, never the widget.
        """

    @abstractmethod
    async def collect(self, widget_type: str, config: dict[str, Any]) -> Any:
        """Perform the upstream request. Its result is what gets cached."""

    @abstractmethod
    def project(
        self, widget_type: str, config: dict[str, Any], raw: Any
    ) -> WidgetData:
        """Map an upstream payload to one widget's data. Must stay pure: it is
        what makes parsing testable against frozen fixtures (§23)."""

    async def fetch(self, widget_type: str, config: dict[str, Any]) -> WidgetData:
        """Collect then project, bypassing the cache.

        Used for previews and manual refreshes. The scheduler calls collect()
        and project() separately so it can share the collection.
        """
        return self.project(widget_type, config, await self.collect(widget_type, config))

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
