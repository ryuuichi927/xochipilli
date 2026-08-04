#!/usr/bin/env bash
# Rebuild in-bundle Mach-O launcher into Xochipilli.app + /Applications
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INC="${PYTHON_INCLUDE:-$HOME/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/include/python3.11}"
LIB="${PYTHON_LIBDIR:-$HOME/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib}"
OUT_REPO="$ROOT/Xochipilli.app/Contents/MacOS/Xochipilli"
OUT_APP="/Applications/Xochipilli.app/Contents/MacOS/Xochipilli"
clang -O2 -arch arm64 \
  -I"$INC" -L"$LIB" -lpython3.11 \
  -Wl,-rpath,"$LIB" \
  -o "$OUT_REPO" \
  "$ROOT/native/xochipilli_launcher.c"
chmod +x "$OUT_REPO"
if [[ -d /Applications/Xochipilli.app ]]; then
  cp -f "$OUT_REPO" "$OUT_APP"
  cp -f "$ROOT/Xochipilli.app/Contents/Info.plist" /Applications/Xochipilli.app/Contents/Info.plist
  chmod +x "$OUT_APP"
  xattr -cr /Applications/Xochipilli.app 2>/dev/null || true
fi
echo "built $OUT_REPO"
file "$OUT_REPO"
