#!/usr/bin/env python3
"""Make images with the Codex image tool, one `codex exec` call per image (D8, D15, D18). Shared by the views and texture agents.

Usage: python3 gen_image_codex.py --model <m> --reasoning <r> --pid-file <f> --prompt <request.md>
           --image <ref> [--image <ref> ...] --out <dir/name.png> [--prompt <b.md> --out <dir/b.png> ...]
           [--batch] [--size 1536x1024] [--timeout 900] [--approve-for-me "<why the last call was blocked>"]
The brief gives --model, --reasoning (preset `image_gen`) and --pid-file. --prompt holds only what to draw;
the script adds the fixed frame (save the image to --out, write <name>.result.json, do nothing else).
Runs `codex exec -C <dir of --out> -s workspace-write`, prompt on stdin, in an env without any *_API_KEY other than
OPENAI_API_KEY and CODEX_API_KEY (a Meshy key never reaches Codex). If --out is missing, Codex reported no error and
exactly one image appeared under $CODEX_HOME/generated_images during the call, it takes that image, saved as PNG (D18.4);
this also holds after a timeout. A valid --out image is accepted even if result.json carries an error.
A try fails when there is no image, Codex reports an error, the image is broken, or the long side is 1040 px or less.
The pid file is written as <stem>-<pid><suffix>, so concurrent gens of one asset each hold a slot.
Several --prompt/--out pairs (same order) share the --image list. D30.20: after each call every expected file is
checked on its own (exists, PNG header, Pillow reads it, long side); only the files that failed are made again.
3 failed tries of one file: that file fails, and the script exits 1 at the end (D8.3). Writes <dir/name>.json and prints
one line per file. D30.22: --batch (the brief adds it when the step has `codex_batch = true`) asks for every pending file
in one call, then checks each file and asks again only for the failed ones; all --out files share one folder, and the
CODEX_HOME fallback holds only for a call with one file. --timeout is per call; the brief gives it from pipeline.toml [codex] timeout_s (≥ 300).
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
import time
from pathlib import Path

from root_guard import require_root

TRIES = 3
MIN_LONG = 1041
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


def new_images(since: float) -> list[Path]:
    d = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "generated_images"
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


def to_png(src: Path, out: Path):
    from PIL import Image
    try:
        with Image.open(src) as im:
            im.save(out, "PNG")
    except (OSError, SyntaxError, ValueError):
        shutil.copyfile(src, out)


def call(a, jobs: list[dict]):
    for j in jobs:
        for p in (j["out"], j["result"]):
            p.unlink(missing_ok=True)
    prompt = FRAME.format(out=jobs[0]["out"], result=jobs[0]["result"], size=a.size, request=jobs[0]["request"]) \
        if len(jobs) == 1 else BATCH_FRAME.format(size=a.size, jobs="\n".join(
            JOB.format(k=k, out=j["out"], result=j["result"], request=j["request"]) for k, j in enumerate(jobs, 1)))
    cmd = ["codex", "exec", "-m", a.model, "-c", f"model_reasoning_effort={a.reasoning}", "-C", str(jobs[0]["out"].parent),
           "-s", "workspace-write", "--skip-git-repo-check", *(["--approve-for-me"] if a.approve_for_me else []),
           *[f"--image={Path(i).resolve()}" for i in a.image], "-"]
    start = time.time() - 1
    try:
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") or k in CODEX_KEYS}
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=a.timeout, env=env)
    except subprocess.TimeoutExpired:
        p = None
    if p is not None and (m := actual_model(p.stderr)):
        a.actual = m
    return p, start


def check(a, j: dict, p, start: float, alone: bool) -> tuple[str | None, bool, list[int] | None]:
    """D30.20: the file of one job after a call. The CODEX_HOME fallback (D18.4) holds only for a call with one job."""
    out, err, fallback = j["out"], codex_error(j["result"]), False
    if alone and not out.is_file() and not err and len(found := new_images(start)) == 1:
        to_png(found[0], out)
        fallback = True
    if not out.is_file():
        if err:
            return f"codex: {err}", False, None
        if p is None:
            return f"hết thời gian chờ {a.timeout} s", False, None
        tail = (p.stderr.strip().splitlines() or [""])[-1][:200]
        return "không có file ảnh" + (f" (codex exit {p.returncode}: {tail})" if p.returncode else ""), False, None
    with out.open("rb") as f:
        if f.read(8) != PNG_SIGNATURE:
            return "file không có header PNG", fallback, None
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


def run_jobs(a, jobs: list[dict]):
    """Each round calls Codex once per pending job, or once for all of them with --batch. After a call every job file is checked on its own, and only the
    jobs that failed go to the next round, at most TRIES tries each."""
    pending = list(jobs)
    while pending:
        for group in [pending] if a.batch else [[j] for j in pending]:
            p, start = call(a, group)
            for j in group:
                rec = j["rec"]
                rec["attempts"] += 1
                err, rec["fallback"], rec["size"] = check(a, j, p, start, len(group) == 1)
                if err is None:
                    rec["status"] = "ok"
                else:
                    rec["errors"].append(err)
        pending = [j for j in pending if j["rec"]["status"] != "ok" and j["rec"]["attempts"] < TRIES]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--reasoning", required=True)
    ap.add_argument("--pid-file", required=True, type=Path)
    ap.add_argument("--prompt", required=True, type=Path, action="append")
    ap.add_argument("--image", action="append", default=[])
    ap.add_argument("--out", required=True, type=Path, action="append")
    ap.add_argument("--size", default="1536x1024")
    ap.add_argument("--timeout", type=int, default=900)
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
    for prompt, out in zip(a.prompt, a.out):
        out = out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        jobs.append({"out": out, "result": out.with_name(out.stem + ".result.json"),
                     "request": prompt.read_text(encoding="utf-8").strip(),
                     "rec": {"status": "fail", "attempts": 0, "model": a.model, "model_requested": a.model,
                             "model_actual": NO_NUMBER, "codex_cli": NO_NUMBER, "reasoning": a.reasoning,
                             "prompt": str(prompt), "images": a.image, "approve_for_me": a.approve_for_me, "batch": a.batch,
                             "size": None, "fallback": False, "errors": []}})
    if shutil.which("codex") is None:
        for j in jobs:
            j["rec"]["errors"].append("không thấy codex trên PATH")
    else:
        cli = cli_version()
        pid_file = a.pid_file.with_name(f"{a.pid_file.stem}-{os.getpid()}{a.pid_file.suffix}")
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
        try:
            run_jobs(a, jobs)
        finally:
            pid_file.unlink(missing_ok=True)
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
        print(f"[gen_image_codex] fail{f' {TRIES}/{TRIES}' if rec['attempts'] else ''}: {rec['errors'][-1]} -> {rec_path}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    require_root()
    main()
