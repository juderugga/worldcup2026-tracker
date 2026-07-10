#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  ⚽  FIFA World Cup 2026 Tracker — Launcher
# ──────────────────────────────────────────────────────────────
#  Run it from a terminal:   ./start.sh   (or:  bash start.sh)
#
#  It will:
#    1. Start a tiny local server on port 3001
#    2. Open the tracker at http://localhost:3001/ in your browser
#    3. Shut the server down cleanly when you press Ctrl+C
#
#  No Node.js or npm needed — uses Python 3, which ships with Ubuntu.
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo ""
echo "  ⚽  FIFA World Cup 2026 Tracker"
echo "  ────────────────────────────────"

# ── Free port 3001 if something is already on it ──
if command -v lsof >/dev/null 2>&1 && lsof -ti:3001 >/dev/null 2>&1; then
  echo "  Stopping previous server on port 3001..."
  # xargs handles multiple PIDs (quoted \$(...) would pass them as one arg)
  lsof -ti:3001 | xargs -r kill 2>/dev/null
  sleep 1
fi

# ── Pick a runtime: prefer Python 3, fall back to Node ──
if command -v python3 >/dev/null 2>&1; then
  echo "  Starting server (Python)..."
  python3 "$SCRIPT_DIR/server.py" &
  SERVER_PID=$!
elif command -v node >/dev/null 2>&1; then
  echo "  Starting server (Node)..."
  node "$SCRIPT_DIR/proxy.js" &
  SERVER_PID=$!
else
  echo ""
  echo "  ✗ Neither Python 3 nor Node.js was found."
  echo "    Ubuntu normally ships Python 3. Install it with:"
  echo "      sudo apt install python3"
  echo ""
  read -rp "  Press Enter to exit..."
  exit 1
fi

# Give the server a moment to bind the port
sleep 1

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo ""
  echo "  ✗ Server failed to start."
  echo ""
  read -rp "  Press Enter to exit..."
  exit 1
fi

# ── Open the tracker in the default browser ──
APP_URL="http://localhost:3001/"
echo "  Opening $APP_URL ..."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$APP_URL" 2>/dev/null
elif command -v open >/dev/null 2>&1; then
  open "$APP_URL"
else
  echo "  Could not auto-open a browser. Open this URL manually: $APP_URL"
fi

echo ""
echo "  ✔ Tracker is live at $APP_URL"
echo "  Keep this window open while using it. Press Ctrl+C to stop."
echo ""

# ── Clean shutdown ──
cleanup() {
  echo ""
  echo "  Stopping server..."
  kill "$SERVER_PID" 2>/dev/null
  wait "$SERVER_PID" 2>/dev/null
  echo "  Done. Goodbye!"
  exit 0
}
trap cleanup INT TERM

wait "$SERVER_PID"
