"""The AWTRIX itself as a source of data.

A clock is not only a screen: it carries a thermometer, a hygrometer, a light
sensor, a battery and a radio. awtrixng-mgr already reads them for the device
page — this connector turns them into widgets like any other.

What that buys, beyond the native Temperature and Humidity apps: the icon, the
colour and the wording are yours, so an indoor reading can no longer be
mistaken for an outdoor one sitting seven seconds away in the same rotation.
And a clock can display *another* clock's sensors, which the native apps
cannot do.
"""

from typing import Any

import httpx

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.registry import register
from app.core.errors import ConnectorError
from app.schemas.fields import FormField, Option, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData

#: Where the factory parks the resolved display. A connector has no database
#: access of its own — that is what keeps it testable without one.
RESOLVED = "_resolved_device"


class Metric:
    """One reading, and how to present it."""

    def __init__(
        self,
        key: str,
        label: str,
        field: str,
        unit: str,
        icon: int,
        *,
        percentage: bool = False,
    ) -> None:
        self.key = key
        self.label = label
        #: Key in the /api/stats payload.
        self.field = field
        self.unit = unit
        self.icon = icon
        #: Feeds a progress bar, for the readings that are out of 100.
        self.percentage = percentage


#: All verified as animated 8x8 GIFs in the LaMetric gallery.
METRICS: tuple[Metric, ...] = (
    Metric("temperature", "Temperature", "temp", "°C", 2422),
    Metric("humidity", "Humidity", "hum", "%", 2423, percentage=True),
    Metric("battery", "Battery", "bat", "%", 6150, percentage=True),
    Metric("illuminance", "Ambient light", "lux", "lx", 8849),
    Metric("brightness", "Matrix brightness", "bri", "", 8699),
    Metric("signal", "Wi-Fi signal", "wifi_signal", "dBm", 2383),
    Metric("uptime", "Uptime", "uptime", "s", 2437),
)

BY_KEY = {metric.key: metric for metric in METRICS}


#: Four icons drawn as one set — a battery outline filling up, red then amber
#: then green. The thresholds are the colour's own, so the picture and the
#: colour never disagree: an amber figure beside a green battery would be the
#: rain widget's old defect, again.
#:
#: Green covers everything above half, so it is split in two: a battery at
#: 95 % and one at 55 % are both fine, and a glance should still tell them
#: apart. The number says the rest.
BATTERY_ICONS: tuple[tuple[float, int], ...] = (
    (20, 12123),   # Device Battery Low — red
    (50, 12124),   # Device Battery Medium — amber
    (90, 12125),   # Device Battery High — green, part filled
)
BATTERY_FULL = 12126  # Device Battery Full — green, filled


def _icon(metric: Metric, value: float | None) -> str:
    """The icon a reading calls for.

    Only the battery has a ladder: it is the one reading whose *level* is the
    whole message, and a single outline said nothing a glance could use.

    **Charging is not knowable.** `/api/stats` carries `bat` and `bat_raw` and
    nothing else — the firmware publishes no charging flag, checked in its
    source. Inferring one from a rising trend would need samples minutes
    apart, would be wrong whenever the level sat still, and would make the
    icon flicker on the noise of a percentage that moves by one.
    """
    if metric.key != "battery" or not isinstance(value, int | float):
        return str(metric.icon)
    for threshold, icon in BATTERY_ICONS:
        if value < threshold:
            return str(icon)
    return str(BATTERY_FULL)


def _colour(metric: Metric, value: float | None) -> str | None:
    """A colour that carries meaning, not decoration."""
    if value is None:
        return None
    if metric.key == "battery":
        return "#f4526b" if value < 20 else "#f5a524" if value < 50 else "#3ddc84"
    if metric.key == "signal":
        return "#3ddc84" if value >= -55 else "#f5a524" if value >= -70 else "#f4526b"
    if metric.key == "temperature":
        # Same bands as the weather connector, so a temperature always reads
        # the same way whatever produced it.
        from app.connectors.weather import wmo

        return wmo.colour_for_temperature(value)
    return None


