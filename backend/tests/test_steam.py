"""Steam, and the thirty-two pixels a game title has to fit in.

Two plain GETs. What is worth testing is everything around them: a 403 that
means two different things, an unknown profile that answers 200 with an empty
list, and a game that keeps no achievements at all — which is neither a
failure nor a score of nought.

The title measurements are pinned here rather than left in a comment, because
they are the reason this connector keeps the ordinary eight-second turn where
the Plex one had to be stretched to fourteen.
"""

import httpx
import pytest
import respx

from app.connectors.steam import api
from app.core.errors import ConnectorError

WHO = "76561197960435530"
SUMMARY = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
ACHIEVEMENTS = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
VANITY = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"


def player(**extra):
    base = {
        "steamid": WHO,
        "personaname": "someone",
        "personastate": 1,
    }
    return base | extra


def playing(game="Baldur's Gate 3", appid="1086940", **extra):
    return player(personastate=1, gameextrainfo=game, gameid=appid, **extra)


def summary_response(one):
    return httpx.Response(200, json={"response": {"players": [one]}})


def unlocked(n, total):
    return {
        "success": True,
        "achievements": [
            {"apiname": f"ACH_{i}", "achieved": 1 if i < n else 0} for i in range(total)
        ],
    }


def connector(**config):
    from app.connectors.steam.connector import SteamConnector

    return SteamConnector(config={"steam_id": WHO, **config}, secrets={"api_key": "k" * 32})


class TestTheTitlesFitOrTheyDoNot:
    """Measured against the transcribed panel font before a line was written,
    at the 15.2 columns/s the Plex work pinned:

        median of the 24 most-played   53 columns   5.0 s
        "Hades", "Rust", "Dota 2"      <= 23        static
        "Skyrim Special Edition"      149 columns  11.3 s

    Three titles in four finish inside an eight-second turn, which is why the
    duration is left alone here. `short` is for the fourth.
    """

    @pytest.mark.parametrize(
        "full,expected",
        [
            ("Call of Duty®: Modern Warfare® II", "Call of Duty"),
            ("Tom Clancy's Rainbow Six Siege", "Rainbow Six Siege"),
            ("Sid Meier's Civilization VI", "Civilization VI"),
            ("PUBG: BATTLEGROUNDS", "PUBG"),
            ("The Elder Scrolls V: Skyrim Special Edition", "The Elder Scrolls V"),
        ],
    )
    def test_the_publisher_and_the_subtitle_go(self, full, expected):
        assert api.short_title(full) == expected

    def test_a_possessive_that_is_the_title_stays(self):
        """"Baldur's" is one word and it is the game's name. "Tom Clancy's" is
        two and it is a publisher's. The rule turns on exactly that, and
        getting it wrong would rename the game."""
        assert api.short_title("Baldur's Gate 3") == "Baldur's Gate 3"
        assert api.short_title("Garry's Mod") == "Garry's Mod"
        assert api.short_title("Assassin's Creed Valhalla") == "Assassin's Creed Valhalla"

    def test_the_typographic_apostrophe_counts_too(self):
        """The store writes Tom Clancy’s with a curly one."""
        assert api.short_title("Tom Clancy’s The Division 2") == "The Division 2"

    def test_a_short_title_is_left_whole(self):
        assert api.short_title("Hades") == "Hades"

    def test_it_never_comes_back_empty(self):
        """A title that is nothing but a subtitle would otherwise leave the
        widget with an icon floating over black, which reads as a fault."""
        assert api.short_title(": Reloaded") == ": Reloaded"


