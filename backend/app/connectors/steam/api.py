"""What Steam answers, and what of it fits on thirty-two pixels.

Two endpoints of the public Web API, both plain GETs with the key in the
query string:

    ISteamUser/GetPlayerSummaries      who you are, and the game if you are in one
    ISteamUserStats/GetPlayerAchievements   that game's achievements, one by one

**The titles were measured before any of this was written**, against the
transcribed panel font and the scroll rate pinned by the Plex work — the
lesson from that connector being that a guess at text width was five times
short. Twenty-four of the most-played titles on Steam:

    median                 53 columns   5.0 s to scroll past once
    "Hades", "Rust"        <= 23        static, no scroll at all
    "Baldur's Gate 3"      53 columns   5.0 s
    "Red Dead Redemption 2"  75         6.4 s
    "Skyrim Special Edition" 149        11.3 s

So, unlike a Plex episode title, a game name is **normally read in a single
turn**: three in four finish inside the eight seconds a widget gets, and the
default duration is left alone here. Only franchise names with a subtitle run
over, which is what `short` exists for — it takes the worst case from 11.3 s
down to 6.1 s and leaves "Baldur's Gate 3" alone, because the possessive
there is the title and not a publisher.

**What is not here, and cannot be:** unread messages. Steam publishes no
endpoint for chat, notifications or an unread count — not in `ISteamUser`,
not in `ISteamFriends`. The only routes are the client's own interfaces or a
scraped session cookie, neither of which belongs in a connector.
"""

import re
from typing import Any

import httpx

from app.core.errors import ConnectorError

BASE = "https://api.steampowered.com"

#: Steam's own light blue, the one the store draws links in. On a black panel
#: it reads at a glance and does not collide with any other connector here —
#: Plex owns the orange, the school calendar the greens.
COLOUR = "#66c0f4"

#: The Steam valve, and a trophy. Both chosen off the panel rather than off
#: the gallery listing: a search for "steam" returns eleven icons and nine of
#: them are a puff of vapour over a coffee cup.
ICON_STEAM = "49986"
ICON_TROPHY = "23334"

#: A persona summary is cheap and changes the moment a game launches, so it is
#: worth asking often. Achievements move far more slowly — but they do move
#: *during* a session, which is the one moment anybody looks at the widget, so
#: this is not stretched as far as it could be.
CACHE_SECONDS = 60
ACHIEVEMENTS_CACHE_SECONDS = 180

#: `personastate` as the API numbers it. Kept as stable English keywords
#: rather than prose: a connector returns data, and the interface translates
#: (ADR-012).
STATES = {
    0: "offline", 1: "online", 2: "busy", 3: "away",
    4: "snooze", 5: "trading", 6: "playing",
}

#: A SteamID64 is seventeen digits beginning 7656119. Anything else typed in
#: that box is taken for a vanity name and resolved.
_STEAM_ID64 = re.compile(r"^\d{17}$")

#: "Tom Clancy's", "Sid Meier's" — a person's name in two words, attached to
#: the title by a publisher. Not "Baldur's", which is one word and is the
#: title. Both apostrophes, because the store uses the typographic one.
_PUBLISHER = re.compile(r"^\S+\s+\S+['’]s\s+")


def looks_like_id64(value: str) -> bool:
    return bool(_STEAM_ID64.match(value.strip()))


def short_title(title: str) -> str:
    """The form that fits a turn: no trademarks, no publisher, no subtitle.

    Measured, not guessed — see the module docstring. Never returns empty: a
    title that is nothing but a subtitle keeps its full form rather than
    leaving the widget with an icon floating over black.
    """
    text = re.sub(r"\s+", " ", title.replace("®", "").replace("™", "").replace("©", "")).strip()
    text = _PUBLISHER.sub("", text)
    for separator in (":", " - ", " – "):
        cut = text.find(separator)
        if cut > 0:
            text = text[:cut]
    return text.strip() or title.strip()


