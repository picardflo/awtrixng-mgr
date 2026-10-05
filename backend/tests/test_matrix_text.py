"""What reaches the matrix.

**This file used to assert the opposite.** AWTRIX 3's font had no accented
letters and drew a question mark instead, so "décroissante" arrived as
"d?croissante" — reported from a real display. The project stripped the
accents on the way out: imperfect French, but readable, which beats a line of
question marks on thirty-two pixels.

AWTRIX NG draws them. Measured on a TC001 by pushing each character on its own
and comparing the framebuffer against the one "?" produces — every accented
letter of French, the ligatures, the degree sign, the euro and the micro sign,
all drawn and none substituted.

So the workaround became the only reason a French label reached the display
misspelt, and these tests now pin its removal.
"""

import pytest

from app.schemas.widget_data import DisplayOptions, WidgetData
from app.widgets import template
from app.widgets.renderer import render


@pytest.mark.parametrize(
    "text",
    [
        "Lune gibbeuse décroissante",
        "Dégagé",
        "Orage et grêle",
        "Bruine verglaçante",
        "Plutôt dégagé",
        "Grésil",
        "Très élevé",
        "Modéré",
    ],
)
def test_accents_reach_the_matrix_untouched(text: str):
    """Every one of these was mangled before, and is drawn now."""
    assert template.for_matrix(text) == text


@pytest.mark.parametrize(
    "character",
    # Pushed one at a time to a TC001 on NG 1.1.2 and compared against the
    # bitmap of "?". Not one came back as a substitution.
    list("àâäéèêëîïôöùûüÿçÀÂÉÈÊËÎÔÙÛÇ") + ["œ", "Œ", "æ", "Æ", "°", "€", "µ"],
)
def test_every_character_the_display_draws_is_passed_through(character: str):
    assert template.for_matrix(character) == character


def test_ligatures_are_no_longer_spelled_out():
    """They were, for want of a glyph. The display has one."""
    assert template.for_matrix("Cœur") == "Cœur"


def test_plain_text_is_left_alone():
    for text in ("80%", "Waning Gibbous", "12 km/h", "", "ng000007"):
        assert template.for_matrix(text) == text


def test_a_rendered_widget_keeps_its_accents():
    """The boundary is where it always was; what changed is that it passes."""
    payload = render(
        WidgetData(values={"condition": "Plutôt dégagé"}),
        DisplayOptions(text="{{ condition }}"),
    )
    assert payload.to_json()["text"] == "Plutôt dégagé"
