#!/usr/bin/env bash
# Views tools, one-time setup per machine: tools/.deps/venv with numpy, Pillow, PyYAML.
#   bash tools/setup_deps.sh            # install (idempotent)
#   DRY_RUN=1 bash tools/setup_deps.sh  # print the commands only
# render_blockout_views.py runs inside Blender and needs only bpy, so there is no Blender-side target.
set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$TOOLS/.deps/venv"
DRY_RUN="${DRY_RUN:-0}"

say() { printf '%s\n' "$*"; }
run() { say "+ $*"; if [ "$DRY_RUN" != "1" ]; then "$@"; fi; }

PY="$(command -v python3.13 || command -v python3)" || { say "no python3 on PATH"; exit 1; }
[ -x "$VENV/bin/python" ] || run "$PY" -m venv "$VENV"
run "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check numpy Pillow pyyaml
say "venv: $VENV/bin/python ($("$VENV/bin/python" -V 2>&1))"
