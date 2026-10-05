"""The CLI's contract: what it refuses, and what it sends.

The refusal matters more than the rest. A development tool pointed at the
wrong display by a stale shell-history line is exactly how the previous
project lost a live display's apps.
"""

import respx

from app.cli import main

BASE = "http://display.test"


def test_no_host_is_an_error_not_a_default(capsys):
    """Guessing a display to talk to would be the worst possible default."""
    assert main(["info"]) == 2
    assert "aucun afficheur" in capsys.readouterr().err


def test_writing_to_a_protected_display_is_refused(capsys, monkeypatch):
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "display.test")
    with respx.mock:
        pushed = respx.put(f"{BASE}/api/v1/apps/pushed/cli")
        assert main(["--host", "display.test", "push", "hello"]) == 3
        # The point of the guard: nothing left the machine.
        assert not pushed.called
    assert "refusé" in capsys.readouterr().err


def test_reading_a_protected_display_is_allowed(monkeypatch):
    """The guard is about writing. Looking at a display in service is how you
    find out what it is doing."""
    monkeypatch.setenv("AWTRIXNG_PROTECTED_HOSTS", "display.test")
    with respx.mock:
        respx.get(f"{BASE}/api/v1/display/screen").respond(
            json={"width": 32, "height": 8, "pixels": [0] * 256}
        )
        assert main(["--host", "display.test", "screen"]) == 0


@respx.mock
def test_push_sends_the_measured_key_names(capsys):
    route = respx.put(f"{BASE}/api/v1/apps/pushed/cli").respond(json={"ok": True})
    assert main(["--host", "display.test", "push", "SALUT", "--color", "#f5a524"]) == 0
    assert route.calls.last.request.read() == b'{"text":"SALUT","textColor":"#f5a524"}'


@respx.mock
def test_push_can_switch_to_what_it_just_pushed(capsys):
    respx.put(f"{BASE}/api/v1/apps/pushed/cli").respond(json={"ok": True})
    switch = respx.put(f"{BASE}/api/v1/apps/active").respond(json={"ok": True})
    assert main(["--host", "display.test", "push", "x", "--switch"]) == 0
    assert switch.calls.last.request.read() == b'{"name":"cli"}'


@respx.mock
def test_a_missing_icon_does_not_stop_the_push(capsys):
    """Text without its icon still beats a blank matrix."""
    respx.get(f"{BASE}/api/v1/files").respond(json={"files": []})
    respx.get("https://developer.lametric.com/content/apps/icon_thumbs/999999").respond(404)
    pushed = respx.put(f"{BASE}/api/v1/apps/pushed/cli").respond(json={"ok": True})

    assert main(["--host", "display.test", "push", "x", "--icon", "999999"]) == 0
    assert pushed.called
    assert "on pousse quand même" in capsys.readouterr().err


@respx.mock
def test_a_rejected_payload_reports_the_field(capsys):
    """The firmware names what it refused; losing that on the way to the
    terminal would waste the whole point of NG's validation."""
    respx.put(f"{BASE}/api/v1/apps/pushed/cli").respond(
        422,
        json={"error": {"code": "validationFailed", "message": 'unknown key "color"',
                        "field": "color"}},
    )
    assert main(["--host", "display.test", "push", "x"]) == 1
    assert "color" in capsys.readouterr().err


@respx.mock
def test_an_unreachable_display_is_not_a_crash(capsys):
    respx.get(f"{BASE}/api/v1/device").respond(500)
    assert main(["--host", "display.test", "info"]) == 1
    assert "erreur" in capsys.readouterr().err


@respx.mock
def test_apps_shows_where_each_app_comes_from(capsys):
    respx.get(f"{BASE}/api/v1/apps").respond(
        json=[
            {"name": "Time", "origin": "builtin", "inLoop": True},
            {"name": "ng000001", "origin": "pushed", "inLoop": False},
        ]
    )
    assert main(["--host", "display.test", "apps"]) == 0
    out = capsys.readouterr().out
    assert "builtin" in out and "pushed" in out


@respx.mock
def test_screen_says_so_when_nothing_is_lit(capsys):
    """A dark matrix and a broken read look identical otherwise."""
    respx.get(f"{BASE}/api/v1/display/screen").respond(
        json={"width": 32, "height": 8, "pixels": [0] * 256}
    )
    assert main(["--host", "display.test", "screen"]) == 0
    assert "éteinte" in capsys.readouterr().err
