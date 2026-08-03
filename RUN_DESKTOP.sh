#!/usr/bin/env bash
# ショチピリ — desktop window (B) + local server
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "venv missing. Create with python3.11 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export VIDEO_PROVIDER="${VIDEO_PROVIDER:-mock}"
export PORT="${PORT:-8787}"

# ensure pywebview
if ! "$ROOT/.venv/bin/python" -c "import webview" 2>/dev/null; then
  echo "Installing pywebview…"
  env -u PYTHONPATH "$ROOT/.venv/bin/pip" install -q "pywebview>=5.0"
fi

exec env -u PYTHONPATH "$ROOT/.venv/bin/python" "$ROOT/desktop_app.py"
