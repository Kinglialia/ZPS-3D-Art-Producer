"""Apply one critic top_fix, rebuild, re-gate, re-measure, revert when worse
(references/self_build.md, step 6.4). Pure Python orchestrator; runs the other tools as
subprocesses.

Usage:
  python3 tools/self_build/apply_edit.py --work <w> --diagnosis <n> --spec task/spec.json
          [--after-structure-edit] [--out <json>]
  python3 tools/self_build/apply_edit.py --work <w> --diagnosis <n> --spec task/spec.json --revert

Reads <w>/diagnoses/<n>.json (3d-critic output; uses top_fix.part and top_fix.kind) and
<w>/renders/renders.json (render_views.py; its code_hash is the code the critic saw).

  kind "param":      renders must show the current code. Runs param_fit.py --part <part>
                     --out <w>/fit_<n>.json (fit.json from step 5 is left alone). When the fit is
                     not kept and the code is unchanged: data.noop true, the fix is recorded as
                     applied and tried, no rebuild and no new snapshot.
  kind "structure":  the builder edits part_graph.json / parts_lib.py first, then calls this with
                     --after-structure-edit. Renders must show the pre-edit code (the current
                     snapshot), and the code must have changed since.
  --revert           undo diagnosis n's applied fix (A/B check said worse or was inconsistent):
                     restore the snapshot that was current before it, point best.json at it,
                     mark the fix as tried. Result goes to edits/apply_<n>.revert.json.
Refuses (overall=fail, data.refused; result in edits/apply_<n>.refused.json) a diagnosis
already applied, stale renders, a structure edit without --after-structure-edit or without a
code change.

Then: assembly.py (full, with spec), gates.py for every part, snapshot to
<w>/snapshots/<k>/ (code, assembled.glb, assembly.json, meta.json). If the worst-view IoU is
more than self_build.revert_tolerance below the best kept snapshot's, the work dir is restored
from the best snapshot and rebuilt. <w>/best.json points to the best snapshot (the last kept
one; a kept snapshot is never more than revert_tolerance below the highest worst-view IoU seen).
<w>/edits.json records applied diagnoses, tried fixes and the current snapshot.
Exit 0 on pass/fail (including refusals), 1 on error.
"""
import datetime
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common  # noqa: E402
import graph as G  # noqa: E402

TOOL = "self_build/apply_edit"
CODE_FILES = ("part_graph.json", "parts_lib.py")


# ------------------------------------------------------------------ running the other tools
def _blender_runner(settings):
    """How to run a script that may need bpy: (prefix, uses_double_dash)."""
    try:
        import bpy
        binary = getattr(bpy.app, "binary_path", "") or ""
        if binary and os.path.basename(binary).lower().startswith("blender"):
            return [binary, "-b", "--python"], True
        return [sys.executable], False
    except ImportError:
        return [settings["paths"]["blender"], "-b", "--python"], True


def _python():
    """A python with trimesh/manifold3d for the pure-Python tools (not Blender's own)."""
    exe = os.path.basename(sys.executable).lower()
    return sys.executable if exe.startswith("python") else "python3"


def run_tool(script, args, settings, needs_bpy):
    path = os.path.join(HERE, script)
    if needs_bpy:
        prefix, dash = _blender_runner(settings)
        cmd = prefix + [path] + (["--"] if dash else []) + args
    else:
        cmd = [_python(), path] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, cmd, (p.stdout + p.stderr)[-3000:]


# ------------------------------------------------------------------ state
def load_state(work):
    path = os.path.join(work, "edits.json")
    if os.path.isfile(path):
        return common.read_json(path)
    return {"applied": {}, "tried_fixes": [], "current_snapshot": None}


def snapshot_ids(work):
    return sorted(int(os.path.basename(d)) for d in glob.glob(os.path.join(work, "snapshots", "*"))
                  if os.path.basename(d).isdigit())


def iou_of(assembly_json):
    d = common.read_json(assembly_json)
    if d.get("overall") == "error":
        return None
    return (d["data"].get("iou") or {})


