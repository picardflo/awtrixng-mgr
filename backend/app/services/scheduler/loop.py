"""The central scheduler.

One asyncio loop, no cron, no Celery, no Redis (§25). Widgets carry their own
due time in memory; on restart everything simply runs at once, which is the
behaviour you want after a deployment anyway.

Database access is synchronous. At this scale a SQLite query costs microseconds
and never yields, so it cannot interleave with the awaits around it — adding an
async driver would be complexity without a problem to solve.
"""

import asyncio
import logging
import time
from datetime import datetime

from sqlmodel import Session, select

from app.connectors import factory
from app.connectors.base import Connector
from app.core.crypto import decrypt
from app.core.errors import AwtrixNgError
from app.db.session import engine
from app.models import (
    ConnectorInstance,
    Device,
    HealthStatus,
    Reminder,
    Widget,
    WidgetTarget,
    utcnow,
)
from app.services.ng import quiet
from app.services.ng.client import NgClient
from app.services.ng.transport import HttpTransport
from app.services.scheduler import reminders as reminder_pass
from app.services.scheduler.cache import SourceCache
from app.services.scheduler.reconcile import Reconciliation
from app.services.scheduler.reconcile import reconcile as reconcile_device
from app.services.scheduler.runner import WidgetOutcome, backoff, run_widget

log = logging.getLogger(__name__)

#: How often the loop wakes up. Widget intervals are multiples of this in
#: practice; a finer tick would only burn CPU.
TICK_SECONDS = 1.0

#: Widgets are handled one after another, in position order, because that is
#: the *only* control over the rotation: the loop order is the order apps were
#: first pushed, and AWTRIX's `pos` key does nothing on v0.98 (measured).
#:
#: Running them concurrently, as an earlier version did, made the rotation
#: order arbitrary. Collecting is cached and shared, so serialising costs one
#: upstream call for a whole family of widgets, not one each.

#: How often the device's app loop is compared with the database. Short enough
#: that a reboot is repaired in a couple of minutes rather than at the next
#: refresh — which is ten minutes for a weather widget — and light enough that
#: it costs one /api/loop per device.
RECONCILE_SECONDS = 120


#: A widget whose data was collected but could not be pushed is retried sooner
#: than its own interval: the display is usually rebooting or briefly away.
RETRY_AFTER_PUSH_FAILURE = 30


