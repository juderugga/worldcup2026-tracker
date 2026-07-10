#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Installs the World Cup 2026 Tracker desktop launcher (GNOME)
#  Run this ONCE from a terminal:   bash install-launcher.sh
#
#  After it runs you'll have:
#    • A double-clickable "World Cup 2026 Tracker" icon on your Desktop
#    • An entry in your Applications menu
#
#  Why this is needed: GNOME refuses to *run* a .desktop file until it
#  is marked executable and "trusted" — until then a double-click just
#  opens it in a text editor (VS Code). This script fixes that.
# ──────────────────────────────────────────────────────────────
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$DIR/WorldCup2026.desktop"

echo "  Installing World Cup 2026 Tracker launcher…"

# Make the launcher + start script executable
chmod +x "$DIR/start.sh" "$SRC" 2>/dev/null || true

# 1) Applications menu entry (always reliable)
APPDIR="$HOME/.local/share/applications"
mkdir -p "$APPDIR"
cp "$SRC" "$APPDIR/WorldCup2026.desktop"
chmod +x "$APPDIR/WorldCup2026.desktop"
update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
echo "  ✔ Added to Applications menu"

# 2) Desktop double-click icon
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESKTOP_DIR"
DEST="$DESKTOP_DIR/WorldCup2026.desktop"
cp "$SRC" "$DEST"
chmod +x "$DEST"

# Mark it trusted so GNOME launches it instead of opening it as text.
# Ubuntu's "Desktop Icons NG" extension only trusts a launcher when
# metadata::trusted is the STRING "true" — the boolean / "yes" forms are ignored.
gio set -t string "$DEST" metadata::trusted true >/dev/null 2>&1 || true
# Fallbacks for other GNOME variants
gio set "$DEST" metadata::trusted true >/dev/null 2>&1 || true
echo "  ✔ Placed icon on Desktop: $DEST"

echo ""
echo "  Done! Double-click the 'World Cup 2026 Tracker' icon on your Desktop."
echo ""
echo "  If GNOME still shows a prompt the first time, right-click the icon"
echo "  and choose 'Allow Launching' (you only need to do this once)."
