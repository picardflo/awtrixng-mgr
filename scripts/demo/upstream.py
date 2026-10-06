"""Everything awtrixng-mgr talks to, faked.

Screenshots must not depend on the weather, on the time of day, or on a clock
being plugged in — and above all they must never touch real hardware: a
reconciler pointed at a display in service deletes the apps it does not know.

So the demo runs against this: two invented AWTRIX displays and an invented
Open-Meteo. Same shapes as the real thing, fixed values.
"""

import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

ROOT = Path(__file__).resolve().parents[2]

#: One profile per port, so two displays can differ without two codebases.
PROFILES: dict[int, dict[str, Any]] = {
    9101: {
        "name": "Office",
        "uid": "b0cbd8a1b560",
        "ipAddress": "192.168.11.211",
        "hostname": "awtrix-cl2",
        "version": "1.1.2",
        "boardType": "awtrixng",
        "soc": "esp32",
        "uptimeSeconds": 421_337,
        "batteryPercent": 87,
        "batteryVoltage": 4.09,
        "lowBattery": False,
        "temperature": 21.4,
        "humidity": 48.0,
        "lightLevel": 13.2,
        "ldrRaw": 412,
        "brightness": 80,
        "wifiRssi": -52,
        "freeHeapBytes": 118_640,
        "matrixPower": True,
        "fps": 42,
        "resetReason": "software",
    },
    9102: {
        "name": "Living room",
        "uid": "b0cbd8a1b561",
        "ipAddress": "192.168.11.212",
        "hostname": "awtrix-cl1",
        "version": "1.1.2",
        "boardType": "awtrixng",
        "soc": "esp32",
        "uptimeSeconds": 98_210,
        "batteryPercent": 64,
        "batteryVoltage": 3.91,
        "lowBattery": False,
        "temperature": 19.8,
        "humidity": 55.0,
        "lightLevel": 4.1,
        "ldrRaw": 128,
        "brightness": 60,
        "wifiRssi": -67,
        "freeHeapBytes": 121_004,
        "matrixPower": True,
        "fps": 42,
        "resetReason": "poweron",
    },
}

#: Custom apps pushed by awtrixng-mgr, per port. Populated as the demo runs, so
#: the loop shown in the interface is the one awtrixng-mgr actually created.
PUSHED: dict[int, dict[str, Any]] = {port: {} for port in PROFILES}

#: The measured responses, served as they came off the hardware.
#:
#: Loaded from `docs/ng-api/` rather than copied in: those files are the
#: relevant part of the project's record, and a demo that invented its own
#: would drift from what the firmware actually answers — which is the one
#: thing it exists to reproduce.
_MEASURED = ROOT / "docs" / "ng-api"


def _recorded(name: str) -> Any:
    return json.loads((_MEASURED / f"{name}.json").read_text(encoding="utf-8"))


#: The 42 display settings, including the keys this project deliberately
#: leaves alone — a write must never carry them back.
SETTINGS: dict[int, dict[str, Any]] = {
    port: _recorded("settings") for port in PROFILES
}

#: The 66 hardware and network settings. `minBrightness` lives here, and it is
#: what replaced the old bedroom mode.
SYSTEM: dict[int, dict[str, Any]] = {port: _recorded("system") for port in PROFILES}

#: What the firmware declares it can do. Read rather than hard-coded by the
#: application, so the demo has to answer it too.
CAPABILITIES: dict[str, Any] = _recorded("capabilities")

#: Panel state. `power` is the one with no AWTRIX 3 equivalent.
DISPLAY: dict[int, dict[str, Any]] = {
    port: {"power": True, "brightness": 80, "overlay": None, "moodlight": None}
    for port in PROFILES
}

#: Icons already on the display, so the interface can show some installed.
ICONS: dict[int, set[str]] = {
    9101: {"12183.gif", "2422.gif", "55274.gif"},
    9102: {"12183.gif"},
}


def _port(request: Request) -> int:
    return request.url.port or 9101


def _profile(request: Request) -> dict[str, Any]:
    return PROFILES.get(_port(request), PROFILES[9101])


# -- The display, speaking /api/v1 -------------------------------------------
#
# Rewritten from the AWTRIX 3 version: every route moved, the payload keys
# changed, and the shapes with them. Each answer below mirrors one kept in
# `docs/ng-api/`, read off a real TC001.


