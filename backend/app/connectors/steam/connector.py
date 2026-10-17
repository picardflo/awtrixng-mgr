"""Steam: what you are playing, and how far through its achievements you are.

Two widgets, as the shape of the data suggests rather than as a menu of
everything the API offers. `api.py` holds the measurements and the one
deliberate absence — there is no unread-messages widget here because Steam
publishes no endpoint that could feed one.
"""

from typing import Any

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.registry import register
from app.connectors.steam import api
from app.core.errors import ConnectorError
from app.schemas.fields import FormField, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData


@register
class SteamConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="steam",
        name="Steam",
        description="The game you are in, and how far through its achievements you are.",
        icon="steam",
        requires_credentials=True,
        config_schema=[
            FormField(
                name="steam_id",
                label="Profile",
                type="text",
                required=True,
                placeholder="76561197960435530",
                # Nobody knows their own seventeen digits, and everybody can
                # copy their profile URL. Both are accepted, and a whole URL
                # is reduced to its last segment rather than refused.
                help=(
                    "Your SteamID64, or the name at the end of your profile "
                    "URL. Pasting the whole URL works too."
                ),
            ),
            FormField(
                name="api_key",
                label="Web API key",
                type="secret",
                required=True,
                help=(
                    "Free, from steamcommunity.com/dev/apikey. Stored "
                    "encrypted. Your profile's game details must be Public."
                ),
            ),
        ],
        widgets=[
            WidgetDescriptor(
                type="steam.playing",
                name="In game",
                description="The game running right now, and nothing when there is none.",
                variables=[
                    Variable(
                        name="game",
                        label="Game — half of them scroll, about 5 s on average",
                        example="Baldur's Gate 3",
                    ),
                    Variable(
                        name="short",
                        label="Shortened: no publisher, no subtitle — fits a turn",
                        example="Civilization VI",
                    ),
                    Variable(name="player", label="Your display name", example="someone"),
                    Variable(
                        name="state",
                        label="playing, online, away, busy, snooze or offline",
                        example="playing",
                    ),
                    Variable(name="appid", label="The game's Steam ID", example="1086940"),
                    Variable(name="server", label="Server being played on, if any", example=""),
                ],
                # Eight seconds, the ordinary turn — and that is the
                # measurement talking. The Plex widget had to be stretched to
                # fourteen because an episode title needs eleven seconds to
                # pass; a game name needs five on average, and three titles in
                # four finish inside a normal turn. See api.py.
                default_display=DisplayOptions(
                    text="{{ game }}",
                    duration=8,
                    font="small",
                    # Not in a game is not a reading of nothing: the widget
                    # leaves the rotation rather than showing an empty slot.
                    hide_when_empty=True,
                ),
                default_refresh=api.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={
                        "game": "Baldur's Gate 3",
                        "short": "Baldur's Gate 3",
                        "player": "someone",
                        "state": "playing",
                        "appid": "1086940",
                        "server": "",
                    },
                    hint_icon=api.ICON_STEAM,
                    hint_color=api.COLOUR,
                ),
            ),
            WidgetDescriptor(
                type="steam.achievements",
                name="Achievements",
                description="Unlocked out of the total, for the game you are in.",
                variables=[
                    Variable(name="unlocked", label="Unlocked", example="23"),
                    Variable(name="total", label="Total in this game", example="49"),
                    Variable(name="remaining", label="Still to unlock", example="26"),
                    Variable(name="percent", label="Completion (%)", example="47"),
                    Variable(name="game", label="The game they belong to", example="Hades"),
                    Variable(name="short", label="Its shortened name", example="Hades"),
                ],
                # The one widget in this connector with something real to draw
                # a bar against: a fraction of a known total is exactly what a
                # progress bar is for. And a bar means the large font — the
                # small one leaves row 6 blank above it (test_renderer.py).
                default_display=DisplayOptions(
                    text="{{ unlocked }}/{{ total }}",
                    duration=8,
                    font="large",
                    show_progress=True,
                    hide_when_empty=True,
                ),
                default_refresh=api.ACHIEVEMENTS_CACHE_SECONDS,
                sample_data=WidgetData(
                    values={
                        "unlocked": 23, "total": 49, "remaining": 26,
                        "percent": 47, "game": "Hades", "short": "Hades",
                    },
                    progress=47,
                    hint_icon=api.ICON_TROPHY,
                    hint_color=api.COLOUR,
                ),
            ),
        ],
    )

    # -- Configuration --------------------------------------------------------

    def _key(self) -> str:
        key = str(self.secrets.get("api_key") or "").strip()
        if not key:
            raise ConnectorError("Give this service its Web API key.", code="steam.no_key")
        return key

    def _typed_id(self) -> str:
        who = str(self.config.get("steam_id") or "").strip()
        if not who:
            raise ConnectorError("Give this service a Steam profile.", code="steam.no_id")
        return who

    # -- Collection -----------------------------------------------------------

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        # The two widgets do *not* share a key, and that is deliberate: the
        # achievements one needs a second call that depends on the first, so
        # pretending they are the same request would cache the wrong thing.
        if widget_type == "steam.achievements":
            return (
                f"steam:achievements:{self._typed_id()}",
                api.ACHIEVEMENTS_CACHE_SECONDS,
            )
        return (f"steam:summary:{self._typed_id()}", api.CACHE_SECONDS)

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        key = self._key()
        who = await api.steam_id(self.client, key, self._typed_id())
        try:
            player = await api.summary(self.client, key, who)
        except ConnectorError as exc:
            # The summary is the call a bad key fails at, since it needs no
            # permission beyond the key itself.
            raise _as_bad_key(exc) from exc

        raw: dict[str, Any] = {"player": player}
        if widget_type == "steam.achievements":
            appid = str(player.get("gameid") or "").strip()
            raw["stats"] = (
                await api.achievements(self.client, key, who, appid) if appid else None
            )
        return raw

    async def test_connection(self) -> ConnectorTestResult:
        try:
            key = self._key()
            who = await api.steam_id(self.client, key, self._typed_id())
            player = await api.summary(self.client, key, who)
        except ConnectorError as exc:
            exc = _as_bad_key(exc) if exc.code == "steam.forbidden" else exc
            return ConnectorTestResult(
                ok=False, message=exc.message, code=exc.code, params=exc.params
            )

        name = str(player.get("personaname") or who)
        game = str(player.get("gameextrainfo") or "").strip()
        if game:
            return ConnectorTestResult(
                ok=True,
                message=f"Connected as {name}, playing {game}.",
                code="steam.ok_playing",
                params={"name": name, "game": game},
            )
        # Not playing is a success. Naming the profile is what proves the key
        # worked — an empty "ok" proves nothing a typo could not also produce.
        return ConnectorTestResult(
            ok=True,
            message=f"Connected as {name}. Not in a game right now.",
            code="steam.ok",
            params={"name": name},
        )

    # -- Projection -----------------------------------------------------------

    def project(self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]) -> WidgetData:
        player = raw.get("player") or {}
        game = str(player.get("gameextrainfo") or "").strip()

        if widget_type == "steam.achievements":
            return self._achievements(game, raw.get("stats"))

        if not game:
            # Online but idle still counts as nothing to show: the widget is
            # about the game, and the persona state is there for anyone who
            # wants to template something else out of it.
            return WidgetData(
                values={
                    "game": "", "short": "", "appid": "",
                    "player": str(player.get("personaname") or ""),
                    "state": api.STATES.get(_int(player.get("personastate")) or 0, "offline"),
                    "server": "",
                },
                status="empty",
                hint_color=api.COLOUR,
            )

        return WidgetData(
            values={
                "game": game,
                "short": api.short_title(game),
                "appid": str(player.get("gameid") or ""),
                "player": str(player.get("personaname") or ""),
                "state": "playing",
                "server": str(player.get("gameserverip") or ""),
            },
            hint_icon=api.ICON_STEAM,
            hint_color=api.COLOUR,
        )

    def _achievements(self, game: str, stats: dict[str, Any] | None) -> WidgetData:
        counted = api.counted(stats or {}) if stats else None
        if not game or counted is None:
            # Three ways to land here — not playing, a game that keeps no
            # achievements, a profile hiding its details — and all three mean
            # the same thing to a rotation: nothing to show.
            return WidgetData(values={}, status="empty", hint_color=api.COLOUR)

        unlocked, total = counted
        percent = round(unlocked * 100 / total) if total else 0
        return WidgetData(
            values={
                "unlocked": unlocked,
                "total": total,
                "remaining": total - unlocked,
                "percent": percent,
                "game": game,
                "short": api.short_title(game),
            },
            progress=percent,
            hint_icon=api.ICON_TROPHY,
            hint_color=api.COLOUR,
        )


def _as_bad_key(exc: ConnectorError) -> ConnectorError:
    """A refusal on the summary call can only be the key.

    Steam answers 403 for a revoked key and for a private profile alike, but
    `GetPlayerSummaries` needs no permission on the profile — it is the call
    that works on strangers. So at this point the key is the only candidate,
    and saying so saves someone hunting through their privacy settings.
    """
    if exc.code != "steam.forbidden":
        return exc
    return ConnectorError("Steam refused the Web API key.", code="steam.bad_key")


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
