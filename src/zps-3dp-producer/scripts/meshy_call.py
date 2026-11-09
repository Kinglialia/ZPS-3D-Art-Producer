#!/usr/bin/env python3
"""The only way to call Meshy retexture (docs/producer.md §6.3, D24.2, D24.3). Runs the kit gen_api.py, unchanged.

  meshy_call.py texture --asset <id> --model <locked GLB> --style-image <png> --out <empty dir> --pid-file <f>
                [--prompt TEXT] [--dry-run] [--timeout 1500]
  meshy_call.py keys | price --model <glb> --style-image <png>

Key: `paths.env_file` of production/PROJECT-PROFILE.yaml, relative to the project folder. Every child process gets
ZPS_ART_ENV_FILE=<absolute .env> and no MESHY_API_KEY, so a key exported in the shell never replaces the project key.
Nothing here prints the key: child output is scrubbed of it before it is printed or recorded.
Budget: production/assets/<id>/texture/budget-<sha256(model)[:12]>.json in the kit format, written by the Producer
script. No budget for that mesh: refused (exit 3), so only the locked mesh can be retextured.
Failures, 3 tries in all (D8.3):
  before the task exists (no task_id in <out>/task.json, gen_api charged the budget): refund the charge, try again.
  after the task exists (wait or download failed, GLB cut off): wait again on the same task_id with gen_api wait() and
  download(); never a new task.
  the task ended FAILED, CANCELED, BANNED or EXPIRED: Meshy refunds a failed task (docs.meshy.ai), so the charge is
  refunded too; stop at once (exit 1), because a new paid task is the user's call.
  refused before any charge (no key, budget used up, <out> not empty): stop at once (exit 3).
A GLB counts only with the glTF magic and a header length equal to the file size.
Writes <out>/meshy_call.json and prints one line. Exit 0 ok, 1 after 3 failed tries (STATUS: BLOCKED), 3 refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.state import ASSETS, ROOT  # noqa: E402

GEN_API = Path(__file__).resolve().parent / "kit" / "tools" / "gen" / "gen_api.py"
TRIES = 3
REFUSED, FAILED = 3, 1
ENDED = re.compile(r"task \S+ (FAILED|CANCELED|CANCELLED|BANNED|EXPIRED)")


class Refused(Exception):
    pass


def env_file() -> Path:
    from check_profile import load_yaml
    prof = load_yaml(ROOT / "PROJECT-PROFILE.yaml") or {}
    ef = (prof.get("paths") or {}).get("env_file")
    if not ef:
        raise Refused("profile không có paths.env_file: chế độ VẼ MỚI, không gọi Meshy")
    p = Path(os.path.expanduser(ef))
    return (p if p.is_absolute() else ROOT.parent / p).resolve()


def child_env(ef: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "MESHY_API_KEY"}
    env["ZPS_ART_ENV_FILE"] = str(ef)
    return env


def secret(ef: Path) -> str | None:
    if not ef.is_file():
        return None
    for line in ef.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().removeprefix("export ").partition("=")
        if sep and k.strip() == "MESHY_API_KEY":
            return v.strip().strip("'\"") or None
    return None


def scrub(text: str, key: str | None) -> str:
    return text.replace(key, "<MESHY_API_KEY>") if key else text


def gen_api(args: list[str], ef: Path, timeout: int | None = None) -> tuple[int | None, dict]:
    try:
        r = subprocess.run([sys.executable, str(GEN_API), *args], capture_output=True, text=True, env=child_env(ef),
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, {"error": f"hết thời gian chờ {timeout} s"}
    text = scrub(r.stdout + r.stderr, secret(ef)).strip()
    try:
        out = json.loads(scrub(r.stdout, secret(ef)))
    except ValueError:
        out = {"error": text[-400:] or f"gen_api exit {r.returncode}"}
    return r.returncode, out


def keys() -> str:
    """'key file' or 'missing' for Meshy: the project .env only, the shell key is never seen."""
    rc, out = gen_api(["keys"], env_file())
    return (out.get("keys") or {}).get("meshy", "missing") if rc == 0 else "missing"


def price(model: Path, style: Path) -> int:
    rc, out = gen_api(["texture", "--provider", "meshy", "--model", str(model), "--style-image", str(style),
                       "--dry-run"], Path(os.devnull))
    if rc != 0 or not isinstance(out.get("expected_credits"), (int, float)):
        raise Refused(f"gen_api --dry-run: {out.get('error', 'không có expected_credits')}")
    return int(out["expected_credits"])


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def budget_of(aid: str, model: Path) -> Path:
    return ASSETS / aid / "texture" / f"budget-{sha256(model)[:12]}.json"


def glb_ok(p: Path) -> bool:
    try:
        head = p.read_bytes()[:12]
        return len(head) == 12 and head[:4] == b"glTF" and struct.unpack("<I", head[8:12])[0] == p.stat().st_size
    except OSError:
        return False


def task(out: Path) -> dict:
    try:
        return json.loads((out / "task.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def used(budget: Path) -> float:
    return json.loads(budget.read_text(encoding="utf-8"))["used_credits"]


def refund(budget: Path, to: float):
    b = json.loads(budget.read_text(encoding="utf-8"))
    b["used_credits"] = to
    budget.write_text(json.dumps(b, indent=2) + "\n")


def resume(out: Path):
    """In a child with the project env: wait on the task of <out>/task.json, download its GLB again."""
    sys.path.insert(0, str(GEN_API.parent))
    import gen_api as G
    rec = task(out)
    key = G.key_for("meshy") or sys.exit(json.dumps({"error": "MESHY_API_KEY is not set"}))
    try:
        t = G.wait("meshy", "retexture", rec["task_id"], key)
        url = (t.get("model_urls") or {}).get("glb") or sys.exit(json.dumps({"error": "task succeeded without a GLB"}))
        dest = out / "glb.glb"
        dest.unlink(missing_ok=True)
        rec["files"] = {"glb": G.download(url, dest)}
        rec["consumed_credits"] = t.get("consumed_credits")
    except (OSError, ValueError, KeyError) as e:
        sys.exit(json.dumps({"error": str(e)}))
    (out / "task.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps(rec))


def call(a) -> tuple[int, dict, str]:
    ef = env_file()
    budget = budget_of(a.asset, a.model)
    if not budget.is_file():
        raise Refused(f"không có {budget.name} cho mesh này: chỉ gọi Meshy trên mesh đã khóa")
    base = ["texture", "--provider", "meshy", "--model", str(a.model), "--style-image", str(a.style_image),
            *(["--prompt", a.prompt] if a.prompt else [])]
    if a.dry_run:
        rc, out = gen_api(base + ["--dry-run"], ef)
        return (0 if rc == 0 else REFUSED), {"status": "dry_run", "expected_credits": out.get("expected_credits"),
                                             "error": out.get("error")}, f"dry-run {out.get('expected_credits')} credit"
    if (a.out / "meshy_call.json").exists():
        raise Refused(f"{a.out} đã dùng cho một lần gọi trước: dùng thư mục mới")
    rec = {"status": "fail", "model": str(a.model), "budget": budget.name, "task_id": None, "glb": None, "tries": []}
    start = used(budget)
    while len(rec["tries"]) < TRIES:
        before = used(budget)
        if task(a.out).get("task_id"):
            rc, out = resume_child(a.out, ef, a.timeout)
        else:
            rc, out = gen_api(base + ["--out", str(a.out), "--budget-file", str(budget)], ef, a.timeout)
        tid = rec["task_id"] = task(a.out).get("task_id")
        if tid and glb_ok(a.out / "glb.glb"):
            rec |= {"status": "ok", "glb": str(a.out / "glb.glb")}
            break
        err = out.get("error") or ("GLB hỏng hoặc thiếu" if rc == 0 else f"gen_api exit {rc}")
        if tid and ENDED.search(err):
            refund(budget, start)
            (a.out / "task.json").rename(a.out / "task-ended.json")
            rec["tries"].append({"stage": "task_ended", "task_id": tid, "error": err, "refunded": True})
            break
        if tid:
            rec["tries"].append({"stage": "after_task", "task_id": tid, "error": err})
            continue
        charged = used(budget) - before
        if not charged:
            rec |= {"status": "refused", "error": err}
            break
        refund(budget, before)
        rec["tries"].append({"stage": "before_task", "error": err, "refunded": charged})
    rec["credits_charged"] = used(budget) - start
    rec["budget_after"] = json.loads(budget.read_text(encoding="utf-8"))
    if rec["status"] == "ok":
        return 0, rec, f"ok lần {len(rec['tries']) + 1} task {rec['task_id']} -> {rec['glb']}"
    if rec["status"] == "refused":
        return REFUSED, rec, f"từ chối: {rec['error']}"
    if rec["tries"][-1]["stage"] == "task_ended":
        return FAILED, rec, f"BLOCKED: Meshy kết thúc task {rec['task_id']}, đã hoàn budget: {rec['tries'][-1]['error']}"
    return FAILED, rec, f"BLOCKED {TRIES}/{TRIES}: {rec['tries'][-1]['error']}"


def resume_child(out: Path, ef: Path, timeout: int) -> tuple[int | None, dict]:
    try:
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_resume", "--out", str(out)],
                           capture_output=True, text=True, env=child_env(ef), timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, {"error": f"hết thời gian chờ {timeout} s"}
    text = scrub((r.stdout + r.stderr).strip(), secret(ef))
    try:
        return r.returncode, json.loads(text.splitlines()[-1])
    except (ValueError, IndexError):
        return r.returncode, {"error": text[-400:] or f"exit {r.returncode}"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("texture")
    t.add_argument("--asset", required=True)
    t.add_argument("--model", required=True, type=Path)
    t.add_argument("--style-image", required=True, type=Path)
    t.add_argument("--out", required=True, type=Path)
    t.add_argument("--pid-file", type=Path)
    t.add_argument("--prompt")
    t.add_argument("--dry-run", action="store_true")
    t.add_argument("--timeout", type=int, default=1500)
    sub.add_parser("keys")
    pr = sub.add_parser("price")
    pr.add_argument("--model", required=True, type=Path)
    pr.add_argument("--style-image", required=True, type=Path)
    sub.add_parser("_resume").add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.cmd == "_resume":
        return resume(a.out)
    try:
        if a.cmd == "keys":
            return print(f"[meshy_call] meshy: {keys()}")
        if a.cmd == "price":
            return print(f"[meshy_call] retexture: {price(a.model, a.style_image)} credit")
        a.out = a.out.resolve()
        pid = None
        if a.pid_file and not a.dry_run:
            pid = a.pid_file.with_name(f"{a.pid_file.stem}-{os.getpid()}{a.pid_file.suffix}")
            pid.parent.mkdir(parents=True, exist_ok=True)
            pid.write_text(str(os.getpid()), encoding="utf-8")
        try:
            code, rec, line = call(a)
        finally:
            if pid:
                pid.unlink(missing_ok=True)
    except Refused as ex:
        print(f"[meshy_call] từ chối: {ex}")
        sys.exit(REFUSED)
    if not a.dry_run:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "meshy_call.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[meshy_call] {line}")
    sys.exit(code)


if __name__ == "__main__":
    main()