async def device(request: Request) -> JSONResponse:
    profile = dict(_profile(request))
    profile.pop("name", None)
    profile["currentApp"] = "Time"
    return JSONResponse(profile)


async def capabilities(request: Request) -> JSONResponse:
    return JSONResponse(CAPABILITIES)


async def version(request: Request) -> JSONResponse:
    return JSONResponse({"version": _profile(request)["version"]})


async def apps(request: Request) -> JSONResponse:
    """Builtins first, then whatever was pushed.

    `origin` is the field that made reconciliation safe: it is what tells a
    firmware app from one of ours, where AWTRIX 3 left only a name prefix.
    """
    port = _port(request)
    listing = [
        {"name": name, "enabled": True, "inLoop": True, "slot": None,
         "present": True, "origin": "builtin"}
        for name in ("Time", "Date", "Temperature", "Humidity", "Battery")
    ]
    listing += [
        {"name": name, "enabled": True, "inLoop": True, "slot": None,
         "present": True, "origin": "pushed"}
        for name in PUSHED[port]
    ]
    return JSONResponse(listing)


async def push_app(request: Request) -> JSONResponse:
    PUSHED[_port(request)][request.path_params["name"]] = await request.json()
    return JSONResponse({"ok": True})


async def delete_app(request: Request) -> JSONResponse:
    """By exact name. AWTRIX 3 deleted by prefix, which is why the previous
    project padded its app names; measured on NG, that hazard is gone."""
    PUSHED[_port(request)].pop(request.path_params["name"], None)
    return JSONResponse({"ok": True})


async def screen(request: Request) -> JSONResponse:
    """The matrix as packed RGB integers, wrapped in its geometry.

    Drawn rather than captured: a fixed pattern keeps the preview screenshot
    identical from one run to the next. AWTRIX 3 answered a bare list; NG
    answers `{width, height, pixels}`.
    """
    pixels = []
    for y in range(8):
        for x in range(32):
            wave = math.sin((x / 32) * math.pi * 2)
            if 1 <= y <= 5 and (x + y) % 7 < 2:
                r, g, b = 0x3D, 0xDC, 0x84
            elif y == 6 and wave > 0.4:
                r, g, b = 0x4A, 0xA8, 0xFF
            else:
                r = g = b = 0
            pixels.append((r << 16) | (g << 8) | b)
    return JSONResponse({"width": 32, "height": 8, "pixels": pixels})


async def settings(request: Request) -> Any:
    """GET, and **PATCH** — not POST. Measured: PUT and POST answer 405."""
    port = _port(request)
    if request.method == "GET":
        return JSONResponse(SETTINGS[port])
    SETTINGS[port].update(await request.json())
    return JSONResponse({"ok": True})


async def system(request: Request) -> Any:
    """GET, and **PUT** — where `/settings` takes PATCH. Two routes, two
    verbs, and the brightness floor lives in this one."""
    port = _port(request)
    if request.method == "GET":
        return JSONResponse(SYSTEM[port])
    SYSTEM[port].update(await request.json())
    return JSONResponse(SYSTEM[port])


async def display(request: Request) -> Any:
    port = _port(request)
    if request.method == "GET":
        return JSONResponse(DISPLAY[port])
    DISPLAY[port].update(await request.json())
    return JSONResponse({"ok": True})


async def files(request: Request) -> Any:
    """Listing and upload share one route, separated by the verb.

    The multipart filename is pulled out with a regular expression rather than
    a real parser: that would be a dependency the application itself does not
    have, and all the demo needs is the name. NG calls the field `file` where
    AWTRIX 3 called it `image`, and takes the folder as a query parameter
    instead of inside the name.
    """
    port = _port(request)
    if request.method == "GET":
        listing = [{"name": name, "size": 1024} for name in sorted(ICONS[port])]
        return JSONResponse(
            {"files": listing, "usedBytes": 40_960 + 1024 * len(listing),
             "totalBytes": 524_288}
        )
    body = await request.body()
    found = re.search(rb'filename="([^"]+)"', body)
    if found:
        ICONS[port].add(found.group(1).decode("utf-8", "replace").rsplit("/", 1)[-1])
    return JSONResponse({"ok": True})