class TestWhoIsBeingAskedAbout:
    @respx.mock
    async def test_seventeen_digits_are_used_as_they_are(self):
        """No round trip for the usual case."""
        route = respx.get(VANITY).mock(return_value=httpx.Response(200, json={}))
        assert await api.steam_id(httpx.AsyncClient(), "k", WHO) == WHO
        assert not route.called

    @respx.mock
    async def test_a_vanity_name_is_resolved(self):
        respx.get(VANITY).mock(
            return_value=httpx.Response(200, json={"response": {"success": 1, "steamid": WHO}})
        )
        assert await api.steam_id(httpx.AsyncClient(), "k", "someone") == WHO

    @respx.mock
    async def test_a_pasted_profile_url_is_not_refused_over_a_slash(self):
        """It is the thing people can actually copy, and the useful half is
        right there."""
        respx.get(VANITY).mock(
            return_value=httpx.Response(200, json={"response": {"success": 1, "steamid": WHO}})
        )
        pasted = "https://steamcommunity.com/id/someone/"
        assert await api.steam_id(httpx.AsyncClient(), "k", pasted) == WHO

    @respx.mock
    async def test_a_pasted_id_url_needs_no_resolution(self):
        route = respx.get(VANITY).mock(return_value=httpx.Response(200, json={}))
        pasted = f"https://steamcommunity.com/profiles/{WHO}"
        assert await api.steam_id(httpx.AsyncClient(), "k", pasted) == WHO
        assert not route.called

    @respx.mock
    async def test_a_name_nobody_owns_is_named_as_such(self):
        respx.get(VANITY).mock(
            return_value=httpx.Response(200, json={"response": {"success": 42}})
        )
        with pytest.raises(ConnectorError) as raised:
            await api.steam_id(httpx.AsyncClient(), "k", "nobody")
        assert raised.value.code == "steam.unknown_player"

    @respx.mock
    async def test_an_unknown_id_answers_200_with_an_empty_list(self):
        """Steam does not call it an error, so without this the widget would
        read "nothing playing" forever and nobody would learn why."""
        empty = httpx.Response(200, json={"response": {"players": []}})
        respx.get(SUMMARY).mock(return_value=empty)
        with pytest.raises(ConnectorError) as raised:
            await api.summary(httpx.AsyncClient(), "k", WHO)
        assert raised.value.code == "steam.unknown_player"


class TestWhatReachesTheInGameWidget:
    def test_a_running_game_carries_both_forms(self):
        data = connector().project("steam.playing", {}, {"player": playing()})
        assert data.values["game"] == "Baldur's Gate 3"
        assert data.values["short"] == "Baldur's Gate 3"
        assert data.values["appid"] == "1086940"
        assert data.values["state"] == "playing"
        assert data.hint_icon == api.ICON_STEAM

    def test_nothing_running_empties_the_widget(self):
        """`hide_when_empty` then takes it off the rotation. Online but idle
        is still nothing to show — the widget is about the game."""
        data = connector().project("steam.playing", {}, {"player": player()})
        assert data.status == "empty"
        assert data.values["game"] == ""

    def test_the_persona_state_survives_an_empty_turn(self):
        """Templated by anyone who wants something other than the game out of
        it, so it must still be there when there is no game."""
        data = connector().project("steam.playing", {}, {"player": player(personastate=3)})
        assert data.values["state"] == "away"

    def test_an_unknown_state_reads_as_offline(self):
        data = connector().project("steam.playing", {}, {"player": player(personastate=99)})
        assert data.values["state"] == "offline"


class TestWhatReachesTheAchievementsWidget:
    def raw(self, stats, game="Hades"):
        return {"player": playing(game=game, appid="1145360"), "stats": stats}

    def test_a_fraction_of_a_known_total_is_what_a_bar_is_for(self):
        data = connector().project("steam.achievements", {}, self.raw(unlocked(23, 49)))
        assert (data.values["unlocked"], data.values["total"]) == (23, 49)
        assert data.values["remaining"] == 26
        assert data.values["percent"] == 47
        assert data.progress == 47
        assert data.hint_icon == api.ICON_TROPHY

    def test_a_game_that_keeps_no_score_is_not_a_score_of_nought(self):
        """Steam answers 400 for a game with no achievements. A bar sitting at
        zero all evening would be a lie about a game that has none."""
        stats = {"success": False, "reason": "no_stats"}
        data = connector().project("steam.achievements", {}, self.raw(stats))
        assert data.status == "empty"
        assert data.values == {}

    def test_a_hidden_profile_empties_it_rather_than_crashing(self):
        stats = {"success": False, "reason": "private"}
        assert connector().project("steam.achievements", {}, self.raw(stats)).status == "empty"

    def test_no_game_means_no_achievements(self):
        raw = {"player": player(), "stats": None}
        assert connector().project("steam.achievements", {}, raw).status == "empty"

    def test_none_unlocked_is_a_real_reading(self):
        """Nought out of forty-nine is a number, unlike a game with no
        achievements at all — and the bar can say it."""
        data = connector().project("steam.achievements", {}, self.raw(unlocked(0, 49)))
        assert data.status == "ok"
        assert data.values["percent"] == 0
        assert data.progress == 0

    def test_counted_tells_the_two_apart(self):
        assert api.counted(unlocked(3, 10)) == (3, 10)
        assert api.counted({"success": True, "achievements": []}) is None
        assert api.counted({"success": False, "reason": "no_stats"}) is None


