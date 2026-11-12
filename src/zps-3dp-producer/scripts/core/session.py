"""production/session.json (D30.10): what the SessionStart hook received on stdin. `source` of the last start, and
the transcript of every main session, so `P stats` can count Producer tokens across `/clear`. The token readers take a
Claude Code transcript and a Codex rollout (D46)."""
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


SPLIT = {"input_tokens": "input", "output_tokens": "output", "cache_read_input_tokens": "cache_read",
         "cache_creation_input_tokens": "cache_creation"}
CODEX = "codex"


def codex_split(u: dict) -> dict:
    """D46: a Codex `last_token_usage` in the four columns. `input_tokens` holds the cached and cache-write tokens and
    `output_tokens` the reasoning tokens, so the four add up to `total_tokens`."""
    read, write = int(u.get("cached_input_tokens") or 0), int(u.get("cache_write_input_tokens") or 0)
    return {"input": int(u.get("input_tokens") or 0) - read - write, "output": int(u.get("output_tokens") or 0),
            "cache_read": read, "cache_creation": write}


def responses(rows: list[dict]):
    """(key, line, split) for each API response of one transcript. The format comes from the line: a Claude Code
    `assistant` line with `message.usage`, or a Codex rollout `event_msg` of type `token_count` (D46). Claude Code
    repeats a message on each content block, and Codex repeats a `token_count` with the same running total: the key
    and the total let each response count once. Codex also counts `last_token_usage`, not the running total, because a
    forked thread starts with the total of its parent."""
    total = None
    for d in rows:
        p = d.get("payload")
        try:
            if d.get("type") == "event_msg" and isinstance(p, dict) and p.get("type") == "token_count":
                info = p.get("info") or {}
                if not isinstance(info.get("last_token_usage"), dict) or info.get("total_token_usage") == total:
                    continue
                total = info.get("total_token_usage")
                key = (CODEX, d.get("timestamp"), json.dumps(total, sort_keys=True))
                yield key, d, codex_split(info["last_token_usage"])
            elif d.get("type") == "assistant" and isinstance((m := d.get("message")), dict) and isinstance(
                    m.get("usage"), dict):
                yield m.get("id") or d.get("requestId") or d.get("uuid"), d, {
                    v: int(m["usage"].get(k) or 0) for k, v in SPLIT.items()}
        except (TypeError, ValueError, AttributeError):
            continue


def rows_of(raw: list[str]) -> list[dict]:
    out = []
    for line in raw:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def rollout(rows: list[dict]) -> bool:
    """A Codex rollout opens with `session_meta`."""
    return bool(rows) and rows[0].get("type") == "session_meta"


def sub_rollout(rows: list[dict]) -> bool:
    return rollout(rows) and isinstance((rows[0].get("payload") or {}).get("source"), dict) and "subagent" in rows[0][
        "payload"]["source"]


def main_usage(paths: list[str]) -> list[tuple[dt.datetime, int]] | None:
    """Tokens of each main-session API response, the four columns added up. Lines of subagents (`isSidechain`, a
    sub-agent rollout) and lines that do not parse are skipped; a transcript that cannot be read gives None."""
    out, seen = [], set()
    for p in paths:
        try:
            rows = rows_of(open(p, encoding="utf-8", errors="replace").read().splitlines())
        except OSError:
            return None
        if sub_rollout(rows):
            continue
        for key, d, part in responses(rows):
            if d.get("isSidechain") or (key is not None and key in seen):
                continue
            try:
                at = local(d["timestamp"])
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if key is not None:
                seen.add(key)
            out.append((at, sum(part.values())))
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
        return rows_of(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return []


def asks_for(d: dict, brief: str) -> bool:
    """A prompt line of the Producer that names the brief: a Claude Code user line, not a tool result or a reminder; in
    a Codex rollout, the task a parent sent (`agent_message`) or a user message the thread did not inherit. Codex
    0.164.0 keeps the `spawn_agent` message as plain text in the `encrypted_content` item of the `agent_message`."""
    p = d.get("payload")
    if d.get("type") == "response_item" and isinstance(p, dict):
        if not (p.get("type") == "agent_message" or p.get("type") == "message" and p.get("role") == "user"
                and not (d.get("metadata") or {}).get("inherited_user_message")):
            return False
        return brief in " ".join(str(x.get("text") or x.get("encrypted_content") or "") for x in p.get("content") or []
                                 if isinstance(x, dict))
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


def agent_usage(files: list[Path], start: str, end: str | None) -> dict | None:
    """The usage of one dispatch from its transcript: responses between the dispatch and the ingest only, as a resumed
    worker keeps one cumulative transcript. Each API response counts once, also across copies of the file. The four
    usage fields stay apart, with the duration in ms (first to last line in the window); a Codex rollout adds
    `format: codex`. Nothing in the window, or nothing readable: None, shown as "không có số"."""
    lo = dt.datetime.fromisoformat(start)
    hi = dt.datetime.fromisoformat(end) + dt.timedelta(seconds=1) if end else None  # stamps keep whole seconds

    def inside(d: dict) -> bool:
        try:
            at = local(d["timestamp"])
        except (KeyError, TypeError, ValueError, AttributeError):
            return False
        return lo <= at and (hi is None or at <= hi)
    seen, split, times, codex = set(), dict.fromkeys(SPLIT.values(), 0), [], False
    for p in files:
        rows = lines_of(p)
        times += [local(d["timestamp"]) for d in rows if inside(d)]
        for key, d, part in responses(rows):
            if not inside(d) or (key is not None and key in seen):
                continue
            if key is not None:
                seen.add(key)
            codex = codex or isinstance(key, tuple)
            for k, n in part.items():
                split[k] += n
    if not seen:
        return None
    return split | {"duration_ms": round((max(times) - min(times)).total_seconds() * 1000)} | (
        {"format": CODEX} if codex else {})


def agent_numbers(files: list[Path], start: str, end: str | None) -> tuple[int | None, int | None]:
    """(tokens, duration ms) of one dispatch: the four usage fields added up."""
    u = agent_usage(files, start, end)
    return (sum(u[k] for k in SPLIT.values()), u["duration_ms"]) if u else (None, None)


def dispatch_numbers(rec: dict, end: str | None) -> tuple[int | None, int | None]:
    return agent_numbers(agent_files(rec.get("agent_id"), rec.get("brief"), rec.get("transcript")), rec["at"], end)


def dispatch_usage(rec: dict, end: str | None) -> dict | None:
    return agent_usage(agent_files(rec.get("agent_id"), rec.get("brief"), rec.get("transcript")), rec["at"], end)
