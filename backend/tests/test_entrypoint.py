"""The container's entry point, which runs as root for a moment.

It is the one piece of this project that holds privileges, so what it refuses
to do matters as much as what it does.
"""

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "docker-entrypoint.py"


@pytest.fixture(scope="module")
def entrypoint():
    spec = importlib.util.spec_from_file_location("docker_entrypoint", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTrustingAMountedAuthority:
    """A home network's own certificate authority, mounted by compose.

    The host trusts it; the container has its own filesystem and does not, so
    every outbound HTTPS call to the LAN fails verification — and the only
    answer left is to turn verification off per service, which is the wrong
    one.
    """

    def test_it_does_nothing_without_privileges(self, entrypoint, monkeypatch):
        """Writing to the system store needs root. Called after privileges
        are dropped it must be a no-op, not an error — and it is called before
        they are dropped precisely so it never has to be."""
        monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 10001)
        ran = []
        monkeypatch.setattr(entrypoint.subprocess, "run", lambda *a, **k: ran.append(a))
        entrypoint.trust_mounted_authorities()
        assert ran == []

    def test_it_does_nothing_when_nothing_is_mounted(self, entrypoint, monkeypatch, tmp_path):
        """The ordinary case: no `volumes:` line, no authority, no noise."""
        monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 0)
        monkeypatch.setattr(entrypoint, "EXTRA_CA_DIR", tmp_path)
        ran = []
        monkeypatch.setattr(entrypoint.subprocess, "run", lambda *a, **k: ran.append(a))
        entrypoint.trust_mounted_authorities()
        assert ran == []

    def test_it_adds_rather_than_replaces(self, entrypoint, monkeypatch, tmp_path):
        """`update-ca-certificates` appends to the store. Substituting it
        would take the public roots with it, and Open-Meteo would stop
        answering on the same day — so no other command is acceptable here."""
        monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 0)
        (tmp_path / "homelan.crt").write_text("-----BEGIN CERTIFICATE-----\n")
        monkeypatch.setattr(entrypoint, "EXTRA_CA_DIR", tmp_path)
        ran = []
        monkeypatch.setattr(entrypoint.subprocess, "run", lambda cmd, **k: ran.append(cmd))
        entrypoint.trust_mounted_authorities()
        assert ran == [["update-ca-certificates"]]

    def test_a_missing_tool_is_reported_not_fatal(self, entrypoint, monkeypatch, tmp_path, capsys):
        """A container that refuses to start because one certificate is
        malformed is worse than one that starts without it and says so."""
        monkeypatch.setattr(entrypoint.os, "geteuid", lambda: 0)
        (tmp_path / "homelan.crt").write_text("x")
        monkeypatch.setattr(entrypoint, "EXTRA_CA_DIR", tmp_path)

        def missing(*args, **kwargs):
            raise FileNotFoundError("update-ca-certificates")

        monkeypatch.setattr(entrypoint.subprocess, "run", missing)
        entrypoint.trust_mounted_authorities()  # must not raise
        assert "could not trust" in capsys.readouterr().err
