"""The dashboard summary, and the token that opens it.

A second key, weaker than the password on purpose: it is meant to sit in a
dashboard's configuration file. What matters is therefore less what it opens
than what it does not.
"""


import pytest

from app.core.config import get_settings

TOKEN = "un-jeton-de-tableau-de-bord"


@pytest.fixture
def dashboard(client, monkeypatch):
    monkeypatch.setenv("AWTRIXNG_PASSWORD", "secret")
    monkeypatch.setenv("AWTRIXNG_API_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield client
    get_settings.cache_clear()


def bearer(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# -- What it opens ----------------------------------------------------------


def test_the_token_reads_the_summary(dashboard):
    assert dashboard.get("/api/summary", headers=bearer()).status_code == 200


def test_without_it_the_summary_is_closed(dashboard):
    assert dashboard.get("/api/summary").status_code == 401


def test_a_session_reads_it_too(dashboard):
    dashboard.post("/api/auth/login", json={"password": "secret"})
    assert dashboard.get("/api/summary").status_code == 200


# -- What it does not open --------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/api/backup", "/api/devices", "/api/widgets", "/api/reminders"]
)
def test_the_token_opens_nothing_else(dashboard, path):
    """The whole point. A key left in a dashboard's config file must not be
    able to download the credentials."""
    assert dashboard.get(path, headers=bearer()).status_code == 401


def test_a_wrong_token_is_refused(dashboard):
    assert dashboard.get("/api/summary", headers=bearer("faux")).status_code == 401


def test_another_scheme_is_refused(dashboard):
    response = dashboard.get(
        "/api/summary", headers={"Authorization": f"Basic {TOKEN}"}
    )
    assert response.status_code == 401


def test_no_token_configured_means_no_token_works(client, monkeypatch):
    """An empty setting must not become an empty password."""
    monkeypatch.setenv("AWTRIXNG_PASSWORD", "secret")
    monkeypatch.setenv("AWTRIXNG_API_TOKEN", "")
    get_settings.cache_clear()
    try:
        assert client.get("/api/summary", headers=bearer("")).status_code == 401
        assert client.get("/api/summary", headers=bearer()).status_code == 401
    finally:
        get_settings.cache_clear()


# -- What it says -----------------------------------------------------------


def test_it_counts_what_a_dashboard_cannot(client):
    """Homepage reads scalars; it cannot count the items of an array. That is
    the reason this route exists at all."""
    device = client.post(
        "/api/devices", json={"name": "Bureau", "host": "127.0.0.1"}
    ).json()
    client.post(
        "/api/reminders",
        json={
            "name": "Médicament",
            "message": "M",
            "at": "07:30:00",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "device_ids": [device["id"]],
        },
    )

    body = client.get("/api/summary").json()
    assert body["displays_total"] == 1
    assert body["reminders_active"] == 1
    assert body["next_reminder"] == "Médicament"
    assert body["next_reminder_at"] is not None


def test_a_disabled_reminder_is_not_the_next_one(client):
    client.post(
        "/api/reminders",
        json={
            "name": "Éteint",
            "message": "M",
            "at": "07:30:00",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "enabled": False,
        },
    )
    body = client.get("/api/summary").json()
    assert body["reminders_active"] == 0
    assert body["next_reminder"] is None


def test_the_soonest_wins_whatever_the_order(client):
    """Reminders are listed by time of day; the next to ring is not
    necessarily the first in that list."""
    for name, at, days in (("Tard", "23:00:00", [0, 1, 2, 3, 4, 5, 6]),
                           ("Tot", "00:30:00", [0, 1, 2, 3, 4, 5, 6])):
        client.post(
            "/api/reminders",
            json={"name": name, "message": "M", "at": at, "days": days},
        )
    assert client.get("/api/summary").json()["next_reminder"] in {"Tard", "Tot"}


def test_an_empty_installation_says_so(client):
    body = client.get("/api/summary").json()
    assert body["displays_total"] == 0
    assert body["next_reminder"] is None
    assert body["status"] == "ok"


class TestWhichRefusal:
    """Three refusals that used to read identically.

    A dashboard showing "Authentication required" while sending a token had no
    way to tell a wrong token from a route its version does not have yet — the
    middleware denies before routing, so an unknown path answers the same. Both
    happened, in that order.
    """

    def test_no_header_at_all(self, dashboard):
        body = dashboard.get("/api/summary").json()
        assert body["code"] == "auth.required"

    def test_a_token_that_is_not_the_right_one(self, dashboard):
        body = dashboard.get("/api/summary", headers=bearer("faux")).json()
        assert body["code"] == "auth.token_refused"

    def test_a_good_token_on_a_path_it_does_not_open(self, dashboard):
        body = dashboard.get("/api/backup", headers=bearer()).json()
        assert body["code"] == "auth.token_scope"

    def test_the_three_are_distinguishable(self, dashboard):
        codes = {
            dashboard.get("/api/summary").json()["code"],
            dashboard.get("/api/summary", headers=bearer("faux")).json()["code"],
            dashboard.get("/api/backup", headers=bearer()).json()["code"],
        }
        assert len(codes) == 3

    def test_saying_which_leaks_nothing(self, dashboard):
        """The caller already knows whether it sent a token. Naming the reason
        tells it nothing it could not deduce, and the body never names a path
        the token does not open."""
        body = dashboard.get("/api/backup", headers=bearer()).json()
        assert "backup" not in body["detail"]
