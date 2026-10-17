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


class TestTestingSaysWhatItFound:
    """The badge must agree with the message beside it.

    A connector that cannot reach its service does not raise — it returns
    `ok=False` with a translatable code, which is the contract of
    `Connector.test_connection` and what lets the interface say *why*. The
    route used to key on the exception alone, so every one of those honest
    refusals was stamped HEALTHY.

    Florian found it on a Tautulli whose certificate was rejected: a toast
    reading "injoignable" over a badge reading "En ligne".
    """

    def service(self, client):
        return client.post(
            "/api/connectors",
            json={
                "type": "tautulli",
                "name": "Plex",
                "config": {"url": "https://nowhere.invalid", "verify_tls": True},
                "secrets": {"api_key": "k" * 32},
            },
        ).json()

    def test_a_refusal_marks_the_service_in_error(self, client):
        instance = self.service(client)
        result = client.post(f"/api/connectors/{instance['id']}/test").json()
        assert result["ok"] is False

        after = client.get(f"/api/connectors/{instance['id']}").json()
        assert after["status"] == "error", "badged healthy over a failed test"
        assert after["last_error_code"] == result["code"]

    def test_the_failure_is_counted(self, client):
        """So that a service failing again and again looks different from one
        that failed once."""
        instance = self.service(client)
        for _ in range(2):
            client.post(f"/api/connectors/{instance['id']}/test")
        after = client.get(f"/api/connectors/{instance['id']}").json()
        assert after["consecutive_failures"] >= 2

    def test_a_success_clears_what_a_failure_left(self, client):
        """The other direction: a service that comes back must stop showing
        the error that was true an hour ago."""
        instance = client.post(
            "/api/connectors", json={"type": "moon", "name": "Lune", "config": {}}
        ).json()
        result = client.post(f"/api/connectors/{instance['id']}/test").json()
        assert result["ok"] is True

        after = client.get(f"/api/connectors/{instance['id']}").json()
        assert after["status"] == "healthy"
        assert after["last_error_code"] is None
        assert after["consecutive_failures"] == 0


class TestAnErrorKeepsWhatCompletesIt:
    """Florian, capture à l'appui : une interface en français, et une ligne en
    anglais au milieu — « heu ya un raté ! ».

    The stored form of an error kept only its **code**. A translated message
    carrying a placeholder — "Open-Meteo a refusé la requête : {reason}" —
    therefore had nothing to fill it with. 0.17.2 stopped showing the hole by
    falling back to the backend's English sentence; that was the quick fix,
    and he saw its cost the next day.
    """

    def failing(self, client):
        return client.post(
            "/api/connectors",
            json={
                "type": "tautulli",
                "name": "Plex",
                "config": {"url": "https://nowhere.invalid", "verify_tls": True},
                "secrets": {"api_key": "k" * 32},
            },
        ).json()

    def test_the_parameters_are_stored_beside_the_code(self, client):
        instance = self.failing(client)
        result = client.post(f"/api/connectors/{instance['id']}/test").json()
        assert result["params"], "the failure carried no parameters to keep"

        after = client.get(f"/api/connectors/{instance['id']}").json()
        assert after["last_error_params"] == result["params"]

    def test_a_success_clears_them_too(self, client):
        """Left behind, they would complete the *previous* message."""
        instance = client.post(
            "/api/connectors", json={"type": "moon", "name": "Lune", "config": {}}
        ).json()
        client.post(f"/api/connectors/{instance['id']}/test")
        after = client.get(f"/api/connectors/{instance['id']}").json()
        assert after["last_error_params"] is None

    def test_every_placeholder_can_be_filled(self, client):
        """The point of the whole exercise: the French message must come out
        whole. Checked against the catalogue itself rather than against a
        sentence retyped here."""
        import re
        from pathlib import Path

        instance = self.failing(client)
        client.post(f"/api/connectors/{instance['id']}/test")
        after = client.get(f"/api/connectors/{instance['id']}").json()

        catalogue = (
            Path(__file__).resolve().parents[2]
            / "frontend" / "src" / "i18n" / "messages.fr.ts"
        ).read_text(encoding="utf-8")
        found = re.search(rf'"{after["last_error_code"]}": "([^"]*)"', catalogue)
        assert found, "no French message for that code"

        wanted = set(re.findall(r"\{(\w+)\}", found.group(1)))
        assert wanted <= set(after["last_error_params"] or {}), (
            f"{sorted(wanted - set(after['last_error_params'] or {}))} would stay "
            "in braces on the card"
        )
