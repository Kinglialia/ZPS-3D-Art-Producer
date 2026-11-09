"""`KEY: value` report contracts of worker and reviewer."""
from __future__ import annotations

import re
from pathlib import Path

WORKER_STATUS = {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
VERDICTS = {"PASS", "FIX", "ESCALATE"}


def parse_contract(path: Path, keys: set[str]) -> dict | None:
    if not path.exists():
        return None
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines()[:40]:
        m = re.match(r"^\s*([A-Z_]+):\s*(.*)$", line)
        if m and m.group(1) in keys and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()
    return out
