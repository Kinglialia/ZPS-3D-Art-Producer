"""production/session.json (D29.4, D30.10): what the SessionStart hook received on stdin. `source` of the last start, and
the transcript of every main session, so `P stats` can count Producer tokens across `/clear`."""
from __future__ import annotations

import datetime as dt
import json
import select
import sys
from pathlib import Path

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


def subagent_dirs() -> list[Path]:
    """Claude Code keeps a subagent's transcript in `<main transcript without .jsonl>/subagents/agent-<id>.jsonl`."""
    doc = load() or {}
    paths = [p for p in [*(doc.get("transcripts") or []), doc.get("transcript_path")] if isinstance(p, str) and p]
    out = []
    for p in dict.fromkeys(paths):
        d = Path(p).with_suffix("") / "subagents"
        if d.is_dir():
            out.append(d)
    return out


def lines_of(p: Path) -> list[dict]:
    try:
        raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in raw:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def asks_for(d: dict, brief: str) -> bool:
    """A prompt line of the Producer: a user line, not a tool result or a reminder, that names the brief."""
    if d.get("type") != "user" or d.get("isMeta"):
        return False
    c = (d.get("message") or {}).get("content")
    text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict)
                                                  and x.get("type") == "text")
    return brief in text


def agent_files(agent_id: str | None, brief: str | None, path: str | None = None) -> list[Path]:
    """D33.22: the transcript of one dispatch. The path the SubagentStop hook recorded, else `agent-<id>.jsonl`, else
    every subagent transcript whose prompt names the brief. The same agent can sit in two session folders."""
    if path and Path(path).is_file():
        return [Path(path)]
    dirs = subagent_dirs()
    if agent_id:
        found = [d / f"agent-{agent_id}.jsonl" for d in dirs if (d / f"agent-{agent_id}.jsonl").is_file()]
        if found:
            return found
    if not brief:
        return []
    return [p for d in dirs for p in sorted(d.glob("agent-*.jsonl")) if any(asks_for(x, brief) for x in lines_of(p))]


SPLIT = {"input_tokens": "input", "output_tokens": "output", "cache_read_input_tokens": "cache_read",
         "cache_creation_input_tokens": "cache_creation"}


def agent_usage(files: list[Path], start: str, end: str | None) -> dict | None:
    """The usage of one dispatch from its transcript: messages between the dispatch and the ingest only, as a resumed
    worker keeps one cumulative transcript. Each API message counts once, also across copies of the file. The four
    usage fields stay apart, with the duration in ms. Nothing in the window, or nothing readable: None, shown as
    "không có số"."""
    lo = dt.datetime.fromisoformat(start)
    hi = dt.datetime.fromisoformat(end) + dt.timedelta(seconds=1) if end else None  # stamps keep whole seconds
    seen, split, times = set(), dict.fromkeys(SPLIT.values(), 0), []
    for p in files:
        for d in lines_of(p):
            try:
                at = local(d["timestamp"])
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if at < lo or (hi is not None and at > hi):
                continue
            times.append(at)
            m = d.get("message") if d.get("type") == "assistant" else None
            if not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
                continue
            key = m.get("id") or d.get("requestId") or d.get("uuid")
            if key is not None and key in seen:
                continue
            try:
                part = {v: int(m["usage"].get(k) or 0) for k, v in SPLIT.items()}
            except (TypeError, ValueError):
                continue
            if key is not None:
                seen.add(key)
            for k, n in part.items():
                split[k] += n
    if not seen:
        return None
    return split | {"duration_ms": round((max(times) - min(times)).total_seconds() * 1000)}


def agent_numbers(files: list[Path], start: str, end: str | None) -> tuple[int | None, int | None]:
    """(tokens, duration ms) of one dispatch: the four usage fields added up."""
    u = agent_usage(files, start, end)
    return (sum(u[k] for k in SPLIT.values()), u["duration_ms"]) if u else (None, None)


def dispatch_numbers(rec: dict, end: str | None) -> tuple[int | None, int | None]:
    return agent_numbers(agent_files(rec.get("agent_id"), rec.get("brief"), rec.get("transcript")), rec["at"], end)


def dispatch_usage(rec: dict, end: str | None) -> dict | None:
    return agent_usage(agent_files(rec.get("agent_id"), rec.get("brief"), rec.get("transcript")), rec["at"], end)
