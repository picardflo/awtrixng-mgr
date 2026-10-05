from app.schemas.widget_data import DisplayOptions, WidgetData
from app.widgets.renderer import lifetime_for, render


def data(**kwargs) -> WidgetData:
    return WidgetData(**{"values": {"value": 18, "unit": "C"}, **kwargs})


class TestText:
    def test_template_is_rendered_against_the_values(self):
        payload = render(data(), DisplayOptions(text="{{ value }}°{{ unit }}"))
        assert payload.to_json()["text"] == "18°C"

    def test_duration_is_sent_in_milliseconds(self):
        """The option stays in seconds — nobody thinks of an app's turn in
        milliseconds — and the suffix `Ms` is converted on the way out."""
        payload = render(data(), DisplayOptions(duration=12))
        assert payload.to_json()["durationMs"] == 12000


class TestMinimalPayload:
    """Only what differs from the firmware default travels."""

    def test_defaults_are_omitted(self):
        keys = render(data(), DisplayOptions(text="x")).to_json().keys()
        for absent in ("scroll", "iconMode", "textCase"):
            assert absent not in keys

    def test_an_awtrix3_key_never_appears(self):
        """Each of these answers `unknown key` on a real device. A payload
        carrying one would be refused whole, taking the widget with it."""
        keys = render(
            data(hint_color="#fff"),
            DisplayOptions(text="x", scroll_speed=50, show_progress=True),
        ).to_json().keys()
        for dead in ("color", "background", "duration", "lifetime", "pushIcon",
                     "scrollSpeed", "center", "noScroll", "rainbow", "progressC"):
            assert dead not in keys

    def test_scrolling_travels_as_one_object(self):
        """NG moved every scroll notion into `scroll`; sending the parts flat
        is how a port gets a 422."""
        result = render(data(), DisplayOptions(scroll_speed=50)).to_json()
        assert result["scroll"] == {"speed": 50}

    def test_a_still_text_is_a_scroll_mode_not_a_flag(self):
        result = render(data(), DisplayOptions(scroll_mode="static")).to_json()
        assert result["scroll"] == {"mode": "static"}

    def test_icon_mode_is_named_not_numbered(self):
        assert render(data(), DisplayOptions(icon_mode="push")).to_json()["iconMode"] == "push"

    def test_text_case_is_named_not_numbered(self):
        assert render(data(), DisplayOptions(text_case="upper")).to_json()["textCase"] == "upper"

    def test_an_overlay_travels(self):
        """New in NG: weather drawn by the firmware over the text."""
        assert render(data(), DisplayOptions(overlay="rain")).to_json()["overlay"] == "rain"


class TestHints:
    def test_connector_hints_are_used_when_the_user_chose_nothing(self):
        payload = render(data(hint_icon="11201", hint_color="#4aa8ff"), DisplayOptions())
        result = payload.to_json()
        assert result["icon"] == "11201"
        assert result["textColor"] == "#4aa8ff"

    def test_user_choice_wins_over_the_hint(self):
        payload = render(
            data(hint_icon="11201", hint_color="#4aa8ff"),
            DisplayOptions(icon="999", color="#ff0000"),
        )
        result = payload.to_json()
        assert result["icon"] == "999"
        assert result["textColor"] == "#ff0000"


class TestEmptyState:
    def test_empty_removes_the_app_by_default(self):
        assert render(data(status="empty"), DisplayOptions()) is None

    def test_empty_can_still_be_displayed(self):
        payload = render(data(status="empty"), DisplayOptions(hide_when_empty=False))
        assert payload is not None

    def test_degraded_still_renders(self):
        """A degraded service keeps showing its last value (§18)."""
        assert render(data(status="degraded"), DisplayOptions()) is not None


class TestProgressAndSeries:
    def test_progress_needs_to_be_enabled(self):
        assert "progress" not in render(data(progress=40), DisplayOptions()).to_json()

    def test_progress_is_sent_when_enabled(self):
        payload = render(data(progress=40), DisplayOptions(show_progress=True))
        assert payload.to_json()["progress"] == 40

    def test_the_series_switch_is_gone(self):
        """It chose between a bar chart and a line chart, and **no connector
        produces a series**: the switch was offered, honoured by the renderer,
        and drew nothing whatever it was set to.

        Found by the test that checks every display option has a control in
        the builder — it had none, because there was nothing worth showing.
        The payload keeps `barChart` and `lineChart`, so the option comes back
        the day something feeds them, with its data rather than before it.
        """
        assert "show_series" not in DisplayOptions.model_fields
        payload = render(data(series=[1.0, 2.0, 3.0]), DisplayOptions(text="x")).to_json()
        assert "barChart" not in payload and "lineChart" not in payload