@register
class DeviceConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="device",
        name="Display",
        description=(
            "The sensors of one of your AWTRIX displays: temperature, humidity, "
            "ambient light, battery and Wi-Fi signal."
        ),
        icon="gauge",
        requires_credentials=False,
        config_schema=[
            FormField(
                name="device_id",
                label="Display to read",
                type="device",
                required=True,
                help="Its sensors can be shown on any display, including another one.",
            )
        ],
        widgets=[
            WidgetDescriptor(
                type="device.metric",
                name="Reading",
                description="One sensor of the chosen display.",
                fields=[
                    FormField(
                        name="metric",
                        label="Reading",
                        type="select",
                        required=True,
                        default="temperature",
                        options=[
                            Option(value=metric.key, label=metric.label)
                            for metric in METRICS
                        ],
                    )
                ],
                variables=[
                    Variable(name="value", label="The reading", example="21"),
                    Variable(name="unit", label="Its unit", example="°C"),
                    # Uptime is in seconds: {{ value | duration }} makes it readable.
                    Variable(name="metric", label="Which reading", example="temperature"),
                    Variable(name="device", label="Display name", example="Office"),
                ],
                default_display=DisplayOptions(text="{{ value }}{{ unit }}", duration=8),
                default_refresh=60,
                sample_data=WidgetData(
                    values={
                        "value": 21,
                        "unit": "°C",
                        "metric": "temperature",
                        "device": "Office",
                    },
                    hint_icon=str(METRICS[0].icon),
                    hint_color="#3ddc84",
                ),
            )
        ],
    )

    # -- Collection -----------------------------------------------------------

    def _target(self) -> dict[str, Any]:
        target = self.config.get(RESOLVED)
        if not isinstance(target, dict) or not target.get("host"):
            raise ConnectorError(
                "Pick a display for this connector.", code="device_connector.no_display"
            )
        return target

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        # Every reading of the same display comes from one /api/stats call.
        target = self._target()
        return f"device:{target['host']}:{target.get('port', 80)}", 30

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        target = self._target()
        url = f"http://{target['host']}:{target.get('port', 80)}/api/stats"
        auth = (
            (target["username"], target.get("password") or "")
            if target.get("username")
            else None
        )
        try:
            response = await self.client.get(url, auth=auth)
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"{target['name']} is unreachable: {exc or type(exc).__name__}",
                code="device_connector.unreachable",
                params={"device": target["name"], "reason": str(exc) or type(exc).__name__},
            ) from exc

        if response.status_code == 401:
            raise ConnectorError(
                f"{target['name']} refused the credentials.",
                code="device_connector.auth_failed",
                params={"device": target["name"]},
            )
        if response.status_code >= 400:
            raise ConnectorError(
                f"{target['name']} answered HTTP {response.status_code}.",
                code="device_connector.http_error",
                params={"device": target["name"], "status": response.status_code},
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorError(
                f"{target['name']} returned an unexpected response.",
                code="device_connector.bad_response",
                params={"device": target["name"]},
            ) from exc

    # -- Projection -----------------------------------------------------------

    def project(
        self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]
    ) -> WidgetData:
        metric = BY_KEY.get(str(config.get("metric") or "temperature"), METRICS[0])
        value = raw.get(metric.field)
        name = (self.config.get(RESOLVED) or {}).get("name", "")

        return WidgetData(
            values={
                "value": value,
                "unit": metric.unit,
                "metric": metric.key,
                "device": name,
            },
            # A missing reading is not a failure: not every AWTRIX has every
            # sensor, and the widget can simply hide.
            status="ok" if value is not None else "empty",
            progress=(
                int(max(0, min(100, value)))
                if metric.percentage and isinstance(value, int | float)
                else None
            ),
            hint_icon=_icon(metric, value if isinstance(value, int | float) else None),
            hint_color=_colour(metric, value if isinstance(value, int | float) else None),
        )

    # -- Test -----------------------------------------------------------------

    async def test_connection(self) -> ConnectorTestResult:
        target = self._target()
        stats = await self.collect("device.metric", {})
        readings = {
            metric.label: stats.get(metric.field)
            for metric in METRICS
            if stats.get(metric.field) is not None
        }
        return ConnectorTestResult(
            ok=True,
            message=(
                f"{target['name']} answered: {stats.get('temp')} °C, "
                f"battery {stats.get('bat')} %."
            ),
            code="device_connector.connected",
            params={
                "device": target["name"],
                "temperature": stats.get("temp"),
                "battery": stats.get("bat"),
            },
            details={"firmware": stats.get("version"), "readings": readings},
        )
