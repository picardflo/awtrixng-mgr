"""The language of what goes on the matrix.

Separate from the interface language on purpose: the scheduler pushes without
a browser, so the displays get a setting of their own.
"""

from datetime import UTC, datetime

import pytest

from app.connectors.moon import phase as lunar
from app.connectors.weather import wmo
from app.core import language
from app.core.config import get_settings


@pytest.fixture
def speaking(monkeypatch):
    def set_to(code: str):
        monkeypatch.setenv("AWTRIXNG_LANGUAGE", code)
        get_settings.cache_clear()

    yield set_to
    get_settings.cache_clear()


def test_english_by_default(speaking):
    speaking("en")
    assert wmo.describe(3)[1] == "Overcast"


def test_french_translates_the_prose(speaking):
    speaking("fr")
    assert wmo.describe(3)[1] == "Couvert"
    assert wmo.describe(95)[1] == "Orage"


def test_the_slug_never_changes_with_the_language(speaking):
    """The contract templates rely on. A condition that renamed itself on a
    language switch would break every widget comparing against it, quietly."""
    speaking("en")
    english = {code: wmo.describe(code)[0] for code in wmo.CODES}
    speaking("fr")
    assert {code: wmo.describe(code)[0] for code in wmo.CODES} == english


def test_an_unsupported_language_falls_back_to_english(speaking):
    """Better a readable English word on the matrix than an empty one."""
    speaking("de")
    assert language.current() == "en"
    assert wmo.describe(3)[1] == "Overcast"


def test_a_malformed_setting_does_not_break_anything(speaking):
    for value in ("", "   ", "FR-fr", "french"):
        speaking(value)
        assert language.current() in language.SUPPORTED
        assert wmo.describe(3)[1]


def test_case_and_region_are_tolerated(speaking):
    speaking("fr_FR.UTF-8")
    assert language.current() == "fr"
    assert wmo.describe(3)[1] == "Couvert"


# -- Coverage ---------------------------------------------------------------
#
# These two caught a first attempt whose French table was written from memory:
# sixteen real slugs had no translation and three translations matched nothing.


@pytest.mark.parametrize("code", sorted(language.SUPPORTED))
def test_every_weather_slug_is_translated(code):
    if code == "en":
        pytest.skip("English is the table itself")
    slugs = {slug for slug, _ in wmo.CODES.values()} | {"unknown"}
    assert slugs - set(wmo.TRANSLATIONS[code]) == set(), "untranslated weather conditions"
    assert set(wmo.TRANSLATIONS[code]) - slugs == set(), "translations matching no condition"


@pytest.mark.parametrize("code", sorted(language.SUPPORTED))
def test_every_moon_phase_is_translated(code):
    if code == "en":
        pytest.skip("English is the table itself")
    slugs = {slug for slug, _ in lunar.PHASES}
    assert slugs - set(lunar.TRANSLATIONS[code]) == set(), "untranslated phases"
    assert set(lunar.TRANSLATIONS[code]) - slugs == set(), "phases that do not exist"


def test_the_moon_speaks_french_too(speaking):
    speaking("fr")
    slug, label = lunar.phase(datetime(2000, 1, 21, 4, 40, tzinfo=UTC))
    assert slug == "full"
    assert label == "Pleine lune"


# -- Sample data ------------------------------------------------------------
#
# Descriptors are class attributes, so their prose is frozen when the module is
# imported — and frozen in English. The preview fell back to it and showed
# "Waning Gibbous" on a French installation while the matrix would say
# otherwise. The hook below is what the preview must go through.


