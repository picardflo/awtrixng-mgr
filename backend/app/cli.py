"""Talk to a display from a terminal.

There is no web interface yet, and `pytest -m device` proves the chain works
without ever showing it. This is the gap: a way to point the client at a real
clock, see what it answers, and watch what the matrix does.

    python -m app.cli --host awtrix-cl2.home.lan info
    python -m app.cli --host awtrix-cl2.home.lan screen --watch

Every command that writes asks `app.core.protected` first, and a protected
display is refused before a single request leaves the machine.

This is a development tool, not the product. It exists so that 0.x versions
are testable before the REST API and the interface arrive, and it is useful
afterwards for the same reason a database shell stays useful.
"""

import argparse
import asyncio
import json
import os
import sys

from app import __version__
from app.core.errors import AwtrixNgError
from app.core.protected import ProtectedHostError, assert_writable
from app.services.ng import matrix
from app.services.ng.client import NgClient
from app.services.ng.payload import NgNotification, NgPayload
from app.services.ng.transport import HttpTransport

#: Refresh of `screen --watch`. The firmware reports around 42 fps; polling
#: that fast over HTTP would say more about the network than about the clock.
WATCH_INTERVAL = 0.5


def connect(host: str, port: int) -> NgClient:
    return NgClient(HttpTransport(host, port))


# -- Commands -----------------------------------------------------------------


async def cmd_info(client: NgClient, args) -> int:
    device = await client.get_device()
    capabilities = await client.get_capabilities()

    print(f"{device.hostname or args.host}  —  AWTRIX NG {device.version}  ({device.board_type})")
    print(f"  uid          {device.uid}            {device.ip_address}")
    print(f"  uptime       {_duration(device.uptime_seconds)}"
          f"   relancé par : {device.reset_reason}")
    print(f"  batterie     {device.battery_percent}%  ({device.battery_voltage} V)")
    print(f"  capteurs     {device.temperature} °C   {device.humidity} %HR")
    print(f"  affichage    luminosité {device.brightness}   {device.fps} fps"
          f"   app : {device.current_app}")
    print(f"  mémoire      {_bytes(device.free_heap_bytes)} libres")
    print()
    print(f"  {len(capabilities.effects)} effets, {len(capabilities.transitions)} transitions, "
          f"{len(capabilities.palettes)} palettes, {len(capabilities.overlays)} overlays")
    audio = ", ".join(name for name, present in capabilities.audio.items() if present) or "aucun"
    print(f"  audio        {audio}")

    files = await client.list_files()
    print(f"  fichiers     {len(files.names)} icônes, {_bytes(files.free_bytes)} libres "
          f"sur {_bytes(files.total_bytes)}")
    return 0


async def cmd_apps(client: NgClient, args) -> int:
    apps = await client.get_apps()
    if not apps:
        print("aucune app")
        return 0
    width = max(len(app.name) for app in apps)
    for app in apps:
        flags = []
        if app.in_loop:
            flags.append("dans la boucle")
        if app.enabled is False:
            flags.append("désactivée")
        print(f"  {app.name:<{width}}  {app.origin or '?':<8}  {', '.join(flags)}")
    return 0


async def cmd_screen(client: NgClient, args) -> int:
    """What the matrix is actually showing, not what we believe we sent."""
    if not args.watch:
        pixels = await client.get_screen()
        print(matrix.render(pixels))
        if matrix.is_blank(pixels):
            print("(matrice éteinte)", file=sys.stderr)
        return 0

    print("\x1b[?25l", end="")  # hide the cursor while redrawing
    lines = 0
    try:
        while True:
            pixels = await client.get_screen()
            frame = matrix.render(pixels)
            if lines:
                print(f"\x1b[{lines}A", end="")  # back to the top of the frame
            print(frame)
            lines = frame.count("\n") + 1
            await asyncio.sleep(WATCH_INTERVAL)
    except KeyboardInterrupt:
        return 0
    finally:
        print("\x1b[?25h", end="")


async def cmd_push(client: NgClient, args) -> int:
    assert_writable(args.host)
    if args.icon:
        # Advisory: text without its icon still beats a blank matrix.
        try:
            await client.ensure_icon(args.icon)
        except AwtrixNgError as exc:
            print(f"icône non installée ({exc.message}), on pousse quand même", file=sys.stderr)

    payload = NgPayload(
        text=args.text,
        text_color=args.color,
        icon=args.icon,
        icon_mode=args.icon_mode,
        duration_ms=args.duration_ms,
        effect=args.effect,
        overlay=args.overlay,
        progress=args.progress,
    )
    await client.push_app(args.name, payload)
    print(f"poussé : {args.name}")
    print(json.dumps(payload.to_json(), ensure_ascii=False))
    if args.switch:
        await client.switch_to(args.name)
        print(f"basculé sur {args.name}")
    return 0


async def cmd_delete(client: NgClient, args) -> int:
    assert_writable(args.host)
    await client.delete_app(args.name)
    print(f"supprimé : {args.name}")
    return 0