class Scheduler:
    def __init__(self) -> None:
        self.cache = SourceCache()
        self._due_at: dict[int, float] = {}
        self._connectors: dict[tuple, Connector] = {}
        self._reconcile_at = 0.0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # -- Lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="awtrixng-mgr-scheduler")
        log.info("scheduler started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for connector in self._connectors.values():
            await connector.aclose()
        self._connectors.clear()
        log.info("scheduler stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                # The loop is the one thing that must never die (§18).
                log.exception("scheduler tick failed")
            await asyncio.sleep(TICK_SECONDS)

    # -- One pass -------------------------------------------------------------

    async def tick(self) -> list[WidgetOutcome]:
        """Run every widget that is due. Returns the outcomes, for tests."""
        if time.monotonic() >= self._reconcile_at:
            self._reconcile_at = time.monotonic() + RECONCILE_SECONDS
            await self.reconcile()


        # Checked every tick: a reminder set for 07:30 should ring at 07:30,
        # not at the next widget refresh.
        await self.fire_reminders()

        with Session(engine) as session:
            due = [w for w in self._enabled_widgets(session) if self._is_due(w)]
            if not due:
                return []

            connectors, devices = self._resources(session, due)

        outcomes: list[WidgetOutcome] = []
        for widget in sorted(due, key=lambda w: (w.position, w.id)):
            connector = connectors.get(widget.connector_id)
            if connector is None:
                continue
            # Only the displays this widget targets, and only those reachable
            # in this pass.
            mine = {
                device_id: devices[device_id]
                for device_id in widget.device_ids
                if device_id in devices
            }
            if not mine:
                continue
            outcomes.append(await run_widget(widget, connector, mine, self.cache))

        for client in devices.values():
            await client.aclose()

        # Persisted after the gather, in one place: running a widget stays free
        # of database concerns.
        with Session(engine) as session:
            self._record(session, outcomes)

        return outcomes

    async def fire_reminders(self) -> list[reminder_pass.Fired]:
        """Send any reminder whose moment has come. Never raises."""
        now = reminder_pass.local_now()

        with Session(engine) as session:
            pending: list[tuple[Reminder, datetime]] = []
            for reminder in session.exec(select(Reminder).where(Reminder.enabled)).all():
                moment = reminder_pass.due(reminder, now)
                if moment is not None:
                    pending.append((reminder, moment))

            if not pending:
                return []

            wanted = {d for reminder, _ in pending for d in reminder.device_ids}
            clients = {}
            # Which displays have their quiet window open right now. Read
            # from the schedule rather than from a stored flag, so a window
            # that opened seconds ago already applies — the pass that records
            # it runs only every half-minute.
            dimmed: set[int] = set()
            at = now.time()
            for device_id in wanted:
                device = session.get(Device, device_id)
                if device is None or not device.enabled:
                    continue
                clients[device_id] = self._client_for(device)
                if (
                    device.quiet_hours
                    and device.quiet_from is not None
                    and device.quiet_to is not None
                    and quiet.is_quiet(device.quiet_from, device.quiet_to, at)
                ):
                    dimmed.add(device_id)
            # Read everything needed before the awaits: the session is closed
            # by then.
            plan = [(r.id, r, m, {d: clients[d] for d in r.device_ids if d in clients})
                    for r, m in pending]

        results: list[reminder_pass.Fired] = []
        try:
            for _, reminder, moment, mine in plan:
                if not mine:
                    continue
                # A reminder marked as ringing at night keeps its melody
                # everywhere; the others lose it on the displays that are
                # dimmed, and keep it on the ones that are not.
                silent_on = frozenset() if reminder.rings_at_night else frozenset(dimmed)
                results.append(
                    await reminder_pass.send(reminder, mine, moment, silent_on=silent_on)
                )
        finally:
            for client in clients.values():
                await client.aclose()

        with Session(engine) as session:
            for fired in results:
                stored = session.get(Reminder, fired.reminder_id)
                if stored is not None:
                    stored.last_fired_at = utcnow()
                    stored.updated_at = utcnow()
                    session.add(stored)
            session.commit()

        return results

    def _enabled_widgets(self, session: Session) -> list[Widget]:
        return list(session.exec(select(Widget).where(Widget.enabled)).all())

    def _is_due(self, widget: Widget) -> bool:
        return self._due_at.get(widget.id, 0.0) <= time.monotonic()

    def _resources(
        self, session: Session, widgets: list[Widget]
    ) -> tuple[dict[int, Connector], dict[int, NgClient]]:
        connectors: dict[int, Connector] = {}
        for connector_id in {w.connector_id for w in widgets}:
            instance = session.get(ConnectorInstance, connector_id)
            if instance is None or not instance.enabled:
                continue
            connector = self._connector_for(instance, session)
            if connector is not None:
                connectors[connector_id] = connector

        clients: dict[int, NgClient] = {}
        for device_id in {d for w in widgets for d in w.device_ids}:
            device = session.get(Device, device_id)
            if device is None or not device.enabled:
                continue
            clients[device_id] = self._client_for(device)
        return connectors, clients

    @staticmethod
    def _client_for(device: Device) -> NgClient:
        password = decrypt(device.password_enc) if device.password_enc else None
        return NgClient(
            HttpTransport(
                device.host, device.port, username=device.username, password=password
            )
        )

    def _connector_for(
        self, instance: ConnectorInstance, session: Session | None = None
    ) -> Connector | None:
        """Reuse a live connector, rebuilding it when anything it depends on
        changed — its own configuration, or a display it reads from.

        Editing either in the UI therefore takes effect on the next pass,
        without restarting anything.
        """
        key = factory.fingerprint(instance, session)
        existing = self._connectors.get(key)
        if existing is not None:
            return existing

        for stale_key in [k for k in self._connectors if k[0] == instance.id]:
            asyncio.create_task(self._connectors.pop(stale_key).aclose())
        self.cache.invalidate(f"{instance.type}:")

        try:
            connector = factory.build(instance, session)
        except AwtrixNgError:
            log.error("connector %s has an unknown type %r", instance.name, instance.type)
            return None
        self._connectors[key] = connector
        return connector

    def _record(self, session: Session, outcomes: list[WidgetOutcome]) -> None:
        for outcome in outcomes:
            widget = session.get(Widget, outcome.widget_id)
            if widget is None:
                continue

            if outcome.icon:
                widget.last_icon = outcome.icon
            delay = self._record_collection(widget, outcome)
            self._record_targets(session, outcome)

            widget.updated_at = utcnow()
            session.add(widget)
            self._due_at[widget.id] = time.monotonic() + delay
        session.commit()

    @staticmethod
    def _record_collection(widget: Widget, outcome: WidgetOutcome) -> int:
        """Collection state, and how long before trying again.

        Only a collection failure backs the widget off. A display that refused
        the push is a local problem: re-collecting on schedule is right, and
        the next pass will retry that display.
        """
        if outcome.collected:
            widget.status = HealthStatus.HEALTHY
            widget.last_success = utcnow()
            widget.last_error = None
            widget.last_error_code = None
            widget.consecutive_failures = 0
            if any(not target.ok for target in outcome.targets):
                # A display refused the push — it is rebooting, or unplugged.
                # Waiting a full refresh interval would leave the matrix bare
                # for ten minutes on a weather widget.
                return min(widget.refresh_seconds, RETRY_AFTER_PUSH_FAILURE)
            return widget.refresh_seconds

        widget.consecutive_failures += 1
        widget.status = (
            HealthStatus.DEGRADED if widget.consecutive_failures < 3 else HealthStatus.ERROR
        )
        if outcome.error is not None:
            widget.last_error = outcome.error.message
            widget.last_error_code = outcome.error.code
        return backoff(widget.refresh_seconds, widget.consecutive_failures)

    @staticmethod
    def _record_targets(session: Session, outcome: WidgetOutcome) -> None:
        for result in outcome.targets:
            target = session.get(WidgetTarget, (outcome.widget_id, result.device_id))
            if target is None:
                continue

            if result.ok:
                target.status = HealthStatus.HEALTHY
                target.last_error = None
                target.last_error_code = None
                target.consecutive_failures = 0
                if not result.removed:
                    target.last_pushed_at = utcnow()
            else:
                target.consecutive_failures += 1
                target.status = (
                    HealthStatus.DEGRADED
                    if target.consecutive_failures < 3
                    else HealthStatus.ERROR
                )
                if result.error is not None:
                    target.last_error = result.error.message
                    target.last_error_code = result.error.code
            session.add(target)

    async def reconcile(self) -> list[Reconciliation]:
        """Put every matrix back in line with the database.

        Repairs a rebooted display, clears apps left by a widget deleted,
        disabled or no longer targeting it, and is what gives "disabled" its
        effect.
        """
        with Session(engine) as session:
            widgets = list(session.exec(select(Widget)).all())
            # Every enabled display, not only those a widget still targets: the
            # one that just stopped being targeted is precisely the one holding
            # an app nobody owns.
            devices = list(session.exec(select(Device).where(Device.enabled)).all())
            clients = {device.id: self._client_for(device) for device in devices}

        results: list[Reconciliation] = []
        for device_id, client in clients.items():
            try:
                result = await reconcile_device(device_id, widgets, client)
                results.append(result)
                # Re-pushing needs a connector, so it is left to the normal
                # pass: marking the widget due is enough.
                for widget_id in result.missing:
                    self.run_now(widget_id)
            except AwtrixNgError as exc:
                # An unplugged display is not an incident; the next pass retries.
                log.debug("could not reconcile device %s: %s", device_id, exc.message)
            finally:
                await client.aclose()

        return results

    def run_now(self, widget_id: int) -> None:
        """Make a widget due on the next tick, e.g. after the user edited it."""
        self._due_at[widget_id] = 0.0

    def forget(self, widget_id: int) -> None:
        self._due_at.pop(widget_id, None)

    def refresh_all(self) -> None:
        """Make every widget due on the next tick.

        For a change that alters what widgets *say* rather than what they
        read — the display language. Without it, switching to French does
        nothing visible for up to half an hour on the air quality widgets,
        and looks exactly like a setting that does not work.

        Cheap: the cached upstream responses are still fresh, so this
        re-projects and re-pushes without asking anyone for data again.
        """
        self._due_at.clear()

    def reconcile_soon(self) -> None:
        """Make the next tick reconcile, e.g. after a widget was disabled."""
        self._reconcile_at = 0.0

    async def reorder(self, device_id: int) -> int:
        """Rebuild one display's rotation in position order.

        The only way to reorder: AWTRIX keeps an app where it first landed, and
        its `pos` key is inoperative (measured on v0.98). So every managed app
        is removed and republished in order.

        The matrix shows only its native apps for a few seconds. That is
        unavoidable, and why this is an explicit action rather than something
        the scheduler does on its own.
        """
        with Session(engine) as session:
            device = session.get(Device, device_id)
            if device is None:
                return 0
            widgets = [
                widget
                for widget in session.exec(
                    select(Widget).where(Widget.enabled).order_by(Widget.position, Widget.id)
                ).all()
                if device_id in widget.device_ids
            ]
            # Built inside the session: resolving a connector may need to read
            # the display it points at.
            connectors: dict[int, Connector] = {}
            for widget in widgets:
                if widget.connector_id in connectors:
                    continue
                instance = session.get(ConnectorInstance, widget.connector_id)
                if instance is None or not instance.enabled:
                    continue
                connector = self._connector_for(instance, session)
                if connector is not None:
                    connectors[widget.connector_id] = connector
            client = self._client_for(device)

        try:
            for name in await client.list_managed_apps():
                await client.delete_app(name)

            pushed = 0
            for widget in widgets:
                connector = connectors.get(widget.connector_id)
                if connector is None:
                    continue
                outcome = await run_widget(widget, connector, {device_id: client}, self.cache)
                if outcome.ok:
                    pushed += 1
        finally:
            await client.aclose()

        log.info("reordered %d app(s) on device %s", pushed, device_id)
        return pushed


#: One scheduler per process, started and stopped by the application lifespan.
scheduler = Scheduler()
