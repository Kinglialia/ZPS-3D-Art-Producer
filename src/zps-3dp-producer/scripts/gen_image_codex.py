#!/usr/bin/env python3
"""Make images with the Codex image tool, one `codex exec` call per image (D8, D15, D18). Shared by the views and texture agents.

Usage: python3 gen_image_codex.py --model <m> --reasoning <r> --pid-file <f> --prompt <request.md>
           --image <ref> [--image <ref> ...] --out <dir/name.png> [--prompt <b.md> --out <dir/b.png> ...]
           [--batch] [--size 1536x1024] [--timeout 900] [--wall-s 3300] [--approve-for-me "<why the last call was blocked>"]
The brief gives --model, --reasoning (preset `image_gen`) and --pid-file. --prompt holds only what to draw;
the script adds the fixed frame (save the image to --out, write <name>.result.json, do nothing else).
Runs `codex exec -C <dir of --out> -s workspace-write`, prompt on stdin, in an env without any *_API_KEY other than
OPENAI_API_KEY and CODEX_API_KEY (a Meshy key never reaches Codex). If --out is missing, Codex reported no error and
exactly one image appeared during the call in $CODEX_HOME/generated_images/<session id>/, it takes that image, saved as
PNG (D18.4, D36.9); this also holds after a timeout. The session id is the `session id:` line of the header that
`codex exec` prints on stderr. Without that line the fallback looks in all of generated_images/, and only while no other
live pid file of the codex_image folder exists, because it cannot tell whose image is new. A valid --out image is accepted
even if result.json carries an error.
A try fails when there is no image, Codex reports an error, the image is broken, or the long side is 1040 px or less.
An image that Pillow reads but is not PNG (a JPEG saved under a .png name) is converted to PNG and accepted (D36.12).
D36.12: a quota, rate-limit or billing error stops the whole run after that one call. A policy or safety error is tried
once more. Any other error is tried up to 3 times.
The pid file is written as <stem>-<pid><suffix>, so concurrent gens of one asset each hold a slot.
Without --batch the jobs of one run go in parallel: one thread, and one pid file <stem>-<pid>-<k><suffix> (k from 1; the
first thread keeps the name above), per free slot, where free = `[limits] codex_image` of pipeline.toml minus the live pid
files of other runs in the folder of --pid-file, and at least 1. Without that limit a run uses one thread. Each thread takes
the next job, and a failed job goes back to the end of the queue, so the retry of one file never waits for the others. A
quota error stops every job that has not started; a call in flight is kept. While two calls of one run overlap, the
CODEX_HOME fallback without a session id is off, because the one new image may be the other call's.
Several --prompt/--out pairs go in the same order. An --image or --size before the first --prompt serves every job; one
after a --prompt, before the next, serves that job only (its images come after the shared ones, its size replaces the
shared one), so one run can paint views with different guides and sizes. With --batch the position does not count: every
image is attached to the one call. D30.20: after each call every expected file is
checked on its own (exists, PNG header, Pillow reads it, long side); only the files that failed are made again.
3 failed tries of one file: that file fails, and the script exits 1 at the end (D8.3). SIGTERM, SIGHUP or SIGINT kill
every codex call in flight, in any thread, start no new call, remove the pid files and exit 128 + the signal number. Writes <dir/name>.json and prints
one line per file. D30.22: --batch (the brief adds it when the step has `codex_batch = true`) asks for every pending file
in one call, then checks each file and asks again only for the failed ones; all --out files share one folder, and the
CODEX_HOME fallback holds only for a call with one file. --timeout is per call; the brief gives it from pipeline.toml [codex] timeout_s (≥ 300).
D33.3: --wall-s caps the whole run below the Bash limit of the settings snippet (BASH_MAX_TIMEOUT_MS 3600000): no new
call starts when it could end after the cap; the jobs left fail with "hết thời gian tổng".
D28.1: the record keeps the requested model (--model) and the actual one, the `model:` line of the header that
`codex exec` prints on stderr ("không có số" without it). When --out lies in <root>/assets/<id>/<step>/vN/, both also go
to the ledger and to `inputs[<step>]["vN"]` of status.json. D30.19: the record and the ledger line also keep the version
that `codex --version` prints (tested with codex-cli 0.164.0). FLAGS lists every `codex exec` flag the command uses;
`P preflight` checks that `codex exec --help` lists each one.
D30.21: codex `--approve-for-me` approves every permission request by itself, so it is never a default and never in the
brief's GEN_ARGS. It is passed only with --approve-for-me "<reason>" after a call was really blocked; the record and
the ledger line keep the reason.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import heartbeat

from root_guard import MARK, require_root

TRIES = 3
MIN_LONG = 1041
QUOTA = re.compile(r"quota|rate[ _-]?limit|usage[ _-]?limit|too many requests|\b429\b|billing", re.I)
POLICY = re.compile(r"polic|safety|moderation", re.I)
POLICY_TRIES = 2
SESSION_LINE = re.compile(r"^session id: *([\w-]+)\s*$", re.M | re.I)
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CODEX_KEYS = {"OPENAI_API_KEY", "CODEX_API_KEY"}
NO_NUMBER = "không có số"
FLAGS = ("-m", "-c", "-C", "-s", "--skip-git-repo-check", "--image")
FRAME = """You are one step of an art build pipeline. Do only this:
1. Use your image generation tool once to make the image that REQUEST describes. Give the tool the attached images.
2. Save the image as PNG at OUTPUT_PATH, SIZE pixels.
3. Write RESULT_PATH as JSON: {{"path": "<OUTPUT_PATH>", "width": <px>, "height": <px>, "error": null}}.
   If you cannot make the image, write {{"path": null, "width": 0, "height": 0, "error": "<reason>"}}.