async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """One call, with the failures Steam actually produces.

    Each is named rather than collapsed into "unreachable": a revoked key, a
    profile set to Friends Only and a mistyped ID all leave the widget blank
    and all need a different fix.
    """
    try:
        response = await client.get(f"{BASE}{path}", params=params)
    except httpx.HTTPError as exc:
        raise ConnectorError(
            f"Steam is unreachable: {exc or type(exc).__name__}",
            code="steam.unreachable",
            params={"reason": str(exc) or type(exc).__name__},
        ) from exc

    if response.status_code in (401, 403):
        # Steam answers 403 both for a bad key and for a profile whose
        # details are not public. The two are told apart by the caller, which
        # knows which of the two it just asked for.
        raise ConnectorError("Steam refused the request.", code="steam.forbidden")
    if response.status_code >= 400:
        raise ConnectorError(
            f"Steam answered {response.status_code}.",
            code="steam.rejected",
            params={"status": response.status_code},
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ConnectorError(
            "Steam returned something that is not its usual answer.",
            code="steam.bad_response",
        ) from exc
    if not isinstance(body, dict):
        raise ConnectorError(
            "Steam returned something that is not its usual answer.",
            code="steam.bad_response",
        )
    return body


async def resolve(client: httpx.AsyncClient, key: str, vanity: str) -> str:
    """A vanity name — the tail of steamcommunity.com/id/xxx — to a SteamID64.

    Offered because almost nobody knows their own seventeen digits, and the
    profile URL is the thing they can copy. Only called when what was typed
    is not already an ID, so the usual case costs nothing.
    """
    body = await _get(
        client, "/ISteamUser/ResolveVanityURL/v1/", {"key": key, "vanityurl": vanity}
    )
    found = body.get("response") or {}
    if found.get("success") == 1 and found.get("steamid"):
        return str(found["steamid"])
    raise ConnectorError(
        f"Steam knows no profile named {vanity}.",
        code="steam.unknown_player",
        params={"name": vanity},
    )


async def steam_id(client: httpx.AsyncClient, key: str, typed: str) -> str:
    typed = typed.strip().rstrip("/")
    # Pasting the whole profile URL is the obvious mistake, and refusing it
    # over a slash would be petty when the useful half is right there.
    if "/" in typed:
        typed = typed.rsplit("/", 1)[-1]
    return typed if looks_like_id64(typed) else await resolve(client, key, typed)


async def summary(client: httpx.AsyncClient, key: str, who: str) -> dict[str, Any]:
    """The player, as `GetPlayerSummaries` describes them right now."""
    body = await _get(client, "/ISteamUser/GetPlayerSummaries/v2/", {"key": key, "steamids": who})
    players = (body.get("response") or {}).get("players")
    if not isinstance(players, list) or not players:
        # An unknown ID is not an error to Steam: it answers 200 with an empty
        # list, which would otherwise read as "nothing playing" forever.
        raise ConnectorError(
            f"Steam knows no profile with the ID {who}.",
            code="steam.unknown_player",
            params={"name": who},
        )
    return players[0] if isinstance(players[0], dict) else {}


async def achievements(
    client: httpx.AsyncClient, key: str, who: str, appid: str
) -> dict[str, Any]:
    """The current game's achievements, or an explanation of why there are none.

    Three ordinary outcomes, and only one of them is a fault:

    - the game has achievements and this returns them;
    - the game has none at all, and Steam answers 400 — common, and not worth
      lighting up a service card in red;
    - the profile hides its game details, which is the one the user can fix.
    """
    try:
        body = await _get(
            client,
            "/ISteamUserStats/GetPlayerAchievements/v1/",
            {"key": key, "steamid": who, "appid": appid},
        )
    except ConnectorError as exc:
        if exc.code == "steam.rejected" and exc.params.get("status") == 400:
            return {"success": False, "reason": "no_stats"}
        if exc.code == "steam.forbidden":
            return {"success": False, "reason": "private"}
        raise

    stats = body.get("playerstats") or {}
    if not stats.get("success"):
        # Steam's own wording, and it is not the obvious one: a hidden profile
        # comes back as "Profile is not public", never as "private". Matching
        # on the word that is not there would have filed every hidden profile
        # under "this game keeps no score", which is a different fix for the
        # user. Both phrasings are accepted in case the wording moves.
        reason = str(stats.get("error") or "").lower()
        hidden = "not public" in reason or "private" in reason
        return {"success": False, "reason": "private" if hidden else "no_stats"}
    return {"success": True, "achievements": stats.get("achievements") or []}


def counted(stats: dict[str, Any]) -> tuple[int, int] | None:
    """(unlocked, total), or None when this game keeps no score.

    None rather than (0, 0): a game without achievements is not a game you
    have none of, and the difference decides whether the widget shows a bar
    at nought or steps out of the rotation entirely.
    """
    if not stats.get("success"):
        return None
    found = [a for a in stats.get("achievements") or [] if isinstance(a, dict)]
    if not found:
        return None
    return sum(1 for a in found if a.get("achieved")), len(found)
