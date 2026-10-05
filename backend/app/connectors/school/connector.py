"""Which school week it is, and how much of it is left.

French collèges alternate a "semaine A" and a "semaine B" timetable. The letter
is not national: each établissement sets it. What *is* national is the calendar
it rides on, so the rule here is anchored on the first day back and can be
flipped in one click for a school that numbers them the other way.
"""

from datetime import date
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
                    show_progress=True,
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
        upcoming = cal.next_holiday(periods, day)

        if holiday is not None:
            # Counting to the morning school resumes, which is the day after
            # the last day off.
            back_in = (holiday.end - day).days + 1
            summary = _t("holiday", name=holiday.name)
            if back_in > 0:
                summary = f"{summary} {_t('back', days=back_in)}"
        else:
            summary = _t("week", letter=letter) if letter else ""

        return WidgetData(
            values={
                "summary": summary,
                "week": letter,
                "days_left": remaining,
                "school_days": total,
                "holiday": holiday is not None,
                "holiday_name": holiday.name if holiday else "",
                "days_to_holiday": (upcoming.start - day).days if upcoming else None,
            },
            # Full on Monday morning, empty once Friday is over. During the
            # holidays there is nothing left to count down.
            progress=round(remaining / total * 100) if total else 0,
            hint_icon=ICON,
            hint_color=colour_for(letter, holiday=holiday is not None),
        )

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
