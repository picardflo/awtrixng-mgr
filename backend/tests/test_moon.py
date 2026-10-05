"""The Moon.

The astronomy is anchored on instants that can be checked against the world,
not on values this code produced. A total solar eclipse in particular can only
happen at a new moon: if that test passes, the calculation is right.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.moon import phase as lunar
from app.connectors.moon.connector import COLOUR, ICONS, MoonConnector

#: Instants published independently of this project.
NEW_MOONS = [
    datetime(2000, 1, 6, 18, 14, tzinfo=UTC),
    datetime(2024, 4, 8, 18, 17, tzinfo=UTC),   # total solar eclipse
    datetime(2017, 8, 21, 18, 30, tzinfo=UTC),  # total solar eclipse
]
FULL_MOONS = [
    datetime(2000, 1, 21, 4, 40, tzinfo=UTC),
]


@pytest.mark.parametrize("moment", NEW_MOONS)
def test_a_new_moon_has_the_sun_and_moon_together(moment):
    """Elongation near 0°, which for an eclipse is not a coincidence but a
    requirement."""
    assert min(lunar.elongation(moment), 360 - lunar.elongation(moment)) < 1.5
    assert lunar.illumination(moment) < 0.5
    assert lunar.phase(moment)[0] == "new"


@pytest.mark.parametrize("moment", FULL_MOONS)
def test_a_full_moon_is_opposite_the_sun(moment):
    assert abs(lunar.elongation(moment) - 180) < 1.5
    assert lunar.illumination(moment) > 99.5
    assert lunar.phase(moment)[0] == "full"


def test_the_moon_was_near_first_quarter_when_apollo_11_landed():
    """The landings were timed for a low sun at the site, which puts the Moon
    near first quarter seen from Earth — not full, as one might assume."""
    landing = datetime(1969, 7, 20, 20, 17, tzinfo=UTC)
    assert 25 < lunar.illumination(landing) < 45


def test_the_naive_method_would_not_have_done():
    """Guards the reason this file exists.

    Mean age — days since a known new moon, modulo the synodic month — drifts
    against the truth because the orbit is an ellipse. Somewhere in a lunation
    the two must disagree by a good fraction of a day, or the whole series
    would be pointless.
    """
    anchor = NEW_MOONS[0]
    worst = max(
        abs(lunar.age(anchor + timedelta(days=offset / 4)) - (offset / 4) % lunar.SYNODIC_MONTH)
        for offset in range(1, 4 * 29)
    )
    assert worst > 0.2, "the true age never departs from the mean one; check the series"


def test_a_lunation_comes_back_to_where_it_started():
    """Near the next new moon, not exactly on it.

    SYNODIC_MONTH is a mean: real lunations run some hours longer or shorter,
    which is a few degrees of elongation. Demanding an exact return would be
    demanding that the orbit be a circle.
    """
    start = NEW_MOONS[1]
    later = start + timedelta(days=lunar.SYNODIC_MONTH)
    assert min(lunar.elongation(later), 360 - lunar.elongation(later)) < 5.0


def test_every_phase_is_reachable_and_they_come_in_order():
    """A full lunation walks the eight phases once, in order, and closes the
    circle by starting the ninth — which is the first again."""
    seen = []
    moment = NEW_MOONS[1]
    for hours in range(0, int(lunar.SYNODIC_MONTH * 24)):
        slug = lunar.phase(moment + timedelta(hours=hours))[0]
        if not seen or seen[-1] != slug:
            seen.append(slug)

    expected = [slug for slug, _ in lunar.PHASES]
    assert seen[: len(expected)] == expected, seen
    assert seen[len(expected) :] in ([], [expected[0]]), seen


def test_illumination_stays_within_its_bounds():
    moment = NEW_MOONS[0]
    for hours in range(0, int(lunar.SYNODIC_MONTH * 24), 3):
        value = lunar.illumination(moment + timedelta(hours=hours))
        assert 0.0 <= value <= 100.0


def test_a_naive_datetime_is_not_silently_wrong():
    """astimezone() on a naive value assumes local time; the calculation would
    then be off by the machine's offset without saying so."""
    aware = datetime(2024, 4, 8, 18, 17, tzinfo=UTC)
    naive = aware.replace(tzinfo=None)
    assert lunar.elongation(aware) == pytest.approx(
        lunar.elongation(naive.replace(tzinfo=UTC)), abs=1e-9
    )


# -- The connector ----------------------------------------------------------


def test_every_phase_has_its_own_icon():
    slugs = [slug for slug, _ in lunar.PHASES]
    assert sorted(ICONS) == sorted(slugs)
    assert len(set(ICONS.values())) == len(slugs), "two phases share an icon"


def test_the_waxing_half_uses_the_right_lit_icons():
    """Checked against the artwork, not the titles: 2319–2321 are lit on the
    right, which is how the Moon waxes in the northern hemisphere."""
    assert {ICONS["waxing_crescent"], ICONS["first_quarter"], ICONS["waxing_gibbous"]} == {
        "2321", "2320", "2319",
    }
    assert {ICONS["waning_gibbous"], ICONS["last_quarter"], ICONS["waning_crescent"]} == {
        "2315", "2316", "2317",
    }


def test_the_reading_carries_everything_the_widget_offers():
    declared = {
        variable.name
        for widget in MoonConnector.descriptor.widgets
        for variable in widget.variables
    }
    produced = set(MoonConnector._reading(datetime.now(UTC)))
    assert declared <= produced
    # `phase_code` is produced without being offered: it picks the icon, and a
    # template could only print it — there is no comparison in this engine.
    assert produced - declared == {"phase_code"}


def test_projection_matches_the_phase():
    connector = MoonConnector(config={}, secrets={})
    raw = connector._reading(FULL_MOONS[0])
    data = connector.project("moon.phase", {}, raw)
    assert data.values["phase_code"] == "full"
    assert data.hint_icon == ICONS["full"]
    assert data.hint_color == COLOUR
    assert data.progress == 100


@pytest.mark.asyncio
async def test_the_test_button_reports_a_phase_rather_than_a_connection():
    result = await MoonConnector(config={}, secrets={}).test_connection()
    assert result.ok is True
    assert result.details["phase"] in ICONS
