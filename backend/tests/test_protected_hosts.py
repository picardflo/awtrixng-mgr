"""The guard that refuses a display in service.

This exists because the written version did not work. On the previous project
a second instance deleted a live display's apps twice, the second time *after*
the risk had been recorded in an architecture decision record. So the rule is
executable, and these tests are what keep it that way.
"""

import pytest

from app.core.protected import (
    ProtectedHostError,
    assert_writable,
    is_protected,
    protected_hosts,
)


def test_nothing_is_protected_until_someone_says_so(monkeypatch, tmp_path):
    """The default is empty, and that is deliberate.

    It used to name the author's own lounge clock. On anyone else's network
    that is a guard full of hostnames that mean nothing — it protects nobody
    while looking like it protects something, which is worse than no guard at
    all because it invites trust.

    Both sources are neutralised, not just the variable: this file is read as
    a fallback, and a developer who has filled their own `.env` would
    otherwise see this test pass or fail depending on their lounge.
    """
    from app.core import protected

    monkeypatch.delenv("AWTRIXNG_PROTECTED_HOSTS", raising=False)
    monkeypatch.setattr(protected, "ENV_FILE", tmp_path / "absent")
    assert protected_hosts() == set()
    assert not is_protected("awtrix-lounge.lan")
    assert_writable("awtrix-lounge.lan")


def test_a_named_display_is_refused(monkeypatch):
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "kitchen.local, hall.local")
    assert protected_hosts() == {"kitchen.local", "hall.local"}
    assert is_protected("hall.local")
    assert not is_protected("study.local")


def test_the_comparison_ignores_case_and_spacing(monkeypatch):
    """Someone types what they see on a label, not what DNS has."""
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "awtrix-lounge.lan")
    assert is_protected("  AWTRIX-Lounge.LAN  ")


def test_assert_writable_names_the_escape_hatch(monkeypatch):
    """Whoever hits this needs to know how to proceed deliberately."""
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "awtrix-lounge.lan")
    with pytest.raises(ProtectedHostError, match="AWTRIXNG_PROTECTED_HOSTS"):
        assert_writable("awtrix-lounge.lan")


def test_an_empty_list_disables_the_guard(monkeypatch):
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "")
    assert protected_hosts() == set()
    assert_writable("anything.local")


class TestTheEnvFileFallback:
    """The half the guard was missing.

    Compose reads `.env` for the container, and nothing read it for the tools
    that actually write to a display: the panel bench, the font extractor and
    the hardware tests all run on a workstation. A list filled in `.env`
    therefore protected the CLI — which pushes one notification — and left the
    benches, which push dozens, entirely free.

    Florian filled his `.env` on the VM and was told he was covered. He was
    covered for the half that was never the danger.
    """

    def test_the_file_is_read_when_the_variable_is_absent(self, monkeypatch, tmp_path):
        from app.core import protected

        monkeypatch.delenv("AWTRIXNG_PROTECTED_HOSTS", raising=False)
        env = tmp_path / ".env"
        env.write_text("FOO=bar\nAWTRIXNG_PROTECTED_HOSTS=lounge.lan, hall.lan\n")
        monkeypatch.setattr(protected, "ENV_FILE", env)
        assert protected.protected_hosts() == {"lounge.lan", "hall.lan"}

    def test_quotes_are_stripped(self, monkeypatch, tmp_path):
        """`.env` files are written both ways, and a quoted name that is never
        matched is a guard that silently does nothing."""
        from app.core import protected

        monkeypatch.delenv("AWTRIXNG_PROTECTED_HOSTS", raising=False)
        env = tmp_path / ".env"
        env.write_text('AWTRIXNG_PROTECTED_HOSTS="lounge.lan"\n')
        monkeypatch.setattr(protected, "ENV_FILE", env)
        assert protected.protected_hosts() == {"lounge.lan"}

    def test_the_environment_wins(self, monkeypatch, tmp_path):
        """In the container the variable is always set, and an empty one is a
        deliberate "no guard" that a stale file must not override."""
        from app.core import protected

        env = tmp_path / ".env"
        env.write_text("AWTRIXNG_PROTECTED_HOSTS=lounge.lan\n")
        monkeypatch.setattr(protected, "ENV_FILE", env)
        monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "")
        assert protected.protected_hosts() == set()

    def test_a_missing_file_is_not_an_error(self, monkeypatch, tmp_path):
        from app.core import protected

        monkeypatch.delenv("AWTRIXNG_PROTECTED_HOSTS", raising=False)
        monkeypatch.setattr(protected, "ENV_FILE", tmp_path / "absent")
        assert protected.protected_hosts() == set()