Do not edit other files. Do not do other work.

OUTPUT_PATH: {out}
RESULT_PATH: {result}
SIZE: {size}

REQUEST:
{request}
"""
BATCH_FRAME = """You are one step of an art build pipeline. Do only this, for each JOB below:
1. Use your image generation tool once per JOB to make the image that its REQUEST describes. Give the tool the attached
   images that its REQUEST names.
2. Save the image as PNG at the OUTPUT_PATH of the JOB, SIZE pixels.
3. Write the RESULT_PATH of the JOB as JSON: {{"path": "<OUTPUT_PATH>", "width": <px>, "height": <px>, "error": null}}.
   If you cannot make the image, write {{"path": null, "width": 0, "height": 0, "error": "<reason>"}}.
Do not edit other files. Do not do other work.

SIZE: {size}

{jobs}"""
JOB = "JOB {k}\nOUTPUT_PATH: {out}\nRESULT_PATH: {result}\nREQUEST:\n{request}\nEND JOB {k}\n"


def new_images(since: float, session: str | None = None) -> list[Path]:
    d = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "generated_images" / (session or "")
    return [p for p in d.rglob("*") if p.suffix.lower() in IMAGES and p.stat().st_mtime >= since] if d.is_dir() else []


def codex_error(result: Path) -> str | None:
    try:
        return json.loads(result.read_text(encoding="utf-8")).get("error")
    except (OSError, ValueError, AttributeError):
        return None


def cli_version() -> str:
    try:
        p = subprocess.run(["codex", "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return NO_NUMBER
    m = re.search(r"codex-cli\s+(\S+)", p.stdout + p.stderr)
    return m[1] if m else NO_NUMBER


def missing_flags(help_text: str) -> list[str]:
    return [f for f in FLAGS if not re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", help_text)]


def actual_model(stderr: str | None) -> str | None:
    m = re.search(r"^model: *(\S+)\s*$", stderr or "", re.M)
    return m[1] if m else None


def session_id(stderr: str | None) -> str | None:
    m = SESSION_LINE.search(stderr or "")
    return m[1] if m else None


def error_kind(err: str) -> str | None:
    """Only text that came from Codex counts: this script's own messages (a timeout of 429 s) are never an error kind."""
    if not err.startswith(("codex: ", "không có file ảnh (codex exit")):
        return None
    return "quota" if QUOTA.search(err) else "policy" if POLICY.search(err) else None


def live_runs(pid_file: Path) -> int:
    """Live pid files in the folder of --pid-file that another process holds (core.limits.used counts them as slots)."""
    n = 0
    for f in pid_file.parent.glob(f"*{pid_file.suffix}"):
        try:
            pid = int(f.read_text(encoding="utf-8").strip())
            if pid > 0 and pid != os.getpid():
                os.kill(pid, 0)
                n += 1
        except PermissionError:
            n += 1
        except (OSError, ValueError):
            pass
    return n


