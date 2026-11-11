#!/usr/bin/env python3
"""Step `assemble`, a script with no agent (docs/producer.md §6.4, D22.11, D24.4). `P brief` prints this command.

Usage: assemble.py --blender <BLENDER> -- <id> <N> <profile hash>
Reads the approved `model` and `texture` versions of status.json and writes assemble/vN/ only:
  1 sha256 of model final/<id>-untextured.glb = locked.model; albedo_<texture_res>.png is res x res.
  2 assemble_glb.py: final/model/<id>.glb (1 mesh, 1 node, 1 material, unlit, base colour) and <id>.blend.
  3 kit QA on a byte copy of that GLB in work/qa_input/ (the validator writes beside its input), results in
    work/evidence/qa/: mesh_check, uv_check, export_check (expect_unlit), screen_tris_check.
  3b kit finalize.py over work/: refuses unless every QA result for this GLB's sha256 passes and mesh_check is there.
     Finalize skips a check with no result, so any of the four not pass or info, missing included, is a fail too.
  4 the GLB rendered again with the texture step's recorded cameras (unlit_34_front, unlit_game) and compared with the
    texture renders: mean |RGB| difference over the object ≤ COMPARE_MEAN, silhouette mismatch ≤ COMPARE_MASK.
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
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import findings  # noqa: E402
from core.contract import unwrap  # noqa: E402
from core.state import ROOT, SKILL_DIR, load_st, now, texture_res, vdir  # noqa: E402
from root_guard import require_root  # noqa: E402

SCRIPTS = SKILL_DIR / "scripts"
MODEL_TOOLS = SKILL_DIR / "agents" / "zps-3dp-step-model" / "tools"
RENDER = SKILL_DIR / "agents" / "zps-3dp-step-texture" / "tools" / "render_texture.py"
FINALIZE = SCRIPTS / "kit" / "tools" / "finalize.py"
QA = ("mesh_check", "uv_check", "export_check", "screen_tris_check")
COMPARE = ("unlit_34_front", "unlit_game")
COMPARE_MEAN = 6.0
COMPARE_MASK = 0.02
OPEN_KINDS = ("minor", "major", "blocker", "unclear")
STEPS = ("blockout", "views_front", "views_rest", "model", "texture")


class Fail(Exception):
    pass


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


BLENDER_TIMEOUT_S = 900  # D33.3: three Blender runs stay under BASH_MAX_TIMEOUT_MS 3600000 of the settings snippet


def blender(exe: str, script: Path, *args) -> tuple[int, str]:
    try:
        r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script), "--",
                            *map(str, args)], capture_output=True, text=True, timeout=BLENDER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 1, f"Blender quá {BLENDER_TIMEOUT_S} s: {script.name}"
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
    """Card `views: none` (D35): no views_rest README, so the texture_only notes of the card stand for its TEXTURE NOTE."""
    from core import asset_card
    if asset_card.views(st) != "none":
        return []
    import yaml
    c = yaml.safe_load((Path(st["concept_dir"]) / "asset-card.yaml").read_text(encoding="utf-8")) or {}
    return [f"- thẻ: {n}" for n in map(str, c.get("real_texture_only_notes") or []) if n.lower().startswith("texture_only")]


def exceptions(st: dict) -> list[str]:
    """README "Ngoại lệ": views_rest exceptions and texture notes (card notes with `views: none`), blockout decisions,
    user waives (D30.1), and the NGOẠI LỆ section of every other step's README, where a worker writes its ACCEPTED_FAIL
    (D31.3)."""
    return [*section(vdir(st["id"], "views_rest", st["approved"].get("views_rest", 0)) / "final" / "README.md", "NGOẠI LỆ"),
            *section(vdir(st["id"], "views_rest", st["approved"].get("views_rest", 0)) / "final" / "README.md", "TEXTURE NOTE"),
            *card_notes(st),
            *section(vdir(st["id"], "blockout", st["approved"].get("blockout", 0)) / "final" / "blockout.md", "Blockout tự quyết"),
            *waived(st, "user", "người dùng waive: "),
            *(f"- {sid}: {x.lstrip('- ')}" for sid in ("blockout", "views_front", "model", "texture")
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
    rc, out = blender(a.blender, SCRIPTS / "assemble_glb.py", "--glb", locked, "--albedo", albedo, "--name", a.id,
                      "--out", final / "model")
    glb = final / "model" / f"{a.id}.glb"
    if rc != 0 or not glb.is_file():
        return [fail_point("export", "GLB", f"work/evidence: assemble_glb {out.strip().splitlines()[-1:]}",
                           "không có GLB cuối", "đọc lỗi Blender, chạy lại (`retry`)", "có final/model/<id>.glb")], data
    data |= json.loads([l for l in out.splitlines() if l.startswith("{")][-1])
    spec = json.loads((mf / "spec.json").read_text(encoding="utf-8"))
    probe = work / "qa_input" / glb.name
    probe.parent.mkdir(parents=True)
    shutil.copy2(glb, probe)
    spec["export"] = {"path": f"qa_input/{glb.name}", "skip_export": True, "expect_unlit": True}
    (work / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    qa = {}
    for q in QA:
        dst = work / "evidence" / "qa" / f"{q}.json"
        blender(a.blender, MODEL_TOOLS / "asset_checks" / f"{q}.py", "--input", probe, "--spec", work / "spec.json",
                "--out", dst)
        qa[q] = json.loads(dst.read_text(encoding="utf-8")) if dst.is_file() else {"overall": "missing", "checks": []}
    r = subprocess.run([sys.executable, str(FINALIZE), "--work", str(work), "--from", str(glb), "--out",
                        str(work / "evidence" / "finalize.json")], capture_output=True, text=True)
    data["qa"] = {q: v.get("overall") for q, v in qa.items()}
    bad = [f"{q}: {o}" for q, o in data["qa"].items() if o not in ("pass", "info")]
    if r.returncode != 0 or bad:
        refused = [l.strip() for l in r.stderr.splitlines()[1:]] or [r.stderr.strip()[-300:]] if r.returncode else []
        fails.append(fail_point("qa", "GLB cuối", f"work/evidence/finalize.json: {'; '.join(bad + refused)}",
                                "QA của kit không pass cho đúng file GLB này", "sửa theo JSON QA fail ở work/evidence/qa/",
                                "finalize.py không từ chối"))
    rc, out = blender(a.blender, RENDER, "--glb", glb, "--cameras", tf / "review" / "renders.json", "--views",
                      ",".join(COMPARE), "--outdir", work / "compare")
    data["compare"] = {}
    (final / "review").mkdir(parents=True, exist_ok=True)
    for view in COMPARE:
        got = work / "compare" / f"{view}.png"
        if rc != 0 or not got.is_file():
            fails.append(fail_point("compare", view, f"work/evidence: render GLB lỗi {out.strip().splitlines()[-1:]}",
                                    "không so được GLB với render bước texture", "đọc lỗi Blender", f"có {view}.png"))
            continue
        c = data["compare"][view] = compare(tf / "review" / f"{view}.png", got,
                                            final / "review" / f"compare_{view.removeprefix('unlit_')}.png")
        if c["mean_abs"] is None or c["mean_abs"] > COMPARE_MEAN or c["mask_mismatch"] > COMPARE_MASK:
            fails.append(fail_point(
                "compare", view, f"work/evidence/compare.json: mean_abs {c['mean_abs']}, mask {c['mask_mismatch']}",
                "GLB trong engine khác render bước texture (color space, alpha, unlit)",
                "kiểm color space, alpha và material của albedo trước khi vẽ lại",
                f"mean_abs ≤ {COMPARE_MEAN:g} và mask ≤ {COMPARE_MASK:g} ở {view}"))
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
