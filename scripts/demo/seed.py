"""The demo data.

Created through awtrixng-mgr's own API rather than written into the database, so
it goes through the same validation as anything a person would create — and so
it keeps working when the models change.

Names and places are deliberately close to a real home installation: a manual
whose screenshots show "Widget 1" and "Connector 2" teaches nothing.
"""

import httpx

OFFICE_PORT, LIVING_PORT = 9101, 9102


async def seed(base: str, password: str = "") -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        if password:
            await http.post("/api/auth/login", json={"password": password})

        bureau = await _post(http, "/api/devices", {
            "name": "Bureau", "host": "127.0.0.1", "port": OFFICE_PORT,
        })
        salon = await _post(http, "/api/devices", {
            "name": "Salon", "host": "127.0.0.1", "port": LIVING_PORT,
        })

        # Tested straight away so the screenshots show displays that are up,
        # with their firmware and sensors, rather than a wall of "unknown".
        for device in (bureau, salon):
            await http.post(f"/api/devices/{device['id']}/test")

        meteo = await _post(http, "/api/connectors", {
            "type": "weather", "name": "Météo Lyon",
            "config": {"place": {
                "name": "Lyon", "latitude": 45.74846, "longitude": 4.84671,
                "country": "France", "admin1": "Auvergne-Rhône-Alpes",
            }},
        })
        lune = await _post(http, "/api/connectors", {
            "type": "moon", "name": "Lune", "config": {},
        })
        # Two fuels checked, four left out: a RAV4 runs on SP95-E10 and SP98,
        # and the columns for the rest are never even asked for.
        carburants = await _post(http, "/api/connectors", {
            "type": "fuel", "name": "Carburants",
            "config": {
                "place": {"name": "Les Essarts-le-Roi", "latitude": 48.7167,
                          "longitude": 1.9, "country": "France",
                          "admin1": "Île-de-France"},
                "radius": 10,
                "fuels": ["e10", "sp98"],
                # The feed carries no brand, so a station is excluded by its
                # own identifier. Here: the one whose price sits well under
                # the local market and would never be the pump you use.
                "excluded_stations": ["3"],
            },
        })
        ecole = await _post(http, "/api/connectors", {
            "type": "school", "name": "Collège",
            "config": {"academie": "Versailles", "invert": False},
        })

        # One display dims itself at night — the office one, next to a bed.
        await http.put(f"/api/devices/{bureau['id']}/bedroom", json={
            "enabled": True, "start": "22:00:00", "end": "07:00:00", "brightness": 1,
        })

        # The clocks speak French here, so a screenshot shows what a French
        # installation actually pushes rather than English words under a
        # French interface — which is the confusion this setting resolves.
        await http.put("/api/settings", json={"language": "fr"})

        # Tested too, so the services do not all read "Never tested".
        for connector in (meteo, lune, ecole, carburants):
            await http.post(f"/api/connectors/{connector['id']}/test")

        # Four widgets, chosen to show off different things: one on two
        # displays at once, one with a progress bar, one with a custom
        # template, one animated icon.
        await _post(http, "/api/widgets", {
            "name": "Température", "connector_id": meteo["id"],
            "widget_type": "weather.current",
            "device_ids": [bureau["id"], salon["id"]],
            "refresh_seconds": 600,
            "display": {"text": "{{ temp | round }}°", "icon": "12183",
                        "duration": 8},
        })
        await _post(http, "/api/widgets", {
            "name": "Pluie", "connector_id": meteo["id"],
            "widget_type": "weather.rain", "device_ids": [bureau["id"]],
            "refresh_seconds": 600,
            "display": {"text": "{{ probability }}%", "icon": "1901",
                        "duration": 8},
        })
        # Same connector, same call: Open-Meteo returns the sun times beside
        # the temperature, so this costs no extra request.
        await _post(http, "/api/widgets", {
            "name": "Soleil", "connector_id": meteo["id"],
            "widget_type": "weather.sun", "device_ids": [salon["id"]],
            "refresh_seconds": 900,
            # The bar left uncoloured on purpose: it must take the connector's
            # own colour, which is the thing that was wrong in the preview.
            "display": {"text": "{{ next }}", "duration": 8, 
                        "show_progress": True},
        })
        # The three air widgets: one call to a second host, shared between them.
        await _post(http, "/api/widgets", {
            "name": "Qualité de l'air", "connector_id": meteo["id"],
            "widget_type": "weather.air", "device_ids": [bureau["id"]],
            "refresh_seconds": 1800,
            "display": {"text": "{{ aqi }}", "duration": 8,
                        "font": "large", "show_progress": True},
        })
        await _post(http, "/api/widgets", {
            "name": "Indice UV", "connector_id": meteo["id"],
            "widget_type": "weather.uv", "device_ids": [bureau["id"]],
            "refresh_seconds": 1800,
            "display": {"text": "UV {{ uv | round }}", "duration": 8,
                        "font": "large", "show_progress": True},
        })
        await _post(http, "/api/widgets", {
            "name": "Humidité extérieure", "connector_id": meteo["id"],
            "widget_type": "weather.humidity", "device_ids": [bureau["id"]],
            "refresh_seconds": 600,
            "display": {"text": "{{ humidity | round }}%", "duration": 8,
                        "font": "large", "show_progress": True},
        })

        await _post(http, "/api/widgets", {
            "name": "Vent", "connector_id": meteo["id"],
            "widget_type": "weather.current", "device_ids": [salon["id"]],
            "refresh_seconds": 600,
            "display": {"text": "{{ wind | round }} km/h", "icon": "2422",
                        "duration": 6},
        })
        await _post(http, "/api/widgets", {
            "name": "Lune", "connector_id": lune["id"],
            "widget_type": "moon.phase", "device_ids": [salon["id"]],
            "refresh_seconds": 1800,
            "display": {"text": "{{ illumination }}%", "duration": 8},
        })
        await _post(http, "/api/widgets", {
            "name": "Semaine", "connector_id": ecole["id"],
            "widget_type": "school.week", "device_ids": [bureau["id"]],
            "refresh_seconds": 3600,
            "display": {"text": "{{ summary }}", "icon": "2536", "duration": 8,
                        "show_progress": True,
                        "progress_color": "#3ddc84",
                        "progress_background": "#000000"},
        })
        # A reminder, which is not a widget: it interrupts at a set time
        # rather than taking its turn in the rotation.
        await _post(http, "/api/reminders", {
            "name": "Médicament", "message": "Medicament !", "icon": "2536",
            "melody": "pilule:d=8,o=6,b=120:c,e,g,e,4c", "rings_at_night": True,
            "at": "07:30:00", "days": [0, 1, 2, 3, 4],
            "duration_seconds": 10, "repeat_count": 2, "repeat_every_minutes": 2,
            "device_ids": [bureau["id"], salon["id"]],
        })
        # Two reminders rather than one with two messages: the bins alternate
        # on their own cycle, and "every N weeks" composes where a special
        # case would not.
        await _post(http, "/api/reminders", {
            "name": "Poubelles noires", "message": "NOIRES", "icon": "1901",
            "at": "19:45:00", "days": [6],
            "duration_seconds": 15, "repeat_count": 1, "repeat_every_minutes": 3,
            "device_ids": [salon["id"]],
        })
        await _post(http, "/api/reminders", {
            "name": "Papiers", "message": "PAPIERS", "icon": "1901",
            "at": "19:45:00", "days": [6],
            "every_weeks": 2, "anchor": "2026-10-11",
            "duration_seconds": 15, "repeat_count": 1, "repeat_every_minutes": 3,
            "device_ids": [salon["id"]],
        })

        await _post(http, "/api/widgets", {
            "name": "SP95-E10", "connector_id": carburants["id"],
            "widget_type": "fuel.cheapest", "device_ids": [bureau["id"]],
            "config": {"fuel": "e10"}, "refresh_seconds": 3600,
            "display": {"text": "{{ price }}", "icon": "55274",
                        "duration": 8},
        })

        # A date rather than a rhythm: the weekday buttons disappear for this
        # one, which is the whole point of showing it here.
        await _post(http, "/api/reminders", {
            "name": "Entretien voiture", "message": "ENTRETIEN", "icon": "6173",
            "at": "09:00:00", "days": [0, 1, 2, 3, 4], "on_date": "2027-03-15",
            "duration_seconds": 15, "device_ids": [bureau["id"]],
        })
        # The schedule is ordinary — every morning — and the message is what
        # changes: "{{ countdown }}" reaches the matrix as "J-532".
        await _post(http, "/api/reminders", {
            "name": "Prêt auto", "message": "PRET {{ countdown }}", "icon": "3961",
            "at": "08:00:00", "days": [0, 1, 2, 3, 4, 5, 6],
            "countdown_to": "2027-11-15",
            "duration_seconds": 10, "device_ids": [bureau["id"]],
        })



async def _post(http: httpx.AsyncClient, path: str, payload: dict) -> dict:
    response = await http.post(path, json=payload)
    if response.status_code >= 400:
        raise SystemExit(f"seeding {path} failed: {response.status_code} {response.text}")
    return response.json()
