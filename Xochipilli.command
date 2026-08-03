#!/usr/bin/env bash
# Double-click launcher (A) — opens desktop shell if possible, else browser.
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

osascript <<EOF 2>/dev/null || true
tell application "Terminal"
  # keep quiet when launched from .app
end tell
EOF

if [[ -x "$ROOT/RUN_DESKTOP.sh" ]]; then
  exec "$ROOT/RUN_DESKTOP.sh"
fi

# fallback: server + browser
if [[ -x "$ROOT/RUN_ME.sh" ]]; then
  open "http://127.0.0.1:${PORT:-8787}" 2>/dev/null || true
  exec "$ROOT/RUN_ME.sh"
fi

echo "Xochipilli launch scripts missing"
read -r _
exit 1