class TestLifetime:
    def test_lifetime_is_sent_in_milliseconds(self):
        """NG has no `lifetimeMode` — the key answers `unknown key`. AWTRIX 3
        could mark a stale app with a red outline instead of removing it; that
        option is gone, and an app that stops being refreshed disappears."""
        result = render(data(), DisplayOptions(), lifetime_seconds=300).to_json()
        assert result["lifetimeMs"] == 300_000
        assert "lifetimeMode" not in result

    def test_absent_when_not_requested(self):
        assert "lifetime" not in render(data(), DisplayOptions()).to_json()

    def test_three_missed_refreshes(self):
        assert lifetime_for(120) == 360

    def test_floor_protects_fast_widgets(self):
        assert lifetime_for(5) == 60


def test_renderer_does_no_io():
    """Guards the contract: pure function, so preview works without a device."""
    import inspect

    from app.widgets import renderer

    source = inspect.getsource(renderer)
    for forbidden in ("httpx", "requests", "import os", "open(", "await "):
        assert forbidden not in source


class TestProgressColours:
    """One palette, chosen once, carrying through the text, the bar and its
    track.

    The track is never left to the firmware: measured on a v0.98 device, it
    paints the unfilled part WHITE, so a 2 % bar lights the whole bottom row
    and reads as full. What changed is what replaces it — a dark wash of the
    bar's own colour rather than a flat black that belongs to nothing.
    """

    def test_the_track_is_never_the_firmware_default(self):
        """Whatever else, something is always sent."""
        result = render(data(progress=2), DisplayOptions(show_progress=True)).to_json()
        assert "progressTrackColor" in result

    def test_the_track_is_a_dark_wash_of_the_bar(self):
        result = render(
            data(progress=40, hint_color="#4aa8ff"), DisplayOptions(show_progress=True)
        ).to_json()
        assert result["progressColor"] == "#4aa8ff"
        assert result["progressTrackColor"] == "#0d1e2e"

    def test_the_track_stays_dark_enough_not_to_read_as_full(self):
        """The whole reason the firmware's white was refused. Every channel of
        the wash must stay far below the bar's own."""
        result = render(
            data(progress=2, hint_color="#ffffff"), DisplayOptions(show_progress=True)
        ).to_json()
        track = result["progressTrackColor"]
        assert all(int(track[i : i + 2], 16) <= 60 for i in (1, 3, 5)), track

    def test_black_is_still_available_by_asking_for_it(self):
        result = render(
            data(progress=2, hint_color="#4aa8ff"),
            DisplayOptions(show_progress=True, progress_background="#000000"),
        ).to_json()
        assert result["progressTrackColor"] == "#000000"

    def test_without_a_colour_to_wash_the_track_is_black(self):
        """Nothing to derive from, and still never nothing.

        Writing this test is what found the regression: the wash alone left
        the key unset when no colour had been proposed, which hands the bar
        back to the firmware's white — the exact fault black was chosen to
        avoid in the first place.
        """
        result = render(data(progress=40), DisplayOptions(show_progress=True)).to_json()
        assert result["progressTrackColor"] == "#000000"

    def test_filled_colour_is_left_to_the_firmware_unless_chosen(self):
        result = render(data(progress=40), DisplayOptions(show_progress=True)).to_json()
        assert "progressColor" not in result

    def test_filled_colour_is_sent_when_chosen(self):
        result = render(
            data(progress=40),
            DisplayOptions(show_progress=True, progress_color="#4aa8ff"),
        ).to_json()
        assert result["progressColor"] == "#4aa8ff"

    def test_no_bar_means_no_colours(self):
        result = render(data(progress=40), DisplayOptions()).to_json()
        assert "progressTrackColor" not in result and "progressColor" not in result


class TestIconChoice:
    """Three states, and the third one was missing."""

    def test_no_choice_takes_the_connector_suggestion(self):
        payload = render(data(hint_icon="12186"), DisplayOptions())
        assert payload.to_json()["icon"] == "12186"

    def test_an_explicit_icon_overrides_the_suggestion(self):
        payload = render(data(hint_icon="12186"), DisplayOptions(icon="12194"))
        assert payload.to_json()["icon"] == "12194"

    def test_the_icon_can_be_turned_off_entirely(self):
        """The only way to give the text all 32 columns."""
        payload = render(data(hint_icon="12186"), DisplayOptions(show_icon=False))
        assert "icon" not in payload.to_json()

    def test_turning_it_off_also_ignores_an_explicit_icon(self):
        payload = render(data(), DisplayOptions(icon="12194", show_icon=False))
        assert "icon" not in payload.to_json()

    def test_turning_the_icon_off_frees_the_whole_width(self):
        """An 8x8 icon costs 9 of the 32 columns. Measured: it also occupies
        the bottom row, which is why the weekday bar narrows beside one."""
        payload = render(
            data(hint_icon="11201"),
            DisplayOptions(text="18°C", show_icon=False),
        )
        result = payload.to_json()
        assert "icon" not in result
        assert result["text"] == "18°C"



