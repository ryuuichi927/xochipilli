#!/usr/bin/env bash
# Assemble Xochipilli.app from source, then sync it to /Applications if installed.
#
# The bundle is build output and is not tracked by git. Its sources are:
#   native/Info.plist               bundle metadata
#   native/xochipilli_launcher.c    in-bundle Mach-O launcher (needed for WKWebView identity)
#   static/brand/icon-primary.png   icon artwork -> AppIcon.icns
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INC="${PYTHON_INCLUDE:-$HOME/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/include/python3.11}"
LIB="${PYTHON_LIBDIR:-$HOME/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib}"

BUNDLE="$ROOT/Xochipilli.app"
CONTENTS="$BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
OUT_REPO="$MACOS_DIR/Xochipilli"
PROJECT_ROOT_FILE="$RESOURCES/ProjectRoot"
ICON_SRC="$ROOT/static/brand/icon-primary.png"
ICON_OUT="$RESOURCES/AppIcon.icns"

mkdir -p "$MACOS_DIR" "$RESOURCES"
cp -f "$ROOT/native/Info.plist" "$CONTENTS/Info.plist"
# Always pin ProjectRoot to this clone (override stale absolute paths).
printf '%s\n' "$ROOT" > "$PROJECT_ROOT_FILE"

if [[ ! -f "$ICON_OUT" || "$ICON_SRC" -nt "$ICON_OUT" ]]; then
  ICONSET="$(mktemp -d)/Xochipilli.iconset"
  mkdir -p "$ICONSET"
  # sips is told the format explicitly: icon-primary.png is JPEG data under a .png
  # name, and iconutil rejects an iconset that is not really PNG.
  for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
              "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" \
              "512 icon_256x256@2x" "512 icon_512x512" "1024 icon_512x512@2x"; do
    size="${spec%% *}"
    name="${spec##* }"
    sips -s format png -z "$size" "$size" "$ICON_SRC" --out "$ICONSET/$name.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$ICON_OUT"
  rm -rf "$(dirname "$ICONSET")"
  echo "icon $ICON_OUT"
fi

if [[ ! -d "$INC" || ! -d "$LIB" ]]; then
  echo "Python headers/libs not found."
  echo "Set PYTHON_INCLUDE / PYTHON_LIBDIR, or install cpython 3.11 via uv."
  echo "INC=$INC"
  echo "LIB=$LIB"
  exit 1
fi

clang -O2 -arch arm64 \
  -I"$INC" -L"$LIB" -lpython3.11 \
  -Wl,-rpath,"$LIB" \
  -o "$OUT_REPO" \
  "$ROOT/native/xochipilli_launcher.c"
chmod +x "$OUT_REPO"

if [[ -d /Applications/Xochipilli.app ]]; then
  mkdir -p /Applications/Xochipilli.app/Contents/{MacOS,Resources}
  cp -f "$OUT_REPO" /Applications/Xochipilli.app/Contents/MacOS/Xochipilli
  cp -f "$CONTENTS/Info.plist" /Applications/Xochipilli.app/Contents/Info.plist
  cp -f "$PROJECT_ROOT_FILE" /Applications/Xochipilli.app/Contents/Resources/ProjectRoot
  cp -f "$ICON_OUT" /Applications/Xochipilli.app/Contents/Resources/AppIcon.icns
  chmod +x /Applications/Xochipilli.app/Contents/MacOS/Xochipilli
  xattr -cr /Applications/Xochipilli.app 2>/dev/null || true
fi

echo "built $OUT_REPO"
echo "ProjectRoot=$(cat "$PROJECT_ROOT_FILE")"
file "$OUT_REPO"
