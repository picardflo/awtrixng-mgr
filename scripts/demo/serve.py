"""Runs awtrixng-mgr against the fake upstream, with fixed demo data.

Used to take the wiki screenshots, and useful on its own to try the interface
without touching a real display.

    python scripts/demo/serve.py [--port 9000] [--password SECRET]

Everything is thrown away on exit: the demo keeps its database in a temporary
directory, so a run never sees what the previous one did, and never sees your
own installation either.
"""

import argparse
import asyncio
import contextlib
import logging
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Ports the fake upstream answers on. The two displays differ only by port,
#: which is what lets one profile table describe both.
OFFICE_PORT, LIVING_PORT, METEO_PORT = 9101, 9102, 9100

log = logging.getLogger("demo")


def redirect_upstream() -> None:
    """Point the connectors at the fake Open-Meteo.

    Patched here rather than made configurable: production has no business
    gaining a setting whose only purpose is to take screenshots.
    """
    import app.connectors.fuel.prices as fuel
    import app.connectors.school.calendar as school
    import app.connectors.weather.air as air
    import app.connectors.weather.connector as weather
    import app.services.places as places

    weather.ENDPOINT = f"http://127.0.0.1:{METEO_PORT}/v1/forecast"
    places.ENDPOINT = f"http://127.0.0.1:{METEO_PORT}/v1/search"
    school.ENDPOINT = f"http://127.0.0.1:{METEO_PORT}/school"
    fuel.ENDPOINT = f"http://127.0.0.1:{METEO_PORT}/fuel"
    air.ENDPOINT = f"http://127.0.0.1:{METEO_PORT}/air"


async def serve(app, port: int) -> None:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    await uvicorn.Server(config).serve()


async def wait_until_up(url: str, timeout: float = 30.0) -> None:
    import httpx

    deadline = asyncio.get_running_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_running_loop().time() < deadline:
            with contextlib.suppress(Exception):
                if (await client.get(url, timeout=2)).status_code < 500:
                    return
            await asyncio.sleep(0.25)
    raise RuntimeError(f"{url} never came up")


def build_app(port: int):
    """awtrixng-mgr, plus the built interface on the same origin.

    One origin, as in production behind nginx (ADR-003), so the screenshots
    show the application exactly as it is served.
    """
    from fastapi.staticfiles import StaticFiles

    from app.main import create_app

    application = create_app()
    dist = ROOT / "frontend" / "dist"
    if not dist.is_dir():
        raise SystemExit(
            "frontend/dist is missing — run `npm run build` in frontend/ first."
        )
    application.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return application


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument(
        "--password",
        default="",
        help="Turn authentication on, to screenshot the login screen.",
    )
    parser.add_argument("--keep", action="store_true", help="Keep the demo database.")
    args = parser.parse_args()

    # Alembic resolves its migrations relative to the working directory, the
    # way the container does with WORKDIR /app. Everything else in here uses
    # absolute paths, so this is safe.
    os.chdir(ROOT / "backend")

    data_dir = Path(tempfile.mkdtemp(prefix="awtrixng-mgr-demo-"))
    os.environ["AWTRIXNG_DATA_DIR"] = str(data_dir)
    os.environ["AWTRIXNG_LOG_LEVEL"] = "WARNING"
    os.environ["AWTRIXNG_PASSWORD"] = args.password
    os.environ["AWTRIXNG_SECURE_COOKIE"] = "false"
    # The screenshots are for a French manual, so the demo speaks French —
    # conditions and phases included.
    os.environ["AWTRIXNG_LANGUAGE"] = "fr"

    redirect_upstream()
    from seed import seed
    from upstream import app as upstream

    tasks = [
        asyncio.create_task(serve(upstream, OFFICE_PORT)),
        asyncio.create_task(serve(upstream, LIVING_PORT)),
        asyncio.create_task(serve(upstream, METEO_PORT)),
        asyncio.create_task(serve(build_app(args.port), args.port)),
    ]
    try:
        await wait_until_up(f"http://127.0.0.1:{args.port}/api/health")
        await seed(f"http://127.0.0.1:{args.port}", args.password)
        print(f"\n  demo ready on http://127.0.0.1:{args.port}", flush=True)
        if args.password:
            print(f"  password: {args.password}", flush=True)
        print("  Ctrl-C to stop\n", flush=True)
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        if not args.keep:
            import shutil

            shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
