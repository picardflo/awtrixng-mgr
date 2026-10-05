"""Phase of the Moon.

The only connector with nothing upstream. The phase is computed from the date
(see `phase.py`), so this service cannot be down, cannot be rate-limited and
needs no key — which is also why it has nothing to configure.

That is the reason it is not a weather widget: an Open-Meteo outage has no
business taking the Moon with it.
"""

from datetime import UTC, datetime
from typing import Any

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.moon import phase as lunar
from app.connectors.registry import register
from app.core import language
from app.schemas.fields import Variable
from app.schemas.widget_data import DisplayOptions, WidgetData

#: LaMetric icons, checked one by one rather than guessed from their titles:
#: the set numbers 2314–2321 draws the lit limb on the left for the single
#: dash and on the right for the double one.
#:
#: In the northern hemisphere the Moon waxes from the right, so the
#: double-dash icons are the waxing half. Below the equator this is mirrored —
#: the set simply does not cover that case, and neither do we.
ICONS: dict[str, str] = {
    "new": "2318",
    "waxing_crescent": "2321",
    "first_quarter": "2320",
    "waxing_gibbous": "2319",
    "full": "2314",
    "waning_gibbous": "2315",
    "last_quarter": "2316",
    "waning_crescent": "2317",
}

#: Pale silver, the colour of the thing itself. The phase is carried by the
#: icon, so the text has no colour to convey.
COLOUR = "#c8d2dc"


@register
class MoonConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="moon",
        name="Moon",
        description=(
            "The phase of the Moon, computed locally. Nothing to configure, "
            "nothing to fail: no account, no API key, no network."
        ),
        icon="moon",
        requires_credentials=False,
        config_schema=[],
        widgets=[
            WidgetDescriptor(
                type="moon.phase",
                name="Moon phase",
                description="Which phase the Moon is in, and how lit it is.",
                fields=[],
                variables=[
                    Variable(name="phase", label="Phase, as shown", example="Waxing Gibbous"),
                    Variable(name="illumination", label="Lit fraction (%)", example="82"),
                    Variable(name="age", label="Days since the new moon", example="11.4"),
                    Variable(name="next_full", label="Days to the full moon", example="3.2"),
                    Variable(name="next_new", label="Days to the new moon", example="17.9"),
                ],
                default_display=DisplayOptions(
                    text="{{ illumination }}%",
                    duration=8,
                    # The bar was computed from the first version and never
                    # switched on — the projection has filled `progress` with
                    # the lit fraction all along, under a comment saying it
                    # "shows the same thing as the icon, in another form".
                    #
                    # Illumination is the one reading here that is already a
                    # percentage, so the scale needs no inventing.
                    show_progress=True,
                    # Large is the font of a widget that has a bar: measured,
                    # it draws the seven rows above it and fills the panel
                    # exactly. Without a bar it sits one row high.
                    font="large",
                ),
                # Fixed rather than computed at import: a descriptor that
                # changed with the date would make two installations disagree
                # about what a sample looks like. The preview uses the real
                # phase as soon as the widget exists anyway.
                sample_data=WidgetData(
                    values={
                        "phase": "Waxing Gibbous",
                        "phase_code": "waxing_gibbous",
                        "illumination": 82,
                        "age": 11.4,
                        "next_full": 3.2,
                        "next_new": 17.9,
                    },
                    progress=82,
                    hint_icon=ICONS["waxing_gibbous"],
                    hint_color=COLOUR,
                ),
                # The phase moves by a degree every two hours. Anything more
                # frequent recomputes the same name and the same percentage.
                default_refresh=1800,
            )
        ],
    )

    # -- Collection -----------------------------------------------------------

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        # No place, no account, so every moon widget in the installation shares
        # one result — which costs microseconds anyway.
        return "moon", 600

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        return self._reading(datetime.now(UTC))

    @staticmethod
    def _reading(moment: datetime) -> dict[str, Any]:
        slug, label = lunar.phase(moment)
        return {
            "phase": label,
            "phase_code": slug,
            "illumination": round(lunar.illumination(moment)),
            "age": round(lunar.age(moment), 1),
            "next_full": round(lunar.days_until(moment, 180.0), 1),
            "next_new": round(lunar.days_until(moment, 360.0), 1),
        }

    @classmethod
    def localised_sample(cls, widget_type: str) -> WidgetData:
        sample = super().localised_sample(widget_type)
        values = dict(sample.values)
        slug = values.get("phase_code")
        if slug:
            values["phase"] = language.localise(
                lunar.TRANSLATIONS, str(slug), str(values.get("phase", ""))
            )
        return sample.model_copy(update={"values": values})

    # -- Projection -----------------------------------------------------------

    def project(
        self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]
    ) -> WidgetData:
        return WidgetData(
            values=dict(raw),
            # The lit fraction is already a proportion, so the progress bar
            # shows the same thing as the icon, in another form.
            progress=int(raw["illumination"]),
            hint_icon=ICONS.get(raw["phase_code"]),
            hint_color=COLOUR,
        )

    # -- Test -----------------------------------------------------------------

    async def test_connection(self) -> ConnectorTestResult:
        """There is nothing to reach, so the test reports what it computes —
        which is the only thing that could be wrong."""
        reading = self._reading(datetime.now(UTC))
        return ConnectorTestResult(
            ok=True,
            message=f"{reading['phase']}, {reading['illumination']}% lit.",
            code="moon.ok",
            params={
                "phase": reading["phase"],
                "illumination": reading["illumination"],
            },
            details={"phase": reading["phase_code"], "age": reading["age"]},
        )
