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


def test_nothing_is_protected_until_someone_says_so(monkeypatch):
    """The default is empty, and that is deliberate.

    It used to name the author's own lounge clock. On anyone else's network
    that is a guard full of hostnames that mean nothing — it protects nobody
    while looking like it protects something, which is worse than no guard at
    all because it invites trust.
    """
    monkeypatch.delenv("AWTRIXNG_PROTECTED_HOSTS", raising=False)
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