class TestTheBarTakesTheConnectorsColour:
    """A bar left uncoloured kept AWTRIX's own default.

    Which clashed with a text the connector had coloured — a blue "70 %" over
    a grey bar, on a widget whose whole colour depends on its value. The text
    already followed the connector when its field was empty; the bar did not,
    and nothing said why.
    """

    def test_an_empty_colour_follows_the_connector(self):
        payload = render(
            data(progress=70, hint_color="#4aa8ff"),
            DisplayOptions(show_progress=True),
        )
        assert payload.to_json()["progressColor"] == "#4aa8ff"

    def test_a_chosen_colour_still_wins(self):
        """Typing one is how you overrule the connector, on the bar as on the
        text. A fallback that could not be overruled would be a regression."""
        payload = render(
            data(progress=70, hint_color="#4aa8ff"),
            DisplayOptions(show_progress=True, progress_color="#ff0000"),
        )
        assert payload.to_json()["progressColor"] == "#ff0000"

    def test_neither_one_nor_the_other_sends_nothing(self):
        """The firmware then picks, as it did before — the minimal payload
        rule: only what differs from the default travels."""
        payload = render(data(progress=70), DisplayOptions(show_progress=True))
        assert "progressColor" not in payload.to_json()

    def test_no_bar_means_no_colour(self):
        payload = render(
            data(progress=70, hint_color="#4aa8ff"), DisplayOptions(show_progress=False)
        )
        assert "progressColor" not in payload.to_json()


class TestTheOverlay:
    """New in NG: the firmware draws weather over the whole app."""

    def test_the_connector_suggestion_is_followed(self):
        payload = render(data(hint_overlay="rain"), DisplayOptions())
        assert payload.to_json()["overlay"] == "rain"

    def test_an_explicit_choice_wins(self):
        payload = render(data(hint_overlay="rain"), DisplayOptions(overlay="snow"))
        assert payload.to_json()["overlay"] == "snow"

    def test_it_can_be_turned_off_entirely(self):
        """An overlay costs no horizontal space, but it moves. A widget read
        at a glance may be better still."""
        payload = render(data(hint_overlay="rain"), DisplayOptions(show_overlay=False))
        assert "overlay" not in payload.to_json()

    def test_turning_it_off_also_ignores_an_explicit_choice(self):
        payload = render(
            data(hint_overlay="rain"), DisplayOptions(overlay="snow", show_overlay=False)
        )
        assert "overlay" not in payload.to_json()

    def test_no_suggestion_means_no_overlay(self):
        assert "overlay" not in render(data(), DisplayOptions()).to_json()


def test_the_track_wash_matches_the_preview():
    """Two implementations of one rule: `wmo.dim` here, `dim()` in
    AwtrixMatrixPreview.tsx.

    A preview that disagreed with the clock would be worse than no preview —
    it is consulted precisely when something looks wrong. The same table is
    pinned in `frontend/src/components/dim.test.ts`, so a drift fails on one
    side or the other rather than on the matrix.
    """
    from app.connectors.weather import wmo

    assert [wmo.dim(c) for c in ("#4aa8ff", "#3ddc84", "#f5a524", "#7e6bff", "#ffffff")] == [
        "#0d1e2e",
        "#0b2818",
        "#2c1e06",
        "#17132e",
        "#2e2e2e",
    ]


def _fills_the_bottom_row(widget) -> bool:
    """A progress bar or the seven day segments. They are the same row."""
    return widget.default_display.show_progress or widget.default_display.show_days


