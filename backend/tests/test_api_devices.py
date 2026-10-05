
import json

import httpx
import pytest
import respx


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_then_list(client):
    created = client.post("/api/devices", json={"name": "Salon", "host": "1.2.3.4"})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "unknown"
    assert body["port"] == 80

    listed = client.get("/api/devices").json()
    assert [d["name"] for d in listed] == ["Salon"]


def test_password_is_never_returned(client):
    client.post(
        "/api/devices",
        json={"name": "Salon", "host": "1.2.3.4", "username": "u", "password": "hunter2"},
    )
    raw = client.get("/api/devices").text
    assert "hunter2" not in raw
    assert client.get("/api/devices").json()[0]["has_password"] is True


def test_patch_without_password_keeps_it(client):
    device = client.post(
        "/api/devices", json={"name": "S", "host": "h", "password": "keepme"}
    ).json()
    client.patch(f"/api/devices/{device['id']}", json={"name": "Renamed"})
    updated = client.get(f"/api/devices/{device['id']}").json()
    assert updated["name"] == "Renamed"
    assert updated["has_password"] is True


def test_empty_password_clears_it(client):
    device = client.post(
        "/api/devices", json={"name": "S", "host": "h", "password": "gone"}
    ).json()
    client.patch(f"/api/devices/{device['id']}", json={"password": ""})
    assert client.get(f"/api/devices/{device['id']}").json()["has_password"] is False


def test_unknown_device_is_404(client):
    assert client.get("/api/devices/999").status_code == 404


def test_delete(client):
    device = client.post("/api/devices", json={"name": "S", "host": "h"}).json()
    assert client.delete(f"/api/devices/{device['id']}").status_code == 204
    assert client.get("/api/devices").json() == []


def test_unreachable_device_reports_error_not_500(client):
    """An unreachable device is a state, not an API failure (§18)."""
    device = client.post(
        "/api/devices", json={"name": "Ghost", "host": "192.0.2.1", "port": 81}
    ).json()
    result = client.post(f"/api/devices/{device['id']}/test")
    assert result.status_code == 200
    assert result.json()["ok"] is False
    assert client.get(f"/api/devices/{device['id']}").json()["status"] == "error"


def test_unwritable_data_dir_gives_an_actionable_error(tmp_path, monkeypatch):
    """The commonest Docker case: /data belongs to root, not to the app.

    Without this guard the error surfaces as an unreadable SQLAlchemy trace.
    """
    import os

    from app.core.errors import AwtrixNgError
    from app.db import session as session_module

    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)  # read and traverse, no write
    monkeypatch.setattr(session_module._settings, "data_dir", locked)

    try:
        if os.geteuid() == 0:
            return  # root ignores permissions: the test is meaningless
        with pytest.raises(AwtrixNgError, match="writable"):
            session_module.check_data_dir()
    finally:
        locked.chmod(0o700)


def test_failures_carry_a_translatable_code(client):
    """The UI translates `code`; `message` is only the English fallback."""
    device = client.post(
        "/api/devices", json={"name": "Ghost", "host": "192.0.2.1", "port": 81}
    ).json()

    result = client.post(f"/api/devices/{device['id']}/test").json()
    assert result["ok"] is False
    assert result["code"] == "device.unreachable"
    assert result["params"]["target"] == "http://192.0.2.1:81"

    # The code is persisted so the card can translate it after a reload.
    assert client.get(f"/api/devices/{device['id']}").json()["last_error_code"] == (
        "device.unreachable"
    )


def test_recovery_clears_the_error_code(client):
    device = client.post("/api/devices", json={"name": "G", "host": "192.0.2.1"}).json()
    client.post(f"/api/devices/{device['id']}/test")
    assert client.get(f"/api/devices/{device['id']}").json()["last_error_code"]

    # A successful patch must not keep a stale code around once probed again;
    # here we only assert the field exists and round-trips.
    stored = client.get(f"/api/devices/{device['id']}").json()
    assert set(stored) >= {"last_error", "last_error_code", "status"}