def test_every_sample_follows_the_display_language(speaking):
    """Generic on purpose: a widget added later is covered without anyone
    remembering to extend this."""
    from app.connectors import registry

    registry.load_all()

    speaking("en")
    english = {
        widget.type: dict(owner.localised_sample(widget.type).values)
        for owner in (registry.owner(w.type) for d in registry.descriptors() for w in d.widgets)
        if owner
        for widget in owner.descriptor.widgets
    }

    speaking("fr")
    checked = 0
    for widget_type, values in english.items():
        owner = registry.owner(widget_type)
        french = dict(owner.localised_sample(widget_type).values)

        for key, value in values.items():
            if not isinstance(value, str) or f"{key}_code" not in values:
                continue  # not prose, or no slug to translate it from
            checked += 1
            assert french[key] != value or value == "", (
                f"{widget_type}.{key} stayed {value!r} in French"
            )
        # The slug is the contract and must not move.
        for key in (k for k in values if k.endswith("_code")):
            assert french[key] == values[key]

    assert checked >= 3, f"only {checked} prose values were exercised"


def test_a_sample_slug_nobody_translated_keeps_its_english(speaking):
    """Falling back beats blanking: a new weather code is usable the day it is
    added, translated or not."""
    speaking("fr")
    assert language.localise(wmo.TRANSLATIONS, "brand_new_code", "Brand new") == "Brand new"


