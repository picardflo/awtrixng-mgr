"""The payload must say what the firmware understands, and nothing else.

These assertions are transcriptions of what a real TC001 on NG 1.1.2 answered
when probed key by key. They are here so that the day someone "helpfully"
restores `color` or `duration` from muscle memory, a test fails instead of a
display going quietly wrong.
"""

import pytest
from pydantic import ValidationError

from app.services.ng.payload import NgNotification, NgPayload, Scroll


def test_wire_keys_are_camel_case():
    payload = NgPayload(
        text="hello",
        text_color="#f5a524",
        background_color="#000000",
        duration_ms=8000,
        lifetime_ms=300_000,
        icon_mode="push",
        text_case="upper",
        progress_color="#00ff00",
        progress_track_color="#333333",
        bar_chart=[1, 2, 3],
        line_chart=[4, 5, 6],
    )
    assert payload.to_json() == {
        "text": "hello",
        "textColor": "#f5a524",
        "backgroundColor": "#000000",
        "durationMs": 8000,
        "lifetimeMs": 300_000,
        "iconMode": "push",
        "textCase": "upper",
        "progressColor": "#00ff00",
        "progressTrackColor": "#333333",
        "barChart": [1, 2, 3],
        "lineChart": [4, 5, 6],
    }


def test_nulls_are_omitted():
    """Every key is optional; sending nulls only gives the firmware something
    to have an opinion about."""
    assert NgPayload(text="x").to_json() == {"text": "x"}


@pytest.mark.parametrize(
    "dead_key",
    [
        # Each of these answered `unknown key` on a real device. They are the
        # AWTRIX 3 names a port is most likely to reach for.
        "color",
        "background",
        "duration",
        "lifetime",
        "pos",
        "center",
        "noScroll",
        "scrollSpeed",
        "textOffset",
        "topText",
        "rainbow",
        "blinkText",
        "fadeText",
        "bar",
        "line",
        "gradient",
        "pushIcon",
    ],
)
def test_awtrix3_keys_are_gone(dead_key):
    """The model must not grow a field that the firmware would refuse."""
    assert dead_key not in NgPayload.model_fields
    aliases = {
        f.serialization_alias for f in NgPayload.model_fields.values() if f.serialization_alias
    }
    assert dead_key not in aliases


def test_icon_mode_rejects_an_awtrix3_value():
    """AWTRIX 3 wrote `pushIcon: 2`; NG wants a named mode."""
    with pytest.raises(ValidationError):
        NgPayload(icon_mode="2")


def test_text_case_accepts_only_measured_values():
    for value in ("inherit", "upper", "asTyped"):
        assert NgPayload(text_case=value).to_json()["textCase"] == value
    with pytest.raises(ValidationError):
        NgPayload(text_case="lower")


def test_scroll_is_an_object_with_its_own_aliases():
    payload = NgPayload(scroll=Scroll(mode="wrap", when_fits="static", hold_ms=1000, speed=100))
    assert payload.to_json()["scroll"] == {
        "mode": "wrap",
        "whenFits": "static",
        "holdMs": 1000,
        "speed": 100,
    }


def test_scroll_refuses_an_unknown_sub_key():
    """The device answers `unknown field` on `scroll.zz`; so do we, earlier."""
    with pytest.raises(ValidationError):
        Scroll(zz=1)


def test_draw_commands_are_checked_here():
    """The firmware knows six commands and refuses the rest by name."""
    assert NgPayload(draw=[["pixel", 0, 0, "#fff"]]).to_json()["draw"] == [
        ["pixel", 0, 0, "#fff"]
    ]
    with pytest.raises(ValidationError, match="unknown draw command"):
        NgPayload(draw=[["fillRect", 0, 0, 1, 1]])


def test_a_draw_command_is_an_array_not_an_object():
    with pytest.raises(ValidationError):
        NgPayload(draw=[{"type": "pixel"}])


def test_progress_is_clamped_by_us_not_by_the_firmware():
    """Measured: the device answers {"ok": true} to {"progress": 500}. The
    bound is ours, and it is the only thing standing between a bad value and
    an arbitrary bar on the matrix."""
    with pytest.raises(ValidationError):
        NgPayload(progress=500)


def test_notification_only_keys_stay_out_of_an_app_payload():
    """All six answered `unknown key` on the pushed-app route."""
    for key in ("hold", "stack", "wakeup", "sound", "sound_rtttl", "sound_loop"):
        assert key not in NgPayload.model_fields
        assert key in NgNotification.model_fields


def test_notification_serialises_its_own_keys():
    payload = NgNotification(text="x", sound_rtttl="two:d=4,o=5,b=100:c", sound_loop=True)
    assert payload.to_json() == {
        "text": "x",
        "soundRtttl": "two:d=4,o=5,b=100:c",
        "soundLoop": True,
    }
