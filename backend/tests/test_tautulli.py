"""Plex through Tautulli, and the thirty-two pixels it has to fit in.

The API is one GET. What is worth testing is everything around it: a key that
is refused with a 200, several people watching at once, and nobody watching —
which is the state a home server spends most of its day in.
"""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.connectors.tautulli import activity
from app.core.errors import ConnectorError

URL = "https://tautulli.example"
ENDPOINT = f"{URL}/api/v2"


def session(**extra):
    base = {
        "media_type": "episode",
        "state": "paused",
        "full_title": "Naruto Shippuden Yabai - Les Kage entrent en scène",
        "title": "Les Kage entrent en scène",
        "grandparent_title": "Naruto Shippuden Yabai",
        "parent_media_index": "3",
        "media_index": "16",
        "year": "2023",
        "progress_percent": "48",
        "friendly_name": "someone",
        "player": "Google TV",
    }
    return base | extra


def answer(sessions, **extra):
    return {
        "response": {
            "result": "success",
            "data": {"sessions": sessions, "stream_count": len(sessions), **extra},
        }
    }


def connector(**config):
    from app.connectors.tautulli.connector import TautulliConnector

    return TautulliConnector(
        config={"url": URL, **config}, secrets={"api_key": "k" * 32}
    )


class TestTheShortForm:
    """What survives the trip to a panel.

    The measurement behind all of this, taken on a real server before a line
    was written: the full title is 50 characters, 185 columns, and 11 seconds
    to scroll past once — for 23 columns of room.
    """

    def test_an_episode_becomes_s03e16(self):
        assert activity.episode_code(session()) == "S03E16"

    def test_it_is_padded_so_the_width_does_not_jump(self):
        """Episode 9 and episode 10 must occupy the same columns, or the
        widget changes width in the middle of a season."""
        assert activity.episode_code(session(media_index="9")) == "S03E09"

    def test_a_film_has_no_code(self):
        assert activity.episode_code(session(parent_media_index=None, media_index=None)) is None

    def test_a_film_falls_back_to_its_year(self):
        film = session(media_type="movie", parent_media_index=None, media_index=None)
        assert activity.label(film) == "2023"

    def test_and_to_something_when_even_that_is_missing(self):
        """Never empty. A text that resolves to nothing leaves an icon and a
        bar floating over black, which reads as a fault rather than as a film
        with no year on record."""
        bare = session(parent_media_index=None, media_index=None, year=None)
        assert activity.label(bare) == "PLEX"


class TestTheIconCarriesTheState:
    """So the text does not have to spend characters on it, and on this panel
    a character costs about a fifth of the room."""

    @pytest.mark.parametrize(
        ("state", "icon"),
        [("playing", activity.ICON_PLAYING), ("paused", activity.ICON_PAUSED)],
    )
    def test_playing_and_paused_differ(self, state, icon):
        assert activity.icon_for(state) == icon

    def test_anything_else_reads_as_buffering(self):
        """A stream stuck buffering is the symptom of a server that cannot
        keep up, and it must not look like one that is playing."""
        assert activity.icon_for("buffering") == activity.ICON_BUFFERING
        assert activity.icon_for("") == activity.ICON_BUFFERING


class TestSeveralPeopleWatching:
    """Florian's choice: one widget that moves from one stream to the next."""

    def streams(self, n):
        return [session(full_title=f"film {i}") for i in range(n)]

    def test_one_stream_is_always_that_stream(self):
        only = self.streams(1)
        for minute in range(0, 600, 30):
            chosen = activity.rotate(only, datetime.fromtimestamp(minute, UTC), 30)
            assert chosen is only[0]

    def test_it_moves_on_at_each_collection(self):
        three = self.streams(3)
        seen = [
            activity.rotate(three, datetime.fromtimestamp(t, UTC), 30)["full_title"]
            for t in (0, 30, 60, 90)
        ]
        assert seen == ["film 0", "film 1", "film 2", "film 0"]

    def test_it_does_not_move_within_one_collection(self):
        """It rotates on the clock rather than on a counter, so it needs no
        stored state — but it must not change while somebody is reading it."""
        three = self.streams(3)
        within = {
            activity.rotate(three, datetime.fromtimestamp(t, UTC), 30)["full_title"]
            for t in (0, 10, 20, 29)
        }
        assert within == {"film 0"}

    def test_two_displays_stay_in_step(self):
        """Deriving it from the clock rather than from a per-widget counter is
        what keeps the same widget on two clocks showing the same stream."""
        three = self.streams(3)
        moment = datetime.fromtimestamp(12345, UTC)
        assert activity.rotate(three, moment, 30) is activity.rotate(three, moment, 30)

    def test_nobody_watching_is_nothing_to_show(self):
        assert activity.rotate([], datetime.now(UTC), 30) is None


