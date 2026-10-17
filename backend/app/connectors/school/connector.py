"""Which school week it is, and how much of it is left.

French collèges alternate a "semaine A" and a "semaine B" timetable. The letter
is not national: each établissement sets it. What *is* national is the calendar
it rides on, so the rule here is anchored on the first day back and can be
flipped in one click for a school that numbers them the other way.
"""

from datetime import date, timedelta
from typing import Any

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.registry import register
from app.connectors.school import calendar as cal
from app.core import language
from app.core.errors import AwtrixNgError
from app.schemas.fields import FormField, Option, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData

#: A calendar published years ahead does not need asking about often. Long
#: enough that a matrix refreshing every minute costs one call a day.
CACHE_SECONDS = 6 * 3600

#: "Time for school" — checked against the artwork, not picked by its name.
ICON = "2536"

#: One animated icon per holiday period, and the weather NG draws over the
#: text for the two that have one. Florian's idea: « plutôt qu'un compteur
#: 16j à 0, une petite animation — feuille orangée avec du vent pour
#: l'automne, un père Noël qui défile avec son traîneau pour Noël ».
#:
#: Matched on the period's name because that is what the Ministry publishes,
#: and it is stable: "Vacances de la Toussaint", "Vacances de Noël". The key
#: is a word that cannot appear in another period's name.
#:
#: Every one was pushed to a TC001 and read back before being chosen. Two
#: were rejected there: a flower that renders as white and red blocks at
#: eight pixels, and a counter with no icon at all, where the snow falls
#: across scrolling text and makes it harder to read rather than prettier.
#:
#: The overlay is the part that costs nothing: snow is drawn by the firmware,
#: over the text, and the counter stays legible underneath — measured.
SEASONS: dict[str, tuple[str, str | None, str]] = {
    # mot-clé        icône    surimpression  couleur
    "toussaint": ("70643", None, "#ff8f80"),
    "noël": ("24817", "snow", "#79c0ff"),
    "noel": ("24817", "snow", "#79c0ff"),
    "hiver": ("33131", "snow", "#79c0ff"),
    "printemps": ("40484", None, "#ff9ecb"),
    "été": ("27253", None, "#ffb65c"),
    "ete": ("27253", None, "#ffb65c"),
    "ascension": ("37677", None, "#6ee7a0"),
}


def season_for(name: str) -> tuple[str, str | None, str] | None:
    """The icon, overlay and colour of a named holiday period.

    None for a name no release of the dataset has used yet — a period this
    code has never heard of keeps the ordinary school icon rather than
    borrowing the wrong season's.
    """
    lowered = (name or "").lower()
    for keyword, season in SEASONS.items():
        if keyword in lowered:
            return season
    return None

#: The letter is the one fact this widget exists to give, and a colour is read
#: before a word is. Cyan and violet rather than two neighbouring shades: at
#: eight pixels, across a room, close colours are one colour.
#:
#: Holidays keep the green they have always had, and need a third anyway —
#: there is then neither an A nor a B.
COLOUR_A = "#4aa8ff"
COLOUR_B = "#b48cff"
COLOUR_HOLIDAY = "#3ddc84"


def colour_for(letter: str, *, holiday: bool) -> str:
    """Holidays first: during them the letter is meaningless, not merely
    unknown, and `week_letter` keeps counting through them."""
    if holiday:
        return COLOUR_HOLIDAY
    return COLOUR_B if letter.upper() == "B" else COLOUR_A

TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {"week": "Semaine {letter}", "holiday": "{name}", "back": "J-{days}"},
}
DEFAULTS = {"week": "Week {letter}", "holiday": "{name}", "back": "{days}d"}


