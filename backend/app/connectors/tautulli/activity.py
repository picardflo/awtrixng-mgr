"""What Tautulli answers, and what of it fits on thirty-two pixels.

Tautulli is the statistics companion to a Plex server. One command is enough
here — `get_activity`, which lists what is playing right now — and it is
reached over a single HTTP call with the key in the query string.

**The titles are the whole design problem.** Measured against this household's
own server before any of this was written:

    full_title        "Naruto Shippuden Yabai - Les Kage entrent en scène"
                      50 characters, 185 columns, 11 s to scroll past once
    grandparent_title "Naruto Shippuden Yabai"      22 characters, 5.7 s
    S03E16                                           6 characters, static

The panel is 32 columns, 23 of them left beside an icon. So everything but the
season-and-episode form scrolls, and the full title scrolls for longer than a
widget's turn lasts — the app hands over in the middle of a word. Both forms
are offered, with the consequence written next to each.
"""

from datetime import datetime
from typing import Any

import httpx

from app.core.errors import ConnectorError

#: Plex's own orange, as the clock draws it.
COLOUR = "#e5a00d"

#: The chevron with a play badge, and the same with a pause badge. The icon
#: carries the state, so the text does not have to spend characters on it —
#: and on this panel a character costs about a fifth of the room.
ICON_PLAYING = "45669"
ICON_PAUSED = "45672"
#: Buffering: the player is neither playing nor stopped, and saying so matters
#: more than it looks. A stream stuck buffering is the symptom of a server
#: that cannot keep up.
ICON_BUFFERING = "45670"

#: Now-playing is worth asking for often; it is one small call to a machine on
#: the same network.
CACHE_SECONDS = 30


def icon_for(state: str) -> str:
    return {"playing": ICON_PLAYING, "paused": ICON_PAUSED}.get(state, ICON_BUFFERING)


async def fetch(client: httpx.AsyncClient, base_url: str, api_key: str) -> dict[str, Any]:
    """`get_activity`, with the failures a home server actually produces.

    Each is named rather than collapsed into "unreachable": a wrong key, a
    stopped container and a certificate the client refuses look identical from
    a widget that has gone blank, and they need three different fixes.
    """
    url = base_url.rstrip("/") + "/api/v2"
    try:
        response = await client.get(url, params={"apikey": api_key, "cmd": "get_activity"})
    except httpx.HTTPError as exc:
        raise ConnectorError(
            f"Tautulli is unreachable: {exc or type(exc).__name__}",
            code="tautulli.unreachable",
            params={"reason": str(exc) or type(exc).__name__},
        ) from exc

    if response.status_code in (401, 403):
        raise ConnectorError(
            "Tautulli refused the API key.", code="tautulli.bad_key"
        )
    if response.status_code >= 400:
        raise ConnectorError(
            f"Tautulli answered {response.status_code}.",
            code="tautulli.rejected",
            params={"status": response.status_code},
        )

    try:
        body = response.json()["response"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ConnectorError(
            "Tautulli returned something that is not its usual answer.",
            code="tautulli.bad_response",
        ) from exc

    if body.get("result") != "success":
        # Tautulli answers 200 with result="error" for a bad key, so the
        # status code alone is not enough to tell success from refusal.
        message = str(body.get("message") or "")
        if "apikey" in message.lower() or "api key" in message.lower():
            raise ConnectorError(
                "Tautulli refused the API key.", code="tautulli.bad_key"
            )
        raise ConnectorError(
            f"Tautulli refused the request: {message}",
            code="tautulli.refused",
            params={"reason": message},
        )

    return body.get("data") or {}


def sessions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    found = raw.get("sessions")
    return [s for s in found if isinstance(s, dict)] if isinstance(found, list) else []


def episode_code(session: dict[str, Any]) -> str | None:
    """"S03E16", or None for anything that is not an episode.

    Zero-padded to two digits, which is what a reader expects and what keeps
    the width of the widget from changing between episode 9 and episode 10.
    """
    season, episode = session.get("parent_media_index"), session.get("media_index")
    try:
        return f"S{int(season):02d}E{int(episode):02d}"
    except (TypeError, ValueError):
        return None


def label(session: dict[str, Any]) -> str:
    """The short form: an episode code, or the year for a film.

    Never empty — a widget whose text resolves to nothing shows an icon and a
    bar floating over black, which reads as a fault rather than as a film with
    no year.
    """
    code = episode_code(session)
    if code:
        return code
    year = str(session.get("year") or "").strip()
    return year or "PLEX"


def percent(session: dict[str, Any]) -> int | None:
    try:
        return max(0, min(100, int(float(session["progress_percent"]))))
    except (KeyError, TypeError, ValueError):
        return None


def rotate(found: list[dict[str, Any]], now: datetime, every: int) -> dict[str, Any] | None:
    """Which stream to show, when several are playing.

    Florian's choice: one widget that moves from one stream to the next rather
    than one widget per viewer. It rotates on the clock, not on a counter, so
    it needs no stored state and two displays showing the same widget stay in
    step with each other.

    `every` is the widget's own refresh interval, so the stream changes once
    per collection — any faster and it would change while being read.
    """
    if not found:
        return None
    if len(found) == 1:
        return found[0]
    step = max(1, every)
    return found[int(now.timestamp() // step) % len(found)]
