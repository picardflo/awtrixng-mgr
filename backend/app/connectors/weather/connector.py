"""Open-Meteo connector.

Chosen because it needs **no account and no API key** (prior-art §7), which
makes it the right first connector: it exercises the whole chain — schema,
form, collection, cache, template, renderer, scheduler, push — without any
credential handling in the way (§29 phase 4).
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.connectors.base import (
    Connector,
    ConnectorDescriptor,
    ConnectorTestResult,
    WidgetDescriptor,
)
from app.connectors.registry import register
from app.connectors.weather import air, sun, wmo
from app.core import language
from app.core.errors import ConnectorError
from app.schemas.fields import FormField, Option, Variable
from app.schemas.widget_data import DisplayOptions, WidgetData

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

#: Requested once for every weather widget, so a single call serves them all.
CURRENT_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "precipitation_probability",
    "weather_code",
    "wind_speed_10m",
    "is_day",
)

#: Sunrise, sunset and the length of the day — carried by the same response,
#: so asking for them costs one extra query parameter rather than a call.
#: Two days, because after today's sunset the next event is tomorrow's sunrise.
DAILY_VARIABLES = ("sunrise", "sunset", "daylight_duration")
FORECAST_DAYS = 2

#: The three that read the air-quality host rather than the forecast one.
AIR_WIDGETS = frozenset({"weather.air", "weather.uv", "weather.pollen"})

CONFIG_SCHEMA = [
    FormField(
        name="place",
        label="Place",
        type="place",
        required=True,
        placeholder="Lyon, Bordeaux, Berlin…",
        help="Search for a town. Exact coordinates can still be typed.",
    ),
]


def _project_air(
    widget_type: str, config: dict[str, Any], raw: dict[str, Any]
) -> WidgetData:
    """The three air widgets, from one response."""
    current = raw.get("current") or {}

    if widget_type == "weather.uv":
        uv = current.get("uv_index")
        band = air.uv_band(uv)
        return WidgetData(
            values={
                "uv": uv,
                "level_code": band.code,
                "level": language.localise(
                    air.UV_TRANSLATIONS, band.code, air.UV_ENGLISH[band.code]
                ),
            },
            hint_icon=str(band.icon),
            hint_color=band.colour,
        )

    if widget_type == "weather.pollen":
        species = str(config.get("species") or "grass")
        field, icon, colour = air.POLLENS.get(species, air.POLLENS["grass"])
        return WidgetData(
            values={
                "grains": current.get(field),
                "species_code": species,
                "species": language.localise(
                    air.POLLEN_TRANSLATIONS,
                    species,
                    air.POLLEN_ENGLISH_NAMES.get(species, species),
                ),
            },
            hint_icon=str(icon),
            hint_color=colour,
        )

    aqi = current.get("european_aqi")
    band = air.aqi_band(aqi)
    return WidgetData(
        values={
            "aqi": aqi,
            "quality_code": band.code,
            "quality": language.localise(
                air.AQI_TRANSLATIONS, band.code, air.AQI_ENGLISH[band.code]
            ),
            "pm2_5": current.get("pm2_5"),
            "pm10": current.get("pm10"),
            "no2": current.get("nitrogen_dioxide"),
            "o3": current.get("ozone"),
            "so2": current.get("sulphur_dioxide"),
        },
        hint_icon=str(band.icon),
        hint_color=band.colour,
    )


@register
class WeatherConnector(Connector):
    descriptor = ConnectorDescriptor(
        id="weather",
        name="Weather",
        description=(
            "Current conditions and rain from Open-Meteo. No account, no API "
            "key, no rate limit for personal use."
        ),
        icon="cloud",
        requires_credentials=False,
        config_schema=CONFIG_SCHEMA,
        widgets=[
            WidgetDescriptor(
                type="weather.current",
                name="Current weather",
                description="Temperature and conditions right now.",
                variables=[
                    Variable(name="temp", label="Temperature (°C)", example="18.4"),
                    Variable(name="feels_like", label="Feels like (°C)", example="17.1"),
                    Variable(name="humidity", label="Humidity (%)", example="66"),
                    Variable(name="wind", label="Wind (km/h)", example="10.6"),
                    Variable(name="precipitation", label="Precipitation (mm)", example="0"),
                    Variable(name="condition", label="Condition, as shown", example="Overcast"),
                    Variable(name="code", label="WMO code", example="3"),
                    Variable(name="is_day", label="Daytime", example="True"),
                ],
                # No words: the animated icon carries the condition, the text
                # carries the number. That is the whole 32x8 budget well spent.
                default_display=DisplayOptions(text="{{ temp | round }}°", duration=8),
                default_refresh=600,
                sample_data=WidgetData(
                    values={
                        "temp": 18.4,
                        "feels_like": 17.1,
                        "humidity": 66,
                        "wind": 10.6,
                        "precipitation": 0.0,
                        "condition": "Overcast",
                        "condition_code": "overcast",
                        "code": 3,
                        "is_day": True,
                    },
                    hint_icon=str(wmo.ICON_PARTLY_CLOUDY_DAY),
                    hint_color="#3ddc84",
                ),
            ),
            WidgetDescriptor(
                type="weather.rain",
                name="Rain",
                description=(
                    "Chance of rain. The icon and the colour forecast; "
                    "the overlay reports."
                ),
                variables=[
                    Variable(name="probability", label="Probability (%)", example="70"),
                    Variable(name="precipitation", label="Precipitation (mm)", example="0.4"),
                    Variable(name="condition", label="Condition, as shown", example="Rain"),
                ],
                default_display=DisplayOptions(
                    text="{{ probability }}%",
                    duration=8,
                    show_progress=True,
                    # Seven rows instead of five, and the seven above the bar:
                    # measured on a TC001, a two-digit figure with an icon and
                    # a progress bar still fits the 32 columns. The number is
                    # the whole point of this widget, so it may as well fill
                    # the panel.
                    font="large",
                ),
                default_refresh=600,
                sample_data=WidgetData(
                    values={
                        "probability": 70,
                        "precipitation": 0.4,
                        "condition": "Rain",
                        "condition_code": "rain",
                    },
                    progress=70,
                    hint_icon=str(wmo.ICON_RAIN),
                    hint_color="#4aa8ff",
                    hint_overlay=wmo.OVERLAY_RAIN,
                ),
            ),
            WidgetDescriptor(
                type="weather.humidity",
                name="Outdoor humidity",
                description="Water in the air, which is not the same question as rain.",
                variables=[
                    Variable(name="humidity", label="Relative humidity (%)", example="65"),
                    Variable(name="temp", label="Temperature (°C)", example="18"),
                    Variable(
                        name="feels_like",
                        label="Apparent temperature (°C)",
                        example="19.5",
                    ),
                    Variable(
                        name="probability",
                        label="Chance of rain (%), for a template that wants both",
                        example="30",
                    ),
                ],
                default_display=DisplayOptions(
                    text="{{ humidity | round }}%",
                    duration=8,
                    show_progress=True,
                    font="large",
                    # Florian's choice: a falling drop that splashes, 21 frames.
                    # It reads as water in the air rather than as weather to
                    # come, which is the distinction this widget exists for.
                    icon=str(wmo.ICON_HUMIDITY),
                ),
                default_refresh=600,
                sample_data=WidgetData(
                    values={
                        "humidity": 65,
                        "temp": 18.0,
                        "feels_like": 19.5,
                        "probability": 30,
                    },
                    progress=65,
                    hint_icon=str(wmo.ICON_HUMIDITY),
                    hint_color=wmo.colour_for_humidity(65),
                ),
            ),
            WidgetDescriptor(
                type="weather.sun",
                name="Sunrise and sunset",
                description=(
                    "When the sun comes up, when it goes down — and a bar "
                    "showing how much daylight is left."
                ),
                variables=[
                    Variable(name="sunrise", label="Sunrise", example="07:54"),
                    Variable(name="sunset", label="Sunset", example="19:27"),
                    Variable(name="next", label="Time of the next of the two", example="19:27"),
                    Variable(name="event", label="Which one is next, as shown", example="Sunset"),
                    Variable(
                        name="daylight",
                        label="Daylight (seconds) — try the duration filter",
                        example="41584",
                    ),
                    Variable(name="is_day", label="Daytime", example="True"),
                ],
                # The icon says which of the two it is, so the text only has
                # to carry the time. "07:54 19:27" would not fit beside an
                # icon anyway — 32 pixels hold about five characters there.
                default_display=DisplayOptions(
                    text="{{ next }}",
                    duration=8,
                    # The bar was computed from the first version and never
                    # switched on. `daylight_elapsed` is written, documented
                    # "drives the progress bar", returns None outside daylight
                    # so it cannot be read as a measurement at night — and the
                    # renderer threw it away for want of this flag.
                    #
                    # It turns a timestamp into something read at a glance:
                    # 19:27 says when, the bar says how much of the day is
                    # left.
                    show_progress=True,
                    # A time is four digits and a colon — nineteen columns in
                    # the large font, which is what the panel is for.
                    font="large",
                ),
                default_refresh=900,
                sample_data=WidgetData(
                    values={
                        "sunrise": "07:54",
                        "sunset": "19:27",
                        "next": "19:27",
                        "event": "Sunset",
                        "event_code": "sunset",
                        "daylight": 41584,
                        "is_day": True,
                    },
                    progress=62,
                    hint_icon=str(sun.ICON_SUNSET),
                    hint_color="#ffb347",
                ),
            ),
            WidgetDescriptor(
                type="weather.air",
                name="Air quality",
                description="The European index, and the pollutants behind it.",
                variables=[
                    Variable(name="aqi", label="European index", example="30"),
                    Variable(name="quality", label="Band, as shown", example="Fair"),
                    Variable(name="pm2_5", label="PM2.5 (µg/m³)", example="10.1"),
                    Variable(name="pm10", label="PM10 (µg/m³)", example="17.3"),
                    Variable(name="no2", label="Nitrogen dioxide (µg/m³)", example="7.6"),
                    Variable(name="o3", label="Ozone (µg/m³)", example="72"),
                    Variable(name="so2", label="Sulphur dioxide (µg/m³)", example="1.7"),
                ],
                default_display=DisplayOptions(text="{{ aqi }}", duration=8),
                default_refresh=air.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={
                        "aqi": 30, "quality": "Fair", "quality_code": "fair",
                        "pm2_5": 10.1, "pm10": 17.3, "no2": 7.6, "o3": 72.0, "so2": 1.7,
                    },
                    hint_icon=str(air.AQI_BANDS[1][1].icon),
                    hint_color=air.AQI_BANDS[1][1].colour,
                ),
            ),
            WidgetDescriptor(
                type="weather.uv",
                name="UV index",
                description="How strong the sun is, on the WHO scale.",
                variables=[
                    Variable(name="uv", label="Index", example="3.1"),
                    Variable(name="level", label="Band, as shown", example="Moderate"),
                ],
                # Rounded in the template rather than in the data: someone may
                # want the decimal.
                default_display=DisplayOptions(text="UV {{ uv | round }}", duration=8),
                default_refresh=air.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={"uv": 3.1, "level": "Moderate", "level_code": "moderate"},
                    hint_icon=str(air.UV_ICON),
                    hint_color=air.UV_BANDS[1][1].colour,
                ),
            ),
            WidgetDescriptor(
                type="weather.pollen",
                name="Pollen",
                description="One species' concentration, for whoever reacts to it.",
                fields=[
                    FormField(
                        name="species",
                        label="Pollen",
                        type="select",
                        required=True,
                        default="grass",
                        help="One widget per species: 'pollen' in general helps nobody.",
                        options=[
                            Option(value=slug, label=air.POLLEN_ENGLISH_NAMES[slug])
                            for slug in air.POLLENS
                        ],
                    ),
                ],
                variables=[
                    Variable(name="grains", label="Grains per m³", example="12.4"),
                    Variable(name="species", label="Which pollen, as shown", example="Grass"),
                ],
                # The figure, plain. It is what the API gives and what
                # someone allergic actually reads.
                default_display=DisplayOptions(text="{{ grains | round }}", duration=8),
                default_refresh=air.CACHE_SECONDS,
                sample_data=WidgetData(
                    values={
                        "grains": 12.4, "species": "Grass", "species_code": "grass",
                    },
                    hint_icon=str(air.POLLEN_ICON_GRASS),
                    hint_color=air.POLLENS["grass"][2],
                ),
            ),
        ],
    )

    # -- Collection -----------------------------------------------------------

    def request_key(self, widget_type: str, config: dict[str, Any]) -> tuple[str, int]:
        # Both widgets read the same response, so they share one call. Keyed on
        # the coordinates, so two connectors on the same spot share it too.
        latitude, longitude = self._coordinates()
        if widget_type in AIR_WIDGETS:
            # A different host, so a different call and its own cache entry —
            # unlike the sun, which rides along on the forecast. The three air
            # widgets share this one between them.
            return f"air:{latitude:.4f},{longitude:.4f}", air.CACHE_SECONDS
        # Open-Meteo refreshes its current conditions every 15 minutes; polling
        # faster only wastes both ends. §6 asks for 10 minutes.
        return f"weather:{latitude:.4f},{longitude:.4f}", 600

    async def collect(self, widget_type: str, config: dict[str, Any]) -> dict[str, Any]:
        # The place is connector configuration, not widget configuration: every
        # weather widget on this connector reads the same coordinates.
        latitude, longitude = self._coordinates()
        if widget_type in AIR_WIDGETS:
            return await air.fetch(self.client, latitude, longitude)
        return await self._request(latitude, longitude)

    async def _request(self, latitude: float, longitude: float) -> dict[str, Any]:
        try:
            response = await self.client.get(
                ENDPOINT,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": ",".join(CURRENT_VARIABLES),
                    "daily": ",".join(DAILY_VARIABLES),
                    "forecast_days": FORECAST_DAYS,
                    # Local time for the place, not for this server: the
                    # response then carries utc_offset_seconds, which is what
                    # makes "is the sun already up there" answerable.
                    "timezone": "auto",
                },
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"Open-Meteo is unreachable: {exc or type(exc).__name__}",
                code="weather.unreachable",
                params={"reason": str(exc) or type(exc).__name__},
            ) from exc

        if response.status_code >= 400:
            # Open-Meteo answers 400 with a JSON body explaining what it did
            # not like — far more useful than the status code alone.
            reason = self._reason(response)
            raise ConnectorError(
                f"Open-Meteo refused the request: {reason}",
                code="weather.rejected",
                params={"reason": reason},
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorError(
                "Open-Meteo returned a non-JSON response.", code="weather.bad_response"
            ) from exc

    @staticmethod
    def _reason(response: httpx.Response) -> str:
        try:
            return str(response.json().get("reason") or response.status_code)
        except ValueError:
            return str(response.status_code)

    def _coordinates(self) -> tuple[float, float]:
        """Where to fetch the weather for.

        The place lives under `place` since the search replaced the two number
        fields. Top-level `latitude`/`longitude` are still read so a connector
        configured before that change keeps working.
        """
        source = self.config.get("place") or self.config
        try:
            return float(source["latitude"]), float(source["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConnectorError(
                "Pick a place for this connector.", code="weather.no_place"
            ) from exc

    @property
    def place_name(self) -> str | None:
        place = self.config.get("place")
        return place.get("name") if isinstance(place, dict) else None

    @classmethod
    def localised_sample(cls, widget_type: str) -> WidgetData:
        sample = super().localised_sample(widget_type)
        values = dict(sample.values)
        slug = values.get("condition_code")
        if slug:
            values["condition"] = language.localise(
                wmo.TRANSLATIONS, str(slug), str(values.get("condition", ""))
            )
        for slug_key, prose_key, table in (
            ("quality_code", "quality", air.AQI_TRANSLATIONS),
            ("level_code", "level", air.UV_TRANSLATIONS),
            ("species_code", "species", air.POLLEN_TRANSLATIONS),
        ):
            slug = values.get(slug_key)
            if slug:
                values[prose_key] = language.localise(
                    table, str(slug), str(values.get(prose_key, ""))
                )

        event_code = values.get("event_code")
        if event_code:
            values["event"] = language.localise(
                sun.TRANSLATIONS, str(event_code), str(values.get("event", ""))
            )
        return sample.model_copy(update={"values": values})

    @staticmethod
    def _project_sun(raw: dict[str, Any], current: dict[str, Any]) -> WidgetData:
        now = datetime.now(UTC)
        sunrise, sunset = sun.today(raw, now)
        upcoming = sun.next_event(raw, now)
        daily = raw.get("daily") or {}
        daylight = (daily.get("daylight_duration") or [None])[0]

        def clock(moment: datetime | None) -> str | None:
            return moment.strftime("%H:%M") if moment else None

        return WidgetData(
            values={
                "sunrise": clock(sunrise),
                "sunset": clock(sunset),
                "next": clock(upcoming.at) if upcoming else None,
                "event_code": upcoming.code if upcoming else None,
                "event": language.localise(
                    sun.TRANSLATIONS,
                    upcoming.code if upcoming else "",
                    sun.ENGLISH.get(upcoming.code, "") if upcoming else "",
                ),
                # Seconds, so `{{ daylight | duration }}` reads "11H33" — the
                # filter is already there and already tested.
                "daylight": int(daylight) if isinstance(daylight, int | float) else None,
                "is_day": bool(current.get("is_day")),
            },
            progress=sun.daylight_elapsed(sunrise, sunset, sun.local_now(raw, now)),
            hint_icon=str(upcoming.icon) if upcoming else str(sun.ICON_SUNRISE),
            hint_color=sun.COLOURS.get(upcoming.code if upcoming else "", "#ffb347"),
        )

    # -- Projection -----------------------------------------------------------

    def project(
        self, widget_type: str, config: dict[str, Any], raw: dict[str, Any]
    ) -> WidgetData:
        current = raw.get("current") or {}
        slug, label = wmo.describe(current.get("weather_code"))

        if widget_type in AIR_WIDGETS:
            return _project_air(widget_type, config, raw)

        if widget_type == "weather.sun":
            return self._project_sun(raw, current)

        if widget_type == "weather.rain":
            probability = current.get("precipitation_probability")
            return WidgetData(
                values={
                    "probability": probability,
                    "precipitation": current.get("precipitation"),
                    "condition": label,
                    "condition_code": slug,
                },
                progress=int(probability) if probability is not None else None,
                hint_icon=wmo.precipitation_icon(
                    current.get("weather_code"),
                    probability,
                    is_day=bool(current.get("is_day")),
                ),
                hint_color=wmo.colour_for_precipitation(
                    current.get("weather_code"), probability
                ),
                # From the condition, never from the probability. This is the
                # threshold question answered by refusing it: at a 70 % chance
                # under a clear sky, a matrix that rains is lying. It rains on
                # screen when it is raining outside, and not before.
                #
                # **The icon and the colour do not follow this rule**, and that
                # is deliberate — Florian's call, 5 October 2026. They follow
                # the probability, so the widget says two things at once: the
                # cloud and the blue announce what is coming, the overlay
                # reports what is happening. Bergen measured at 98 % under an
                # overcast sky shows a rain cloud and a dry matrix, which is
                # the case worth understanding.
                #
                # It reads as one thing only if someone says so, which is why
                # the widget's own description does.
                hint_overlay=wmo.overlay_for(current.get("weather_code")),
            )

        if widget_type == "weather.humidity":
            humidity = current.get("relative_humidity_2m")
            return WidgetData(
                values={
                    "humidity": humidity,
                    "temp": current.get("temperature_2m"),
                    "feels_like": current.get("apparent_temperature"),
                    "probability": current.get("precipitation_probability"),
                },
                # The bar shows the same number the text does. Deliberately:
                # two quantities under one colour scale would make the scale
                # mean two things, and a bar that repeats the figure is read
                # from across a room where eight-pixel digits are not.
                progress=int(humidity) if humidity is not None else None,
                hint_icon=str(wmo.ICON_HUMIDITY),
                hint_color=wmo.colour_for_humidity(humidity),
            )

        temperature = current.get("temperature_2m")
        is_day = bool(current.get("is_day"))
        return WidgetData(
            values={
                "temp": temperature,
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind": current.get("wind_speed_10m"),
                "precipitation": current.get("precipitation"),
                "condition": label,
                "condition_code": slug,
                "code": current.get("weather_code"),
                "is_day": is_day,
            },
            # An animated icon says more on 32x8 than a word would, and costs
            # no horizontal space the text needs.
            hint_icon=wmo.icon_for(current.get("weather_code"), is_day=is_day),
            hint_color=wmo.colour_for_temperature(temperature),
            # And NG can draw the weather over the whole app, which is what a
            # 32x8 panel is actually good at: showing rather than describing.
            # None for most codes — a matrix that drizzles under a clear sky
            # is worse than one that draws nothing.
            hint_overlay=wmo.overlay_for(current.get("weather_code")),
        )

    # -- Test -----------------------------------------------------------------

    async def test_connection(self) -> ConnectorTestResult:
        latitude, longitude = self._coordinates()
        payload = await self._request(latitude, longitude)
        current = payload.get("current") or {}
        temperature = current.get("temperature_2m")
        _, label = wmo.describe(current.get("weather_code"))
        return ConnectorTestResult(
            ok=True,
            message=(
                f"Open-Meteo answered for {self.place_name or 'this place'}: "
                f"{temperature} °C, {label.lower()}."
            ),
            code="weather.connected",
            params={
                "temperature": temperature,
                "condition": label,
                "place": self.place_name or "",
            },
            details={"timezone": payload.get("timezone"), "elevation": payload.get("elevation")},
        )
