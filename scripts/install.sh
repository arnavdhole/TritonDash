#!/usr/bin/env bash
# One-command setup for the UCSD dashboard.
#   bash scripts/install.sh              set up, then install the background jobs (macOS)
#   bash scripts/install.sh --no-agents  set up only
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

INSTALL_AGENTS=1
for arg in "$@"; do
    [ "$arg" = "--no-agents" ] && INSTALL_AGENTS=0
done

echo "=== UCSD dashboard setup ==="

# Python 3.9+ is enough for the dashboard.
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" &>/dev/null; then PYTHON="$candidate"; break; fi
done
if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    echo "Python 3.9 or newer is required. On a Mac: brew install python"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi
echo "Installing dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
mkdir -p logs data

[ -f .env ] || cp .env.example .env
[ -f config/dashboard.yaml ] || cp config/dashboard.example.yaml config/dashboard.yaml

# Ask for the Canvas feed URL if it is not set yet. It is written to .env only.
if ! grep -qE '^CANVAS_ICAL_URL=.+' .env; then
    if [ -t 0 ]; then
        echo ""
        echo "In Canvas, open Calendar, click 'Calendar Feed' (bottom right) and copy the URL."
        read -r -p "Paste your Canvas calendar feed URL (or press Enter to add it later): " FEED_URL
        if [ -n "$FEED_URL" ]; then
            FEED_URL="$FEED_URL" .venv/bin/python - <<'PY'
import os, re
from pathlib import Path
env = Path(".env")
text = env.read_text()
text = re.sub(r"^CANVAS_ICAL_URL=.*$", lambda _: "CANVAS_ICAL_URL=" + os.environ["FEED_URL"], text, count=1, flags=re.M)
env.write_text(text)
PY
        fi
    fi
fi

if grep -qE '^CANVAS_ICAL_URL=.+' .env; then
    echo "Fetching your deadlines..."
    .venv/bin/python -m src.dashboard_export || echo "The first fetch failed. Check the feed URL in .env."
else
    echo "No feed URL yet. Add CANVAS_ICAL_URL to .env, then run: .venv/bin/python -m src.dashboard_export"
fi

if [ "$INSTALL_AGENTS" = "1" ] && [ "$(uname)" = "Darwin" ]; then
    AGENT_DIR="$HOME/Library/LaunchAgents"
    mkdir -p "$AGENT_DIR"
    for name in sync server; do
        label="local.ucsd-dashboard.$name"
        target="$AGENT_DIR/$label.plist"
        sed -e "s|__PYTHON__|$PROJECT_DIR/.venv/bin/python|g" \
            -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
            "launchd/ucsd-dashboard.$name.plist.template" > "$target"
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
        launchctl bootstrap "gui/$(id -u)" "$target"
    done
    echo "Installed background jobs: nightly refresh at 2:00 AM and the dashboard server."
else
    echo ""
    echo "Background jobs were not installed. Start the dashboard server yourself with:"
    echo "  .venv/bin/python scripts/dashboard_server.py"
fi

echo ""
echo "Done. Open the dashboard at http://127.0.0.1:8765"
echo "Optional: install the browser extension for PrairieLearn and Gradescope (see README)."