class TestTheFailuresSteamProduces:
    @respx.mock
    async def test_a_refused_key_is_not_reported_as_a_privacy_setting(self):
        """Steam answers 403 for both, but GetPlayerSummaries needs no
        permission on the profile — it works on strangers. So at that point
        the key is the only candidate, and saying "make your profile public"
        would send someone hunting through the wrong settings."""
        respx.get(SUMMARY).mock(return_value=httpx.Response(403))
        with pytest.raises(ConnectorError) as raised:
            await connector().collect("steam.playing", {})
        assert raised.value.code == "steam.bad_key"

    @respx.mock
    async def test_a_test_connection_says_the_same(self):
        respx.get(SUMMARY).mock(return_value=httpx.Response(403))
        result = await connector().test_connection()
        assert not result.ok and result.code == "steam.bad_key"

    @respx.mock
    async def test_an_unreachable_steam_is_named_as_such(self):
        respx.get(SUMMARY).mock(side_effect=httpx.ConnectError("no route"))
        with pytest.raises(ConnectorError) as raised:
            await api.summary(httpx.AsyncClient(), "k", WHO)
        assert raised.value.code == "steam.unreachable"

    @respx.mock
    async def test_html_instead_of_json_is_not_a_crash(self):
        respx.get(SUMMARY).mock(return_value=httpx.Response(200, text="<html>down</html>"))
        with pytest.raises(ConnectorError) as raised:
            await api.summary(httpx.AsyncClient(), "k", WHO)
        assert raised.value.code == "steam.bad_response"

    @respx.mock
    async def test_a_game_without_achievements_is_not_an_error(self):
        """400 here is ordinary — plenty of games keep no score — and it must
        not light up the service card in red."""
        respx.get(ACHIEVEMENTS).mock(return_value=httpx.Response(400))
        stats = await api.achievements(httpx.AsyncClient(), "k", WHO, "1")
        assert stats == {"success": False, "reason": "no_stats"}

    @respx.mock
    async def test_a_private_profile_is_not_an_error_either(self):
        """It is the user's own setting, and the in-game widget still works."""
        respx.get(ACHIEVEMENTS).mock(return_value=httpx.Response(403))
        stats = await api.achievements(httpx.AsyncClient(), "k", WHO, "1")
        assert stats == {"success": False, "reason": "private"}

    @respx.mock
    async def test_the_word_private_in_the_body_counts_too(self):
        respx.get(ACHIEVEMENTS).mock(
            return_value=httpx.Response(
                200,
                json={"playerstats": {"success": False, "error": "Profile is not public"}},
            )
        )
        stats = await api.achievements(httpx.AsyncClient(), "k", WHO, "1")
        assert stats["reason"] == "private"

    async def test_no_key_is_refused_before_the_network(self):
        from app.connectors.steam.connector import SteamConnector

        bare = SteamConnector(config={"steam_id": WHO}, secrets={})
        with pytest.raises(ConnectorError) as raised:
            await bare.collect("steam.playing", {})
        assert raised.value.code == "steam.no_key"

    async def test_no_profile_is_refused_before_the_network(self):
        from app.connectors.steam.connector import SteamConnector

        bare = SteamConnector(config={}, secrets={"api_key": "k"})
        with pytest.raises(ConnectorError) as raised:
            await bare.collect("steam.playing", {})
        assert raised.value.code == "steam.no_id"


class TestTheTwoWidgetsAskDifferentThings:
    def test_they_do_not_share_a_request_key(self):
        """Unlike the Plex pair. The achievements widget needs a second call
        that depends on the first, so pretending the two are one request
        would cache the summary under the achievements' TTL."""
        c = connector()
        keys = {c.request_key(t, {})[0] for t in ("steam.playing", "steam.achievements")}
        assert len(keys) == 2

    def test_achievements_are_cached_for_longer(self):
        c = connector()
        assert (
            c.request_key("steam.achievements", {})[1] > c.request_key("steam.playing", {})[1]
        )

    @respx.mock
    async def test_the_in_game_widget_makes_one_call(self):
        """The achievements call is not made for a widget that cannot use it."""
        summary = respx.get(SUMMARY).mock(return_value=summary_response(playing()))
        achievements = respx.get(ACHIEVEMENTS).mock(return_value=httpx.Response(200, json={}))
        await connector().collect("steam.playing", {})
        assert summary.called and not achievements.called

    @respx.mock
    async def test_the_achievements_widget_makes_two(self):
        respx.get(SUMMARY).mock(return_value=summary_response(playing()))
        route = respx.get(ACHIEVEMENTS).mock(
            return_value=httpx.Response(200, json={"playerstats": unlocked(23, 49)})
        )
        raw = await connector().collect("steam.achievements", {})
        assert route.called
        assert api.counted(raw["stats"]) == (23, 49)

    @respx.mock
    async def test_and_only_one_when_there_is_no_game_to_ask_about(self):
        respx.get(SUMMARY).mock(return_value=summary_response(player()))
        route = respx.get(ACHIEVEMENTS).mock(return_value=httpx.Response(200, json={}))
        raw = await connector().collect("steam.achievements", {})
        assert not route.called and raw["stats"] is None