class TestWhatReachesTheWidget:
    def test_now_playing_carries_both_forms_of_the_title(self):
        raw = answer([session()])["response"]["data"]
        data = connector().project("tautulli.now_playing", {}, raw)
        assert data.values["title"].startswith("Naruto Shippuden")
        assert data.values["label"] == "S03E16"
        assert data.values["percent"] == 48
        assert data.progress == 48
        assert data.hint_icon == activity.ICON_PAUSED

    def test_nobody_watching_empties_the_widget(self):
        """`hide_when_empty` then takes it off the rotation entirely. A clock
        showing "0" all evening is worse than a clock showing nothing."""
        data = connector().project("tautulli.now_playing", {}, {"sessions": []})
        assert data.status == "empty"
        assert data.values == {}

    def test_the_stream_count_is_also_empty_when_nobody_watches(self):
        data = connector().project("tautulli.streams", {}, {"sessions": []})
        assert data.status == "empty"
        assert data.values["streams"] == 0

    def test_the_stream_count_separates_transcoding_from_direct(self):
        """Transcoding is what makes a server sweat; the total alone hides
        the one number worth watching."""
        raw = answer([session(), session()], stream_count_transcode=1,
                     stream_count_direct_play=1)["response"]["data"]
        data = connector().project("tautulli.streams", {}, raw)
        assert (data.values["streams"], data.values["transcoding"]) == (2, 1)

    def test_a_missing_progress_is_not_a_bar_at_zero(self):
        """Zero percent and "we do not know" are different, and a bar cannot
        say the second."""
        raw = {"sessions": [session(progress_percent=None)]}
        assert connector().project("tautulli.now_playing", {}, raw).progress is None


class TestTheFailuresAHomeServerProduces:
    """Each named rather than collapsed into "unreachable": a wrong key, a
    stopped container and a refused certificate look identical from a widget
    that has gone blank, and they need three different fixes."""

    @respx.mock
    async def test_a_refused_key_answers_200(self):
        """Tautulli says `result: error` with a 200, so the status code alone
        cannot tell success from refusal — which is exactly the shape that
        makes a connector report "connected" over nothing."""
        respx.get(ENDPOINT).mock(
            return_value=httpx.Response(
                200, json={"response": {"result": "error", "message": "Invalid apikey"}}
            )
        )
        with pytest.raises(ConnectorError) as raised:
            await activity.fetch(httpx.AsyncClient(), URL, "wrong")
        assert raised.value.code == "tautulli.bad_key"

    @respx.mock
    async def test_an_unreachable_server_is_named_as_such(self):
        respx.get(ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(ConnectorError) as raised:
            await activity.fetch(httpx.AsyncClient(), URL, "k")
        assert raised.value.code == "tautulli.unreachable"

    @respx.mock
    async def test_html_instead_of_json_is_not_a_crash(self):
        respx.get(ENDPOINT).mock(return_value=httpx.Response(200, text="<html>login</html>"))
        with pytest.raises(ConnectorError) as raised:
            await activity.fetch(httpx.AsyncClient(), URL, "k")
        assert raised.value.code == "tautulli.bad_response"

    async def test_no_address_is_refused_before_the_network(self):
        from app.connectors.tautulli.connector import TautulliConnector

        bare = TautulliConnector(config={}, secrets={"api_key": "k"})
        with pytest.raises(ConnectorError) as raised:
            await bare.collect("tautulli.now_playing", {})
        assert raised.value.code == "tautulli.no_url"


class TestOneCallForBothWidgets:
    def test_they_share_a_request(self):
        """Two widgets must not mean two round trips to the same server."""
        c = connector()
        keys = {c.request_key(t, {})[0] for t in ("tautulli.now_playing", "tautulli.streams")}
        assert len(keys) == 1

    def test_a_self_signed_certificate_can_be_accepted(self):
        """The ordinary case on a home network — and still off by default, so
        that it is a decision."""
        assert connector(verify_tls=False).client is not None
