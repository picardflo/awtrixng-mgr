# awtrixng-mgr

**English** · [Français](README.fr.md)

**Give your AWTRIX NG clock something to say.**

A self-hosted web app that fetches the weather, air quality, fuel prices,
school holidays or the moon phase, and composes them into apps on one or more
[AWTRIX NG](https://github.com/Blueforcer/awtrix-ng) displays. Plus reminders:
a message, at a time, on the clocks you choose.

No account, no cloud, no subscription. One `docker compose up` on your own
network.

![Dashboard](docs/screenshots/dashboard.png)

---

## Quick start

You need an AWTRIX NG clock reachable on your network, and Docker.

```bash
git clone https://github.com/picardflo/awtrixng-mgr.git
cd awtrixng-mgr
docker compose up -d --build
```

Open `http://<host>/`, then:

1. **Displays → Add an AWTRIX.** Give the clock's network name, say
   `awtrix-lounge.lan`. "Test connection" should report its firmware version.
2. **Services → Weather.** Search for your town. No API key: Open-Meteo is
   open.
3. **Widgets → Add.** Pick the service, pick "Current weather", save.

The app reaches the clock within a second and takes its place in the rotation.

**Before letting anyone else near it**, set a password — see
[Security](docs/manuel/Securite.md). Without one, anybody on your network can
read your service credentials.

The interface speaks English and French; each browser picks its own.

## What it shows

| | |
|---|---|
| **Weather** | temperature, rain ahead, humidity, wind, sunrise and sunset, with NG's native overlays — it rains over the text when it rains outside |
| **Air quality** | the European index and the five pollutants behind it; UV on the WHO scale |
| **Moon** | phase and illumination |
| **Reminders** | at a fixed time, with a melody, repeats and a countdown |
| **Fuel prices** 🇫🇷 | the cheapest pump near you, from the French open data feed |
| **School holidays** 🇫🇷 | week A/B and a countdown, French zones |

The last two are France-specific, because that is where they come from. The
rest works anywhere Open-Meteo does, which is everywhere.

Every widget is adjustable: text template, icon, colour, font, scrolling,
progress bar, effects. A preview shows what the panel will do **before** you
save — and the font in it is the firmware's own, read off the hardware.

![Editing a widget](docs/screenshots/widget-edition.png)

## What makes this one a bit different

**Everything was measured on a real clock.** AWTRIX NG's API is not
exhaustively documented, so every route and every payload key was pushed to an
Ulanzi TC001 and read back off the panel. What the firmware accepts without
acting on — and there is some — is not offered in the interface. The raw
readings are in [`docs/ng-api/`](docs/ng-api/).

**The failures found became tests.** Not fixes: tests that name the failure.
A backup that did not contain the reminders, a proxy holding a dead address, a
display option no control could reach — each has its test, and the
[CHANGELOG](CHANGELOG.md) tells how it was found.

**Light or dark**, aligned on AWTRIX NG's own palette — read out of the
interface the firmware serves itself, not sampled from a screenshot.

![Light theme](docs/screenshots/clair-dashboard.png)

## Manual

**The manual is in French**, in [`docs/manuel/`](docs/manuel/README.md). An
English edition is not written yet; the pages are short and translate well
enough in a browser.

- [Getting started](docs/manuel/Demarrage.md) — from a bare clock to a first widget
- [Widgets](docs/manuel/Widgets.md) — the display options in detail
- [Reminders](docs/manuel/Rappels.md) · [Displays](docs/manuel/Afficheurs.md)
- [Security](docs/manuel/Securite.md) · [Backup and maintenance](docs/manuel/Maintenance.md)
- [Troubleshooting](docs/manuel/Depannage.md) — the symptoms that point at nothing
- [What NG changes](docs/manuel/AWTRIX-NG.md) — if you are coming from AWTRIX 3

Under the bonnet: [`docs/architecture.md`](docs/architecture.md) for the
decisions and their reasons, [`docs/ng-api/`](docs/ng-api/) for the measured
API.

## Configuration

Everything is set in the interface. `.env` carries only what has to exist
before the first start — see [`.env.example`](.env.example), which comments
every line.

The two worth knowing:

```ini
# Interface password. Empty = no authentication at all.
AWTRIXNG_PASSWORD=

# Displays the command-line tools must refuse to write to.
# Empty by default. Fill it the day you own two.
AWTRIXNG_PROTECTED_HOSTS=
```

## Development

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest          # ~990 tests, no hardware required
cd ../frontend && npm install && npm run dev
```

The tests that write to a real clock are deselected by default:

```bash
AWTRIXNG_TEST_HOST=awtrix-lab.lan .venv/bin/python -m pytest -m device
```

They refuse any display listed in `AWTRIXNG_PROTECTED_HOSTS`.

## Versioning

| Level | When | What it costs you |
|---|---|---|
| Patch `0.1.x` | a defect fixed, the interface adjusted, docs filled in | `git pull && docker compose up -d --build` |
| Minor `0.x.0` | a new widget, a new service, a database migration | automatic, but something new appears |
| Major `x.0.0` | a required variable, an incompatible backup format | **something for you to do** |

## Thanks

- [**AWTRIX NG**](https://github.com/Blueforcer/awtrix-ng) by Blueforcer, the
  firmware without which none of this would have a point. This project
  contains none of its code: it talks to its HTTP API.
- [**Open-Meteo**](https://open-meteo.com),
  [**data.economie.gouv.fr**](https://data.economie.gouv.fr) and
  [the French school calendar API](https://data.education.gouv.fr) — open, and
  keyless.
- [**LaMetric**](https://developer.lametric.com) for the icon gallery. Icons
  are never redistributed: the clock fetches them itself.

## Licence

Copyright © 2026 Florian Picard — [GNU AGPL v3](LICENSE).

Use it, modify it, host it. If you make it a service reachable over a network,
you must publish your changes. That is the point of the choice: these tools
exist because the commercial equivalents are priced out of reach, and this is
the licence that stops them becoming a closed product again.

AWTRIX NG itself is under
[PolyForm Noncommercial](https://github.com/Blueforcer/awtrix-ng) — a separate
licence, which covers the firmware and not this project.
