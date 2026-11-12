#!/usr/bin/env python3
"""Step `assemble`, a script with no agent (docs/producer.md §6.4, D22.11, D24.4). `P brief` prints this command.

Usage: assemble.py --blender <BLENDER> -- <id> <N> <profile hash>
Reads the approved `model` and `texture` versions of status.json and writes assemble/vN/ only:
  1 sha256 of model final/<id>-untextured.glb = locked.model; albedo_<texture_res>.png is res x res, and its sha256 equals
    albedo_sha256 of the texture step's renders.json when that key is there (T2).
  2 one Blender session, assemble_qa.py (D37.4): assemble_glb.build writes final/model/<id>.glb (1 mesh, 1 node, 1 material,
    unlit, base colour) and <id>.blend; then kit QA on a byte copy of that GLB in work/qa_input/ (the validator writes
    beside its input), results in work/evidence/qa/: mesh_check, uv_check, export_check (expect_unlit), screen_tris_check;
    then the GLB rendered again with the texture step's recorded cameras (unlit_34_front, unlit_game), only the views its
    renders.json has, in work/compare/. The outcome of each stage is in work/evidence/session.json.
  3 kit finalize.py over work/: refuses unless every QA result for this GLB's sha256 passes and mesh_check is there.
     Finalize skips a check with no result, so any of the four not pass or info, missing included, is a fail too.
  4 the render compared with the texture renders: mean |RGB| difference over the object ≤ COMPARE_MEAN, silhouette
    mismatch ≤ COMPARE_MASK. A view that renders.json lacks is not compared; the README says it was not checked (T1).
  5 package: texture/ (albedo, notes.md), review/ (model_sheet.png, the texture renders, final_lit_vs_concept.png,
    compare_<view>.png, compare.json, the texture reviewer report).
  6 README.md from the step reports: status line, method, exceptions, open work, what was not checked.
Writes report-script.md: worker contract lines, then each fail point as a finding (board). Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import findings  # noqa: E402
from core.contract import unwrap  # noqa: E402
import heartbeat  # noqa: E402
from core.state import ROOT, SKILL_DIR, load_st, now, texture_res, vdir  # noqa: E402
from root_guard import require_root  # noqa: E402

SCRIPTS = SKILL_DIR / "scripts"
FINALIZE = SCRIPTS / "kit" / "tools" / "finalize.py"
QA = ("mesh_check", "uv_check", "export_check", "screen_tris_check")
COMPARE = ("unlit_34_front", "unlit_game")
COMPARE_MEAN = 6.0
COMPARE_MASK = 0.02
OPEN_KINDS = ("minor", "major", "blocker", "unclear")
STEPS = ("blockout", "views", "model", "texture")


class Fail(Exception):
    pass


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


BLENDER_TIMEOUT_S = 1800  # D33.3: the one Blender session and finalize.py together stay under BASH_MAX_TIMEOUT_MS 3600000
FINALIZE_TIMEOUT_S = 300


def blender(exe: str, script: Path, vd: Path, *args) -> tuple[int, str]:
    try:
        r = heartbeat.run([exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script), "--",
                           *map(str, args)], tool=f"blender {script.stem}", vd=vd,
                          timeout=BLENDER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 1, f"Blender quá {BLENDER_TIMEOUT_S} s: {script.name}"
    if heartbeat.sandbox_crash(r):
        print(heartbeat.SANDBOX_HELP.format(cmd=shlex.join([sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]])),
              file=sys.stderr)
        raise Fail("Blender chết trong sandbox của Codex: chạy lại đúng dòng lệnh in ở stderr")
    return r.returncode, r.stdout + r.stderr


def fail_point(kind: str, region: str, evidence: str, consequence: str, repair: str, acceptance: str) -> dict:
    return {"priority": "blocker", "kind": kind, "region": region, "viewing_condition": "assemble.py",
            "evidence": evidence, "consequence": consequence, "confidence": "high", "repair": repair,
            "preserve": "mesh đã khóa ở DUYỆT 1", "acceptance": acceptance}


def compare(ref: Path, got: Path, side: Path) -> dict:
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(ref).convert("RGBA"), float)
    b = np.asarray(Image.open(got).convert("RGBA"), float)
    if a.shape != b.shape:
        return {"mean_abs": None, "mask_mismatch": 1.0, "note": f"cỡ ảnh {a.shape[:2]} ≠ {b.shape[:2]}"}
    ma, mb = a[..., 3] > 127, b[..., 3] > 127
    both, union = ma & mb, ma | mb
    diff = np.abs(a[..., :3] - b[..., :3]).mean(-1)
    out = {"mean_abs": round(float(diff[both].mean()), 2) if both.any() else None,
           "mask_mismatch": round(float((ma ^ mb).sum() / max(union.sum(), 1)), 4)}
    vis = np.zeros(a.shape[:2] + (3,), np.uint8)
    vis[both] = np.clip(diff[both, None] * 8, 0, 255).astype(np.uint8)
    vis[ma ^ mb] = (255, 0, 255)
    strip = [Image.fromarray(x[..., :3].astype(np.uint8)) for x in (a, b)] + [Image.fromarray(vis)]
    canvas = Image.new("RGB", (sum(s.width for s in strip), strip[0].height), (255, 255, 255))
    x = 0
    for s in strip:
        canvas.paste(s, (x, 0))
        x += s.width
    canvas.save(side)
    return out


def recorded_views(renders: Path) -> list[str]:
    """The compare views the texture step rendered. A spec with no camera has no `unlit_game` (T1)."""
    doc = json.loads(renders.read_text(encoding="utf-8")) if renders.is_file() else {}
    return [v for v in COMPARE if v in doc.get("renders", {})]


def compare_renders(tf: Path, work: Path, final: Path, views: list[str], rendered: bool, why) -> tuple[list[dict], dict]:
    fails, results = [], {}
    if not views:
        fails.append(fail_point("compare", "renders.json", "work/evidence: renders.json không có view nào để so",
                                "không so được GLB với render bước texture", "làm lại texture để có render unlit",
                                f"renders.json có {' hoặc '.join(COMPARE)}"))
    for view in views:
        got = work / "compare" / f"{view}.png"
        if not rendered or not got.is_file():
            fails.append(fail_point("compare", view, f"work/evidence: render GLB lỗi {why}",
                                    "không so được GLB với render bước texture", "đọc lỗi Blender", f"có {view}.png"))
            continue
        c = results[view] = compare(tf / "review" / f"{view}.png", got,
                                    final / "review" / f"compare_{view.removeprefix('unlit_')}.png")
        if c["mean_abs"] is None or c["mean_abs"] > COMPARE_MEAN or c["mask_mismatch"] > COMPARE_MASK:
            fails.append(fail_point(
                "compare", view, f"work/evidence/compare.json: mean_abs {c['mean_abs']}, mask {c['mask_mismatch']}",
                "GLB trong engine khác render bước texture (color space, alpha, unlit)",
                "kiểm color space, alpha và material của albedo trước khi vẽ lại",
                f"mean_abs ≤ {COMPARE_MEAN:g} và mask ≤ {COMPARE_MASK:g} ở {view}"))
    return fails, results


def section(path: Path, key: str) -> list[str]:
    """Lines under the first heading that names key, up to the next heading."""
    if not path.is_file():
        return []
    out, on = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            if on:
                break
            on = key.lower() in line.lower()
            continue
        if on and line.strip():
            out.append(line.rstrip())
    return out


def open_work(st: dict) -> list[str]:
    """§6.4.6, D25.H, D27.8: findings still open in the approved version of every step, the user's H<n> first. A note
    of an earlier step leaves the list once the reviewer of a later approved version confirmed the worker did it."""
    docs = {sid: findings.load(st["id"], sid, st["approved"].get(sid)) for sid in STEPS}
    done = {x for d in docs.values() for x in (d or {}).get("resolved_notes", [])}
    rows = []
    for sid in STEPS:
        n = st["approved"].get(sid)
        for i, f in findings.open_of(docs[sid]).items():
            if f["priority"] in OPEN_KINDS and f"{sid} v{n} {i}" not in done:
                rows.append((not i.startswith("H"), f"- {sid} v{n} {i} [{f['priority']}] {f['region']}: {f['repair']}"))
    return [r for _, r in sorted(rows, key=lambda r: r[0])]


def waived(st: dict, by: str, tag: str = "") -> list[str]:
    """D30.1: findings waived in the approved version of every step, by the user or by the Producer (test_mode)."""
    rows = []
    for sid in STEPS:
        n = st["approved"].get(sid)
        for i, f in findings.waived_of(findings.load(st["id"], sid, n)).items():
            if f["waived"]["by"] == by:
                rows.append(f"- {sid} v{n} {i} [{f['priority']}] {f['region']}: {tag}{f['waived']['why']}")
    return rows


def card_notes(st: dict) -> list[str]:
    """Card `views: none` (D35): no views README, so the texture_only notes of the card stand for its TEXTURE NOTE."""
    from core import asset_card
    if asset_card.views(st) != "none":
        return []
    import yaml
    c = yaml.safe_load((Path(st["concept_dir"]) / "asset-card.yaml").read_text(encoding="utf-8")) or {}
    return [f"- thẻ: {n}" for n in map(str, c.get("real_texture_only_notes") or []) if n.lower().startswith("texture_only")]


def exceptions(st: dict) -> list[str]:
    """README "Ngoại lệ": views exceptions and texture notes (card notes with `views: none`), blockout decisions,
    user waives (D30.1), and the NGOẠI LỆ section of every other step's README, where a worker writes its ACCEPTED_FAIL
    (D31.3)."""
    return [*section(vdir(st["id"], "views", st["approved"].get("views", 0)) / "final" / "README.md", "NGOẠI LỆ"),
            *section(vdir(st["id"], "views", st["approved"].get("views", 0)) / "final" / "README.md", "TEXTURE NOTE"),
            *card_notes(st),
            *section(vdir(st["id"], "blockout", st["approved"].get("blockout", 0)) / "final" / "blockout.md", "Blockout tự quyết"),
            *waived(st, "user", "người dùng waive: "),
            *(f"- {sid}: {x.lstrip('- ')}" for sid in ("blockout", "model", "texture")
              for x in section(vdir(st["id"], sid, st["approved"].get(sid, 0)) / "final" / "README.md", "NGOẠI LỆ"))]


def meshy_spend(st: dict) -> tuple[int, float]:
    price = st.get("meshy_price") or 10
    used = sum(json.loads(p.read_text(encoding="utf-8"))["used_credits"]
               for p in (ROOT / "assets" / st["id"] / "texture").glob("budget-*.json"))
    return int(used // price), used


def readme(st, mv, tv, mf, tf, res, qa, data) -> str:
    spec = json.loads((tf / "texture_spec.json").read_text(encoding="utf-8")) if (tf / "texture_spec.json").is_file() else {}
    calls, credits = meshy_spend(st)
    small = next((c.get("value") for c in qa.get("screen_tris_check", {}).get("checks", [])
                  if c.get("check") == "screen.small_tri_ratio"), None)
    exc = exceptions(st)
    work = open_work(st)
    cam = json.loads((mf / "spec.json").read_text(encoding="utf-8")).get("camera") or {}
    return "\n".join([
        f"Trạng thái: chờ DUYỆT 2 · {now()}", "", f"# {st['title']} (`{st['id']}`)", "", "## Cách làm",
        f"- Model v{mv}, mesh đã khóa sha256 `{st['locked']['model'][:12]}`, {data.get('tris')} tris.",
        f"- Texture v{tv}: chế độ {spec.get('used', '?')} (đề xuất {spec.get('proposed', '?')}); "
        f"Meshy {calls} lần gọi, {credits:g} credit (file budget).",
        f"- `model/{st['id']}.glb`: 1 mesh, 1 node, 1 material, unlit, base color `texture/albedo_{res}.png`.",
        "- Trong engine: material unlit, chỉ base color.", "", "## Ngoại lệ", *(exc or ["- không có"]), "",
        "## Việc còn mở", *(work or ["- không có"]), "",
        *(["## Producer đã waive", *by_producer, ""] if (by_producer := waived(st, "producer")) else []), "## Chưa kiểm",
        "- Engine: ảnh render bằng Blender (Workbench), chưa mở trong engine.",
        f"- Camera game: {'chưa chốt (spec không có distance_m)' if not cam.get('distance_m') else 'đã chốt'}.",
        *(f"- {v.removeprefix('unlit_')} view chưa kiểm: bước texture không render {v}"
          f"{' (spec không có camera)' if v == 'unlit_game' else ''}." for v in data["skipped_views"]),
        f"- Tam giác nhỏ ở camera game: {small if small is not None else 'not_checked'} (screen_tris_check, chỉ cảnh báo).",
        ""])


def run(a, d: Path) -> tuple[list[dict], dict]:
    st = load_st(a.id)
    fails, data = [], {}
    mv, tv = st["approved"].get("model"), st["approved"].get("texture")
    if not (mv and tv):
        raise Fail(f"cần model và texture đã duyệt (model={mv}, texture={tv})")
    mf, tf = vdir(a.id, "model", mv) / "final", vdir(a.id, "texture", tv) / "final"
    final, work = d / "final", d / "work"
    res = texture_res(st)
    locked = mf / f"{a.id}-untextured.glb"
    if not locked.is_file() or sha256(locked) != (st.get("locked") or {}).get("model"):
        return [fail_point("hash", "mesh", f"work/evidence: sha256 {locked.name} khác locked.model",
                           "mesh không phải mesh đã duyệt ở DUYỆT 1", "duyệt lại model (`redo --step model`)",
                           "sha256 bằng locked.model")], data
    albedo = tf / f"albedo_{res}.png"
    from PIL import Image
    size = Image.open(albedo).size if albedo.is_file() else None
    if size != (res, res):
        return [fail_point("albedo", "texture", f"work/evidence: {albedo.name} cỡ {size}", f"texture_res của thẻ là {res}",
                           "làm lại texture đúng texture_res (`redo --step texture`)", f"albedo {res}x{res}")], data
    renders = tf / "review" / "renders.json"
    want = json.loads(renders.read_text(encoding="utf-8")).get("albedo_sha256") if renders.is_file() else None
    if want and sha256(albedo) != want:
        return [fail_point("albedo", "texture", f"work/evidence: {albedo.name} đã đổi sau lần render của bước texture "
                           "(sha256 khác renders.json)", "gói cuối mang texture chưa ai xem trên render",
                           "render lại texture (`redo --step texture`)", "sha256 albedo bằng albedo_sha256 của renders.json")], data
    glb = final / "model" / f"{a.id}.glb"
    probe = work / "qa_input" / glb.name
    views = recorded_views(renders)
    data["skipped_views"] = [v for v in COMPARE if v not in views]
    session = work / "evidence" / "session.json"
    _, out = blender(a.blender, SCRIPTS / "assemble_qa.py", d, "--glb", locked, "--albedo", albedo, "--name", a.id,
                      "--out", final / "model", "--probe", probe, "--spec", mf / "spec.json", "--qa-spec", work / "spec.json",
                      "--checks", ",".join(QA), "--qa-dir", work / "evidence" / "qa", "--result", session,
                      *(["--cameras", renders, "--views", ",".join(views), "--outdir", work / "compare"] if views else []))
    done = json.loads(session.read_text(encoding="utf-8")) if session.is_file() else {}
    if "export" not in done or not glb.is_file():
        return [fail_point("export", "GLB", f"work/evidence: assemble_qa {out.strip().splitlines()[-1:]}",
                           "không có GLB cuối", "đọc lỗi Blender, chạy lại (`retry`)", "có final/model/<id>.glb")], data
    data |= done["export"]
    qa = {}
    for q in QA:
        dst = work / "evidence" / "qa" / f"{q}.json"
        qa[q] = json.loads(dst.read_text(encoding="utf-8")) if dst.is_file() else {"overall": "missing", "checks": []}
    r = subprocess.run([sys.executable, str(FINALIZE), "--work", str(work), "--from", str(glb), "--out",
                        str(work / "evidence" / "finalize.json")], capture_output=True, text=True,
                       timeout=FINALIZE_TIMEOUT_S)
    data["qa"] = {q: v.get("overall") for q, v in qa.items()}
    bad = [f"{q}: {o}" for q, o in data["qa"].items() if o not in ("pass", "info")]
    if r.returncode != 0 or bad:
        refused = [l.strip() for l in r.stderr.splitlines()[1:]] or [r.stderr.strip()[-300:]] if r.returncode else []
        fails.append(fail_point("qa", "GLB cuối", f"work/evidence/finalize.json: {'; '.join(bad + refused)}",
                                "QA của kit không pass cho đúng file GLB này", "sửa theo JSON QA fail ở work/evidence/qa/",
                                "finalize.py không từ chối"))
    (final / "review").mkdir(parents=True, exist_ok=True)
    stage = done["stages"].get("compare")
    why = f"{stage}, xem work/compare/render.json" if stage and stage != "ok" else (out.strip().splitlines() or [""])[-1]
    cfails, data["compare"] = compare_renders(tf, work, final, views, stage == "ok", why)
    fails += cfails
    (final / "texture").mkdir(parents=True, exist_ok=True)
    shutil.copy2(albedo, final / "texture" / albedo.name)
    if (tf / "notes.md").is_file():
        shutil.copy2(tf / "notes.md", final / "texture" / "notes.md")
    for src in [mf / "review" / "model_sheet.png", tf / "final_lit_vs_concept.png", *sorted((tf / "review").glob("*.png"))]:
        if src.is_file():
            shutil.copy2(src, final / "review" / src.name)
    rv = vdir(a.id, "texture", tv) / "review-out.md"
    if rv.is_file():
        text = unwrap(rv.read_text(encoding="utf-8"))
        (final / "review" / "report-review-texture.md").write_text(text, encoding="utf-8")
    (final / "review" / "compare.json").write_text(json.dumps(
        {"tris": data.get("tris"), "threshold": {"mean_abs": COMPARE_MEAN, "mask_mismatch": COMPARE_MASK},
         "views": data["compare"], "qa": data["qa"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (final / "README.md").write_text(readme(st, mv, tv, mf, tf, res, qa, data), encoding="utf-8")
    return fails, data


def report(a, d: Path, fails: list[dict]) -> str:
    head = [f"STATUS: {'BLOCKED' if fails else 'DONE'}", f"OUTPUT: {os.path.relpath(d / 'final')}/",
            "ISSUES: " + ("; ".join(f"{f['kind']} {f['region']}: {f['evidence'].split(': ', 1)[-1]}" for f in fails)
                          if fails else "none"),
            f"PROFILE_HASH: {a.profile_hash}", "EVIDENCE_OPENED: work/evidence", "FINDINGS:" if fails else "FINDINGS: none"]
    for i, f in enumerate(fails, 1):
        head += [f"- F{i} [{f['priority']}] {f['kind']}",
                 f"  region: {f['region']} | viewing_condition: {f['viewing_condition']} | evidence: {f['evidence']}",
                 f"  consequence: {f['consequence']} | confidence: {f['confidence']}",
                 f"  repair: {f['repair']} | preserve: {f['preserve']} | acceptance: {f['acceptance']}"]
    return "\n".join(head) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("id")
    p.add_argument("version", type=int)
    p.add_argument("profile_hash")
    p.add_argument("--blender", default="blender")
    a = p.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", a.id):
        p.error(f"id '{a.id}' không hợp lệ: chỉ gồm a-z, 0-9 và '-'")
    if not (st := ROOT / "assets" / a.id / "status.json").is_file():
        p.error(f"không thấy {st}: chạy lệnh từ gốc project")
    d = vdir(a.id, "assemble", a.version)
    for sub in ("final", "work"):
        shutil.rmtree(d / sub, ignore_errors=True)
        (d / sub).mkdir(parents=True)
    pid = ROOT / "pids" / "blender" / f"{a.id}-{os.getpid()}.pid"
    pid.parent.mkdir(parents=True, exist_ok=True)
    pid.write_text(str(os.getpid()), encoding="utf-8")
    try:
        fails, _ = run(a, d)
    except Fail as ex:
        fails = [fail_point("input", "assemble", f"work/evidence: {ex}", "không ghép được gói", "xem lỗi", "chạy lại pass")]
    except Exception as ex:  # noqa: BLE001
        fails = [fail_point("script", "assemble", f"work/evidence: {type(ex).__name__}: {ex}", "script dừng giữa chừng",
                            "sửa môi trường theo lỗi rồi `retry`", "chạy lại pass")]
    finally:
        pid.unlink(missing_ok=True)
    for f in fails:
        f["evidence"] = re.sub(r"\s+", " ", f["evidence"])[:300]
    (d / "report-script.md").write_text(report(a, d, fails), encoding="utf-8")
    print(f"[assemble] {'fail ' + str(len(fails)) + ' điểm' if fails else 'pass'} -> {os.path.relpath(d / 'report-script.md')}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    require_root()
    main()
