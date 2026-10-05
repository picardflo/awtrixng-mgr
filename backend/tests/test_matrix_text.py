"""What reaches the matrix.

The firmware's font has no accented letters: it draws a question mark instead,
so "décroissante" arrived as "d?croissante". Reported from a real display.
"""

import pytest

from app.schemas.widget_data import DisplayOptions, WidgetData
from app.widgets import template
from app.widgets.renderer import render


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Lune gibbeuse décroissante", "Lune gibbeuse decroissante"),
        ("Dégagé", "Degage"),
        ("Orage et grêle", "Orage et grele"),
        ("Bruine verglaçante", "Bruine verglacante"),
        ("Plutôt dégagé", "Plutot degage"),
        ("Grésil", "Gresil"),
    ],
)
def test_accents_are_stripped(given, expected):
    assert template.for_matrix(given) == expected


def test_the_degree_sign_survives():
    """It is not an accent and the font draws it — a plain ASCII filter would
    have eaten it, and every temperature widget with it."""
    assert template.for_matrix("20°") == "20°"
    assert template.for_matrix("-3.5°C") == "-3.5°C"


def test_ligatures_are_spelled_out():
    """No combining mark to drop, so they need saying."""
    assert template.for_matrix("Cœur") == "Coeur"
    assert template.for_matrix("Straße") == "Strasse"


def test_plain_text_is_left_alone():
    for text in ("80%", "Waning Gibbous", "12 km/h", "", "ng000007"):
        assert template.for_matrix(text) == text


def test_the_pushed_text_is_stripped_but_the_data_is_not():
    """The interface keeps proper French; only the hardware gets less."""
    data = WidgetData(values={"phase": "Lune gibbeuse décroissante"})
    payload = render(data, DisplayOptions(text="{{ phase }}"), lifetime_seconds=60)

    assert payload.to_json()["text"] == "Lune gibbeuse decroissante"
    assert data.values["phase"] == "Lune gibbeuse décroissante"


def test_a_user_typed_accent_is_handled_too():
    """Not only our own labels: whatever someone writes in a template."""
    payload = render(
        WidgetData(values={}), DisplayOptions(text="Café à 5€"), lifetime_seconds=60
    )
    assert "?" not in payload.to_json()["text"]
    assert payload.to_json()["text"].startswith("Cafe a ")
