#!/usr/bin/env bash
#
# Regenerates every wiki screenshot.
#
#   ./scripts/update-screenshots.sh              # all of them
#   ./scripts/update-screenshots.sh dashboard    # only those matching
#
# Runs against the demo environment, never against your own installation:
# the shots have to be identical from one run to the next, and a reconciler
# pointed at a real display would delete the apps it does not know about.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DEMO_PORT:-9000}"
OUT="$ROOT/docs/screenshots"
PYTHON="$ROOT/backend/.venv/bin/python"
FILTER="${1:-}"

[ -x "$PYTHON" ] || { echo "backend/.venv is missing — see the README."; exit 1; }

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/5  Building the interface"
(cd "$ROOT/frontend" && npm run --silent build)

say "2/5  Installing Playwright if needed"
(cd "$ROOT/scripts/screenshots" && npm install --silent && npx playwright install --no-shell chromium >/dev/null)

say "3/5  Starting the demo environment"
"$PYTHON" "$ROOT/scripts/demo/serve.py" --port "$PORT" >/tmp/awtrixng-mgr-demo.log 2>&1 &
DEMO=$!
cleanup() { kill "$DEMO" 2>/dev/null || true; wait "$DEMO" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 120); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || {
  echo "the demo never came up — see /tmp/awtrixng-mgr-demo.log"; tail -20 /tmp/awtrixng-mgr-demo.log; exit 1;
}
# Let the scheduler push the widgets, so the loop shown is the real one.
sleep 6

say "4/5  Capturing"
cd "$ROOT/scripts/screenshots"
if [ -n "$FILTER" ]; then
  node capture.mjs --base "http://127.0.0.1:$PORT" --out "$OUT" --only "$FILTER"
else
  node capture.mjs --base "http://127.0.0.1:$PORT" --out "$OUT"
fi

say "5/5  Login screen (second pass, with a password)"
cleanup
"$PYTHON" "$ROOT/scripts/demo/serve.py" --port "$PORT" --password "demo" \
  >/tmp/awtrixng-mgr-demo-auth.log 2>&1 &
DEMO=$!
for _ in $(seq 1 120); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
node capture.mjs --base "http://127.0.0.1:$PORT" --out "$OUT" --scenario login

say "Done — $OUT"
ls -1 "$OUT" | sed 's/^/  /'

# Le numéro de version figure dans l'en-tête des images. Capturer avant de
# bumper les laisse porter l'ancien sans que rien ne le signale — c'est arrivé
# une fois, et seul un œil attentif sur une capture l'a vu.
VERSION=$(sed -nE 's/^__version__ = "(.+)"$/\1/p' "$ROOT/backend/app/__init__.py")
say "Figé en v$VERSION"
echo "  Ce numéro apparaît dans les images : bumper après avoir capturé"
echo "  les laisserait porter l'ancien."