async def logs(request: Request) -> JSONResponse:
    lines = [
        f"[     0s] boot: AWTRIX NG {_profile(request)['version']} on ESP32",
        "[     0s] heap: 256 KB pool, 206 KB free before radio",
        "[     3s] wifi: connected as " + str(_profile(request)["ipAddress"]),
    ]
    return JSONResponse({"next": len(lines), "lines": lines})


async def accept(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def _json(request: Request, body: bytes) -> Any:
    import json


    try:
        return json.loads(body)
    except ValueError:
        return {}


# -- Open-Meteo -------------------------------------------------------------

#: Overcast, 18.4 °C — the same conditions as the sample data the interface
#: shows in a preview, so a screenshot of the preview and one of the real
#: widget agree.
FORECAST = {
    "latitude": 45.75,
    "longitude": 4.85,
    "timezone": "Europe/Paris",
    "elevation": 175.0,
    "current": {
        "time": "2026-09-30T14:00",
        "temperature_2m": 18.4,
        "apparent_temperature": 17.1,
        "relative_humidity_2m": 66,
        "wind_speed_10m": 10.6,
        "precipitation": 0.0,
        "precipitation_probability": 12,
        "weather_code": 3,
        "is_day": 1,
    },
    "utc_offset_seconds": 7200,
}


def _sun_days() -> dict[str, Any]:
    """The sun block, dated today and tomorrow.

    The only fake value here that cannot be frozen. The widget answers "which
    comes next", so a fixed date means every event is in the past and the
    matrix shows nothing — which is what a screenshot would then prove. The
    *times* stay fixed, so only the date under them moves.
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    return {
        "time": [today.isoformat(), tomorrow.isoformat()],
        "sunrise": [f"{today}T07:49", f"{tomorrow}T07:51"],
        "sunset": [f"{today}T19:33", f"{tomorrow}T19:31"],
        "daylight_duration": [42240.0, 42020.0],
    }

#: A real answer from the air-quality host, trimmed. Grass pollen is set to a
#: figure that actually says something: at 0.1 the widget reads "nothing", and
#: a screenshot of nothing documents nothing.
AIR = {
    "current": {
        "european_aqi": 30, "pm10": 17.3, "pm2_5": 10.1,
        "nitrogen_dioxide": 7.6, "ozone": 72.0, "sulphur_dioxide": 1.7,
        "uv_index": 3.05, "alder_pollen": 0.0, "birch_pollen": 0.0,
        "grass_pollen": 34.0, "ragweed_pollen": 0.0,
    }
}

#: Four stations around Rambouillet, shaped like the real feed. Fixed
#: prices: a screenshot must not change with the pumps.
FUEL = {
    "total_count": 4,
    "results": [
        {"id": 1, "ville": "Rambouillet", "adresse": "37 RN 10", "cp": "78690",
         "geom": {"lat": 48.7260, "lon": 1.8930},
         "e10_prix": 1.99, "e10_maj": "2026-09-30T00:01:00+00:00",
         "sp98_prix": None, "sp98_maj": None},
        {"id": 2, "ville": "Le Perray-en-Yvelines", "adresse": "2 RUE DE CHARTRES",
         "cp": "78610", "geom": {"lat": 48.7050, "lon": 1.8560},
         "e10_prix": 1.95, "e10_maj": "2026-09-29T08:06:51+00:00",
         "sp98_prix": 2.05, "sp98_maj": "2026-09-29T08:06:51+00:00"},
        {"id": 3, "ville": "Coignières", "adresse": "222 RN 10", "cp": "78310",
         "geom": {"lat": 48.7530, "lon": 1.9230},
         "e10_prix": 1.99, "e10_maj": "2026-09-30T00:01:00+00:00",
         "sp98_prix": 2.01, "sp98_maj": "2026-09-30T00:01:00+00:00"},
        {"id": 4, "ville": "Auffargis", "adresse": "RN 306", "cp": "78610",
         "geom": {"lat": 48.7000, "lon": 1.8880},
         "e10_prix": None, "e10_maj": None, "sp98_prix": None, "sp98_maj": None},
    ],
}

PLACES = {
    "results": [
        {
            "id": 2996944, "name": "Lyon", "latitude": 45.74846, "longitude": 4.84671,
            "country": "France", "country_code": "FR", "admin1": "Auvergne-Rhône-Alpes",
            "timezone": "Europe/Paris", "population": 472317,
        },
        {
            "id": 6453366, "name": "Rambouillet", "latitude": 48.6436,
            "longitude": 1.9, "country": "France", "country_code": "FR",
            "admin1": "Île-de-France", "timezone": "Europe/Paris", "population": 6500,
        },
        {
            "id": 2998324, "name": "Limoges", "latitude": 45.83362, "longitude": 1.26111,
            "country": "France", "country_code": "FR", "admin1": "Nouvelle-Aquitaine",
            "timezone": "Europe/Paris", "population": 133627,
        },
    ]
}


#: The Versailles calendar for 2026-2027, as the Ministry publishes it —
#: including the two quirks worth keeping: midnight in Paris expressed in UTC,
#: which shifts with daylight saving, and a Pont de l'Ascension whose two
#: bounds are the same instant.
SCHOOL = {
    "total_count": 6,
    "results": [
        {"description": "Vacances de la Toussaint", "location": "Versailles",
         "zones": "Zone C", "annee_scolaire": "2026-2027", "population": "-",
         "start_date": "2026-10-16T22:00:00+00:00", "end_date": "2026-11-01T23:00:00+00:00"},
        {"description": "Vacances de Noël", "location": "Versailles",
         "zones": "Zone C", "annee_scolaire": "2026-2027", "population": "-",
         "start_date": "2026-12-18T23:00:00+00:00", "end_date": "2027-01-03T23:00:00+00:00"},
        {"description": "Vacances d'Hiver", "location": "Versailles",
         "zones": "Zone C", "annee_scolaire": "2026-2027", "population": "-",
         "start_date": "2027-02-05T23:00:00+00:00", "end_date": "2027-02-21T23:00:00+00:00"},
        {"description": "Vacances de Printemps", "location": "Versailles",
         "zones": "Zone C", "annee_scolaire": "2026-2027", "population": "-",
         "start_date": "2027-04-02T22:00:00+00:00", "end_date": "2027-04-18T22:00:00+00:00"},
        {"description": "Pont de l'Ascension", "location": "Versailles",
         "zones": "Zone C", "annee_scolaire": "2026-2027", "population": "-",
         "start_date": "2027-05-06T22:00:00+00:00", "end_date": "2027-05-06T22:00:00+00:00"},
        {"description": "Vacances d'Été", "location": "Versailles",
         "zones": "Zone C", "annee_scolaire": "2025-2026", "population": "Élèves",
         "start_date": "2026-07-04T22:00:00+00:00", "end_date": "2026-08-31T22:00:00+00:00"},
    ],
}


async def school(request: Request) -> JSONResponse:
    return JSONResponse(SCHOOL)


async def forecast(request: Request) -> JSONResponse:
    return JSONResponse({**FORECAST, "daily": _sun_days()})


async def geocode(request: Request) -> JSONResponse:
    return JSONResponse(PLACES)


async def fuel(request: Request) -> JSONResponse:
    return JSONResponse(FUEL)


async def air_quality(request: Request) -> JSONResponse:
    return JSONResponse(AIR)


app = Starlette(
    routes=[
        Route("/api/v1/device", device),
        Route("/api/v1/capabilities", capabilities),
        Route("/api/v1/version", version),
        Route("/api/v1/apps", apps),
        Route("/api/v1/apps/active", accept, methods=["PUT"]),
        Route("/api/v1/apps/pushed/{name}", push_app, methods=["PUT"]),
        Route("/api/v1/apps/{name}", delete_app, methods=["DELETE"]),
        Route("/api/v1/notifications", accept, methods=["POST"]),
        Route("/api/v1/settings", settings, methods=["GET", "PATCH"]),
        Route("/api/v1/system", system, methods=["GET", "PUT"]),
        Route("/api/v1/display", display, methods=["GET", "PATCH"]),
        Route("/api/v1/display/screen", screen),
        Route("/api/v1/files", files, methods=["GET", "POST"]),
        Route("/api/v1/logs", logs),
        # Not a firmware endpoint: what awtrixng-mgr actually sent, so a doubt
        # about the pushed text is settled by reading it rather than by
        # reasoning about it. It caught a case where the preview was right and
        # nobody had checked the push.
        Route("/debug/pushed", lambda r: JSONResponse(PUSHED[_port(r)])),
        Route("/v1/forecast", forecast),
        Route("/school", school),
        Route("/v1/search", geocode),
        Route("/fuel", fuel),
        Route("/air", air_quality),
    ]
)