def make_snapshot(work, k, src_dir, meta, settings, spec_path, build=False):
    """Copy code (and build outputs) from src_dir into snapshots/<k>/; build there if asked."""
    sdir = os.path.join(work, "snapshots", str(k))
    if os.path.isdir(sdir):
        shutil.rmtree(sdir)
    os.makedirs(sdir)
    for name in CODE_FILES:
        if os.path.isfile(os.path.join(src_dir, name)):
            shutil.copy2(os.path.join(src_dir, name), sdir)
    if build:
        rc, cmd, log = run_tool("assembly.py", ["--work", sdir, "--spec", spec_path], settings, True)
        if rc != 0:
            raise RuntimeError(f"assembly failed on snapshot {k}: {log}")
    else:
        for name in ("assembled.glb", "assembly.json"):
            shutil.copy2(os.path.join(src_dir, name), sdir)
        if os.path.isdir(os.path.join(src_dir, "parts")):
            shutil.copytree(os.path.join(src_dir, "parts"), os.path.join(sdir, "parts"))
    iou = iou_of(os.path.join(sdir, "assembly.json")) or {}
    meta = dict(meta, snapshot=k, code_hash=G.code_hash(sdir), iou_worst=iou.get("worst"),
                iou_mean=iou.get("mean"), iou_per_view=iou.get("per_view"),
                created=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
    common.write_json(os.path.join(sdir, "meta.json"), meta)
    return sdir, meta


def restore(work, sdir, settings, spec_path):
    for name in CODE_FILES:
        src = os.path.join(sdir, name)
        dst = os.path.join(work, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
        elif os.path.isfile(dst):
            os.remove(dst)
    rc, cmd, log = run_tool("assembly.py", ["--work", work, "--spec", spec_path], settings, True)
    if rc != 0:
        raise RuntimeError(f"assembly failed after restoring {sdir}: {log}")


def max_kept_worst(work):
    vals = []
    for k in snapshot_ids(work):
        m = common.read_json(os.path.join(work, "snapshots", str(k), "meta.json"))
        if m.get("status") in ("baseline", "kept") and m.get("iou_worst") is not None:
            vals.append(m["iou_worst"])
    return max(vals) if vals else None


def part_name(raw):
    """'2 lid' / 'lid' / 'NEW: hinge' -> 'lid' / 'lid' / 'hinge'."""
    s = str(raw or "").strip()
    if s.upper().startswith("NEW:"):
        s = s[4:].strip()
    head, _, rest = s.partition(" ")
    return rest.strip() if head.isdigit() and rest else s


def refuse(reason, data):
    data.update({"refused": True, "reason": reason})
    return "fail", [common.check("edit.allowed", "fail", note=reason)], {}, [], data


# ------------------------------------------------------------------ main flow
def apply(a, settings):
    work = a.work
    tol = settings["self_build"]["revert_tolerance"]
    state = load_state(work)
    key = str(a.diagnosis)
    dpath = os.path.join(work, "diagnoses", f"{a.diagnosis}.json")
    diag = common.read_json(dpath)
    fix = diag.get("top_fix") or {}
    kind = fix.get("kind")
    part = part_name(fix.get("part"))
    data = {"diagnosis": a.diagnosis, "top_fix": fix, "kind": kind, "part": part, "refused": False}
    warnings = []
    best_path = os.path.join(work, "best.json")

    if a.revert:
        rec = state["applied"].get(key)
        if not rec or rec.get("snapshot") is None:
            return refuse(f"diagnosis {a.diagnosis} has no applied edit to revert", data)
        if rec.get("reverted"):
            return refuse(f"diagnosis {a.diagnosis} was already reverted", data)
        target = rec["snapshot_before"]
        tdir = os.path.join(work, "snapshots", str(target))
        restore(work, tdir, settings, a.spec)
        mpath = os.path.join(work, "snapshots", str(rec["snapshot"]), "meta.json")
        m = common.read_json(mpath)
        m["status"] = "reverted_ab"
        common.write_json(mpath, m)
        tmeta = common.read_json(os.path.join(tdir, "meta.json"))
        common.write_json(best_path, {"snapshot": target, "iou_worst": tmeta["iou_worst"],
                                      "iou_mean": tmeta["iou_mean"], "max_worst_seen": max_kept_worst(work),
                                      "code_hash": tmeta["code_hash"]})
        rec["reverted"] = True
        state["tried_fixes"].append({"diagnosis": a.diagnosis, "top_fix": fix, "reason": "A/B check"})
        state["current_snapshot"] = target
        common.write_json(os.path.join(work, "edits.json"), state)
        data.update({"reverted_to": target, "undone_snapshot": rec["snapshot"]})
        return "pass", [common.check("edit.reverted", "pass", value=target,
                                     note=f"undid snapshot {rec['snapshot']}")], {}, warnings, data

    if key in state["applied"]:
        rec = state["applied"][key]
        what = "noop: param_fit found no gain" if rec.get("noop") else f"snapshot {rec.get('snapshot')}"
        return refuse(f"diagnosis {a.diagnosis} was already applied ({what}); ask the critic again", data)
    if kind not in ("param", "structure"):
        return refuse(f"top_fix.kind must be param or structure, got {kind!r}", data)
    rpath = os.path.join(work, "renders", "renders.json")
    if not os.path.isfile(rpath):
        return refuse("no renders/renders.json: run render_views.py --mode critic first", data)
    rhash = common.read_json(rpath)["data"].get("code_hash")
    now = G.code_hash(work)
    data.update({"renders_code_hash": rhash, "code_hash_before": now})

    # baseline snapshot 0 = the code the critic saw
    if not snapshot_ids(work):
        src = os.path.join(work, "renders", "code")
        if G.code_hash(src) != rhash:
            return refuse("renders/code does not match renders.json; re-render", data)
        _, meta = make_snapshot(work, 0, src, {"status": "baseline", "diagnosis": None}, settings,
                                a.spec, build=True)
        common.write_json(best_path, {"snapshot": 0, "iou_worst": meta["iou_worst"],
                                      "iou_mean": meta["iou_mean"], "max_worst_seen": meta["iou_worst"],
                                      "code_hash": meta["code_hash"]})
        state["current_snapshot"] = 0
    cur = state.get("current_snapshot")
    cur_meta = common.read_json(os.path.join(work, "snapshots", str(cur), "meta.json"))

    if kind == "param":
        if a.after_structure_edit:
            warnings.append("--after-structure-edit ignored for a param fix")
        if rhash != now:
            return refuse("renders are older than the code (part_graph.json/parts_lib.py changed "
                          "after render_views); re-render and ask the critic again", data)
    else:
        if not a.after_structure_edit:
            return refuse("structure fix: the builder edits the part first, then call with "
                          "--after-structure-edit", data)
        if rhash != cur_meta["code_hash"]:
            return refuse(f"renders do not show the pre-edit code (snapshot {cur}); "
                          "re-render and ask the critic again", data)
        if now == rhash:
            return refuse("no code change since the renders: edit the part first", data)

    checks, metrics = [common.check("edit.allowed", "pass")], {}
    fit = None
    if kind == "param":
        g = G.load_graph(work)
        if part not in [p.get("name") for p in g.get("parts", [])]:
            return refuse(f"top_fix.part '{fix.get('part')}' is not in part_graph.json", data)
        # fit_<n>.json, so the step-5 fit.json (the full fit) is never overwritten
        fit_path = os.path.join(work, f"fit_{a.diagnosis}.json")
        rc, cmd, log = run_tool("param_fit.py", ["--work", work, "--spec", a.spec, "--part", part,
                                                 "--out", fit_path], settings, True)
        if rc != 0:
            raise RuntimeError(f"param_fit failed: {log}")
        fit = common.read_json(fit_path)
        data["fit"] = {k: fit["data"].get(k) for k in ("kept", "gain", "changes", "evals", "seconds")}
        data["fit"]["before"] = fit["data"]["before"]
        data["fit"]["after"] = fit["data"]["after"]
        data["fit"]["path"] = fit_path
        checks.append(common.check("edit.param_fit", "pass" if fit["data"].get("kept") else "info",
                                   value=fit["data"].get("gain"),
                                   note="params changed" if fit["data"].get("kept") else
                                   "param_fit kept the old values (gain below min_gain)"))
        if not fit["data"].get("kept") and G.code_hash(work) == now:
            # nothing changed: no rebuild, no snapshot; the fix counts as applied and tried
            state["applied"][key] = {"snapshot": None, "snapshot_before": cur, "kind": kind, "part": part,
                                     "reverted": False, "noop": True, "iou_worst_after": cur_meta.get("iou_worst")}
            state["tried_fixes"].append({"diagnosis": a.diagnosis, "top_fix": fix,
                                         "reason": "param_fit found no gain >= min_gain (noop)"})
            common.write_json(os.path.join(work, "edits.json"), state)
            checks.append(common.check("edit.noop", "info", value=True,
                                       note=f"no param or structure change; snapshot {cur} stays current, "
                                            "no new snapshot"))
            data.update({"noop": True, "snapshot": None, "current_snapshot": cur,
                         "code_hash_after": now, "revert_tolerance": tol})
            metrics.update({"iou_worst_before": cur_meta.get("iou_worst"),
                            "iou_worst_after": cur_meta.get("iou_worst"), "noop": True})
            return None, checks, metrics, warnings, data

    # rebuild, re-gate, re-measure
    rc, cmd, log = run_tool("assembly.py", ["--work", work, "--spec", a.spec], settings, True)
    asm_ok = rc == 0
    gates = {}
    if asm_ok:
        rows = common.read_json(os.path.join(work, "assembly.json"))["data"]["parts"]
        for r in rows:
            run_tool("gates.py", ["--work", work, "--part", r["name"], "--spec", a.spec], settings, False)
            gj = common.read_json(os.path.join(work, "gates", f"{r['name']}.json"))
            gates[r["name"]] = {"overall": gj["overall"],
                                "failed": [c["check"] for c in gj["checks"] if c["status"] == "fail"],
                                "metrics": gj["metrics"]}
        failed = {n: g["failed"] for n, g in gates.items() if g["failed"]}
        checks.append(common.check("edit.gates", "fail" if failed else "pass",
                                   value=len(failed), note=str(failed) if failed else None))
    else:
        checks.append(common.check("edit.build", "fail", note=log[-500:]))
    data["gates"] = gates

    best = common.read_json(best_path)
    k = max(snapshot_ids(work)) + 1
    if asm_ok:
        sdir, meta = make_snapshot(work, k, work, {"status": "candidate", "diagnosis": a.diagnosis,
                                                  "kind": kind, "part": part}, settings, a.spec)
        new_worst = meta["iou_worst"]
    else:
        sdir, meta, new_worst = None, None, None
    ref = best.get("max_worst_seen", best["iou_worst"])
    drop = None if new_worst is None or ref is None else round(ref - new_worst, 5)
    floor = (common.read_json(a.spec).get("concept") or {}).get("min_iou")
    if kind == "structure" and floor is not None:
        # A structure fix may trade silhouette precision for the right block language, which IoU
        # cannot see. Keep it while every view stays above the spec floor; the critic's A/B
        # check decides (apply_edit --revert when it says worse).
        reverted = (not asm_ok) or (new_worst is not None and new_worst < floor)
    else:
        reverted = (not asm_ok) or (drop is not None and drop > tol)
    metrics.update({"iou_worst_before": cur_meta.get("iou_worst"), "iou_worst_after": new_worst,
                    "iou_worst_best_seen": ref, "drop": drop, "reverted": reverted})
    if reverted:
        restore(work, os.path.join(work, "snapshots", str(best["snapshot"])), settings, a.spec)
        if meta:
            meta["status"] = "reverted"
            common.write_json(os.path.join(sdir, "meta.json"), meta)
        state["current_snapshot"] = best["snapshot"]
        state["tried_fixes"].append({"diagnosis": a.diagnosis, "top_fix": fix,
                                     "reason": "build failed" if not asm_ok else f"worst IoU dropped {drop}"})
        why = (f"structure fix: worst IoU {new_worst} < spec floor {floor}" if kind == "structure" and floor is not None
               else f"dropped {drop} > revert_tolerance {tol}")
        checks.append(common.check("edit.iou_worst", "fail", value=new_worst,
                                   threshold=floor if kind == "structure" and floor is not None else ref,
                                   note=f"{why}; restored snapshot {best['snapshot']}" if asm_ok
                                   else "build failed; restored best"))
    else:
        meta["status"] = "kept"
        common.write_json(os.path.join(sdir, "meta.json"), meta)
        state["current_snapshot"] = k
        seen = new_worst if (kind == "structure" or ref is None) else max(ref, new_worst)
        best = {"snapshot": k, "iou_worst": new_worst, "iou_mean": meta["iou_mean"],
                "max_worst_seen": seen,
                "code_hash": meta["code_hash"]}
        common.write_json(best_path, best)
        checks.append(common.check("edit.iou_worst", "pass", value=new_worst,
                                   threshold=floor if kind == "structure" else ref,
                                   note=(f"structure fix: worst IoU {new_worst} >= spec floor {floor} "
                                         f"(drop {drop} vs best seen); the critic's A/B check decides")
                                   if kind == "structure" else f"drop {drop} <= revert_tolerance {tol}"))
    state["applied"][key] = {"snapshot": k if asm_ok else None, "snapshot_before": cur, "kind": kind, "part": part,
                             "reverted": reverted, "iou_worst_after": new_worst}
    common.write_json(os.path.join(work, "edits.json"), state)
    data.update({"noop": False, "snapshot": k if asm_ok else None, "reverted": reverted, "best": best,
                 "code_hash_after": G.code_hash(work), "revert_tolerance": tol})
    return None, checks, metrics, warnings, data


def main():
    p = common.make_parser(__doc__)
    p.add_argument("--work", required=True)
    p.add_argument("--diagnosis", required=True, type=int)
    p.add_argument("--spec", required=True)
    p.add_argument("--after-structure-edit", action="store_true")
    p.add_argument("--revert", action="store_true")
    p.add_argument("--out")
    a = p.parse_args(common.script_argv())
    out = a.out or os.path.join(a.work, "edits", f"apply_{a.diagnosis}.json")
    try:
        settings, _ = common.load_settings(a.spec)
        overall, checks, metrics, warnings, data = apply(a, settings)
        if not a.out and (data.get("refused") or a.revert):   # keep the applied edit's result
            tag = "refused" if data.get("refused") else "revert"
            out = os.path.join(a.work, "edits", f"apply_{a.diagnosis}.{tag}.json")
    except Exception as e:  # noqa: BLE001
        common.write_error(out, TOOL, e, source=os.path.join(a.work, "part_graph.json"))
        sys.exit(1)
    common.write_result(out, TOOL, checks, metrics, warnings, data=data, overall=overall,
                        source=os.path.join(a.work, "part_graph.json"), spec_path=a.spec)


if __name__ == "__main__":
    main()
