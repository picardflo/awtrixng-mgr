"""Plex, through Tautulli: what is playing, and how many are watching.

Two widgets from one call. The interesting half of this connector is not the
API — it is one small GET — but what survives the trip to thirty-two pixels.
`activity.py` has the measurements; this file spends them.
"""

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.registry import register
from app.connectors.tautulli import activity
from app.core.errors import ConnectorError
from app.schemas.fields import FormField, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData

#: The full title needs eleven seconds to pass once, measured on a TC001.
#: A widget's usual turn is seven or eight, so the default is raised here and
#: nowhere else — every other widget in this project is read at a glance, and
#: this one is read like a sentence.
NOW_PLAYING_SECONDS = 14


@register
class TautulliConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="tautulli",
        name="Tautulli (Plex)",
        description="What is playing on Plex right now, and how many streams are open.",
        icon="tautulli",
        requires_credentials=True,
        config_schema=[
            FormField(
                name="url",
                label="Tautulli address",
                type="url",
                required=True,
                placeholder="https://tautulli.lan",
                help="The address you open in a browser, without /home.",
            ),
            FormField(
                name="api_key",
                label="API key",
                type="secret",
                required=True,
                help="Tautulli, Settings → Web Interface → API. Stored encrypted.",
            ),
            FormField(
                name="verify_tls",
                label="Verify the certificate",
                type="boolean",
                default=True,
                # A self-hosted Tautulli behind a private name usually carries
                # a certificate no browser trusts. Turning this off is the
                # ordinary case on a home network, and leaving it on by
                # default is still right: it should be a decision.
                help="Turn off for a self-signed certificate on your own network.",
            ),
        ],
        widgets=[
            WidgetDescriptor(
                type="tautulli.now_playing",
                name="Now playing",
                description="The stream in progress, with how far through it is.",
                variables=[
                    Variable(
                        name="title",
                        label="Full title — long, it scrolls for about 11 s",
                        example="Naruto Shippuden - Les Kage entrent en scène",
                    ),
                    Variable(
                        name="label",
                        label="Short form: S03E16, or the year for a film",
                        example="S03E16",
                    ),
                    Variable(name="show", label="Series or film", example="Naruto Shippuden"),
                    Variable(
                        name="episode",
                        label="Episode title",
                        example="Les Kage entrent en scène",
                    ),
                    Variable(name="season", label="Season number", example="3"),
                    Variable(name="number", label="Episode number", example="16"),
                    Variable(name="year", label="Year", example="2023"),
                    Variable(name="percent", label="Progress (%)", example="48"),
                    Variable(name="state", label="playing, paused or buffering", example="paused"),
                    Variable(name="user", label="Who is watching", example="someone"),
                    Variable(name="player", label="On what", example="Google TV"),
                    Variable(name="streams", label="Streams open in total", example="2"),
                ],
                # Florian's choice, against the advice: the whole title, with
                # the turn lengthened so it finishes. The measurement that
                # made it a choice rather than an oversight is in activity.py.
                default_display=DisplayOptions(
                    text="{{ title }}",
                    duration=NOW_PLAYING_SECONDS,
                    show_progress=True,
                    # Small, because the text is a sentence rather than a
                    # figure: see NARROW_ON_PURPOSE in tests/test_renderer.py.
                    font="small",
                    # It scrolls by construction, so there is nothing to
                    # decide about what happens when it fits.
                    hide_when_empty=True,
                ),
                default_refresh=activity.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={
                        "title": "Naruto Shippuden - Les Kage entrent en scène",
                        "label": "S03E16",
                        "show": "Naruto Shippuden",
                        "episode": "Les Kage entrent en scène",
                        "season": 3, "number": 16, "year": 2023,
                        "percent": 48, "state": "paused",
                        "user": "someone", "player": "Google TV", "streams": 1,
                    },
                    progress=48,
                    hint_icon=activity.ICON_PAUSED,
                    hint_color=activity.COLOUR,
                ),
            ),
            WidgetDescriptor(
                type="tautulli.streams",
                name="Active streams",
                description="How many are watching, and how many the server is transcoding.",
                variables=[
                    Variable(name="streams", label="Streams open", example="3"),
                    Variable(
                        name="transcoding",
                        label="Of those, transcoded — what makes a server sweat",
                        example="1",
                    ),
                    Variable(name="direct", label="Of those, played directly", example="2"),
                    Variable(name="bandwidth", label="Total bandwidth (kbps)", example="24000"),
                ],
                # Small, and not by taste. A number of streams is not a
                # fraction of anything — there is no ceiling to draw a bar
                # against — and the large font without something on the bottom
                # row sits one row high, measured on a TC001. The suite caught
                # this one the moment it was written.
                default_display=DisplayOptions(
                    text="{{ streams }}",
                    duration=8,
                    font="small",
                    hide_when_empty=True,
                ),
                default_refresh=activity.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={"streams": 3, "transcoding": 1, "direct": 2, "bandwidth": 24000},
                    hint_icon=activity.ICON_PLAYING,
                    hint_color=activity.COLOUR,
                ),
            ),
        ],
    )

    # -- Configuration --------------------------------------------------------

    def _url(self) -> str:
        url = str(self.config.get("url") or "").strip()
        if not url:
            raise ConnectorError("Give this service its Tautulli address.", code="tautulli.no_url")
        return url

    def _key(self) -> str:
        key = str(self.secrets.get("api_key") or "").strip()
        if not key:
            raise ConnectorError("Give this service its API key.", code="tautulli.no_key")
        return key

    # -- Collection -----------------------------------------------------------

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        # Both widgets read the same answer: two widgets must not mean two
        # round trips to the same server.
        return (f"tautulli:{self._url()}", activity.CACHE_SECONDS)

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        return await activity.fetch(self.client, self._url(), self._key())

    async def test_connection(self) -> ConnectorTestResult:
        try:
            raw = await activity.fetch(self.client, self._url(), self._key())
        except ConnectorError as exc:
            return ConnectorTestResult(
                ok=False, message=exc.message, code=exc.code, params=exc.params
            )

        found = activity.sessions(raw)
        # Nothing playing is a success, not a failure — and saying how many
        # there are proves the key works, which an empty "ok" does not.
        return ConnectorTestResult(
            ok=True,
            message=(
                f"Connected. {len(found)} stream(s) playing."
                if found
                else "Connected. Nothing playing right now."
            ),
            code="tautulli.ok",
            params={"streams": len(found)},
        )

    # -- Projection -----------------------------------------------------------

    def project(self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]) -> WidgetData:
        found = activity.sessions(raw)

        if widget_type == "tautulli.streams":
            return WidgetData(
                values={
                    "streams": len(found),
                    "transcoding": _count(raw, "stream_count_transcode"),
                    "direct": _count(raw, "stream_count_direct_play"),
                    "bandwidth": _count(raw, "total_bandwidth"),
                },
                # Empty, not zero: nobody watching is not a reading of nought
                # streams worth a slot in the rotation. `hide_when_empty`
                # takes it off the clock entirely.
                status="ok" if found else "empty",
                hint_icon=activity.ICON_PLAYING,
                hint_color=activity.COLOUR,
            )

        every = int(config.get("refresh") or activity.CACHE_SECONDS)
        session = activity.rotate(found, _now(), every)
        if session is None:
            return WidgetData(values={}, status="empty", hint_color=activity.COLOUR)

        state = str(session.get("state") or "")
        return WidgetData(
            values={
                "title": session.get("full_title") or session.get("title") or "",
                "label": activity.label(session),
                "show": session.get("grandparent_title") or session.get("title") or "",
                "episode": session.get("title") or "",
                "season": _int(session.get("parent_media_index")),
                "number": _int(session.get("media_index")),
                "year": _int(session.get("year")),
                "percent": activity.percent(session),
                "state": state,
                "user": session.get("friendly_name") or "",
                "player": session.get("player") or "",
                "streams": len(found),
            },
            progress=activity.percent(session),
            hint_icon=activity.icon_for(state),
            hint_color=activity.COLOUR,
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _count(raw: dict[str, Any], key: str) -> int:
    try:
        return int(float(raw.get(key) or 0))
    except (TypeError, ValueError):
        return 0
