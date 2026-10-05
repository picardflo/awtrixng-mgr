"""Drawing the framebuffer.

The renderer is the only place where a wrong byte turns into a wrong picture
silently, so its geometry is pinned here rather than judged by eye.
"""

import pytest

from app.services.ng import matrix

RED = 0xFF0000
GREEN = 0x00FF00
BLUE = 0x0000FF


def test_unpack_splits_a_packed_colour():
    assert matrix.unpack(0xF5A524) == (0xF5, 0xA5, 0x24)
    assert matrix.unpack(0) == (0, 0, 0)


def test_two_pixel_rows_share_one_text_row():
    """Drawing one block per pixel would make the clock twice as tall as it
    is. The upper-half block puts the top pixel in the foreground and the
    bottom one in the background."""
    rendered = matrix.render([RED, GREEN, BLUE, 0], width=2)
    assert rendered.count("\n") == 0  # two rows of pixels, one row of text
    assert "\x1b[38;2;255;0;0m" in rendered  # top-left, foreground
    assert "\x1b[48;2;0;0;255m" in rendered  # bottom-left, background


def test_a_full_panel_comes_out_four_lines_tall():
    rendered = matrix.render([0] * (32 * 8))
    assert len(rendered.split("\n")) == 4


def test_an_odd_row_count_is_tolerated():
    """A truncated answer draws the missing row black, which is what an unlit
    pixel looks like anyway — better than refusing to show anything."""
    rendered = matrix.render([RED, GREEN], width=2)
    assert "\x1b[48;2;0;0;0m" in rendered


def test_every_line_resets_the_colour():
    """Without the reset, the last pixel's colour bleeds into the prompt."""
    for line in matrix.render([0] * 64, width=32).split("\n"):
        assert line.endswith("\x1b[0m")


def test_a_zero_width_is_refused():
    with pytest.raises(ValueError):
        matrix.render([RED], width=0)


def test_is_blank_spots_a_dark_matrix():
    assert matrix.is_blank([0] * 256)
    assert not matrix.is_blank([0] * 255 + [1])