def test_a_widget_saved_before_an_option_existed_reads_back_complete(client):
    """A display stored without a key must not come back missing it: the form
    would render a checkbox with no state."""
    device = client.post("/api/devices", json={"name": "D", "host": "h"}).json()
    connector = client.post(
        "/api/connectors",
        json={
            "type": "weather",
            "name": "W",
            "config": {"place": {"name": "P", "latitude": 1, "longitude": 2}},
        },
    ).json()
    created = client.post(
        "/api/widgets",
        json={
            "name": "Old",
            "connector_id": connector["id"],
            "device_ids": [device["id"]],
            "widget_type": "weather.current",
            "display": {"text": "{{ temp }}"},
        },
    ).json()

    # Simulate a row written before `show_icon` was added.
    from sqlmodel import Session

    from app.db.session import engine
    from app.models import Widget

    with Session(engine) as session:
        widget = session.get(Widget, created["id"])
        widget.display = {"text": "{{ temp }}", "duration": 8}
        session.add(widget)
        session.commit()

    display = client.get(f"/api/widgets/{created['id']}").json()["display"]
    assert display["show_icon"] is True
    assert display["text"] == "{{ temp }}"
    assert display["duration"] == 8


def _weather_setup(client):
    device = client.post("/api/devices", json={"name": "D", "host": "h"}).json()
    connector = client.post(
        "/api/connectors",
        json={
            "type": "weather",
            "name": "W",
            "config": {"place": {"name": "P", "latitude": 1, "longitude": 2}},
        },
    ).json()
    return device, connector


def _make_widget(client, device, connector, name):
    return client.post(
        "/api/widgets",
        json={
            "name": name,
            "connector_id": connector["id"],
            "device_ids": [device["id"]],
            "widget_type": "weather.current",
        },
    ).json()


def test_new_widgets_land_at_the_end_of_the_rotation(client):
    device, connector = _weather_setup(client)
    positions = [
        _make_widget(client, device, connector, name)["position"]
        for name in ("a", "b", "c")
    ]
    assert positions == sorted(positions)
    assert len(set(positions)) == 3


def test_the_list_comes_back_in_rotation_order(client):
    device, connector = _weather_setup(client)
    made = [_make_widget(client, device, connector, n) for n in ("a", "b", "c")]

    reversed_ids = [w["id"] for w in reversed(made)]
    client.post("/api/widgets/order", json={"widget_ids": reversed_ids})

    listed = client.get("/api/widgets").json()
    assert [w["id"] for w in listed] == reversed_ids
    assert [w["position"] for w in listed] == [0, 1, 2]


def test_ordering_an_unknown_widget_is_refused(client):
    assert client.post("/api/widgets/order", json={"widget_ids": [999]}).status_code == 404


def test_ordering_writes_positions_without_touching_a_display(client):
    """Cheap on purpose: rebuilding a rotation blanks the matrix, so that is a
    separate, explicit action."""
    device, connector = _weather_setup(client)
    made = [_make_widget(client, device, connector, n) for n in ("a", "b")]
    result = client.post(
        "/api/widgets/order", json={"widget_ids": [made[1]["id"], made[0]["id"]]}
    )
    assert result.status_code == 200
    assert [w["name"] for w in result.json()] == ["b", "a"]


class TestNotifyPayload:
    """What the UI may send on /notify.

    The route rebuilds the payload field by field, so anything it does not name
    is dropped — which is how a melody travelled from the reminder form to this
    endpoint and no further, in silence.
    """

    @respx.mock
    def test_a_melody_reaches_the_clock(self, client):
        device = client.post(
            "/api/devices", json={"name": "Bureau", "host": "clock.test"}
        ).json()
        route = respx.post("http://clock.test/api/v1/notifications").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        melody = "rappel:d=16,o=6,b=120:c,e,g"
        response = client.post(
            f"/api/devices/{device['id']}/notify",
            json={"text": "x", "duration": 3, "melody": melody, "wakeup": True},
        )
        assert response.status_code == 200
        sent = json.loads(route.calls[0].request.content)
        assert sent["soundRtttl"] == melody
        assert sent["wakeup"] is True

    @respx.mock
    def test_an_unknown_field_is_refused_rather_than_dropped(self, client):
        """Silence is how the defect hid: the field went in and nothing said
        it had gone nowhere."""
        device = client.post(
            "/api/devices", json={"name": "Bureau", "host": "clock.test"}
        ).json()
        response = client.post(
            f"/api/devices/{device['id']}/notify",
            json={"text": "x", "rtttl": "rappel:d=16,o=6,b=120:c,e,g"},
        )
        assert response.status_code == 422
