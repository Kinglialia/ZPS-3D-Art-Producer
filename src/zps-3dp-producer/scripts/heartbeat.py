"""D33.7: `vN/heartbeat.log` of a Producer tool that runs a long child (Blender, `codex exec`, the Meshy child).

One line at the start, one at the end, and one about every EVERY_S seconds while the child, or a process under it,
still uses CPU or still writes output. A child that hangs (no CPU, no output) writes nothing, so the Producer sees the
silence and does not take a hung process for a slow one; an 8-minute render that works keeps writing. Standard library
only: the tools run with different venvs.

Line: `YYYY-MM-DD HH:MM:SS · <tool> · <start|running|done|timeout> · <note>`."""
from __future__ import annotations

import datetime as dt
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

EVERY_S = 30
LOG = "heartbeat.log"
VERSION = re.compile(r"^v\d+$")
STOP = (signal.SIGTERM, signal.SIGHUP)
CODEX_EXEC = "codex exec"


def vdir_of(*paths) -> Path | None:
    """The version folder `production/assets/<id>/<step>/vN` that holds one of the paths, else None (no log)."""
    for p in paths:
        if not p:
            continue
        q = Path(p).resolve()
        for d in (q, *q.parents):
            if VERSION.match(d.name) and len(d.parents) >= 3 and d.parents[2].name == "assets":
                return d
    return None


def write(vd: Path | None, tool: str, state: str, note: str = ""):
    if vd is None or not vd.is_dir():
        return
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · {tool} · {state}" + (f" · {note}" if note else "")
    with open(vd / LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def last(vd: Path) -> tuple[dt.datetime, str, str] | None:
    """(time, tool, state) of the newest line, or None."""
    try:
        rows = (vd / LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for row in reversed(rows):
        parts = row.split(" · ")
        try:
            return dt.datetime.fromisoformat(parts[0]), parts[1], parts[2]
        except (ValueError, IndexError):
            continue
    return None


def starts(vd: Path, tool: str) -> int | None:
    """Runs of `tool` in this version: its `start` lines, written before each child starts. None when vN has no log."""
    try:
        rows = (vd / LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return sum(1 for row in rows if row.split(" · ")[1:3] == [tool, "start"])


def seconds(text: str) -> float:
    """`ps -o time` as macOS (`1:02.50`) and Linux (`1-02:03:04`) print it."""
    days, _, rest = text.rpartition("-")
    total = 0.0
    for part in rest.split(":"):
        total = total * 60 + float(part)
    return total + (int(days) * 86400 if days else 0)


def cpu_s(root: int) -> float | None:
    """CPU seconds of a process and every process under it; None when `ps` gives nothing."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,time="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    kids, used = {}, {}
    for row in out.splitlines():
        parts = row.split()
        try:
            pid, ppid, t = int(parts[0]), int(parts[1]), seconds(parts[2])
        except (ValueError, IndexError):
            continue
        kids.setdefault(ppid, []).append(pid)
        used[pid] = t
    if root not in used:
        return None
    total, todo = 0.0, [root]
    while todo:
        p = todo.pop()
        total += used.get(p, 0.0)
        todo += kids.get(p, [])
    return total


def run(cmd: list[str], *, tool: str, vd: Path | None, timeout: float | None = None, input: str | None = None,
        env: dict | None = None, cwd=None, every: float = EVERY_S) -> subprocess.CompletedProcess:
    """subprocess.run(cmd, capture_output=True, text=True, ...) with the heartbeat. Raises TimeoutExpired as it does.
    The child runs in its own session, so a timeout, an exception, a SIGTERM or a SIGHUP kills every process under it;
    the new session no longer gets a signal sent to this process, so those signals become a group kill here."""
    write(vd, tool, "start")
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd, start_new_session=True)
    old = {}
    try:
        if threading.current_thread() is threading.main_thread():
            for s in STOP:
                old[s] = signal.signal(s, stop)
        return watch(p, cmd, tool, vd, timeout, input, every)
    except BaseException:
        kill_group(p)
        raise
    finally:
        for s, h in old.items():
            signal.signal(s, h)


def stop(signum, _frame):
    raise SystemExit(128 + signum)


def kill_group(p: subprocess.Popen):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    p.wait()


def watch(p: subprocess.Popen, cmd: list[str], tool: str, vd: Path | None, timeout: float | None, input: str | None,
          every: float) -> subprocess.CompletedProcess:
    bufs, size = ([], []), [0]

    def pump(stream, buf):
        while chunk := os.read(stream.fileno(), 65536):
            buf.append(chunk)
            size[0] += len(chunk)

    threads = [threading.Thread(target=pump, args=(s, b), daemon=True) for s, b in zip((p.stdout, p.stderr), bufs)]
    if input is not None:
        def feed():
            try:
                p.stdin.write(input.encode())
                p.stdin.close()
            except OSError:
                pass
        threads.append(threading.Thread(target=feed, daemon=True))
    for t in threads:
        t.start()
    start = time.monotonic()
    tick, cpu, seen = start + every, cpu_s(p.pid) or 0.0, 0

    def text(i):
        return b"".join(bufs[i]).decode("utf-8", errors="replace")
    while True:
        try:
            rc = p.wait(timeout=min(0.2, every))
            break
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        if timeout is not None and now - start > timeout:
            kill_group(p)
            for t in threads:
                t.join(5)
            write(vd, tool, "timeout", f"{timeout:g} s")
            raise subprocess.TimeoutExpired(cmd, timeout, output=text(0), stderr=text(1))
        if now >= tick:
            c, grew = cpu_s(p.pid), size[0] - seen
            used = (c - cpu) if c is not None else 0.0
            if used > 0 or grew > 0:
                write(vd, tool, "running", f"cpu +{used:.1f} s · output +{grew} B")
            cpu, seen, tick = (c if c is not None else cpu), size[0], now + every
    for t in threads:
        t.join(5)
    write(vd, tool, "done", f"exit {rc}")
    return subprocess.CompletedProcess(cmd, rc, text(0), text(1))