def runs_alive(pid_file: Path) -> bool:
    return live_runs(pid_file) > 0


def free_slots(pid_file: Path) -> int:
    """Threads for one run: the free codex_image slots, at least 1. No limit in pipeline.toml: 1."""
    try:
        limit = int(tomllib.loads(Path(MARK).read_text(encoding="utf-8"))["limits"]["codex_image"])
    except (OSError, ValueError, KeyError, TypeError):
        return 1
    return max(1, limit - live_runs(pid_file))


def own_pid_file(pid_file: Path, k: int) -> Path:
    return pid_file.with_name(f"{pid_file.stem}-{os.getpid()}{f'-{k}' if k else ''}{pid_file.suffix}")


def convert_to_png(path: Path) -> bool:
    from PIL import Image
    tmp = path.with_name(path.name + ".tmp")
    try:
        with Image.open(path) as im:
            im.load()
            (im if im.mode in ("RGB", "RGBA", "L", "LA", "P") else im.convert("RGB")).save(tmp, "PNG")
    except (OSError, SyntaxError, ValueError):
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True


def version_of(out: Path) -> tuple[Path, str, str, int] | None:
    parts = out.parts
    for i in range(len(parts) - 4, -1, -1):
        if parts[i] == "assets" and re.fullmatch(r"v\d+", parts[i + 3]):
            return Path(*parts[:i]), parts[i + 1], parts[i + 2], int(parts[i + 3][1:])
    return None


def record_models(out: Path, requested: str, actual: str, cli: str, approve: str | None):
    """Several gens of one asset run at once: status.json is written under the Producer lock. The image is paid for
    already, so a failure here (no status.json, an old Python in the agent venv) only warns."""
    if not (where := version_of(out)):
        return
    root, aid, sid, n = where
    os.environ["PRODUCER_ROOT"] = str(root)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from core.state import ledger, load_st, locked, save_st
        with locked():
            st = load_st(aid)
            inp = st.setdefault("inputs", {}).setdefault(sid, {}).setdefault(f"v{n}", {})
            for k, v in (("image_model_requested", requested), ("image_model_actual", actual)):
                seen = inp[k].split(", ") if inp.get(k) else []
                inp[k] = ", ".join(seen + [v] if v not in seen else seen)
            save_st(st)
            ledger(f"{aid} · {sid} v{n} · gen ảnh {out.name}: model yêu cầu {requested} · model thực tế {actual} "
                   f"· codex-cli {cli}" + (f" · --approve-for-me: {approve}" if approve else ""))
    except (Exception, SystemExit) as ex:
        print(f"[gen_image_codex] không ghi được model vào status.json/ledger: {ex}", file=sys.stderr)


class Placed(argparse.Action):
    """Collect (number of --prompt seen so far, value): 0 means before the first --prompt."""
    def __call__(self, parser, ns, value, option_string=None):
        getattr(ns, self.dest).append((len(ns.prompt), value))


class Prompt(argparse.Action):
    def __call__(self, parser, ns, value, option_string=None):
        ns.prompt.append(Path(value))


def placed_for(placed: list, k: int, batch: bool) -> list:
    """The values that serve job k (counted from 1): the shared ones, then its own; with --batch, all of them."""
    return [v for n, v in placed if batch or n in (0, k)]


def call(a, jobs: list[dict]):
    for j in jobs:
        for p in (j["out"], j["result"]):
            p.unlink(missing_ok=True)
    prompt = FRAME.format(out=jobs[0]["out"], result=jobs[0]["result"], size=jobs[0]["size"], request=jobs[0]["request"]) \
        if len(jobs) == 1 else BATCH_FRAME.format(size=jobs[0]["size"], jobs="\n".join(
            JOB.format(k=k, out=j["out"], result=j["result"], request=j["request"]) for k, j in enumerate(jobs, 1)))
    cmd = ["codex", "exec", "-m", a.model, "-c", f"model_reasoning_effort={a.reasoning}", "-C", str(jobs[0]["out"].parent),
           "-s", "workspace-write", "--skip-git-repo-check", *(["--approve-for-me"] if a.approve_for_me else []),
           *[f"--image={Path(i).resolve()}" for i in jobs[0]["images"]], "-"]
    start, busy = time.time() - 1, runs_alive(a.pid_file)
    with a.lock:
        a.open_calls, a.calls_started = a.open_calls + 1, a.calls_started + 1
        mark, overlap = a.calls_started, a.open_calls > 1
    try:
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") or k in CODEX_KEYS}
        p = heartbeat.run(cmd, tool=heartbeat.CODEX_EXEC, vd=heartbeat.vdir_of(*(j["out"] for j in jobs)), input=prompt,
                          timeout=a.timeout, env=env)
        stderr = p.stderr
    except subprocess.TimeoutExpired as ex:
        p, stderr = None, ex.stderr if isinstance(ex.stderr, str) else ""
    finally:
        with a.lock:
            a.open_calls -= 1
            overlap = overlap or a.calls_started != mark
    if m := actual_model(stderr):
        a.actual = m
    return p, start, {"stderr": stderr, "busy": busy or overlap}


