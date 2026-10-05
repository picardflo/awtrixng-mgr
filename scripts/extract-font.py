#!/usr/bin/env python3
"""Extract both AWTRIX NG fonts from the display itself.

The preview's font was transcribed by hand from screenshots and does not
match: its 'A' is 010/101/111/101/101 where the firmware draws
110/101/111/101/101. Rather than correct a drawing by eye, each glyph is
pushed to the panel on its own and read back out of the framebuffer.
"""
import json, sys, time, urllib.request

H = "http://awtrix-cl2.home.lan/api/v1"

def call(m, p, b=None):
    d = json.dumps(b, ensure_ascii=False).encode("utf-8") if b is not None else None
    r = urllib.request.Request(f"{H}{p}", data=d, method=m)
    if d: r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")

CHARS = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "àâäéèêëîïôöùûüÿçÀÂÉÈÊËÎÏÔÖÙÛÜÇœŒæÆ"
    "°€µ£¥©®±×÷"
)

def glyph(ch, font):
    call("PUT", "/apps/pushed/g", {
        "text": ch, "font": font, "durationMs": 60000,
        "scroll": {"mode": "static"}, "textColor": "#ffffff",
        "textCase": "asTyped",
    })
    call("PUT", "/apps/active", {"name": "g"})
    time.sleep(1.4)
    s = call("GET", "/display/screen")
    w, h, px = s["width"], s["height"], s["pixels"]
    cols = [c for c in range(w) if any(px[r * w + c] for r in range(h))]
    if not cols:
        return None
    # Rows are fixed per font (1..5 small, 0..6 large) so the baseline is kept.
    top, bottom = (1, 5) if font == "small" else (0, 6)
    return [
        "".join("1" if px[r * w + c] else "0" for c in range(min(cols), max(cols) + 1))
        for r in range(top, bottom + 1)
    ]

out = {}
for font in ("small", "large"):
    out[font] = {}
    for n, ch in enumerate(CHARS):
        g = glyph(ch, font)
        if g:
            out[font][ch] = g
        print(f"{font} {n+1}/{len(CHARS)} {ch!r} -> {'ok' if g else 'VIDE'}", flush=True)
call("DELETE", "/apps/g")
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print("écrit dans", sys.argv[1])
