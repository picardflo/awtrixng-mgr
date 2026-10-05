"""Drawing the display's framebuffer in a terminal.

`GET /api/v1/display/screen` hands back what the matrix is *actually* showing,
which is the one thing worth looking at: not the payload we believe we sent,
but the pixels that came of it. AWTRIX 3 had the same route; what is new is
that there is now something to compare against, since NG refuses a bad payload
instead of rendering something approximate.

Two rows of pixels share one row of text, using the upper-half block: the
foreground colour draws the top pixel and the background colour the bottom
one. A 32x8 matrix therefore comes out as 4 lines of 32 characters, which is
roughly square on a normal terminal. Drawing one block per pixel instead would
produce an image twice as tall as the clock.
"""

#: Panels are 32x8 on a TC001; NG supports wider ones, so the width is read
#: from the device rather than assumed.
DEFAULT_WIDTH = 32


def unpack(colour: int) -> tuple[int, int, int]:
    """A packed RGB integer, as the firmware sends it, into components."""
    return (colour >> 16) & 0xFF, (colour >> 8) & 0xFF, colour & 0xFF


def render(pixels: list[int], width: int = DEFAULT_WIDTH) -> str:
    """The framebuffer as ANSI truecolor text, ready to print.

    An odd number of rows is tolerated: the missing bottom row is drawn black,
    which is what an unlit pixel looks like anyway.
    """
    if width <= 0:
        raise ValueError("width must be positive")

    rows = [pixels[start : start + width] for start in range(0, len(pixels), width)]
    lines = []
    for top_index in range(0, len(rows), 2):
        top = rows[top_index]
        bottom = rows[top_index + 1] if top_index + 1 < len(rows) else [0] * width
        line = []
        for column in range(width):
            tr, tg, tb = unpack(top[column] if column < len(top) else 0)
            br, bg, bb = unpack(bottom[column] if column < len(bottom) else 0)
            line.append(f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m▀")
        lines.append("".join(line) + "\x1b[0m")
    return "\n".join(lines)


def is_blank(pixels: list[int]) -> bool:
    """True when nothing is lit — a dark matrix, or a display asleep."""
    return not any(pixels)