def fallback_image(a, ctx: dict, start: float) -> Path | None:
    """D36.9: the one new image of this call's session folder. With no session id, any folder, but only while no other
    codex_image run is alive (before the call or now), because the image could be that run's."""
    sid = session_id(ctx["stderr"])
    if sid is None and (ctx["busy"] or runs_alive(a.pid_file)):
        return None
    return found[0] if len(found := new_images(start, sid)) == 1 else None


def check(a, j: dict, p, start: float, ctx: dict, alone: bool) -> tuple[str | None, bool, list[int] | None]:
    """D30.20: the file of one job after a call. The CODEX_HOME fallback (D18.4) holds only for a call with one job."""
    out, err, fallback, rec = j["out"], codex_error(j["result"]), False, j["rec"]
    rec["session"], rec["converted"] = session_id(ctx["stderr"]), False
    if alone and not out.is_file() and not err and (found := fallback_image(a, ctx, start)):
        shutil.copyfile(found, out)
        fallback = True
    if not out.is_file():
        if err:
            return f"codex: {err}", False, None
        if p is None:
            return f"hết thời gian chờ {a.timeout} s", False, None
        tail = (p.stderr.strip().splitlines() or [""])[-1][:200]
        return "không có file ảnh" + (f" (codex exit {p.returncode}: {tail})" if p.returncode else ""), False, None
    with out.open("rb") as f:
        is_png = f.read(8) == PNG_SIGNATURE
    if not is_png:
        if not convert_to_png(out):
            return "file ảnh hỏng", fallback, None
        rec["converted"] = True
    from PIL import Image
    try:
        with Image.open(out) as im:
            im.load()
            size = list(im.size)
    except (OSError, SyntaxError, ValueError):
        return "file ảnh hỏng", fallback, None
    if max(size) < MIN_LONG:
        return f"ảnh {size[0]}x{size[1]}, cạnh dài cần > 1040 px", fallback, size
    return None, fallback, size


def attempt(a, group: list[dict]):
    """One Codex call for the jobs of `group`, then the check of each file. A quota error sets a.stop."""
    if time.monotonic() - a.t0 + a.timeout > a.wall_s:
        for j in group:
            j["rec"]["errors"].append(f"hết thời gian tổng {a.wall_s} s (D33.3): không gọi thêm")
            j["rec"]["attempts"] = TRIES
        return
    p, start, ctx = call(a, group)
    for j in group:
        rec = j["rec"]
        rec["attempts"] += 1
        err, rec["fallback"], rec["size"] = check(a, j, p, start, ctx, len(group) == 1)
        if err is None:
            rec["status"] = "ok"
            continue
        rec["errors"].append(err)
        kind = error_kind(err)
        rec["limit"] = min(rec["limit"], {"quota": 1, "policy": POLICY_TRIES}.get(kind, TRIES))
        if kind == "quota":
            a.stop.set()


def retry(j: dict) -> bool:
    return j["rec"]["status"] != "ok" and j["rec"]["attempts"] < j["rec"]["limit"]


