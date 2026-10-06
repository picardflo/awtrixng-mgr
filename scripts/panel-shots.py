#!/usr/bin/env python3
"""Photograph a layout on the panel itself, and lay the shots out side by side.

The widget previews in the interface are drawn from a transcription of the
firmware's font and its bar geometry. They are faithful — `test_renderer.py`
and `dim.test.ts` pin both sides against each other — but they are still our
drawing of the display. A choice between two icons is settled by the display.

So this pushes each layout to an app of its own, switches to it, and reads
`/display/screen` back: the pixels the panel is actually lighting. The result
is `docs/screenshots/panneau-air-uv.png` and anything like it.

    AWTRIXNG_PANEL=awtrix-desk.lan ./scripts/panel-shots.py cas.json sortie.png

where `cas.json` is a list of `{"label": ..., "payload": {...}}`, the payload
being what the firmware takes — `text`, `icon`, `font`, `textColor`,
`progress`, `progressColor`, `progressTrackColor`.

**It writes to the display it is pointed at.** Name it in `AWTRIXNG_PANEL`;
there is no default, because a default here is someone else's clock. Whatever
`AWTRIXNG_PROTECTED_HOSTS` lists is refused, for the same reason the device
tests refuse it.

Two precautions, both bought by a bench that lied:

- the transition takes about a second, so a capture taken immediately
  photographs the previous app fading out;
- the firmware's own rotation took the panel back once mid-run and the sheet
  came out with its Date app in it, so the app is re-activated right before
  reading.
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFont

_PANEL = os.environ.get("AWTRIXNG_PANEL", "")
HOST = f"http://{_PANEL}/api/v1"
LAMETRIC = "https://developer.lametric.com/content/apps/icon_thumbs/{}"
APP = "panelshots"

#: Long enough for the transition, then a second settle after re-activating.
SETTLE, RESETTLE = 2.4, 1.2
#: An animated icon has no single image: several are read and the distinct
#: ones are all kept, which is what shows an animation on a still sheet.
FRAMES, GAP = 4, 0.30

SCALE, PAD, ROW = 14, 10, 24
LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"{HOST}{path}", data=data, method=method)
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def installed():
    _, listing = call("GET", "/files?dir=/ICONS")
    files = listing if isinstance(listing, list) else listing.get("files", [])
    return {str(f.get("name", f)).split(".")[0] for f in files}


def install(icon_id):
    """Put an icon on the display, the way the application does.

    A still icon comes from the gallery as a PNG, which the firmware cannot
    read at all, so it is converted to a single-frame GIF — see
    `app/services/ng/icons.py`, which does the same thing for the same reason.
    """
    if str(icon_id) in installed():
        return "déjà là"
    request = urllib.request.Request(LAMETRIC.format(icon_id), headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(request, timeout=20) as response:
        blob, kind = response.read(), response.headers.get("Content-Type", "")
    if "gif" not in kind:
        buffer = io.BytesIO()
        Image.open(io.BytesIO(blob)).convert("RGB").save(buffer, format="GIF")
        blob = buffer.getvalue()
    boundary = "----panelshots"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{icon_id}.gif"\r\nContent-Type: image/gif\r\n\r\n'
    ).encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{HOST}/files?dir=/ICONS",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return f"posée ({response.status})"


def frames():
    """The distinct images seen over a short window, in the order they came."""
    seen, out = set(), []
    for _ in range(FRAMES):
        _, screen = call("GET", "/display/screen")
        pixels = tuple(screen["pixels"])
        if pixels not in seen:
            seen.add(pixels)
            out.append(pixels)
        time.sleep(GAP)
    return out


def tile(pixels, width=32, height=8):
    image = Image.new("RGB", (width, height))
    image.putdata([((p >> 16) & 255, (p >> 8) & 255, p & 255) for p in pixels])
    return image.resize((width * SCALE, height * SCALE), Image.NEAREST)


def shoot(payload):
    code, body = call("PUT", f"/apps/pushed/{APP}", payload)
    if code != 200:
        return None, body
    call("PUT", "/apps/active", {"name": APP})
    time.sleep(SETTLE)
    call("PUT", "/apps/active", {"name": APP})
    time.sleep(RESETTLE)
    return frames(), body


def sheet(shots, out_path):
    try:
        font = ImageFont.truetype(LABEL_FONT, 13)
    except OSError:  # the labels are French; a bitmap fallback mangles them
        font = ImageFont.load_default()
    cell_w, cell_h = 32 * SCALE, 8 * SCALE
    columns = max(len(f) for _, f in shots)
    image = Image.new(
        "RGB",
        (PAD + columns * (cell_w + PAD), PAD + len(shots) * (cell_h + ROW + PAD)),
        (24, 24, 24),
    )
    draw = ImageDraw.Draw(image)
    y = PAD
    for label, got in shots:
        draw.text((PAD, y), label, font=font, fill=(240, 240, 240))
        x = PAD
        for pixels in got:
            image.paste(tile(pixels), (x, y + ROW))
            x += cell_w + PAD
        y += cell_h + ROW + PAD
    image.save(out_path)


def main(spec_path, out_path):
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
    from app.core.protected import is_protected

    if not _PANEL:
        raise SystemExit(
            "AWTRIXNG_PANEL n'est pas défini : nommez l'afficheur sur lequel "
            "écrire, par exemple AWTRIXNG_PANEL=awtrix-desk.lan"
        )
    host = _PANEL
    if is_protected(host):
        raise SystemExit(f"{host} est un afficheur en service : ce script écrit, j'arrête.")

    cases = json.load(open(spec_path, encoding="utf-8"))
    for icon in sorted({c["payload"].get("icon") for c in cases if c["payload"].get("icon")}):
        print(f"  icône {icon} : {install(icon)}")

    shots = []
    for case in cases:
        got, body = shoot({"durationMs": 120000, **case["payload"]})
        if got is None:
            print(f"  !! {case['label']} : {body}")
            continue
        print(f"  ✓ {case['label']} — {len(got)} image(s)")
        shots.append((case["label"], got))

    if not shots:
        raise SystemExit("aucune image : rien à écrire")
    sheet(shots, out_path)
    print(f"  -> {out_path}")
    call("DELETE", f"/apps/{APP}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage : {sys.argv[0]} cas.json sortie.png")
    main(sys.argv[1], sys.argv[2])
