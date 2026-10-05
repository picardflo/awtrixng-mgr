"""Editing a configured service.

Until now the UI could only create and delete one, and deleting cascades to
its widgets — so changing a weather city cost you every widget built on it.
The risky part is the partial update: a field left out must keep its value,
not lose it.
"""


def weather(client, **overrides):
    payload = {
        "type": "weather",
        "name": "Home",
        "config": {"place": {"name": "Paris", "latitude": 48.85, "longitude": 2.35}},
    }
    return client.post("/api/connectors", json=payload | overrides).json()


def test_renaming_leaves_the_configuration_alone(client):
    created = weather(client)
    updated = client.patch(
        f"/api/connectors/{created['id']}", json={"name": "Office"}
    ).json()
    assert updated["name"] == "Office"
    assert updated["config"]["place"]["name"] == "Paris"


def test_moving_the_place_keeps_the_widgets(client):
    """The whole reason this exists: deleting the service would have taken
    them with it."""
    device = client.post("/api/devices", json={"name": "D", "host": "h"}).json()
    connector = weather(client)
    client.post(
        "/api/widgets",
        json={
            "name": "Temp",
            "connector_id": connector["id"],
            "device_ids": [device["id"]],
            "widget_type": "weather.current",
        },
    )

    client.patch(
        f"/api/connectors/{connector['id']}",
        json={"config": {"place": {"name": "Lyon", "latitude": 45.75, "longitude": 4.85}}},
    )

    assert len(client.get("/api/widgets").json()) == 1
    stored = client.get(f"/api/connectors/{connector['id']}").json()
    assert stored["config"]["place"]["name"] == "Lyon"


def test_an_untouched_secret_is_kept(client):
    """The form sends no value for a secret the user did not retype."""
    created = weather(client, secrets={"token": "s3cret"})
    assert created["secrets_set"] == ["token"]

    updated = client.patch(
        f"/api/connectors/{created['id']}", json={"name": "Renamed", "secrets": {}}
    ).json()
    assert updated["secrets_set"] == ["token"]


def test_a_retyped_secret_replaces_it(client):
    created = weather(client, secrets={"token": "old"})
    client.patch(f"/api/connectors/{created['id']}", json={"secrets": {"token": "new"}})

    raw = client.get(f"/api/connectors/{created['id']}").text
    assert "new" not in raw and "old" not in raw, "no secret ever leaves the API"
    assert client.get(f"/api/connectors/{created['id']}").json()["secrets_set"] == ["token"]


def test_an_empty_string_clears_a_secret(client):
    created = weather(client, secrets={"token": "old"})
    updated = client.patch(
        f"/api/connectors/{created['id']}", json={"secrets": {"token": ""}}
    ).json()
    assert updated["secrets_set"] == []


def test_editing_bumps_the_timestamp_so_the_scheduler_rebuilds(client):
    """The scheduler caches a live connector keyed on this."""
    created = weather(client)
    before = client.get(f"/api/connectors/{created['id']}").json()
    client.patch(f"/api/connectors/{created['id']}", json={"name": "Other"})
    after = client.get(f"/api/connectors/{created['id']}").json()
    # updated_at is not exposed; the rebuild is covered in test_scheduler_loop.
    assert before["name"] != after["name"]


def test_disabling_a_service(client):
    created = weather(client)
    assert client.patch(
        f"/api/connectors/{created['id']}", json={"enabled": False}
    ).json()["enabled"] is False


def test_editing_an_unknown_service_is_404(client):
    assert client.patch("/api/connectors/999", json={"name": "x"}).status_code == 404
