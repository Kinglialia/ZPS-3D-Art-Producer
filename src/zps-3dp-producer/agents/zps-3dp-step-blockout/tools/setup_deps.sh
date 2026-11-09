#!/usr/bin/env bash
# Blockout tools, one-time setup per machine. Reduced from kit v0.10.4 tools/setup_deps.sh.
#   bash tools/setup_deps.sh            # install (idempotent)
#   DRY_RUN=1 bash tools/setup_deps.sh  # print the commands only
# tools/.deps/venv: pure-Python tools and checks.
# tools/.deps/blender-py<ver>: packages for Blender-side scripts (lib/bootstrap.py); never numpy,
# because Blender bundles it and a second copy breaks its modules.
set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS="$TOOLS/.deps"
DRY_RUN="${DRY_RUN:-0}"
VENV_PKGS=(numpy pyyaml trimesh scipy opencv-python-headless manifold3d Pillow)
BLENDER_PKGS=(pyyaml trimesh opencv-python-headless scipy manifold3d Pillow)

say() { printf '%s\n' "$*"; }
run() { say "+ $*"; if [ "$DRY_RUN" != "1" ]; then "$@"; fi; }

find_blender() {
  if [ -n "${BLENDER:-}" ]; then printf '%s\n' "$BLENDER"; return 0; fi
  local mac=/Applications/Blender.app/Contents/MacOS/Blender
  if [ -x "$mac" ]; then printf '%s\n' "$mac"; return 0; fi
  command -v blender 2>/dev/null
}
find_python() {
  local p
  for p in python3.13 python3; do
    if command -v "$p" >/dev/null 2>&1; then command -v "$p"; return 0; fi
  done
  return 1
}

BL="$(find_blender)" || { say "Blender not found. Set BLENDER=/path/to/blender."; exit 1; }
PROBE='import sys
try:
    import numpy; nv = numpy.__version__
except Exception:
    nv = "none"
print("DEPS_PROBE %d.%d %s" % (sys.version_info[0], sys.version_info[1], nv))'
LINE="$("$BL" -b --factory-startup --python-expr "$PROBE" 2>/dev/null | grep '^DEPS_PROBE ' | tail -n 1 || true)"
[ -n "$LINE" ] || { say "could not read Python/numpy versions from $BL"; exit 1; }
PYVER="$(printf '%s\n' "$LINE" | awk '{print $2}')"
TARGET="$DEPS/blender-py${PYVER/./}"

PY="$(find_python)" || { say "no python3 on PATH"; exit 1; }
VENV="$DEPS/venv"
[ -x "$VENV/bin/python" ] || run "$PY" -m venv "$VENV"
VPY="$VENV/bin/python"
run "$VPY" -m pip install --quiet --disable-pip-version-check "${VENV_PKGS[@]}"
run mkdir -p "$TARGET"
run "$VPY" -m pip install --quiet --disable-pip-version-check --upgrade --target "$TARGET" \
  --python-version "$PYVER" --only-binary=:all: --no-deps "${BLENDER_PKGS[@]}"
if [ -d "$TARGET/numpy" ]; then
  run rm -rf "$TARGET/numpy" "$TARGET"/numpy-*.dist-info "$TARGET/numpy.libs"
fi
say "Blender $BL (Python $PYVER) deps: $TARGET; venv: $VPY ($("$VPY" -V 2>&1))"