def run_jobs(a, jobs: list[dict]):
    """After a call every job file is checked on its own, and only the jobs that failed are tried again, up to the
    `limit` of each: TRIES, or fewer after a quota or policy error (D36.12). A quota error ends the run: the quota is
    shared by every file. With --batch one call asks for every pending job. Without it each thread of a.pid_files
    takes one job at a time, and a job that failed goes to the end of the queue."""
    a.t0, a.stop, a.lock, a.open_calls, a.calls_started = time.monotonic(), threading.Event(), threading.Lock(), 0, 0
    if a.batch:
        pending = list(jobs)
        while pending and not a.stop.is_set():
            attempt(a, pending)
            pending = [j for j in pending if retry(j) and not a.stop.is_set()]
        return
    queue = deque(jobs)

    def thread(k: int):
        try:
            while True:
                with a.lock:
                    if a.stop.is_set() or not queue:
                        return
                    job = queue.popleft()
                attempt(a, [job])
                if retry(job):
                    with a.lock:
                        queue.append(job)
        finally:
            a.pid_files[k].unlink(missing_ok=True)

    with ThreadPoolExecutor(len(a.pid_files)) as pool:
        for f in [pool.submit(thread, k) for k in range(len(a.pid_files))]:
            f.result()
    for j in queue:
        if not j["rec"]["attempts"]:
            j["rec"]["errors"].append("không gọi: codex hết quota ở file khác")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--reasoning", required=True)
    ap.add_argument("--pid-file", required=True, type=Path)
    ap.add_argument("--prompt", required=True, action=Prompt, default=[])
    ap.add_argument("--image", action=Placed, default=[])
    ap.add_argument("--out", required=True, type=Path, action="append")
    ap.add_argument("--size", action=Placed, default=[])
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--wall-s", type=int, default=3300)
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--approve-for-me", metavar="REASON")
    a = ap.parse_args()
    if a.approve_for_me is not None and not a.approve_for_me.strip():
        ap.error("--approve-for-me cần lý do: lần gọi trước bị chặn ở đâu")
    if len(a.prompt) != len(a.out):
        ap.error("mỗi --out cần đúng một --prompt, cùng thứ tự")
    if a.batch and len({o.resolve().parent for o in a.out}) > 1:
        ap.error("--batch cần mọi --out trong cùng một thư mục: codex exec -C chỉ mở một thư mục")
    a.actual, jobs = None, []
    for k, (prompt, out) in enumerate(zip(a.prompt, a.out), 1):
        out = out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        images = placed_for(a.image, k, a.batch)
        jobs.append({"out": out, "result": out.with_name(out.stem + ".result.json"), "images": images,
                     "size": (placed_for(a.size, k, a.batch) or ["1536x1024"])[-1],
                     "request": prompt.read_text(encoding="utf-8").strip(),
                     "rec": {"status": "fail", "attempts": 0, "model": a.model, "model_requested": a.model,
                             "model_actual": NO_NUMBER, "codex_cli": NO_NUMBER, "reasoning": a.reasoning,
                             "prompt": str(prompt), "images": images, "approve_for_me": a.approve_for_me, "batch": a.batch,
                             "size": None, "fallback": False, "converted": False, "session": None, "limit": TRIES,
                             "errors": []}})
    if shutil.which("codex") is None:
        for j in jobs:
            j["rec"]["errors"].append("không thấy codex trên PATH")
    else:
        cli = cli_version()
        a.pid_files = [own_pid_file(a.pid_file, k) for k in range(1 if a.batch else min(len(jobs), free_slots(a.pid_file)))]
        a.pid_file.parent.mkdir(parents=True, exist_ok=True)
        for f in a.pid_files:
            f.write_text(str(os.getpid()), encoding="utf-8")
        try:
            run_jobs(a, jobs)
        finally:
            for f in a.pid_files:
                f.unlink(missing_ok=True)
        for j in jobs:
            j["rec"]["model_actual"], j["rec"]["codex_cli"] = a.actual or NO_NUMBER, cli
    failed = False
    for j in jobs:
        out, rec, rec_path = j["out"], j["rec"], j["out"].with_suffix(".json")
        if rec["status"] != "ok":
            out.unlink(missing_ok=True)
        rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        if rec["attempts"]:
            record_models(out, rec["model_requested"], rec["model_actual"], rec["codex_cli"], a.approve_for_me)
        if rec["status"] == "ok":
            print(f"[gen_image_codex] ok {rec['size'][0]}x{rec['size'][1]} lần {rec['attempts']} -> {out}")
            continue
        failed = True
        tries = f" {rec['attempts']}/{rec['limit']}" if rec["attempts"] else ""
        print(f"[gen_image_codex] fail{tries}: {rec['errors'][-1]} -> {rec_path}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    require_root()
    heartbeat.stop_on_signals()
    main()