class TestTestConnection:
    @respx.mock
    async def test_it_names_the_profile_rather_than_saying_ok(self):
        """An empty "connected" proves nothing a typo could not also produce."""
        respx.get(SUMMARY).mock(return_value=summary_response(player()))
        result = await connector().test_connection()
        assert result.ok and result.code == "steam.ok"
        assert result.params["name"] == "someone"

    @respx.mock
    async def test_it_prints_the_resolved_id_so_a_stranger_can_be_spotted(self):
        """The failure this exists for, and it is a quiet one.

        A vanity name belongs to whoever registered it, and it is not the
        display name. A persona name typed as-is resolved to an unrelated
        account on the other side of the world — 200 OK, no error, the
        connector working perfectly on the wrong person. Nothing downstream
        can catch that: the data is valid, it is simply somebody else's.

        So the seventeen digits are printed next to the name, every time, and
        a user who compares them with their own profile URL sees it at once.
        """
        other = "76561190000000001"
        respx.get(VANITY).mock(
            return_value=httpx.Response(200, json={"response": {"success": 1, "steamid": other}})
        )
        respx.get(SUMMARY).mock(return_value=summary_response(player(personaname="someone else")))

        from app.connectors.steam.connector import SteamConnector

        typed = SteamConnector(config={"steam_id": "aname"}, secrets={"api_key": "k" * 32})
        result = await typed.test_connection()
        assert result.params["steamid"] == other
        assert other in result.message

    @respx.mock
    async def test_the_id_is_printed_for_a_game_in_progress_too(self):
        respx.get(SUMMARY).mock(return_value=summary_response(playing()))
        respx.get(ACHIEVEMENTS).mock(
            return_value=httpx.Response(200, json={"playerstats": unlocked(1, 10)})
        )
        result = await connector().test_connection()
        assert result.params["steamid"] == WHO

    @respx.mock
    async def test_a_game_in_progress_is_worth_saying(self):
        respx.get(SUMMARY).mock(return_value=summary_response(playing()))
        respx.get(ACHIEVEMENTS).mock(
            return_value=httpx.Response(200, json={"playerstats": unlocked(1, 10)})
        )
        result = await connector().test_connection()
        assert result.ok and result.code == "steam.ok_playing"
        assert result.params["game"] == "Baldur's Gate 3"

    @respx.mock
    async def test_it_says_when_the_achievements_are_out_of_reach(self):
        """The symptom this exists for has none of its own.

        Measured on a real account: "Game details" was not Public, so
        GetPlayerAchievements answered 403 while everything else kept
        working — the in-game widget fine, the service card green, and the
        achievements widget empty for ever with nothing pointing anywhere.

        Steam's own exception is what hides it: a key tied to the account
        being asked about bypasses privacy on GetPlayerSummaries and
        GetOwnedGames, but *not* on GetPlayerAchievements. So the profile
        looks open from every angle except the one that matters.
        """
        respx.get(SUMMARY).mock(return_value=summary_response(playing()))
        respx.get(ACHIEVEMENTS).mock(return_value=httpx.Response(403))
        result = await connector().test_connection()
        # Still a success: the key is good and one of the two widgets works.
        assert result.ok and result.code == "steam.ok_no_stats"
        assert result.params["game"] == "Baldur's Gate 3"

    @respx.mock
    async def test_a_game_without_achievements_is_not_reported_as_private(self):
        """400 means the game keeps no score, which is nobody's mistake and
        must not send someone into their privacy settings."""
        respx.get(SUMMARY).mock(return_value=summary_response(playing()))
        respx.get(ACHIEVEMENTS).mock(return_value=httpx.Response(400))
        result = await connector().test_connection()
        assert result.code == "steam.ok_playing"
