"""Reconciliation: what the display holds against what the database expects.

This is the code path that deleted a live display's apps twice on the previous
project, so it is checked from both sides: an app we did not push is never an
orphan, and an app we did push is never mistaken for someone else's.
"""

from app.models import Widget, WidgetTarget
from app.services.ng.models import AppEntry
from app.services.scheduler.reconcile import compare

#: What the firmware puts there by itself. `origin` is NG's own word for it,
#: and it is what makes "not ours" checkable rather than guessed from a name.
BUILTIN = [
    AppEntry(name=name, origin="builtin", inLoop=True)
    for name in ("Time", "Date", "Temperature", "Humidity", "Battery")
]


def pushed(*names: str) -> list[AppEntry]:
    """Apps that are on the display because something pushed them."""
    return [AppEntry(name=name, origin="pushed", inLoop=True) for name in names]


def widget(widget_id: int, *, devices: tuple[int, ...] = (1,), enabled: bool = True) -> Widget:
    return Widget(
        id=widget_id,
        name=f"W{widget_id}",
        connector_id=1,
        widget_type="weather.current",
        enabled=enabled,
        targets=[
            WidgetTarget(widget_id=widget_id, device_id=device_id) for device_id in devices
        ],
    )


def test_everything_in_place_means_no_drift():
    result = compare(1, [widget(1), widget(2)], BUILTIN + pushed("ng000001", "ng000002"))
    assert not result.drifted


def test_a_rebooted_device_has_lost_its_apps():
    """Without this, a reboot leaves the matrix bare until the next refresh —
    up to ten minutes for a weather widget."""
    result = compare(1, [widget(1), widget(2)], BUILTIN)
    assert result.missing == [1, 2]
    assert result.orphans == []


def test_an_app_deleted_by_hand_is_noticed():
    result = compare(1, [widget(1), widget(2)], BUILTIN + pushed("ng000001"))
    assert result.missing == [2]


def test_a_widget_deleted_while_the_device_was_off_leaves_an_orphan():
    result = compare(1, [widget(1)], BUILTIN + pushed("ng000001", "ng000099"))
    assert result.orphans == ["ng000099"]
    assert result.missing == []


def test_a_disabled_widget_is_removed_from_the_matrix():
    """This is what makes "disabled" mean anything at all."""
    result = compare(1, [widget(1, enabled=False)], BUILTIN + pushed("ng000001"))
    assert result.orphans == ["ng000001"]


def test_native_apps_are_left_alone():
    result = compare(1, [], BUILTIN)
    assert not result.drifted


def test_apps_pushed_by_hand_are_left_alone():
    """A name that is not ours is not ours, even on our device."""
    result = compare(1, [], BUILTIN + pushed("myapp", "ng1", "ngXXXXXX"))
    assert result.orphans == []


def test_widgets_of_another_device_are_ignored():
    """Two clocks: the living room loop says nothing about the office one."""
    result = compare(1, [widget(1, devices=(1,)), widget(2, devices=(2,))], BUILTIN)
    assert result.missing == [1]


def test_a_widget_on_both_displays_is_expected_on_both():
    """The whole point of the change: one widget, two clocks."""
    both = [widget(1, devices=(1, 2))]
    assert compare(1, both, BUILTIN).missing == [1]
    assert compare(2, both, BUILTIN).missing == [1]
    assert not compare(1, both, BUILTIN + pushed("ng000001")).drifted


def test_dropping_a_display_leaves_an_orphan_there():
    """Untargeting a clock must free it."""
    result = compare(2, [widget(1, devices=(1,))], BUILTIN + pushed("ng000001"))
    assert result.orphans == ["ng000001"]


def test_an_app_belonging_to_another_device_is_an_orphan_here():
    result = compare(
        1, [widget(2, devices=(2,))], BUILTIN + pushed("ng000002")
    )
    assert result.orphans == ["ng000002"]


def test_an_empty_display_and_no_widget():
    assert not compare(1, [], []).drifted


def test_a_builtin_named_like_ours_is_never_an_orphan():
    """Belt and braces. A name is a weak signal — the firmware could gain an
    app called ng000001 tomorrow, and deleting it would be ours to answer for.
    `origin` is the strong one, and both have to agree."""
    impostor = [AppEntry(name="ng000001", origin="builtin", inLoop=True)]
    assert compare(1, [], impostor).orphans == []


def test_an_app_from_a_script_is_left_alone():
    """NG runs Berry scripts on the device, which can push apps of their own.
    They are not ours even when they are not builtin either."""
    result = compare(1, [], [AppEntry(name="ng000001", origin="script", inLoop=True)])
    assert result.orphans == []
