"""What a connector produces and what the user chooses.

These two objects meet in the renderer, which is a pure function. Keeping them
free of any AWTRIX notion is what makes a connector unaware of the display
(§32.8).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import utcnow
from app.services.ng.payload import IconMode, TextCase

#: Measured on the device: anything else answers "unknown value" on
#: scroll.mode / scroll.whenFits.
ScrollMode = Literal["wrap", "bounce", "static", "loop"]
ScrollWhenFits = Literal["static", "scroll"]

#: "empty" is not a failure: no Plex stream playing is a normal state, and the
#: widget may legitimately hide instead of showing stale data.
DataStatus = Literal["ok", "empty", "degraded"]


class WidgetData(BaseModel):
    """A connector's output. Knows nothing about matrices or colours."""

    #: Template variables, exposed to the user as {{ name }}.
    values: dict[str, Any] = Field(default_factory=dict)
    status: DataStatus = "ok"

    #: Suggestions the user may override in the display options.
    hint_icon: str | None = None
    hint_color: str | None = None
    #: Weather for the firmware to draw over the app — AWTRIX NG only, and
    #: usually None. A connector proposes it the way it proposes an icon; the
    #: display options can override it or turn it off.
    hint_overlay: str | None = None

    progress: int | None = Field(default=None, ge=0, le=100)
    series: list[float] | None = None

    fetched_at: datetime = Field(default_factory=utcnow)


class DisplayOptions(BaseModel):
    """The user's presentation choices. Simple mode first, advanced after.

    `extra="forbid"`, deliberately. A `center=True` left behind in a connector
    survived this port because Pydantic drops unknown keys in silence — the
    very behaviour this project left AWTRIX 3 to escape. The firmware now
    names the field it refuses; so does this.

    These are AWTRIX NG's own notions, not AWTRIX 3's renamed. Three options
    the previous project offered have no equivalent here and are gone rather
    than kept as controls that do nothing:

    - **`center`** — NG has no centring key. Text that fits is drawn by the
      firmware according to `scroll_when_fits`.
    - **`no_scroll`** — replaced by `scroll_mode="static"`, which says the same
      thing in the firmware's own vocabulary.
    - **`rainbow`** — measured: `palette` colours *effects*, not text. Pushing
      `{"text": "ARC", "palette": "Rainbow"}` and reading the matrix back gave
      a single colour. There is no rainbow text in NG.

    Keeping a control whose value the firmware ignores is the mistake that
    cost an hour on the previous project with `{{ quality_code }}`.
    """

    model_config = ConfigDict(extra="forbid")

    # -- Simple ---------------------------------------------------------------
    text: str = "{{ value }}"
    #: None means "let the connector choose", which is what most people want.
    #: An explicit id overrides it. To show *no* icon, use show_icon.
    icon: str | None = None
    #: An 8x8 icon costs 9 of the 32 columns. Turning it off is the only way to
    #: get the whole width for text.
    show_icon: bool = True
    color: str | None = None
    #: Seconds, converted to the firmware's milliseconds on the way out. The
    #: unit stays human here: nobody thinks of an app's turn in milliseconds.
    duration: int = Field(default=7, ge=1, le=120)

    # -- Advanced -------------------------------------------------------------
    background: str | None = None
    effect: str | None = None
    #: Weather drawn by the firmware *over* the text — rain, snow, drizzle,
    #: storm, thunder, frost. New in NG, and the device lists what it supports
    #: in GET /api/v1/capabilities.
    #:
    #: None means "let the connector choose", exactly as for `icon`: the
    #: weather connector proposes one from the WMO code and most connectors
    #: propose nothing. To have none at all, use `show_overlay`.
    overlay: str | None = None
    #: An overlay costs no horizontal space, but it does move, and a widget
    #: read at a glance may be better still. This is the way to say so.
    show_overlay: bool = True
    repeat: int | None = None

    #: How the icon behaves beside scrolling text. Was an integer 0/1/2.
    icon_mode: IconMode = "fixed"
    #: Was an integer 0/1/2. "inherit" follows the display's own setting.
    text_case: TextCase = "inherit"

    #: What the text does when it does not fit the panel.
    scroll_mode: ScrollMode = "wrap"
    scroll_speed: int = Field(default=100, ge=0, le=500)
    #: What it does when it *does* fit. "static" leaves it still, which is
    #: what anyone expects of a short word.
    scroll_when_fits: ScrollWhenFits = "static"

    show_progress: bool = False
    #: Filled part. None leaves the firmware's own colour.
    progress_color: str | None = None
    #: Unfilled part. **Not** the firmware default, which is white: at 2 % the
    #: whole bottom row lights up and reads as 100 %. Black means only the
    #: filled part is lit, which cannot mislead.
    progress_background: str = "#000000"
    show_series: Literal["none", "bar", "line"] = "none"

    #: When the connector reports "empty", remove the app instead of leaving a
    #: stale value on the matrix.
    hide_when_empty: bool = True
