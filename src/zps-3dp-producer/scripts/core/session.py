"""production/session.json (D29.4, D30.10): what the SessionStart hook received on stdin. `source` of the last start, and
the transcript of every main session, so `P stats` can count Producer tokens across `/clear`."""
from __future__ import annotations

import datetime as dt
import json
import select
import sys

from .state import ROOT, stamp, write_atomic

OUT = ROOT / "session.json"
WAIT_S = 1.0


def load() -> dict | None:
    try:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def record(text: str) -> dict | None:
    """Only a project that has production/ gets the file: `next` runs unlocked and must not create the root."""
    try:
        hook = json.loads(text)
    except ValueError:
        return None
    if not isinstance(hook, dict) or not ROOT.is_dir():
        return None
    seen = [p for p in ((load() or {}).get("transcripts") or []) if isinstance(p, str)]
    tp = hook.get("transcript_path")
    if isinstance(tp, str) and tp and tp not in seen:
        seen.append(tp)
    doc = {"session_id": hook.get("session_id"), "source": hook.get("source"), "transcript_path": tp, "at": stamp(),
           "transcripts": seen}
    write_atomic(OUT, json.dumps(doc, ensure_ascii=False, indent=2))
    return doc


def from_stdin() -> dict | None:
    """A hand-typed `next --session` has a terminal or nothing on stdin; it must not hang there."""
    s = sys.stdin
    if s is None or s.isatty():
        return None
    try:
        if not select.select([s], [], [], WAIT_S)[0]:
            return None
        return record(s.read())
    except (OSError, ValueError):
        return None


def local(ts: str) -> dt.datetime:
    """Transcript `timestamp` is UTC (`…Z`); dispatch stamps are local and naive."""
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


USAGE = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def main_usage(paths: list[str]) -> list[tuple[dt.datetime, int]] | None:
    """Tokens of each main-session API message: the four usage fields, as a subagent's total counts them. Claude Code
    writes one line per content block with the same message id and usage, so a message counts once. Lines of
    subagents (`isSidechain`) and lines that do not parse are skipped; a transcript that cannot be read gives None."""
    out, seen = [], set()
    for p in paths:
        try:
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            return None
        for line in lines:
            try:
                d = json.loads(line)
                if not isinstance(d, dict) or d.get("isSidechain") or d.get("type") != "assistant":
                    continue
                m = d["message"]
                key = m.get("id") or d.get("requestId") or d.get("uuid")
                if (key is not None and key in seen) or not isinstance(m.get("usage"), dict):
                    continue
                n = sum(int(m["usage"].get(k) or 0) for k in USAGE)
                at = local(d["timestamp"])
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if key is not None:
                seen.add(key)
            out.append((at, n))
    return out
