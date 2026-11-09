#!/usr/bin/env bash
# Creates or updates scripts/.deps/venv with the packages producer.py and its tests use.
#   bash scripts/setup_deps.sh
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPTS/.deps/venv"
PY="${PYTHON:-python3}"

command -v "$PY" >/dev/null 2>&1 || { echo "không thấy $PY"; exit 1; }
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "cần Python 3.11+ ($PY là $("$PY" -V 2>&1))"; exit 1; }

[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check pyyaml pytest Pillow numpy
echo "venv: $VENV ($("$VENV/bin/python" -V 2>&1))"
