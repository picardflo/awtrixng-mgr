"""The two themes, checked against each other.

Read as text from Python, like `test_frontend_contract.py` reads the forms,
and for the same reason: nothing in TypeScript watches a CSS custom property.
It lives here rather than in vitest because a stylesheet imported with `?raw`
comes back **compiled** — Tailwind has already run, and `@theme` no longer
exists in what the test would see. Reading the file off disk from the browser
suite would mean pulling in Node's type declarations for one assertion.

The fault being guarded against: a token declared in one block and forgotten
in the other. It is invisible until somebody switches, and then a muted grey
chosen against #171717 sits on #f5f4f1 as a smear nobody can read.
"""

import re
from pathlib import Path

import pytest

TOKENS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "theme" / "tokens.css"
)

#: Colours that are the matrix, not the page.
THE_PANEL = ("--color-pixel-off", "--color-matrix-bg")


def block(selector: str) -> dict[str, str]:
    """The variables declared inside the block a selector opens."""
    css = TOKENS.read_text(encoding="utf-8")
    start = css.find(selector)
    assert start > -1, f"{selector} is gone from tokens.css"
    open_at = css.index("{", start)
    close_at = css.index("\n}", open_at)
    return {
        name: value.strip()
        for name, value in re.findall(
            r"(--[a-z0-9-]+)\s*:\s*([^;]+);", css[open_at:close_at]
        )
    }


@pytest.fixture(scope="module")
def dark() -> dict[str, str]:
    return block("@theme")


@pytest.fixture(scope="module")
def light() -> dict[str, str]:
    return block(':root[data-theme="light"]')


def colours(theme: dict[str, str]) -> set[str]:
    return {name for name in theme if name.startswith("--color-")}


def test_both_define_every_colour(dark, light):
    assert len(colours(dark)) > 10, "the dark block looks empty — parser drift?"
    missing = sorted(colours(dark) - colours(light))
    assert not missing, f"declared dark and forgotten light: {missing}"


def test_the_light_theme_adds_nothing_the_dark_one_lacks(dark, light):
    """The other direction.

    A variable only the light block knows falls back to nothing at all in
    dark — transparent, or whatever was inherited — which is a fault that
    shows on the *default* theme while the one being worked on looks fine.
    """
    extra = sorted(colours(light) - colours(dark))
    assert not extra, f"declared light only: {extra}"


def test_every_colour_that_is_not_the_panel_changes(dark, light):
    """A value repeated identically in both is almost always one that was
    pasted and not thought about. The two exceptions are stated, not
    tolerated: an unlit LED is unlit at noon too."""
    same = sorted(
        name
        for name in colours(dark)
        if name not in THE_PANEL and light.get(name) == dark[name]
    )
    assert not same, f"identical in both themes: {same}"


@pytest.mark.parametrize("name", THE_PANEL)
def test_the_matrix_stays_dark_in_both(dark, light, name: str):
    for theme in (dark, light):
        value = theme[name]
        assert int(value[1:3], 16) < 0x40, f"{name} = {value}"


def test_it_is_awtrix_ngs_own_palette_not_an_impression_of_it(dark, light):
    """Read off the firmware, which serves its own interface:

        curl http://<clock>/ | grep -o -- '--[a-z]*: *#[0-9a-f]*'

    Pinned so that a later tidy-up of the greys has to be a decision rather
    than a drift. The states are deliberately **not** pinned: those are ours,
    and the reason is written at the top of `tokens.css`.
    """
    assert dark["--color-bg"] == "#171717"
    assert dark["--color-surface"] == "#222221"
    assert dark["--color-accent"] == "#f5a568"
    assert light["--color-bg"] == "#f5f4f1"
    assert light["--color-surface"] == "#ffffff"
    assert light["--color-accent"] == "#ac470f"
