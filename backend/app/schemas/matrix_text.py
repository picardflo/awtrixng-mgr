"""How a line of text is presented on the matrix.

**Shared by widgets and reminders, deliberately.** The two declared their own
sets and drifted: a widget could choose its font, its letter case and what its
icon does beside scrolling text; a reminder could choose none of them, for no
reason anybody could state. Florian found it from the outside — « comme pour
les widgets, je dois pouvoir choisir la taille du texte ».

One definition is also the only way the two stay aligned. A new option added
here appears in both, and `tests/test_frontend_contract.py` checks that both
forms offer it — which a second copy of the list could not do.

Every option below was measured on the display **on both routes**, because a
pushed app and a notification are not the same endpoint and acceptance is not
proof: this firmware answers `{"ok": true}` to `DELETE /api/v1/apps/Battery`
and changes nothing. What is kept here is what moved pixels on
`PUT /api/v1/apps/pushed/<name>` *and* on `POST /api/v1/notifications`.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.ng.payload import Font, IconMode, TextCase

#: Measured on the device: anything else answers "unknown value" on
#: scroll.mode / scroll.whenFits.
ScrollMode = Literal["wrap", "bounce", "static", "loop"]
ScrollWhenFits = Literal["static", "scroll"]


class MatrixText(BaseModel):
    """What anyone writing to the matrix may choose about how it looks."""

    background: str | None = None

    #: An animation the firmware draws *behind* the text — the display lists
    #: what it has in `GET /api/v1/capabilities`. Measured on both routes.
    #:
    #: Worth saying out loud: some of them fill the panel. `Matrix` and
    #: `Plasma` light every pixel and the text is read against them rather
    #: than on black. `TwinklingStars` sits behind the words and leaves them
    #: legible. Which is why this is a free choice and not a shortlist — the
    #: one that works depends on the text.
    effect: str | None = None

    #: Weather drawn by the firmware *over* the text — rain, snow, drizzle,
    #: storm, thunder, frost. New in NG.
    #:
    #: None means nothing is drawn, unless something upstream proposes one: a
    #: weather widget reads it off the WMO code. A reminder has nothing
    #: upstream, so for it None simply means none.
    overlay: str | None = None

    #: How the icon behaves beside scrolling text. Was an integer 0/1/2.
    icon_mode: IconMode = "fixed"
    #: Was an integer 0/1/2. "inherit" follows the display's own setting,
    #: which on a stock display means capitals.
    text_case: TextCase = "inherit"

    #: `large` draws seven rows instead of five — and the seven above the
    #: progress bar, so a number can fill the panel and keep its bar. Measured
    #: on a TC001: a two-digit figure with an icon and a bar still fits in the
    #: 32 columns. AWTRIX 3 had one font and no say in it.
    #:
    #: It buys no width: both fonts advance the same number of columns per
    #: character, so a message that scrolls in one scrolls in the other.
    font: Font = "small"

    #: What the text does when it does not fit the panel.
    scroll_mode: ScrollMode = "wrap"
    scroll_speed: int = Field(default=100, ge=0, le=500)
    #: What it does when it *does* fit. "static" leaves it still, which is
    #: what anyone expects of a short word.
    scroll_when_fits: ScrollWhenFits = "static"
