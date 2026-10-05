"""Exporting and restoring the configuration.

Without it, losing /data/awtrixng.db means retyping every template, icon,
colour and position by hand — and every API key, several of which a service
only ever shows once. The file therefore carries credentials in clear text,
and has to say so.
"""

def build(client):
    """A configuration worth losing: two displays, one service, two widgets."""
    salon = client.post("/api/devices", json={"name": "Salon", "host": "h1"}).json()
    bureau = client.post(
        "/api/devices",
        json={"name": "Bureau", "host": "h2", "port": 8080,
              "username": "u", "password": "p"},
    ).json()
    connector = client.post(
        "/api/connectors",
        json={"type": "weather", "name": "Météo",
              "config": {"place": {"name": "Lyon", "latitude": 45.75, "longitude": 4.85}},
              "secrets": {"token": "s3cret"}},
    ).json()
    first = client.post(
        "/api/widgets",
        json={"name": "Température", "connector_id": connector["id"],
              "device_ids": [salon["id"], bureau["id"]],
              "widget_type": "weather.current",
              "display": {"text": "{{ temp | round }}°", "icon": "12182"},
              "refresh_seconds": 600},
    ).json()
    second = client.post(
        "/api/widgets",
        json={"name": "Pluie", "connector_id": connector["id"],
              "device_ids": [bureau["id"]], "widget_type": "weather.rain"},
    ).json()
    return {"salon": salon, "bureau": bureau, "connector": connector,
            "widgets": [first, second]}


class TestExport:
    def test_holds_everything_tedious_to_retype(self, client):
        build(client)
        backup = client.get("/api/backup").json()

        assert len(backup["devices"]) == 2
        assert len(backup["connectors"]) == 1
        assert len(backup["widgets"]) == 2

        widget = backup["widgets"][0]
        assert widget["display"]["text"] == "{{ temp | round }}°"
        assert widget["display"]["icon"] == "12182"
        assert widget["refresh_seconds"] == 600
        assert len(widget["devices"]) == 2

    def test_credentials_are_included(self, client):
        """A backup that does not restore is half a backup: some API keys are
        shown once by the service that issues them."""
        build(client)
        backup = client.get("/api/backup").json()
        assert backup["connectors"][0]["secrets"] == {"token": "s3cret"}
        assert [d["password"] for d in backup["devices"]] == [None, "p"]

    def test_the_file_warns_about_it_in_its_first_field(self, client):
        """Anyone opening the JSON must see it without reading documentation."""
        backup = client.get("/api/backup").json()
        assert "credentials in clear text" in backup["warning"]
        assert list(backup)[0] == "warning"

    def test_an_empty_installation_exports_an_empty_file(self, client):
        backup = client.get("/api/backup").json()
        assert backup["devices"] == [] and backup["widgets"] == []
        assert backup["format"] == 1


class TestRoundTrip:
    def test_restoring_into_an_empty_installation_rebuilds_everything(self, client):
        build(client)
        backup = client.get("/api/backup").json()

        # Wipe it the way a lost database would.
        for widget in client.get("/api/widgets").json():
            client.delete(f"/api/widgets/{widget['id']}")
        for connector in client.get("/api/connectors").json():
            client.delete(f"/api/connectors/{connector['id']}")
        for device in client.get("/api/devices").json():
            client.delete(f"/api/devices/{device['id']}")
        assert client.get("/api/widgets").json() == []

        result = client.post("/api/backup/restore", json=backup).json()
        assert result["ok"]
        assert (result["devices"], result["connectors"], result["widgets"]) == (2, 1, 2)

        restored = client.get("/api/backup").json()
        for section in ("devices", "connectors", "widgets"):
            assert len(restored[section]) == len(backup[section])

    def test_references_are_remapped_not_copied(self, client):
        """Database ids differ after a restore; the widgets must still point at
        the right service and displays."""
        build(client)
        backup = client.get("/api/backup").json()
        client.post("/api/backup/restore", json=backup)

        widgets = client.get("/api/widgets").json()
        devices = {d["id"] for d in client.get("/api/devices").json()}
        connectors = {c["id"] for c in client.get("/api/connectors").json()}

        for widget in widgets:
            assert widget["connector_id"] in connectors
            assert {t["device_id"] for t in widget["targets"]} <= devices

        by_name = {w["name"]: w for w in widgets}
        assert len(by_name["Température"]["targets"]) == 2
        assert len(by_name["Pluie"]["targets"]) == 1

    def test_restoring_replaces_rather_than_merges(self, client):
        build(client)
        backup = client.get("/api/backup").json()
        client.post("/api/backup/restore", json=backup)
        assert len(client.get("/api/widgets").json()) == 2, "not doubled"

    def test_credentials_survive_and_are_re_encrypted(self, client):
        """Restored into another installation, they must work — so they are
        re-encrypted with the receiving key, not copied as stored."""
        build(client)
        backup = client.get("/api/backup").json()
        client.post("/api/backup/restore", json=backup)

        connector = client.get("/api/connectors").json()[0]
        assert connector["secrets_set"] == ["token"], "the key is set again"

        again = client.get("/api/backup").json()
        assert again["connectors"][0]["secrets"] == {"token": "s3cret"}
        assert [d["password"] for d in again["devices"]] == [None, "p"]

    def test_a_display_password_is_still_never_returned_elsewhere(self, client):
        """Only the backup endpoint exposes one; the device API must not."""
        build(client)
        raw = client.get("/api/devices").text
        assert '"p"' not in raw
        assert all(d["has_password"] in (True, False) for d in client.get("/api/devices").json())

    def test_the_rotation_order_survives(self, client):
        build(client)
        widgets = client.get("/api/widgets").json()
        client.post(
            "/api/widgets/order",
            json={"widget_ids": [widgets[1]["id"], widgets[0]["id"]]},
        )
        backup = client.get("/api/backup").json()
        client.post("/api/backup/restore", json=backup)
        assert [w["name"] for w in client.get("/api/widgets").json()] == [
            "Pluie",
            "Température",
        ]


