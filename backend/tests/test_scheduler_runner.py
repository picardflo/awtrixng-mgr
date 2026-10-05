"""Running a widget end to end, with the network replaced by fakes."""

import pytest

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.core.errors import ConnectorError
from app.models import Widget, WidgetTarget
from app.schemas.widget_data import DisplayOptions, WidgetData
from app.services.scheduler.cache import SourceCache
from app.services.scheduler.runner import backoff, run_widget


class FakeConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="fake",
        name="Fake",
        description="test double",
        widgets=[WidgetDescriptor(type="fake.value", name="Value", description="")],
    )

    def __init__(self, payload=None, error=None):
        super().__init__({}, {})
        self.payload = payload if payload is not None else {"v": 42}
        self.error = error
        self.collect_calls = 0

    async def test_connection(self):
        return ConnectorTestResult(ok=True, message="ok", code="fake.ok")

    def request_key(self, widget_type, config):
        return "fake:shared", 60

    async def collect(self, widget_type, config):
        self.collect_calls += 1
        if self.error:
            raise self.error
        return self.payload

    def project(self, widget_type, config, raw):
        if raw.get("nothing"):
            return WidgetData(status="empty")
        return WidgetData(values={"value": raw["v"]})


class FakeClient:
    def __init__(self):
        self.pushed: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    async def ensure_icon(self, icon):
        return bool(icon)

    async def push_app(self, name, payload):
        self.pushed.append((name, payload.to_json()))

    async def delete_app(self, name):
        self.deleted.append(name)


def widget(widget_id: int = 12, *, devices: tuple[int, ...] = (1,), **kwargs) -> Widget:
    return Widget(
        **{
            "id": widget_id,
            "name": "Test",
            "connector_id": 1,
            "widget_type": "fake.value",
            "display": DisplayOptions(text="{{ value }}").model_dump(),
            "refresh_seconds": 60,
            "targets": [
                WidgetTarget(widget_id=widget_id, device_id=d) for d in devices
            ],
            **kwargs,
        }
    )


async def test_pushes_a_rendered_app():
    client = FakeClient()
    outcome = await run_widget(widget(), FakeConnector(), {1: client}, SourceCache())

    assert outcome.ok
    name, payload = client.pushed[0]
    assert name == "ng000012"  # noms de largeur fixe
    assert payload["text"] == "42"
    assert payload["lifetimeMs"] == 180_000  # three missed refreshes, in ms


async def test_empty_data_deletes_the_app():
    client = FakeClient()
    outcome = await run_widget(
        widget(), FakeConnector(payload={"nothing": True}), {1: client}, SourceCache()
    )

    # "removed" now belongs to the display, not to the widget: the same widget
    # can be removed from one clock and kept on another.
    assert outcome.ok
    assert [t.removed for t in outcome.targets] == [True]
    assert client.deleted == ["ng000012"]
    assert client.pushed == []


async def test_empty_data_can_still_be_displayed():
    client = FakeClient()
    display = DisplayOptions(text="none", hide_when_empty=False).model_dump()
    await run_widget(
        widget(display=display),
        FakeConnector(payload={"nothing": True}),
        {1: client},
        SourceCache(),
    )
    assert client.pushed and not client.deleted


async def test_connector_failure_is_reported_not_raised():
    outcome = await run_widget(
        widget(),
        FakeConnector(error=ConnectorError("upstream down", code="fake.down")),
        {1: FakeClient()},
        SourceCache(),
    )
    assert outcome.ok is False
    assert outcome.error.code == "fake.down"


async def test_unexpected_connector_bug_does_not_escape():
    """A broken connector must not take the scheduler down (§18)."""
    outcome = await run_widget(
        widget(), FakeConnector(error=ZeroDivisionError("oops")), {1: FakeClient()}, SourceCache()
    )
    assert outcome.ok is False
    assert outcome.error.code == "widget.unexpected_error"


async def test_widgets_sharing_a_request_key_collect_once():
    connector, cache, client = FakeConnector(), SourceCache(), FakeClient()
    await run_widget(widget(1), connector, {1: client}, cache)
    await run_widget(widget(2), connector, {1: client}, cache)
    assert connector.collect_calls == 1
    assert [name for name, _ in client.pushed] == ["ng000001", "ng000002"]


class TestBackoff:
    def test_no_failure_keeps_the_normal_interval(self):
        assert backoff(60, 0) == 60

    def test_doubles_per_failure(self):
        assert backoff(60, 1) == 120
        assert backoff(60, 2) == 240

    def test_is_capped(self):
        assert backoff(600, 10) == 900

    @pytest.mark.parametrize("failures", range(0, 12))
    def test_never_exceeds_the_cap(self, failures):
        assert backoff(300, failures) <= 900


async def test_one_widget_reaches_several_displays():
    """Collected once, rendered once, pushed to each clock."""
    connector = FakeConnector()
    salon, bureau = FakeClient(), FakeClient()

    outcome = await run_widget(
        widget(7, devices=(1, 2)), connector, {1: salon, 2: bureau}, SourceCache()
    )

    assert connector.collect_calls == 1
    assert [name for name, _ in salon.pushed] == ["ng000007"]
    assert [name for name, _ in bureau.pushed] == ["ng000007"]
    assert outcome.ok


async def test_one_unreachable_display_does_not_sink_the_others():
    """The reason per-display state exists at all."""

    class Broken(FakeClient):
        async def push_app(self, name, payload):
            raise ConnectorError("unplugged", code="device.unreachable")

    ok_client = FakeClient()
    outcome = await run_widget(
        widget(7, devices=(1, 2)), FakeConnector(), {1: ok_client, 2: Broken()}, SourceCache()
    )

    assert outcome.collected is True
    assert ok_client.pushed, "the reachable clock still got its widget"
    results = {t.device_id: t.ok for t in outcome.targets}
    assert results == {1: True, 2: False}
    assert outcome.ok is False


class TestRememberedIcon:
    """The icon a list can show.

    `display["icon"]` is what someone pinned; left empty, the connector picks
    one from the data — a cloud or a sun, the current moon phase. A list that
    only knew the first would show a thumbnail for the widgets whose icon never
    changes and nothing for those where it says the most.
    """

    class Hinting(FakeConnector):
        def project(self, widget_type, config, raw):
            return WidgetData(values={"value": raw["v"]}, hint_icon="12246")

    @pytest.mark.asyncio
    async def test_the_connectors_choice_is_remembered(self):
        outcome = await run_widget(
            widget(display={"text": "{{ value }}", "show_icon": True}),
            self.Hinting(),
            {1: FakeClient()},
            SourceCache(),
        )
        assert outcome.icon == "12246"

    @pytest.mark.asyncio
    async def test_a_chosen_icon_wins_over_the_suggestion(self):
        outcome = await run_widget(
            widget(display={"text": "{{ value }}", "icon": "2536", "show_icon": True}),
            self.Hinting(),
            {1: FakeClient()},
            SourceCache(),
        )
        assert outcome.icon == "2536"

    @pytest.mark.asyncio
    async def test_no_icon_at_all_remembers_nothing(self):
        outcome = await run_widget(
            widget(display={"text": "{{ value }}", "show_icon": False}),
            self.Hinting(),
            {1: FakeClient()},
            SourceCache(),
        )
        assert outcome.icon is None