@register
class SchoolConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="school",
        name="School calendar",
        description=(
            "Week A or week B, and the days left before the next holiday. "
            "Official French calendar, no account and no API key."
        ),
        icon="calendar",
        requires_credentials=False,
        config_schema=[
            FormField(
                name="academie",
                label="Académie",
                type="select",
                required=True,
                default="Versailles",
                help="Holidays differ by zone; the académie decides which.",
                options=[Option(value=name, label=name) for name in cal.ACADEMIES],
            ),
            FormField(
                name="invert",
                label="Swap A and B",
                type="boolean",
                required=False,
                default=False,
                help=(
                    "The first week back counts as A. Tick this if your school "
                    "calls it B."
                ),
            ),
        ],
        widgets=[
            WidgetDescriptor(
                type="school.week",
                name="School week",
                description="Week A or B, with the days left before the weekend.",
                fields=[],
                variables=[
                    Variable(name="summary", label="Ready to display", example="Semaine A"),
                    Variable(name="week", label="The letter", example="A"),
                    Variable(
                        name="days_left",
                        label="School days left, today included",
                        example="3",
                    ),
                    Variable(name="school_days", label="School days this week", example="5"),
                    Variable(name="holiday", label="On holiday", example="False"),
                    Variable(
                        name="holiday_name",
                        label="Which holiday",
                        example="Vacances de la Toussaint",
                    ),
                    Variable(
                        name="days_to_holiday",
                        label="Days to the next holiday",
                        example="12",
                    ),
                    Variable(
                        name="days_to_school",
                        label="Days until school resumes — only during the holidays",
                        example="16",
                    ),
                    Variable(
                        name="countdown",
                        label="Whichever of the two is the one worth showing today",
                        example="16",
                    ),
                    Variable(
                        name="season",
                        label="The period being counted, which sets the icon",
                        example="Vacances de Noël",
                    ),
                ],
                default_display=DisplayOptions(
                    # `{{ summary }}` reads "Semaine A", which is nine
                    # characters — about 35 columns where an icon leaves 23.
                    # It scrolled, which works and is still a poor default: a
                    # glance at a clock should not have to wait for the text
                    # to come round. Measured on the panel, not guessed.
                    text="Sem. {{ week }}",
                    icon=ICON,
                    duration=8,
                    # Large is the font of a widget that has a bar: it draws
                    # the seven rows above it and fills the panel exactly.
                    # Measured — with the small font the text sat squeezed
                    # against the bar, rows 1 to 7 with row 0 empty.
                    font="large",
                    # The firmware's own weekday bar, reused: seven segments
                    # of three pixels instead of one filled proportion. A bar
                    # at 60 % says nothing about *which* days are left; seven
                    # marks say it at a glance, and they line up pixel for
                    # pixel with the Date app that follows in the rotation.
                    show_days=True,
                    progress_color="#3ddc84",
                    progress_background="#000000",
                ),
                sample_data=WidgetData(
                    values={
                        "summary": "Semaine A",
                        "week": "A",
                        "days_left": 3,
                        "school_days": 5,
                        "holiday": False,
                        "holiday_name": "",
                        "days_to_holiday": 12,
                    },
                    progress=60,
                    days=["past", "past", "today", "school", "school",
                          "off", "off"],
                    hint_icon=ICON,
                    hint_color="#3ddc84",
                ),
                # The letter changes once a week and the day once a day; an
                # hour is frequent enough, and survives a midnight restart.
                default_refresh=3600,
            )
        ],
    )

    # -- Collection -----------------------------------------------------------

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        return f"school:{self._academie()}", CACHE_SECONDS

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        # The periods travel as objects: the cache holds them in memory, so
        # there is nothing to serialise and nothing to parse back.
        return {"periods": await cal.fetch_periods(self._academie(), self.client)}

    def _academie(self) -> str:
        chosen = str(self.config.get("academie") or "Versailles")
        return chosen if chosen in cal.ACADEMIES else "Versailles"

    # -- Projection -----------------------------------------------------------

    def project(
        self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]
    ) -> WidgetData:
        periods: list[cal.Period] = raw["periods"]
        day = cal.today()
        return self._describe(day, periods, invert=bool(self.config.get("invert")))

    @staticmethod
    def _describe(day: date, periods: list[cal.Period], *, invert: bool) -> WidgetData:
        holiday = cal.holiday_on(periods, day)
        rentree = cal.rentree_before(periods, day)
        letter = cal.week_letter(day, rentree, invert=invert) if rentree else ""
        remaining, total = cal.school_days_of_week(day, periods)
        semaine = cal.week_days(day, periods)
        upcoming = cal.next_holiday(periods, day)

        back_in = None
        if holiday is not None:
            # Counting to the morning school resumes, which is the day after
            # the last day off.
            back_in = (holiday.end - day).days + 1
            summary = _t("holiday", name=holiday.name)
            if back_in > 0:
                summary = f"{summary} {_t('back', days=back_in)}"
        else:
            summary = _t("week", letter=letter) if letter else ""

        # The season belongs to the period being counted: the one we are in
        # during the holidays, the one we are waiting for during term. So the
        # sleigh appears in December while school is still on, which is the
        # point — it is the arrival being counted down to.
        counted = holiday or upcoming
        season = season_for(counted.name) if counted else None

        return WidgetData(
            values={
                "summary": summary,
                "week": letter,
                "days_left": remaining,
                "school_days": total,
                "holiday": holiday is not None,
                "holiday_name": holiday.name if holiday else "",
                "days_to_holiday": (upcoming.start - day).days if upcoming else None,
                # The count that only existed inside a sentence. During the
                # holidays "63 days to the next ones" is true and useless;
                # what someone wants is the morning school resumes.
                "days_to_school": back_in,
                # The one number that is always the useful one, because a
                # template has no `if`. During term it counts to the holidays;
                # during the holidays it counts to the morning school resumes.
                # `J-{{ countdown }}` therefore says the right thing all year
                # without anybody composing two widgets.
                "countdown": back_in if holiday is not None else (
                    (upcoming.start - day).days if upcoming else None
                ),
                "season": counted.name if counted else "",
            },
            # Full on Monday morning, empty once Friday is over. During the
            # holidays there is nothing left to count down.
            # Kept as well: someone may prefer a plain bar, and the
            # preview needs a figure to show beside the segments.
            progress=round(remaining / total * 100) if total else 0,
            days=semaine,
            hint_icon=season[0] if season else ICON,
            hint_overlay=season[1] if season else None,
            # **The colour follows the season only during the holidays.**
            #
            # In term time this widget exists to say A or B, and the comment
            # on `colour_for` is right that a colour is read before a word is.
            # Painting it autumn-orange because Toussaint is coming destroys
            # the one fact it is there to give. A test caught exactly that,
            # which is what tests defending a decision are for.
            #
            # During the holidays there is no letter, so the season is free to
            # take the colour too — and that is when it means something.
            hint_color=(
                season[2]
                if season and holiday is not None
                else colour_for(letter, holiday=holiday is not None)
            ),
        )

    def preview_dates(self, widget_type: str, raw: Any) -> list[tuple[str, date]]:
        """One per holiday period of the year ahead, labelled by the Ministry.

        The labels are not written here: they are the names the dataset
        publishes, so a year that renames a period renames the button too.
        The date offered is the period's **second day** rather than its first
        — on the first, the countdown to school is at its maximum and the
        preview shows the same figure as the day before.
        """
        periods: list[cal.Period] = raw["periods"]
        today = cal.today()
        ahead = sorted((p for p in periods if p.end >= today), key=lambda p: p.start)
        return [(p.name, p.start + timedelta(days=1)) for p in ahead[:6]]

    def project_as_of(
        self, widget_type: str, config: dict[str, Any], raw: Any, day: date
    ) -> WidgetData | None:
        if widget_type != "school.week":
            return None
        periods: list[cal.Period] = raw["periods"]
        return self._describe(day, periods, invert=bool(self.config.get("invert")))

    # -- Test -----------------------------------------------------------------

    async def test_connection(self) -> ConnectorTestResult:
        academie = self._academie()
        try:
            periods = await cal.fetch_periods(academie, self.client)
        except AwtrixNgError as exc:
            return ConnectorTestResult(
                ok=False, message=exc.message, code=exc.code, params=exc.params
            )

        day = cal.today()
        data = self._describe(day, periods, invert=bool(self.config.get("invert")))
        return ConnectorTestResult(
            ok=True,
            message=f"{academie}: {data.values['summary']}.",
            code="school.ok",
            params={"academie": academie, "summary": data.values["summary"]},
            details={"periods": len(periods), "week": data.values["week"]},
        )


def _t(key: str, **params: Any) -> str:
    return language.localise(TRANSLATIONS, key, DEFAULTS[key]).format(**params)
