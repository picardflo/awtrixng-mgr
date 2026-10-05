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


def test_the_lounge_clock_is_protected_by_default():
    assert is_protected("awtrix-cl1")
    assert is_protected("awtrix-cl1.home.lan")


def test_the_comparison_ignores_case_and_spacing():
    assert is_protected("  AWTRIX-CL1.Home.Lan  ")


def test_the_test_bench_is_not_protected():
    assert not is_protected("awtrix-cl2.home.lan")


def test_assert_writable_names_the_escape_hatch():
    """Whoever hits this needs to know how to proceed deliberately."""
    with pytest.raises(ProtectedHostError, match="AWTRIXNG_PROTECTED_HOSTS"):
        assert_writable("awtrix-cl1.home.lan")


def test_the_list_can_be_replaced(monkeypatch):
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "kitchen.local, hall.local")
    assert protected_hosts() == {"kitchen.local", "hall.local"}
    assert is_protected("hall.local")
    # The default no longer applies once the variable is set.
    assert not is_protected("awtrix-cl1")


def test_an_empty_list_disables_the_guard(monkeypatch):
    """What a published copy of this project would do: the host names in the
    default are one household's, not everyone's."""
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "")
    assert protected_hosts() == set()
    assert_writable("awtrix-cl1")