class TestTheFontRule:
    """The large font is the font of a widget that has a bar.

    Measured on a TC001, rows occupied by the text:

        small, no bar      1..5    centred
        large, no bar      0..6    one row high
        large, with bar    0..7    fills the panel exactly

    So it is not a matter of taste. `large` draws the seven rows above the
    bottom row, which is a perfect fit when something occupies it and a
    lopsided one when nothing does. "Something" is a progress bar or the seven
    day segments — they share that row and only one of them is ever drawn.

    Width is unaffected either way — the same measurement
    gave identical column counts for both fonts, which is why the choice costs
    nothing horizontally.
    """

    def widgets(self):
        from app.connectors import registry

        registry.load_all()
        return [w for d in registry.descriptors() for w in d.widgets]

    def test_every_widget_with_a_bar_uses_the_large_font(self):
        wrong = [
            w.type
            for w in self.widgets()
            if _fills_the_bottom_row(w) and w.default_display.font != "large"
        ]
        assert not wrong, f"these have a bar and sit squeezed above it: {wrong}"

    def test_no_widget_uses_the_large_font_without_a_bar(self):
        """It would sit one row high, with nothing underneath to balance it."""
        wrong = [
            w.type
            for w in self.widgets()
            if w.default_display.font == "large" and not _fills_the_bottom_row(w)
        ]
        assert not wrong, f"these would sit one row high: {wrong}"

    def test_a_bar_needs_something_to_fill_it(self):
        """A widget that asks for a bar and never computes one shows nothing
        where the bar should be — which is how the sun and the moon spent the
        whole of the previous project."""
        missing = [
            w.type
            for w in self.widgets()
            if w.default_display.show_progress
            and not w.default_display.show_days
            and w.sample_data.progress is None
        ]
        assert not missing, f"these ask for a bar with no value behind it: {missing}"


class TestTheWeekdayBar:
    """Seven day segments instead of one filled proportion.

    Florian's idea, from the firmware's own bar under the Date app. A progress
    bar at 60 % says nothing about *which* days are left — Thursday and Friday,
    or a Wednesday and a holiday. Seven marks say it at a glance.

    The geometry is the firmware's, read off the panel rather than guessed:
    seven runs of three pixels, one apart, from column 2, on the bottom row.
    """

    DAYS = ["past", "past", "today", "school", "school", "off", "off"]

    def render(self, **options):
        return render(
            WidgetData(values={}, days=self.DAYS, hint_color="#3ddc84"),
            DisplayOptions(text="Sem. B", show_days=True, **options),
        ).to_json()

    def test_without_an_icon_it_is_the_firmware_s_own_bar(self):
        """Pixel for pixel, so a widget and the Date app line up when they
        follow each other in the rotation."""
        commands = self.render(show_icon=False)["draw"]
        assert [(c[1], c[3]) for c in commands] == [
            (2, 3), (6, 3), (10, 3), (14, 3), (18, 3), (22, 3), (26, 3)
        ]
        assert all(c[0] == "rect" and c[2] == 7 and c[4] == 1 for c in commands)

    def test_with_an_icon_it_narrows_to_fit(self):
        """Measured, not predicted: the icon occupies columns 0 to 8 of every
        row *including the bottom one*, so three-pixel segments were painted
        over. Two pixels and a gap is 20 columns, which lands inside the 23
        an icon leaves."""
        commands = self.render(icon="2536")["draw"]
        assert [(c[1], c[3]) for c in commands] == [
            (10, 2), (13, 2), (16, 2), (19, 2), (22, 2), (25, 2), (28, 2)
        ]
        assert max(c[1] + c[3] for c in commands) <= 32

    def test_the_four_states_are_four_shades(self):
        """The firmware only has to say which day it is. This has to say how
        much of the week is left, which needs more than two."""
        colours = [c[5] for c in self.render(show_icon=False)["draw"]]
        assert colours[2] == "#ffffff", "today is the brightest"
        assert colours[3] == "#3ddc84", "a school day still to come takes the widget colour"
        assert colours[0] != colours[3], "a day already past is dimmer"
        assert len(set(colours)) == 4

    def test_it_replaces_the_progress_bar_rather_than_joining_it(self):
        """They share the bottom row; a widget drawing both would overwrite
        one with the other."""
        payload = render(
            WidgetData(values={}, days=self.DAYS, progress=60, hint_color="#3ddc84"),
            DisplayOptions(text="x", show_days=True, show_progress=True),
        ).to_json()
        assert "draw" in payload
        assert "progress" not in payload

    def test_a_connector_with_no_days_falls_back_to_the_bar(self):
        payload = render(
            WidgetData(values={}, progress=60, hint_color="#3ddc84"),
            DisplayOptions(text="x", show_days=True, show_progress=True),
        ).to_json()
        assert "draw" not in payload
        assert payload["progress"] == 60

    def test_the_connector_names_states_not_colours(self):
        """The one thing this layer must not know is what the matrix looks
        like. A connector that returned "#ffffff" would be deciding it."""
        from app.connectors.school import calendar as cal

        assert set(cal.week_days(cal.today(), [])) <= {"past", "today", "school", "off"}