class TestInspect:
    def test_it_describes_a_file_without_touching_anything(self, client):
        build(client)
        backup = client.get("/api/backup").json()
        before = len(client.get("/api/widgets").json())

        summary = client.post("/api/backup/inspect", json=backup).json()

        assert summary["ok"]
        assert (summary["devices"], summary["connectors"], summary["widgets"]) == (2, 1, 2)
        assert len(client.get("/api/widgets").json()) == before

    def test_it_counts_the_credentials_so_the_warning_is_concrete(self, client):
        build(client)
        summary = client.post(
            "/api/backup/inspect", json=client.get("/api/backup").json()
        ).json()
        assert summary["secrets"] == 2  # one service token, one display password


class TestRefusals:
    def test_a_file_from_a_newer_version_is_refused(self, client):
        build(client)
        summary = client.post(
            "/api/backup/inspect", json={"format": 99, "devices": [], "widgets": []}
        ).json()
        assert summary["ok"] is False
        assert summary["code"] == "backup.format_too_new"

    def test_and_restoring_it_changes_nothing(self, client):
        build(client)
        before = len(client.get("/api/widgets").json())
        assert client.post(
            "/api/backup/restore", json={"format": 99, "devices": []}
        ).status_code == 400
        assert len(client.get("/api/widgets").json()) == before

    def test_a_widget_pointing_at_a_missing_service_is_skipped(self, client):
        """A hand-edited file should not abort the whole restore."""
        result = client.post(
            "/api/backup/restore",
            json={
                "format": 1,
                "devices": [{"ref": 1, "name": "D", "host": "h"}],
                "connectors": [],
                "widgets": [{"name": "orphan", "connector": 7, "devices": [1],
                             "widget_type": "weather.current"}],
            },
        ).json()
        assert result["ok"] and result["widgets"] == 0
        assert result["devices"] == 1

    def test_the_same_display_listed_twice_is_tolerated(self, client):
        result = client.post(
            "/api/backup/restore",
            json={
                "format": 1,
                "devices": [{"ref": 1, "name": "D", "host": "h"}],
                "connectors": [{"ref": 1, "type": "weather", "name": "W", "config": {}}],
                "widgets": [{"name": "w", "connector": 1, "devices": [1, 1],
                             "widget_type": "weather.current"}],
            },
        ).json()
        assert result["ok"]
        assert len(client.get("/api/widgets").json()[0]["targets"]) == 1

    def test_a_failure_mid_restore_leaves_the_configuration_untouched(
        self, client, monkeypatch
    ):
        """The guarantee: one transaction, so a bad file cannot half-replace."""
        build(client)
        backup = client.get("/api/backup").json()
        before = client.get("/api/backup").json()

        from app.api.routes import backup as module

        original = module.Widget

        def explode(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(module, "Widget", explode)
        # The route turns it into a 400 rather than letting it escape.
        assert client.post("/api/backup/restore", json=backup).status_code == 400
        monkeypatch.setattr(module, "Widget", original)

        after = client.get("/api/backup").json()
        assert len(after["devices"]) == len(before["devices"])
        assert len(after["widgets"]) == len(before["widgets"])
