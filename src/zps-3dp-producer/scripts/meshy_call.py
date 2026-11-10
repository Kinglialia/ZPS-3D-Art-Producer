#!/usr/bin/env python3
"""The only way to call Meshy retexture (docs/producer.md §6.3, D24.2, D24.3, D30.3). Runs the kit gen_api.py, unchanged.

  meshy_call.py texture --asset <id> --model <locked GLB> --style-image <png> --out <empty dir> --pid-file <f>
                [--prompt TEXT] [--dry-run] [--timeout 1500]
  meshy_call.py keys | price --model <glb> --style-image <png>

Key: `paths.env_file` of production/PROJECT-PROFILE.yaml, relative to the project folder. Every child process gets
ZPS_ART_ENV_FILE=<absolute .env> and no MESHY_API_KEY, so a key exported in the shell never replaces the project key.
Nothing here prints the key: child output is scrubbed of it before it is printed or recorded.
Budget: production/assets/<id>/texture/budget-<sha256(model)[:12]>.json in the kit format, written by the Producer
script. No budget for that mesh: refused (exit 3), so only the locked mesh can be retextured.
One call per mesh at a time: budget-<sha>.lock (O_EXCL, beside the budget) is held for the whole call; a second call
is refused (exit 3).
Failures, 3 tries in all (D8.3):
  before the task exists (no task_id in <out>/task.json, gen_api charged the budget): refund the charge and try again
  only when the POST provably never reached Meshy (connection refused, DNS failure, HTTP 4xx); any other error (reset,
  timeout) may have left a paid task on Meshy: keep the charge, stop as BLOCKED, never send it again.
  after the task exists (wait or download failed, GLB cut off): wait again on the same task_id with gen_api wait() and
  download(); never a new task.
  the task ended FAILED, CANCELED, BANNED or EXPIRED: Meshy refunds a failed task (docs.meshy.ai), so the charge is
  refunded too; stop at once (exit 1), because a new paid task is the user's call.
  refused before any charge (no key, budget used up, <out> not empty): stop at once (exit 3).
Albedo (D30.3): Meshy normalizes the GLB it returns (scale x2, centre moved), so the albedo is texture_urls[0].base_color
of the task, saved as <out>/base_color.png; the kit keeps only the GLB, so a child gets the task again for that URL.
The URL is never written or printed. A download error of base_color is an after-task try on the same task_id.
Topology gate (hard, never ACCEPTED_FAIL): the Meshy GLB against --model, on triangles only, never on positions or scale:
  meshy.tris          same triangle count
  meshy.uv_triples    the 3 UVs of each triangle sorted, the set of triangles sorted, then each row equal within UV_TOL
  meshy.base_color_px base_color.png is texture_res x texture_res (asset card, default 2048)
  Written to <out>/topology.json with the sha256 of the locked GLB, the Meshy GLB and base_color.png.
An <out> of an earlier call is refused, unless its task has no GLB or no base_color yet: then the call gets them again
from that task. A GLB counts only with the glTF magic and a header length equal to the file size; an image only when its
PNG or JPEG end marker is there.
Writes <out>/meshy_call.json and prints one line. Exit 0 ok, 1 after 3 failed tries (STATUS: BLOCKED), 3 refused,
4 topology fail (the paid layer is not usable: no albedo).
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

from core.state import ASSETS, ROOT, texture_res  # noqa: E402

GEN_API = Path(__file__).resolve().parent / "kit" / "tools" / "gen" / "gen_api.py"
TRIES = 3
REFUSED, FAILED, TOPOLOGY = 3, 1, 4
UV_TOL = 1e-4
ENDED = re.compile(r"task \S+ (FAILED|CANCELED|CANCELLED|BANNED|EXPIRED)")
NOT_SENT = re.compile(r"Connection refused|nodename nor servname|Name or service not known|getaddrinfo failed|"
                      r"Temporary failure in name resolution|^HTTP 4\d\d from ")


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


def key_line_ok(ef: Path):
    lines = ef.read_text(encoding="utf-8").splitlines() if ef.is_file() else []
    if any(re.match(r"\s*export\s+MESHY_API_KEY\s*=", line) for line in lines):
        raise Refused(f"{ef.name} có `export MESHY_API_KEY=`, kit không đọc dòng đó: bỏ chữ `export ` ở đầu dòng")


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
    ef = env_file()
    key_line_ok(ef)
    rc, out = gen_api(["keys"], ef)
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


def image_ok(p: Path) -> bool:
    try:
        data = p.read_bytes()
    except OSError:
        return False
    return ((data[:8] == b"\x89PNG\r\n\x1a\n" and data[-8:] == b"IEND\xaeB`\x82")
            or (data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"))


def complete(out: Path) -> bool:
    return glb_ok(out / "glb.glb") and image_ok(out / "base_color.png")


def task(out: Path) -> dict:
    try:
        return json.loads((out / "task.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def topology(out: Path) -> dict:
    try:
        return json.loads((out / "topology.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tri_uvs(p: Path):
    """UV of the 3 corners of every triangle the scene draws, (n, 3, 2). Positions are never read."""
    import numpy as np
    data, doc, binary, off = p.read_bytes(), None, b"", 12
    while off + 8 <= len(data):
        n, kind = struct.unpack("<II", data[off:off + 8])
        if kind == 0x4E4F534A:
            doc = json.loads(data[off + 8:off + 8 + n])
        elif kind == 0x004E4942:
            binary = data[off + 8:off + 8 + n]
        off += 8 + n

    def acc(i, width):
        a = doc["accessors"][i]
        bv = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype({5121: "<u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[a["componentType"]])
        stride = bv.get("byteStride") or dt.itemsize * width
        raw = np.frombuffer(binary, np.uint8, offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0))
        rows = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * width), (stride, 1))
        return np.ascontiguousarray(rows).view(dt).reshape(a["count"], width), a

    nodes, scenes, out = doc.get("nodes", []), doc.get("scenes", []), []
    stack = list(scenes[doc.get("scene", 0)]["nodes"] if scenes else range(len(nodes)))
    while stack:
        node = nodes[stack.pop()]
        stack.extend(node.get("children", []))
        for prim in doc["meshes"][node["mesh"]]["primitives"] if "mesh" in node else []:
            if prim.get("mode", 4) != 4 or "TEXCOORD_0" not in prim["attributes"]:
                raise ValueError("primitive không phải tam giác hoặc không có TEXCOORD_0")
            uv, a = acc(prim["attributes"]["TEXCOORD_0"], 2)
            if a["componentType"] != 5126:
                raise ValueError("TEXCOORD_0 không phải float")
            idx = acc(prim["indices"], 1)[0].reshape(-1, 3) if "indices" in prim else np.arange(len(uv)).reshape(-1, 3)
            out.append(uv.astype(float)[idx])
    return np.concatenate(out) if out else np.zeros((0, 3, 2))


def uv_triples(t):
    """Triangle order and corner order removed: corners sorted inside each triangle, then the rows sorted. Sorting keys
    are the UVs rounded to UV_TOL, so float noise below the tolerance never reorders two rows."""
    import numpy as np
    q = np.round(t / UV_TOL).astype(np.int64)
    corner = np.lexsort((q[..., 1], q[..., 0]), axis=-1)[..., None]
    t, q = np.take_along_axis(t, corner, 1).reshape(-1, 6), np.take_along_axis(q, corner, 1).reshape(-1, 6)
    return t[np.lexsort(q.T[::-1])]


def check(name, ok, value, threshold, note=None) -> dict:
    return {"check": name, "status": "pass" if ok else "fail", "value": value, "threshold": threshold, "note": note}


def topology_check(locked: Path, out: Path, res: int) -> dict:
    """D30.3 hard gate. Written to <out>/topology.json."""
    import numpy as np
    from PIL import Image
    try:
        a, b = tri_uvs(locked), tri_uvs(out / "glb.glb")
    except (ValueError, KeyError, IndexError, struct.error) as ex:
        checks = [check("meshy.glb_read", False, str(ex), None)]
    else:
        checks = [check("meshy.tris", len(a) == len(b), len(b), len(a))]
        if len(a) == len(b):
            d = np.abs(uv_triples(a) - uv_triples(b)).max(axis=1) if len(a) else np.zeros(0)
            checks.append(check("meshy.uv_triples", int((d > UV_TOL).sum()) == 0, int((d > UV_TOL).sum()), 0,
                                f"tam giác lệch UV > {UV_TOL:g}; lệch lớn nhất {float(d.max(initial=0)):.3g}"))
        else:
            checks.append(check("meshy.uv_triples", False, None, 0, "số tam giác khác: không so được"))
    with Image.open(out / "base_color.png") as im:
        size = list(im.size)
    checks.append(check("meshy.base_color_px", size == [res, res], size, [res, res], "texture_res của thẻ asset"))
    r = {"tool": "meshy_call/topology", "overall": "pass" if all(c["status"] == "pass" for c in checks) else "fail",
         "hard_gate": True, "checks": checks,
         "data": {"uv_tolerance": UV_TOL, "texture_res": res, "locked_sha256": sha256(locked),
                  "glb_sha256": sha256(out / "glb.glb"), "base_color_sha256": sha256(out / "base_color.png")}}
    (out / "topology.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


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


def base_color(out: Path):
    """In a child with the project env: get the task of <out>/task.json again and download texture_urls[0].base_color.
    Prints the file, never the URL."""
    sys.path.insert(0, str(GEN_API.parent))
    import gen_api as G
    rec = task(out)
    key = G.key_for("meshy") or sys.exit(json.dumps({"error": "MESHY_API_KEY is not set"}))
    try:
        t = G.wait("meshy", "retexture", rec["task_id"], key)
        url = ((t.get("texture_urls") or [{}])[0] or {}).get("base_color") or sys.exit(
            json.dumps({"error": "task không có texture_urls[0].base_color"}))
        dest = out / "base_color.png"
        dest.unlink(missing_ok=True)
        G.download(url, dest)
    except (OSError, ValueError, KeyError) as e:
        sys.exit(json.dumps({"error": str(e)}))
    print(json.dumps({"base_color": str(dest)}))


def call(a) -> tuple[int, dict, str]:
    ef = env_file()
    key_line_ok(ef)
    budget = budget_of(a.asset, a.model)
    if not budget.is_file():
        raise Refused(f"không có {budget.name} cho mesh này: chỉ gọi Meshy trên mesh đã khóa")
    status = ASSETS / a.asset / "status.json"
    if not a.dry_run and not status.is_file():
        raise Refused(f"không có {status.name} của {a.asset}: không biết texture_res")
    base = ["texture", "--provider", "meshy", "--model", str(a.model), "--style-image", str(a.style_image),
            *(["--prompt", a.prompt] if a.prompt else [])]
    if a.dry_run:
        rc, out = gen_api(base + ["--dry-run"], ef)
        return (0 if rc == 0 else REFUSED), {"status": "dry_run", "expected_credits": out.get("expected_credits"),
                                             "error": out.get("error")}, f"dry-run {out.get('expected_credits')} credit"
    lock = budget.with_suffix(".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Refused(f"{lock.name} có: một lần gọi Meshy khác đang chạy trên mesh này (pid "
                      f"{lock.read_text(encoding='utf-8').strip()}); chờ nó xong, hoặc xóa file đó khi không còn "
                      "process này") from None
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        return paid_call(a, ef, budget, base)
    finally:
        lock.unlink(missing_ok=True)


def paid_call(a, ef: Path, budget: Path, base: list[str]) -> tuple[int, dict, str]:
    if (a.out / "meshy_call.json").exists() and not (task(a.out).get("task_id") and not complete(a.out)):
        raise Refused(f"{a.out} đã dùng cho một lần gọi trước: dùng thư mục mới")
    res = texture_res(json.loads((ASSETS / a.asset / "status.json").read_text(encoding="utf-8")))
    rec = {"status": "fail", "model": str(a.model), "budget": budget.name, "task_id": None, "glb": None,
           "albedo": None, "tries": []}
    start = used(budget)
    glb = a.out / "glb.glb"
    while len(rec["tries"]) < TRIES:
        before = used(budget)
        if task(a.out).get("task_id") and glb_ok(glb):
            rc, out = child("_base_color", a.out, ef, a.timeout)
        elif task(a.out).get("task_id"):
            rc, out = child("_resume", a.out, ef, a.timeout)
        else:
            rc, out = gen_api(base + ["--out", str(a.out), "--budget-file", str(budget)], ef, a.timeout)
        tid = rec["task_id"] = task(a.out).get("task_id")
        if tid and glb_ok(glb) and not image_ok(a.out / "base_color.png") and not out.get("error"):
            rc, out = child("_base_color", a.out, ef, a.timeout)
        if tid and complete(a.out):
            rec |= {"status": "ok", "glb": str(glb)}
            break
        err = out.get("error") or (f"gen_api exit {rc}" if rc else "GLB hỏng hoặc thiếu" if not glb_ok(glb)
                                   else "base_color hỏng hoặc thiếu")
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
        if not NOT_SENT.search(err):
            rec["tries"].append({"stage": "maybe_sent", "error": err, "refunded": 0})
            break
        refund(budget, before)
        rec["tries"].append({"stage": "before_task", "error": err, "refunded": charged})
    rec["credits_charged"] = used(budget) - start
    rec["budget_after"] = json.loads(budget.read_text(encoding="utf-8"))
    if rec["status"] == "ok":
        topo = topology_check(a.model, a.out, res)
        rec["topology"] = topo["overall"]
        if topo["overall"] == "fail":
            rec["status"] = "topology_fail"
            bad = ", ".join(c["check"] for c in topo["checks"] if c["status"] == "fail")
            return TOPOLOGY, rec, (f"topology fail ({bad}) task {rec['task_id']}: không dùng lớp Meshy này, đã tốn "
                                   f"{rec['credits_charged']:g} credit -> {a.out / 'topology.json'}")
        rec["albedo"] = str(a.out / "base_color.png")
        return 0, rec, f"ok lần {len(rec['tries']) + 1} task {rec['task_id']}, topology pass -> {rec['albedo']}"
    if rec["status"] == "refused":
        return REFUSED, rec, f"từ chối: {rec['error']}"
    if rec["tries"][-1]["stage"] == "maybe_sent":
        return FAILED, rec, (f"BLOCKED: POST có thể đã tới Meshy ({rec['tries'][-1]['error']}): giữ "
                             f"{rec['credits_charged']:g} credit, không gửi lại; xem task trên Meshy trước khi gọi tiếp")
    if rec["tries"][-1]["stage"] == "task_ended":
        return FAILED, rec, f"BLOCKED: Meshy kết thúc task {rec['task_id']}, đã hoàn budget: {rec['tries'][-1]['error']}"
    return FAILED, rec, f"BLOCKED {TRIES}/{TRIES}: {rec['tries'][-1]['error']}"


def child(cmd: str, out: Path, ef: Path, timeout: int) -> tuple[int | None, dict]:
    try:
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()), cmd, "--out", str(out)],
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
    sub.add_parser("_base_color").add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.cmd == "_resume":
        return resume(a.out)
    if a.cmd == "_base_color":
        return base_color(a.out)
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
