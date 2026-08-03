#!/usr/bin/env bash
# ショチピリ D1 — local server
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "venv missing. Create with:"
  echo "  env -u PYTHONPATH /path/to/python3.11 -m venv .venv"
  echo "  env -u PYTHONPATH .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Optional shell-side .env (Python also loads via dotenv)
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export VIDEO_PROVIDER="${VIDEO_PROVIDER:-mock}"
PORT="${PORT:-8787}"

echo "ショチピリ (Xochipilli) → http://127.0.0.1:${PORT}"
echo "VIDEO_PROVIDER=${VIDEO_PROVIDER}  (mock | xai/grok | fal)"
if [[ "${VIDEO_PROVIDER}" == "fal" ]]; then
  if [[ -n "${FAL_KEY:-}${FAL_API_KEY:-}" ]]; then
    echo "FAL key: set"
  else
    echo "WARN: VIDEO_PROVIDER=fal but FAL_KEY is empty → generate will fall back to mock"
  fi
  echo "FAL_VIDEO_MODEL=${FAL_VIDEO_MODEL:-fal-ai/minimax-video}"
fi
if [[ "${VIDEO_PROVIDER}" == "xai" || "${VIDEO_PROVIDER}" == "grok" ]]; then
  echo "xAI / Grok Imagine: Ben's Tool OAuth (~/.bentool) or XAI_API_KEY"
  echo "XAI_VIDEO_MODEL=${XAI_VIDEO_MODEL:-grok-imagine-video}"
fi

exec env -u PYTHONPATH "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --app-dir "$ROOT"