async def cmd_notify(client: NgClient, args) -> int:
    assert_writable(args.host)
    await client.notify(
        NgNotification(
            text=args.text,
            text_color=args.color,
            icon=args.icon,
            duration_ms=args.duration_ms,
            wakeup=args.wakeup,
            hold=args.hold,
            sound_rtttl=args.rtttl,
        )
    )
    print("notification envoyée")
    return 0


async def cmd_icon(client: NgClient, args) -> int:
    assert_writable(args.host)
    await client.ensure_icon(args.id)
    print(f"icône {args.id} disponible sur l'appareil")
    return 0


async def cmd_logs(client: NgClient, args) -> int:
    lines, cursor = await client.get_logs(since=args.since)
    for line in lines:
        print(line)
    if args.follow:
        try:
            while True:
                await asyncio.sleep(2)
                lines, cursor = await client.get_logs(since=cursor)
                for line in lines:
                    print(line)
        except KeyboardInterrupt:
            return 0
    return 0


async def cmd_settings(client: NgClient, args) -> int:
    print(json.dumps(await client.get_settings(), indent=2, ensure_ascii=False))
    return 0


async def cmd_capabilities(client: NgClient, args) -> int:
    print(json.dumps(
        (await client.get_capabilities()).model_dump(by_alias=True), indent=2, ensure_ascii=False
    ))
    return 0


# -- Formatting ---------------------------------------------------------------


def _duration(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min {secs:02d} s" if minutes else f"{secs} s"


def _bytes(count: int | None) -> str:
    if count is None:
        return "?"
    if count >= 1024 * 1024:
        return f"{count / (1024 * 1024):.1f} Mo"
    return f"{count / 1024:.0f} Ko"


# -- Entry point --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Parler à un afficheur AWTRIX NG depuis un terminal.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("AWTRIXNG_HOST", ""),
        help="nom ou adresse de l'afficheur (ou AWTRIXNG_HOST)",
    )
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--version", action="version", version=f"awtrixng-mgr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="état de l'appareil et ce qu'il sait faire").set_defaults(
        run=cmd_info
    )
    sub.add_parser("apps", help="les apps présentes, avec leur origine").set_defaults(run=cmd_apps)
    sub.add_parser("settings", help="les réglages, bruts").set_defaults(run=cmd_settings)
    sub.add_parser("capabilities", help="les capacités, brutes").set_defaults(run=cmd_capabilities)

    screen = sub.add_parser("screen", help="dessiner la matrice dans le terminal")
    screen.add_argument("--watch", action="store_true", help="rafraîchir en continu (Ctrl-C)")
    screen.set_defaults(run=cmd_screen)

    push = sub.add_parser("push", help="pousser une app")
    push.add_argument("text")
    push.add_argument("--name", default="cli", help="nom de l'app sur l'appareil")
    push.add_argument("--color", help="couleur du texte, ex. #f5a524")
    push.add_argument("--icon", help="identifiant LaMetric ; installé s'il manque")
    push.add_argument("--icon-mode", choices=["fixed", "pushOnce", "push"])
    push.add_argument("--duration-ms", type=int)
    push.add_argument("--effect")
    push.add_argument("--overlay", help="rain, snow, drizzle, storm, thunder, frost")
    push.add_argument("--progress", type=int, help="0 à 100")
    push.add_argument("--switch", action="store_true", help="basculer dessus aussitôt")
    push.set_defaults(run=cmd_push)

    delete = sub.add_parser("delete", help="retirer une app")
    delete.add_argument("name")
    delete.set_defaults(run=cmd_delete)

    notify = sub.add_parser("notify", help="envoyer une notification")
    notify.add_argument("text")
    notify.add_argument("--color")
    notify.add_argument("--icon")
    notify.add_argument("--duration-ms", type=int)
    notify.add_argument("--wakeup", action="store_true", help="réveiller la matrice")
    notify.add_argument("--hold", action="store_true", help="rester jusqu'à un appui bouton")
    notify.add_argument("--rtttl", help="mélodie RTTTL jouée avec")
    notify.set_defaults(run=cmd_notify)

    icon = sub.add_parser("icon", help="installer une icône LaMetric par son identifiant")
    icon.add_argument("id")
    icon.set_defaults(run=cmd_icon)

    logs = sub.add_parser("logs", help="le journal de démarrage")
    logs.add_argument("--since", type=int, default=0)
    logs.add_argument("--follow", action="store_true")
    logs.set_defaults(run=cmd_logs)

    return parser


async def _run(args) -> int:
    client = connect(args.host, args.port)
    try:
        return await args.run(client, args)
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.host:
        print("aucun afficheur visé : --host, ou AWTRIXNG_HOST", file=sys.stderr)
        return 2

    try:
        return asyncio.run(_run(args))
    except ProtectedHostError as exc:
        # The whole point of the guard: say no, loudly, having done nothing.
        print(f"refusé : {exc}", file=sys.stderr)
        return 3
    except AwtrixNgError as exc:
        print(f"erreur : {exc.message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
