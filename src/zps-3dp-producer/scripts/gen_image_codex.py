#!/usr/bin/env python3
"""Make one image with the Codex image tool (D8, D15, D18). Shared by the views and texture agents.

Usage: python3 gen_image_codex.py --model <m> --reasoning <r> --pid-file <f> --prompt <request.md>
           --image <ref> [--image <ref> ...] --out <dir/name.png> [--size 1536x1024] [--timeout 900]
The brief gives --model, --reasoning (preset `image_gen`) and --pid-file. --prompt holds only what to draw;
the script adds the fixed frame (save the image to --out, write <name>.result.json, do nothing else).
Runs `codex exec -C <dir of --out> -s workspace-write`, prompt on stdin, in an env without any *_API_KEY other than
OPENAI_API_KEY and CODEX_API_KEY (a Meshy key never reaches Codex). If --out is missing, Codex reported no error and
exactly one image appeared under $CODEX_HOME/generated_images during the call, it takes that image (D18.4);
this also holds after a timeout. A valid --out image is accepted even if result.json carries an error.
A try fails when there is no image, Codex reports an error, the image is broken, or the long side is 1040 px or less.
The pid file is written as <stem>-<pid><suffix>, so concurrent gens of one asset each hold a slot.
3 failed tries in a row: exit 1 (D8.3). Writes <dir/name>.json, prints one line.
D28.1: the record keeps the requested model (--model) and the actual one, the `model:` line of the header that
`codex exec` prints on stderr ("không có số" without it). When --out lies in <root>/assets/<id>/<step>/vN/, both also go
to the ledger and to `inputs[<step>]["vN"]` of status.json.
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

TRIES = 3
MIN_LONG = 1041
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
CODEX_KEYS = {"OPENAI_API_KEY", "CODEX_API_KEY"}
NO_NUMBER = "không có số"
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


def new_images(since: float) -> list[Path]:
    d = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "generated_images"
    return [p for p in d.rglob("*") if p.suffix.lower() in IMAGES and p.stat().st_mtime >= since] if d.is_dir() else []


def codex_error(result: Path) -> str | None:
    try:
        return json.loads(result.read_text(encoding="utf-8")).get("error")
    except (OSError, ValueError, AttributeError):
        return None


def actual_model(stderr: str | None) -> str | None:
    m = re.search(r"^model: *(\S+)\s*$", stderr or "", re.M)
    return m[1] if m else None


def version_of(out: Path) -> tuple[Path, str, str, int] | None:
    parts = out.parts
    for i in range(len(parts) - 4, -1, -1):
        if parts[i] == "assets" and re.fullmatch(r"v\d+", parts[i + 3]):
            return Path(*parts[:i]), parts[i + 1], parts[i + 2], int(parts[i + 3][1:])
    return None


def record_models(out: Path, requested: str, actual: str):
    """Several gens of one asset run at once: status.json is written under the Producer lock."""
    if not (where := version_of(out)):
        return
    root, aid, sid, n = where
    os.environ["PRODUCER_ROOT"] = str(root)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from core.state import ProducerError, ledger, load_st, locked, save_st
    try:
        with locked():
            st = load_st(aid)
            inp = st.setdefault("inputs", {}).setdefault(sid, {}).setdefault(f"v{n}", {})
            for k, v in (("image_model_requested", requested), ("image_model_actual", actual)):
                seen = inp[k].split(", ") if inp.get(k) else []
                inp[k] = ", ".join(seen + [v] if v not in seen else seen)
            save_st(st)
            ledger(f"{aid} · {sid} v{n} · gen ảnh {out.name}: model yêu cầu {requested} · model thực tế {actual}")
    except (ProducerError, OSError) as ex:
        print(f"[gen_image_codex] không ghi được model vào status.json/ledger: {ex}", file=sys.stderr)


def attempt(a, out: Path, result: Path, prompt: str) -> tuple[str | None, bool, list[int] | None]:
    for p in (out, result):
        p.unlink(missing_ok=True)
    cmd = ["codex", "exec", "-m", a.model, "-c", f"model_reasoning_effort={a.reasoning}", "-C", str(out.parent),
           "-s", "workspace-write", "--skip-git-repo-check", *[f"--image={Path(i).resolve()}" for i in a.image], "-"]
    start = time.time() - 1
    try:
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") or k in CODEX_KEYS}
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=a.timeout, env=env)
    except subprocess.TimeoutExpired:
        p = None
    if p is not None and (m := actual_model(p.stderr)):
        a.actual = m
    err, fallback = codex_error(result), False
    if not out.is_file() and not err and len(found := new_images(start)) == 1:
        shutil.copyfile(found[0], out)
        fallback = True
    if not out.is_file():
        if err:
            return f"codex: {err}", False, None
        if p is None:
            return f"hết thời gian chờ {a.timeout} s", False, None
        tail = (p.stderr.strip().splitlines() or [""])[-1][:200]
        return "không có file ảnh" + (f" (codex exit {p.returncode}: {tail})" if p.returncode else ""), False, None
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--reasoning", required=True)
    ap.add_argument("--pid-file", required=True, type=Path)
    ap.add_argument("--prompt", required=True, type=Path)
    ap.add_argument("--image", action="append", default=[])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--size", default="1536x1024")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    out = a.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    result, rec_path = out.with_name(out.stem + ".result.json"), out.with_suffix(".json")
    prompt = FRAME.format(out=out, result=result, size=a.size, request=a.prompt.read_text(encoding="utf-8").strip())
    a.actual = None
    rec = {"status": "fail", "attempts": 0, "model": a.model, "model_requested": a.model, "model_actual": NO_NUMBER, "reasoning": a.reasoning, "prompt": str(a.prompt),
           "images": a.image, "size": None, "fallback": False, "errors": []}
    if shutil.which("codex") is None:
        rec["errors"].append("không thấy codex trên PATH")
    else:
        pid_file = a.pid_file.with_name(f"{a.pid_file.stem}-{os.getpid()}{a.pid_file.suffix}")
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
        try:
            while rec["attempts"] < TRIES:
                rec["attempts"] += 1
                err, rec["fallback"], rec["size"] = attempt(a, out, result, prompt)
                if err is None:
                    rec["status"] = "ok"
                    break
                rec["errors"].append(err)
        finally:
            pid_file.unlink(missing_ok=True)
        rec["model_actual"] = a.actual or NO_NUMBER
    if rec["status"] != "ok":
        out.unlink(missing_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    if rec["attempts"]:
        record_models(out, rec["model_requested"], rec["model_actual"])
    if rec["status"] == "ok":
        print(f"[gen_image_codex] ok {rec['size'][0]}x{rec['size'][1]} lần {rec['attempts']} -> {out}")
        return
    print(f"[gen_image_codex] fail{f' {TRIES}/{TRIES}' if rec['attempts'] else ''}: {rec['errors'][-1]} -> {rec_path}")
    sys.exit(1)


if __name__ == "__main__":
    main()
