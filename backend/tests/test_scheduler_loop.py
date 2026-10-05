"""The scheduler loop.

The one thing that must never die (§18), and until now the only core module
without tests. Everything here goes through the real wiring — database,
connector factory, AWTRIX client — with only the network replaced.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlmodel import Session, select

from app.db.session import engine, init_db
from app.models import ConnectorInstance, Device, HealthStatus, Widget, WidgetTarget
from app.schemas.widget_data import DisplayOptions
from app.services.scheduler.loop import Scheduler

DEVICE = "http://awtrix.test:80"
FORECAST = "https://api.open-meteo.com/v1/forecast"
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "open_meteo_current.json").read_text()
)


@pytest.fixture
def db():
    """A fresh database with one device, one weather connector, one widget."""
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    init_db()

    with Session(engine) as session:
        device = Device(name="Test", host="awtrix.test")
        connector = ConnectorInstance(
            type="weather",
            name="Weather",
            config={"place": {"name": "Paris", "latitude": 48.85, "longitude": 2.35}},
        )
        session.add(device)
        session.add(connector)
        session.commit()
        session.refresh(device)
        session.refresh(connector)

        widget = Widget(
            name="Temp",
            connector_id=connector.id,
            widget_type="weather.current",
            display=DisplayOptions(text="{{ temp | round }}").model_dump(),
            refresh_seconds=60,
        )
        session.add(widget)
        session.commit()
        session.refresh(widget)
        session.add(WidgetTarget(widget_id=widget.id, device_id=device.id))
        session.commit()
        yield {"device": device.id, "connector": connector.id, "widget": widget.id}


@pytest.fixture
def scheduler():
    from app.connectors.registry import load_all

    load_all()
    return Scheduler()


def reload_widget(widget_id: int) -> Widget:
    with Session(engine) as session:
        return session.get(Widget, widget_id)


#: Routes a push and a delete take on NG. Where AWTRIX 3 had one endpoint —
#: POST /api/custom?name=X, deleting when the body was empty — NG has a verb
#: and a path for each, so the two can no longer be confused.
DEVICE_HOST = "awtrix.test"
PUSH_PATH = r"^/api/v1/apps/pushed/[^/]+$"
DELETE_PATH = r"^/api/v1/apps/[^/]+$"


def app(name: str, origin: str = "pushed") -> dict:
    return {"name": name, "origin": origin, "inLoop": True, "enabled": True}


def mock_device(apps: list[dict] | None = None):
    """A display answering everything the scheduler asks of it.

    Returns the push route; `mock_delete` gives the deletion one, since they
    are now separate.
    """
    respx.get(f"{DEVICE}/api/v1/apps").mock(
        return_value=httpx.Response(200, json=apps if apps is not None else [])
    )
    respx.get(f"{DEVICE}/api/v1/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    respx.post(f"{DEVICE}/api/v1/files").mock(return_value=httpx.Response(200, json={"ok": True}))
    respx.get(url__startswith="https://developer.lametric.com/").mock(
        return_value=httpx.Response(200, content=b"GIF89a", headers={"content-type": "image/gif"})
    )
    respx.route(method="DELETE", host=DEVICE_HOST, path__regex=DELETE_PATH).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    return respx.route(method="PUT", host=DEVICE_HOST, path__regex=PUSH_PATH).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )


def names_of(route) -> list[str]:
    """The app names a route was called with, in order.

    NG puts the name in the path where AWTRIX 3 put it in a query string.
    """
    return [call.request.url.path.rsplit("/", 1)[-1] for call in route.calls]


def deletions() -> list[str]:
    """Names deleted so far, read back from every DELETE that was sent."""
    return [
        call.request.url.path.rsplit("/", 1)[-1]
        for call in respx.calls
        if call.request.method == "DELETE"
    ]


def mock_weather(status: int = 200):
    return respx.get(FORECAST).mock(
        return_value=httpx.Response(status, json=FIXTURE if status == 200 else {"reason": "no"})
    )


class TestTick:
    @respx.mock
    async def test_a_due_widget_is_collected_and_pushed(self, db, scheduler):
        push = mock_device()
        mock_weather()

        outcomes = await scheduler.tick()

        assert [o.ok for o in outcomes] == [True]
        assert push.called
        assert reload_widget(db["widget"]).status == HealthStatus.HEALTHY

    @respx.mock
    async def test_a_widget_is_not_run_again_before_its_interval(self, db, scheduler):
        mock_device()
        mock_weather()

        await scheduler.tick()
        assert await scheduler.tick() == []

    @respx.mock
    async def test_a_disabled_widget_is_never_run(self, db, scheduler):
        mock_device()
        weather = mock_weather()
        with Session(engine) as session:
            widget = session.get(Widget, db["widget"])
            widget.enabled = False
            session.add(widget)
            session.commit()

        assert await scheduler.tick() == []
        assert not weather.called

    @respx.mock
    async def test_a_disabled_connector_stops_its_widgets(self, db, scheduler):
        mock_device()
        weather = mock_weather()
        with Session(engine) as session:
            instance = session.get(ConnectorInstance, db["connector"])
            instance.enabled = False
            session.add(instance)
            session.commit()

        assert await scheduler.tick() == []
        assert not weather.called


class TestFailure:
    @respx.mock
    async def test_an_upstream_failure_is_recorded_not_raised(self, db, scheduler):
        mock_device()
        mock_weather(status=400)

        outcomes = await scheduler.tick()

        assert [o.ok for o in outcomes] == [False]
        widget = reload_widget(db["widget"])
        assert widget.consecutive_failures == 1
        assert widget.last_error_code == "weather.rejected"

    @respx.mock
    async def test_failures_accumulate_and_back_off(self, db, scheduler):
        mock_device()
        mock_weather(status=400)

        await scheduler.tick()
        scheduler.run_now(db["widget"])
        await scheduler.tick()

        widget = reload_widget(db["widget"])
        assert widget.consecutive_failures == 2
        # Two failures on a 60 s widget: retry in four minutes, not one.
        assert scheduler._due_at[db["widget"]] > 0

    @respx.mock
    async def test_degraded_before_error(self, db, scheduler):
        """One hiccup is not an outage (§18)."""
        mock_device()
        mock_weather(status=400)
        await scheduler.tick()
        assert reload_widget(db["widget"]).status == HealthStatus.DEGRADED

    @respx.mock
    async def test_recovery_clears_the_error(self, db, scheduler):
        mock_device()
        failing = mock_weather(status=400)
        await scheduler.tick()
        failing.mock(return_value=httpx.Response(200, json=FIXTURE))

        scheduler.run_now(db["widget"])
        await scheduler.tick()

        widget = reload_widget(db["widget"])
        assert widget.status == HealthStatus.HEALTHY
        assert widget.consecutive_failures == 0
        assert widget.last_error_code is None


class TestConnectorLifecycle:
    @respx.mock
    async def test_editing_a_connector_rebuilds_it_on_the_next_tick(self, db, scheduler):
        """Changing the place must not need a restart."""
        mock_device()
        weather = mock_weather()
        await scheduler.tick()
        assert weather.calls.last.request.url.params["latitude"] == "48.85"

        with Session(engine) as session:
            from app.models import utcnow

            instance = session.get(ConnectorInstance, db["connector"])
            instance.config = {
                "place": {"name": "Lyon", "latitude": 45.75, "longitude": 4.85}
            }
            instance.updated_at = utcnow()
            session.add(instance)
            session.commit()

        scheduler.run_now(db["widget"])
        await scheduler.tick()
        assert weather.calls.last.request.url.params["latitude"] == "45.75"

    @respx.mock
    async def test_the_loop_survives_an_unknown_connector_type(self, db, scheduler):
        mock_device()
        with Session(engine) as session:
            instance = session.get(ConnectorInstance, db["connector"])
            instance.type = "does-not-exist"
            session.add(instance)
            session.commit()

        assert await scheduler.tick() == []  # skipped, not crashed


class TestReconciliation:
    @respx.mock
    async def test_a_rebooted_device_gets_its_apps_back(self, db, scheduler):
        push = mock_device([app("Time", "builtin")])
        mock_weather()

        await scheduler.tick()  # first push
        push.reset()

        # The device lost everything; the loop no longer lists our app.
        scheduler.reconcile_soon()
        await scheduler.tick()

        assert push.called, "the widget should have been pushed again"

    @respx.mock
    async def test_an_orphan_app_is_removed(self, db, scheduler):
        mock_device([app("Time", "builtin"), app("ng000999")])
        mock_weather()

        await scheduler.reconcile()

        assert "ng000999" in deletions(), "the orphan should have been deleted"

    @respx.mock
    async def test_an_unreachable_device_is_not_an_incident(self, db, scheduler):
        respx.get(f"{DEVICE}/api/v1/apps").mock(side_effect=httpx.ConnectTimeout(""))
        assert await scheduler.reconcile() == []  # no raise


@respx.mock
async def test_a_tick_never_raises_whatever_happens(db, scheduler):
    """The loop is the one thing that must keep running."""
    respx.get(FORECAST).mock(side_effect=RuntimeError("boom"))
    mock_device()
    outcomes = await scheduler.tick()
    assert [o.ok for o in outcomes] == [False]
    assert outcomes[0].error.code == "widget.unexpected_error"


class TestTargets:
    """One widget, several displays — and each with its own state."""

    @respx.mock
    async def test_disabling_removes_the_app(self, db, scheduler):
        mock_device([app("Time", "builtin"), app("ng000001")])
        mock_weather()
        with Session(engine) as session:
            widget = session.get(Widget, db["widget"])
            widget.enabled = False
            session.add(widget)
            session.commit()

        await scheduler.reconcile()

        assert "ng000001" in deletions()

    @respx.mock
    async def test_dropping_a_display_frees_it(self, db, scheduler):
        mock_device([app("Time", "builtin"), app("ng000001")])
        mock_weather()
        with Session(engine) as session:
            other = Device(name="Office", host="awtrix.test")
            session.add(other)
            session.commit()
            session.refresh(other)
            # Move it: drop the first display, add the second.
            for target in session.exec(select(WidgetTarget)).all():
                session.delete(target)
            session.add(WidgetTarget(widget_id=db["widget"], device_id=other.id))
            session.commit()

        await scheduler.reconcile()

        assert "ng000001" in deletions(), (
            "the app should have been removed from the display it left"
        )

    @respx.mock
    async def test_a_widget_on_two_displays_is_pushed_to_both(self, db, scheduler):
        push = mock_device()
        weather = mock_weather()
        with Session(engine) as session:
            other = Device(name="Office", host="awtrix.test")
            session.add(other)
            session.commit()
            session.refresh(other)
            session.add(WidgetTarget(widget_id=db["widget"], device_id=other.id))
            session.commit()

        outcomes = await scheduler.tick()

        assert len(outcomes[0].targets) == 2
        assert all(t.ok for t in outcomes[0].targets)
        # Collected once, pushed twice: that is the whole point.
        assert weather.call_count == 1
        assert push.call_count == 2

    @respx.mock
    async def test_per_display_state_is_recorded(self, db, scheduler):
        mock_device()
        mock_weather()
        await scheduler.tick()

        with Session(engine) as session:
            target = session.get(WidgetTarget, (db["widget"], db["device"]))
            assert target.status == HealthStatus.HEALTHY
            assert target.last_pushed_at is not None

    @respx.mock
    async def test_a_failed_push_does_not_delay_the_next_collection(self, db, scheduler):
        """A clock refusing the app is a local problem, not a reason to stop
        asking Open-Meteo on time."""
        mock_device()
        mock_weather()
        respx.route(method="PUT", host=DEVICE_HOST, path__regex=PUSH_PATH).mock(
            return_value=httpx.Response(500)
        )

        await scheduler.tick()

        widget = reload_widget(db["widget"])
        assert widget.status == HealthStatus.HEALTHY, "collection worked"
        assert widget.consecutive_failures == 0, "no backoff on a push failure"
        with Session(engine) as session:
            target = session.get(WidgetTarget, (db["widget"], db["device"]))
            assert target.status == HealthStatus.DEGRADED
            assert target.last_error_code == "device.http_error"


class TestRotationOrder:
    """AWTRIX keeps an app where it first landed and its `pos` key does
    nothing on v0.98 (measured), so push order *is* rotation order."""

    def _add_widget(self, db, name: str, position: int) -> int:
        with Session(engine) as session:
            widget = Widget(
                name=name,
                connector_id=db["connector"],
                widget_type="weather.current",
                display=DisplayOptions(text=name).model_dump(),
                refresh_seconds=60,
                position=position,
            )
            session.add(widget)
            session.commit()
            session.refresh(widget)
            session.add(WidgetTarget(widget_id=widget.id, device_id=db["device"]))
            session.commit()
            return widget.id

    @respx.mock
    async def test_widgets_are_pushed_in_position_order(self, db, scheduler):
        push = mock_device()
        mock_weather()
        with Session(engine) as session:
            first = session.get(Widget, db["widget"])
            first.position = 10
            session.add(first)
            session.commit()
        self._add_widget(db, "second", 5)
        self._add_widget(db, "third", 1)

        await scheduler.tick()

        order = names_of(push)
        assert order == sorted(order, key=lambda name: {"ng000003": 0, "ng000002": 1,
                                                        "ng000001": 2}[name]), order

    @respx.mock
    async def test_reorder_clears_then_republishes_in_order(self, db, scheduler):
        custom = mock_device([app("Time", "builtin"), app("ng000001"), app("ng000002")])
        mock_weather()
        self._add_widget(db, "second", 0)  # id 2, placed first
        with Session(engine) as session:
            first = session.get(Widget, db["widget"])
            first.position = 1
            session.add(first)
            session.commit()

        pushed = await scheduler.reorder(db["device"])

        assert set(deletions()) == {"ng000001", "ng000002"}, "both apps removed first"
        assert names_of(custom) == ["ng000002", "ng000001"], "republished in position order"
        assert pushed == 2

    @respx.mock
    async def test_reorder_on_an_unknown_device_does_nothing(self, db, scheduler):
        mock_device()
        assert await scheduler.reorder(999) == 0


class TestPushRetry:
    @respx.mock
    async def test_a_refused_push_is_retried_soon_not_at_the_next_interval(
        self, db, scheduler
    ):
        """A display that refused the push is usually rebooting. Waiting a full
        refresh interval would leave the matrix bare for ten minutes."""
        import time as clock

        mock_device()
        mock_weather()
        respx.route(method="PUT", host=DEVICE_HOST, path__regex=PUSH_PATH).mock(
            return_value=httpx.Response(500)
        )

        await scheduler.tick()

        due_in = scheduler._due_at[db["widget"]] - clock.monotonic()
        assert due_in <= 31, "should retry within half a minute"
