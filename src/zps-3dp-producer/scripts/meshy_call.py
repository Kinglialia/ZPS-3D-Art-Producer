#!/usr/bin/env python3
"""The only way to call Meshy retexture (docs/producer.md §6.3, D24.2, D24.3, D30.3). Runs the kit gen_api.py, unchanged.

  meshy_call.py texture --asset <id> --model <locked GLB> --style-image <png> --out <empty dir> --pid-file <f>
                [--prompt TEXT] [--dry-run] [--timeout 1700] [--resume] [--total-s 1800]
  meshy_call.py keys | price --model <glb> --style-image <png>

Key: `paths.env_file` of production/PROJECT-PROFILE.yaml, relative to the project folder. Every child process gets
ZPS_ART_ENV_FILE=<absolute .env> and no MESHY_API_KEY, so a key exported in the shell never replaces the project key.
Nothing here prints the key: child output is scrubbed of it before it is printed or recorded.
Budget: production/assets/<id>/texture/budget-<sha256(model)[:12]>.json in the kit format, written by the Producer
script. No budget for that mesh: refused (exit 3), so only the locked mesh can be retextured.
One call per mesh at a time: budget-<sha>.lock (O_EXCL, beside the budget, holds the pid) is held for the whole call; a
second call is refused (exit 3). A lock whose pid is not alive is left by a killed call: it is taken over.
Failures, 3 tries in all (D8.3):
  before the task exists (no task_id in <out>/task.json, gen_api charged the budget): refund the charge and try again
  only when the POST provably never reached Meshy (connection refused, DNS failure, HTTP 4xx); any other error (reset,
  timeout) may have left a paid task on Meshy: keep the charge, stop as BLOCKED, never send it again.
  after the task exists (wait or download failed, GLB cut off): wait again on the same task_id with gen_api wait() and
  download(); never a new task.
  the task ended FAILED, CANCELED, BANNED or EXPIRED: Meshy refunds a failed task (docs.meshy.ai), so the charge is
  refunded too; stop at once (exit 1), because a new paid task is the user's call. The refund is the credit charged at
  the POST (expected_credits of task.json, written by the kit at that moment), also on a --resume run, when the budget
  already holds the charge of the first run.
  refused before any charge (no key, budget used up, <out> not empty): stop at once (exit 3).
Albedo (D30.3): Meshy normalizes the GLB it returns (scale x2, centre moved), so the albedo is texture_urls[0].base_color
of the task, saved as <out>/base_color.png; the kit keeps only the GLB, so a child gets the task again for that URL.
The URL is never written or printed. A download error of base_color is an after-task try on the same task_id.
Topology gate (hard, never ACCEPTED_FAIL): the Meshy GLB against --model, on triangles only, never on positions or scale:
  meshy.tris          same triangle count
  meshy.uv_triples    the multiset of per-triangle UV triples (corner order removed) equal, each UV within UV_TOL
  meshy.base_color_px base_color.png is square and at least texture_res (asset card, default 2048)
  The request asks Meshy for texture_resolution = the smallest of 2k, 4k, 8k at or above texture_res (the kit has no
  flag for it: a child imports the kit unchanged and adds the field to the retexture body). When every check passes and
  base_color is larger, it is downscaled to exactly texture_res with an area filter (Pillow BOX); topology.json and the
  ledger record both sizes.
  Written to <out>/topology.json (data.hard_gate: true) with the sha256 of the locked GLB, the Meshy GLB and base_color.png.
An <out> of an earlier call is refused, unless its task has no GLB or no base_color yet (then the call gets them again
from that task), or both files are there and topology.json is missing (then only the topology gate runs: no request, no
charge). A GLB counts only with the glTF magic and a header length equal to the file size; an image only when its
PNG or JPEG end marker is there.
Pending (D33.5): --timeout is the wait of one run (default 1700 s). When it runs out after the task
exists, the run exits 5 with status `pending` (not an error, not a try); task_id stays in <out>/task.json. Run it again
with --resume and the same --out: it waits on that task only, never sends a new task, never charges again. --resume
without a task_id in <out>/task.json is refused. Past --total-s (default 1800) since the first run of <out>: one status
request, no wait. SUCCEEDED, or ended: the run goes on as above (download, or refund). Still running: BLOCKED
(`blocked_total`), no new task, no charge.
Writes <out>/meshy_call.json and prints one line. Exit 0 ok, 1 after 3 failed tries or past --total-s (STATUS:
BLOCKED), 3 refused, 4 topology fail (the paid layer is not usable: no albedo), 5 pending.
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
import time
from pathlib import Path

import heartbeat

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.limits import alive  # noqa: E402
from core.state import ASSETS, ROOT, ledger, texture_res  # noqa: E402
from root_guard import require_root  # noqa: E402

GEN_API = Path(__file__).resolve().parent / "kit" / "tools" / "gen" / "gen_api.py"
TRIES = 3
REFUSED, FAILED, TOPOLOGY, PENDING = 3, 1, 4, 5
UV_TOL = 1e-4
MESHY_RES = {"2k": 2048, "4k": 4096, "8k": 8192}


def meshy_resolution(res: int) -> str:
    """The smallest Meshy texture_resolution at or above texture_res (docs.meshy.ai/api/retexture)."""
    for name, px in MESHY_RES.items():
        if px >= res:
            return name
    raise Refused(f"texture_res {res} lớn hơn 8k, mức lớn nhất của Meshy retexture: chọn VẼ MỚI")
ENDED_STATUS = ("FAILED", "CANCELED", "CANCELLED", "BANNED", "EXPIRED")
ENDED = re.compile(rf"task \S+ ({'|'.join(ENDED_STATUS)})")
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


def gen_api(args: list[str], ef: Path, timeout: int | None = None,
            texture_resolution: str | None = None) -> tuple[int | None, dict]:
    cmd = ([str(Path(__file__).resolve()), "_kit", texture_resolution] if texture_resolution else [str(GEN_API)])
    try:
        r = heartbeat.run([sys.executable, *cmd, *args], tool="meshy gen_api", vd=heartbeat.vdir_of(*args), env=child_env(ef),
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


def uv_triples(locked, meshy) -> tuple[int, float]:
    """Triangles of `meshy` whose sorted UV triple is not in the multiset of sorted UV triples of `locked`, and the
    largest snap distance. Each Meshy corner snaps to the nearest locked UV within UV_TOL (max of |du|, |dv|); a corner
    with none matches nothing. Then the triples are compared exactly, so triangle and corner order never count and
    float noise below UV_TOL never moves a triangle to another row."""
    import numpy as np
    from collections import Counter
    pts, ids = np.unique(locked.reshape(-1, 2), axis=0, return_inverse=True)
    grid = {}
    for i, c in enumerate(map(tuple, np.floor(pts / UV_TOL).astype(np.int64))):
        grid.setdefault(c, []).append(i)
    snap, worst = np.full(len(meshy) * 3, -1), 0.0
    for k, (uv, c) in enumerate(zip(meshy.reshape(-1, 2), np.floor(meshy.reshape(-1, 2) / UV_TOL).astype(np.int64))):
        near = [i for du in (-1, 0, 1) for dv in (-1, 0, 1) for i in grid.get((c[0] + du, c[1] + dv), [])]
        if near:
            d = np.abs(pts[near] - uv).max(axis=1)
            j = int(d.argmin())
            if d[j] <= UV_TOL:
                snap[k], worst = near[j], max(worst, float(d[j]))
    want = Counter(map(tuple, np.sort(ids.reshape(-1, 3), axis=1)))
    got = Counter(map(tuple, np.sort(snap.reshape(-1, 3), axis=1)))
    return sum((got - want).values()), worst


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
            bad, worst = uv_triples(a, b)
            checks.append(check("meshy.uv_triples", bad == 0, bad, 0,
                                f"tam giác có UV lệch > {UV_TOL:g}; lệch lớn nhất trong dung sai {worst:.3g}"))
        else:
            checks.append(check("meshy.uv_triples", False, None, 0, "số tam giác khác: không so được"))
    base = out / "base_color.png"
    with Image.open(base) as im:
        size = list(im.size)
    checks.append(check("meshy.base_color_px", size[0] == size[1] >= res, size, [res, res],
                        "vuông và không nhỏ hơn texture_res của thẻ asset; lớn hơn thì thu về texture_res"))
    ok = all(c["status"] == "pass" for c in checks)
    if ok and size != [res, res]:
        with Image.open(base) as im:
            im.load()
            small = im.resize((res, res), Image.Resampling.BOX)
        small.save(base)
    r = {"tool": "meshy_call/topology", "overall": "pass" if ok else "fail", "checks": checks,
         "data": {"hard_gate": True, "uv_tolerance": UV_TOL, "texture_res": res, "base_color_px_meshy": size,
                  "base_color_px": [res, res] if ok else size, "locked_sha256": sha256(locked),
                  "glb_sha256": sha256(out / "glb.glb"), "base_color_sha256": sha256(base)}}
    (out / "topology.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def used(budget: Path) -> float:
    return json.loads(budget.read_text(encoding="utf-8"))["used_credits"]


def refund(budget: Path, to: float):
    b = json.loads(budget.read_text(encoding="utf-8"))
    b["used_credits"] = to
    budget.write_text(json.dumps(b, indent=2) + "\n")


def kit(texture_resolution: str, argv: list[str]):
    """In a child: run the kit gen_api.py unchanged, with texture_resolution added to the Meshy retexture body."""
    sys.path.insert(0, str(GEN_API.parent))
    import gen_api as G
    plan = G.plan

    def with_resolution(a):
        steps, kind = plan(a)
        if a.provider == "meshy" and a.op == "texture":
            steps = [(m, u, {**b, "texture_resolution": texture_resolution} if m == "POST" else b) for m, u, b in steps]
        return steps, kind
    G.plan = with_resolution
    sys.argv = [str(GEN_API), *argv]
    sys.exit(G.main())


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


def status(out: Path):
    """In a child with the project env: one GET of the task of <out>/task.json, no wait. Prints the status only."""
    sys.path.insert(0, str(GEN_API.parent))
    import gen_api as G
    key = G.key_for("meshy") or sys.exit(json.dumps({"error": "MESHY_API_KEY is not set"}))
    try:
        t = G.http("GET", f"{G.MESHY}/retexture/{task(out)['task_id']}", key)
    except (OSError, ValueError, KeyError) as e:
        sys.exit(json.dumps({"error": str(e)}))
    print(json.dumps({"status": str(t.get("status", "")).upper()}))


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
    a.res = texture_res(json.loads(status.read_text(encoding="utf-8"))) if status.is_file() else texture_res({})
    a.meshy_res = meshy_resolution(a.res)
    base = ["texture", "--provider", "meshy", "--model", str(a.model), "--style-image", str(a.style_image),
            *(["--prompt", a.prompt] if a.prompt else [])]
    if a.dry_run:
        rc, out = gen_api(base + ["--dry-run"], ef, texture_resolution=a.meshy_res)
        return (0 if rc == 0 else REFUSED), {"status": "dry_run", "expected_credits": out.get("expected_credits"),
                                             "error": out.get("error")}, f"dry-run {out.get('expected_credits')} credit"
    lock = budget.with_suffix(".lock")
    take_lock(lock)
    try:
        return paid_call(a, ef, budget, base)
    finally:
        lock.unlink(missing_ok=True)


def lock_pid(lock: Path) -> int | None:
    try:
        return int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def take_lock(lock: Path):
    """O_EXCL create with our pid. A lock of a dead pid is deleted once and taken again; an empty or unreadable one may be
    a call that is starting, so it stays a refusal."""
    for attempt in (0, 1):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = lock_pid(lock)
            if attempt == 0 and holder is not None and not alive(holder):
                lock.unlink(missing_ok=True)
                continue
            who = lock.read_text(encoding="utf-8").strip() if lock.is_file() else "?"
            raise Refused(f"{lock.name} có: một lần gọi Meshy khác đang chạy trên mesh này (pid {who}); chờ nó xong, "
                          "hoặc xóa file đó khi không còn process này") from None
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return


def earlier(out: Path) -> dict:
    try:
        return json.loads((out / "meshy_call.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def paid_call(a, ef: Path, budget: Path, base: list[str]) -> tuple[int, dict, str]:
    tid0 = task(a.out).get("task_id")
    gate_only = bool(tid0) and complete(a.out) and not topology(a.out)
    if (a.out / "meshy_call.json").exists() and not (tid0 and not complete(a.out)) and not gate_only:
        raise Refused(f"{a.out} đã dùng cho một lần gọi trước: dùng thư mục mới")
    if a.resume and not task(a.out).get("task_id"):
        raise Refused(f"--resume: {a.out / 'task.json'} không có task_id; không tạo task mới khi resume")
    res = a.res
    started = earlier(a.out).get("started") or time.time()
    rec = {"status": "fail", "model": str(a.model), "budget": budget.name, "task_id": None, "glb": None,
           "albedo": None, "tries": [], "started": started}
    if gate_only:
        rec |= {"task_id": tid0, "status": "ok", "glb": str(a.out / "glb.glb")}
    elif tid0 and time.time() - started > a.total_s:
        _, seen = child("_status", a.out, ef, a.timeout)
        if seen.get("status") not in ("SUCCEEDED", *ENDED_STATUS):
            rec |= {"task_id": tid0, "status": "blocked_total"}
            rec["credits_charged"], rec["budget_after"] = 0, json.loads(budget.read_text(encoding="utf-8"))
            return FAILED, rec, (f"BLOCKED: task {tid0} chưa xong sau {a.total_s} s tính từ lần chạy đầu "
                                 f"(trạng thái hỏi một lần: {seen.get('status') or 'không hỏi được'}); không chờ "
                                 "thêm, không gửi task mới")
    start = used(budget)
    glb = a.out / "glb.glb"
    while rec["status"] != "ok" and len(rec["tries"]) < TRIES:
        before = used(budget)
        if task(a.out).get("task_id") and glb_ok(glb):
            rc, out = child("_base_color", a.out, ef, a.timeout)
        elif task(a.out).get("task_id"):
            rc, out = child("_resume", a.out, ef, a.timeout)
        else:
            rc, out = gen_api(base + ["--out", str(a.out), "--budget-file", str(budget)], ef, a.timeout,
                              a.meshy_res)
        tid = rec["task_id"] = task(a.out).get("task_id")
        if tid and rc is None and not complete(a.out):
            rec["status"] = "pending"
            rec["credits_charged"] = used(budget) - start
            rec["budget_after"] = json.loads(budget.read_text(encoding="utf-8"))
            return PENDING, rec, (f"pending: task {tid} chưa xong sau {a.timeout} s; chạy lại cùng lệnh với --resume "
                                  "(không tạo task mới, không tốn thêm credit)")
        if tid and glb_ok(glb) and not image_ok(a.out / "base_color.png") and not out.get("error"):
            rc, out = child("_base_color", a.out, ef, a.timeout)
        if tid and complete(a.out):
            rec |= {"status": "ok", "glb": str(glb)}
            break
        err = out.get("error") or (f"gen_api exit {rc}" if rc else "GLB hỏng hoặc thiếu" if not glb_ok(glb)
                                   else "base_color hỏng hoặc thiếu")
        if tid and ENDED.search(err):
            paid = task(a.out).get("expected_credits")
            if not isinstance(paid, (int, float)):
                paid = used(budget) - start
            refund(budget, max(used(budget) - paid, 0))
            start = used(budget)
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
        d = topo["data"]
        if d["base_color_px_meshy"] != d["base_color_px"]:
            (w, h), n = d["base_color_px_meshy"], res
            ledger(f"{a.asset} · texture · Meshy base_color {w}x{h} → {n}x{n} (BOX, texture_res) · {a.out.name}")
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
        r = heartbeat.run([sys.executable, str(Path(__file__).resolve()), cmd, "--out", str(out)], tool=f"meshy {cmd}",
                          vd=heartbeat.vdir_of(out), env=child_env(ef), timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, {"error": f"hết thời gian chờ {timeout} s"}
    text = scrub((r.stdout + r.stderr).strip(), secret(ef))
    try:
        return r.returncode, json.loads(text.splitlines()[-1])
    except (ValueError, IndexError):
        return r.returncode, {"error": text[-400:] or f"exit {r.returncode}"}


def main():
    if sys.argv[1:2] == ["_kit"]:
        return kit(sys.argv[2], sys.argv[3:])
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
    t.add_argument("--timeout", type=int, default=1700, help="seconds one run waits for the task (default: %(default)s)")
    t.add_argument("--resume", action="store_true")
    t.add_argument("--total-s", type=int, default=1800)
    sub.add_parser("keys")
    pr = sub.add_parser("price")
    pr.add_argument("--model", required=True, type=Path)
    pr.add_argument("--style-image", required=True, type=Path)
    sub.add_parser("_resume").add_argument("--out", required=True, type=Path)
    sub.add_parser("_base_color").add_argument("--out", required=True, type=Path)
    sub.add_parser("_status").add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.cmd == "_resume":
        return resume(a.out)
    if a.cmd == "_base_color":
        return base_color(a.out)
    if a.cmd == "_status":
        return status(a.out)
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
    require_root()
    main()