def test_the_preview_route_goes_through_the_hook(client, speaking):
    """The wiring, not just the hook: the route used to read
    descriptor.sample_data straight and bypass every translation."""
    speaking("fr")
    response = client.post(
        "/api/widgets/preview",
        json={
            "widget_type": "moon.phase",
            "config": {},
            "connector_id": None,
            "display": {"text": "{{ phase }}"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sample"] is True, "this test only means something on the sample path"
    assert body["text"] == "Lune gibbeuse croissante"


def test_no_identifier_is_offered_in_the_builder(speaking):
    """The trap, closed rather than signposted.

    It has cost an hour twice. First with `{{ phase_code }}`, which showed
    `waning_gibbous` on a matrix where someone expected the phase. Then with
    `{{ quality_code }}`, which showed `MODERATE` under a French interface and
    sent two people hunting a translation bug for an hour — in a template that
    had explicitly asked for the untranslated word.

    The earlier answer was to make the two tellable apart: different labels,
    different examples. It was not enough, because they still sat side by side
    and "code" reads as "the code for the level".

    They are simply no longer offered. The template engine has no comparison —
    no `if`, no `==`, see ADR-006 — so a template can only ever *print* one,
    which is the mistake. They remain in the data, drive the icon and the
    colour, and still resolve if typed, so existing templates keep working.
    """
    from app.connectors import registry

    registry.load_all()
    speaking("fr")

    for descriptor in registry.descriptors():
        for widget in descriptor.widgets:
            offered = [v.name for v in widget.variables if v.name.endswith("_code")]
            assert not offered, f"{widget.type} offers {offered}"


def test_the_prose_is_offered_wherever_an_identifier_exists(speaking):
    """Removing one must not have removed both: every `x_code` the data
    carries needs an `x` someone can actually display."""
    from app.connectors import registry

    registry.load_all()
    speaking("fr")

    pairs = 0
    for descriptor in registry.descriptors():
        for widget in descriptor.widgets:
            offered = {v.name for v in widget.variables}
            for key in widget.sample_data.values:
                if key.endswith("_code"):
                    pairs += 1
                    assert key[:-5] in offered, f"{widget.type}: {key} has no prose twin"

    assert pairs >= 3, f"only {pairs} identifiers were checked"


class TestTheClocksLanguageIsSettable:
    """It lived in `.env` alone, and nothing said so.

    Someone switching the interface to French saw the air quality widget still
    reading "Moderate" with no way to learn why, let alone to fix it without
    opening a file — which the README promises nobody has to do.
    """

    def test_it_starts_from_the_environment(self, client):
        answer = client.get("/api/settings").json()
        assert answer["language"] in ("en", "fr")

    def test_setting_it_takes_effect_at_once(self, client):
        """Not at the next restart: a projection reads a module-level value
        that the write refreshes."""
        from app.core import language

        client.put("/api/settings", json={"language": "fr"})
        assert language.current() == "fr"

        client.put("/api/settings", json={"language": "en"})
        assert language.current() == "en"

    def test_it_survives_a_restart(self, client):
        """Stored, not held in memory."""
        from sqlmodel import Session, select

        from app.db.session import engine
        from app.models import LANGUAGE, Setting

        client.put("/api/settings", json={"language": "fr"})
        with Session(engine) as session:
            row = session.exec(select(Setting).where(Setting.key == LANGUAGE)).first()
        assert row is not None
        assert row.value == "fr"

    def test_an_unsupported_language_is_refused(self, client):
        """Rather than stored and silently falling back, which would leave the
        picker showing something the clocks do not speak."""
        assert client.put("/api/settings", json={"language": "klingon"}).status_code == 422

    def test_what_a_widget_says_follows_it(self, client):
        """The whole point, end to end."""
        from app.connectors import registry

        registry.load_all()
        owner = registry.owner("weather.uv")

        client.put("/api/settings", json={"language": "en"})
        assert owner.localised_sample("weather.uv").values["level"] == "Moderate"

        client.put("/api/settings", json={"language": "fr"})
        assert owner.localised_sample("weather.uv").values["level"] == "Modéré"

    def test_the_countdown_follows_it_too(self, client):
        """"J-406" was hard-coded French in an application whose default
        display language is English — the mirror of the bug reported."""
        from datetime import date, time

        from app.models import Reminder
        from app.services.scheduler import reminders as pass_

        reminder = Reminder(
            name="x", message="{{ countdown }}", at=time(8, 0), weekdays="0",
            countdown_to=date(2027, 11, 15),
        )
        client.put("/api/settings", json={"language": "en"})
        assert pass_.countdown_values(reminder, date(2027, 11, 15))["countdown"] == "D-DAY"

        client.put("/api/settings", json={"language": "fr"})
        assert pass_.countdown_values(reminder, date(2027, 11, 15))["countdown"] == "JOUR J"

    def test_french_reaches_the_matrix_spelt_properly(self, client):
        """It used to arrive stripped — "Modéré" as "Modere".

        That was AWTRIX 3, whose font drew a question mark for a letter it
        had not got, so dropping the accent was the lesser evil. NG draws
        them, measured character by character, and translating a word only to
        misspell it on the way out was the last thing standing between a
        French interface and a French display.
        """
        from app.widgets import template

        client.put("/api/settings", json={"language": "fr"})
        for word in ("Modéré", "Très élevé", "Graminées", "Dégradé"):
            assert template.for_matrix(word) == word


class TestChangingItRepushes:
    """Switching the language has to be visible at once.

    The air quality widgets refresh every half-hour. Without this, someone
    switching to French watched an English matrix for thirty minutes and
    reasonably concluded the setting did nothing — which is what happened.
    """

    def test_every_widget_becomes_due(self, client):
        from app.services.scheduler.loop import scheduler

        scheduler._due_at[1] = 9e9  # far in the future
        scheduler._due_at[2] = 9e9

        client.put("/api/settings", json={"language": "fr"})

        assert scheduler._due_at == {}

    def test_nothing_is_collected_again(self, client):
        """The cached upstream answers are still fresh: this re-projects and
        re-pushes, it does not ask anyone for data twice."""
        from app.services.scheduler.loop import scheduler

        before = scheduler.cache.misses
        client.put("/api/settings", json={"language": "fr"})
        assert scheduler.cache.misses == before


class TestHealthSaysWhichLanguage:
    """The only route that answers without a password.

    "The interface says French but the matrix says MODERATE" was undiagnosable
    from outside: one had to trust what a form showed about a value held in
    another process. A two-letter code beside a version number settles it.
    """

    def test_it_reports_the_clock_language(self, client):
        client.put("/api/settings", json={"language": "fr"})
        assert client.get("/api/health").json()["clock_language"] == "fr"

        client.put("/api/settings", json={"language": "en"})
        assert client.get("/api/health").json()["clock_language"] == "en"

    def test_it_still_needs_no_password(self, client, monkeypatch):
        """Adding a field must not have made it private."""
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert "clock_language" in body
