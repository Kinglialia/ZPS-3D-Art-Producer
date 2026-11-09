"""Write final*.glb once the QA gate passed for that exact file (SKILL.md, QA gate). Pure Python.

Usage:
  python3 tools/finalize.py --work output/<asset> --from <baked GLB> [--min-pass <baked GLB>]
         [--out output/<asset>/evidence/finalize.json]

Reads every asset_checks result JSON under <work>/evidence/qa/ (recursive) and keeps those whose
source_sha256 is the sha256 of the given GLB (ac_common records --input as source_file), the
newest per script. Refuses (exit 1, nothing copied) when, for any given GLB:
  - one of those results is fail or error (it prints which, with their failing checks), or
  - no QA result matches the file, or mesh_check is not among them (SKILL.md rule 5).
QA scripts that did not run on the file are listed in data.not_run (iou_check and
concept_coverage only apply with a concept). Results for other files are ignored and listed in
data.other_files.
Copies: --from -> <work>/final.glb; with --min-pass also --from -> final_budget.glb and
--min-pass -> final_min_pass.glb (budget below the floor: export both, explain the gap).
Writes <work>/evidence/finalize.json either way. Exit 0 when written, 1 when refused or on error.
"""
import argparse
import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import common  # noqa: E402

TOOL = "finalize"
QA_SCRIPTS = ["mesh_check", "uv_check", "contact_check", "iou_check", "concept_coverage",
              "render_rig", "screen_tris_check", "export_check"]
REQUIRED = ["mesh_check"]


def qa_results(work):
    out = []
    for p in sorted(glob.glob(os.path.join(work, "evidence", "qa", "**", "*.json"), recursive=True)):
        try:
            d = common.read_json(p)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and str(d.get("tool", "")).startswith("asset_checks/"):
            out.append((p, d))
    return out


def gate(work, glb, results):
    """QA verdict for one GLB: (ok, detail dict)."""
    sha = common.file_sha256(glb)
    mine = [(p, d) for p, d in results if d.get("source_sha256") == sha]
    newest = {}
    for p, d in mine:
        s = d["tool"].split("/", 1)[1]
        if s not in newest or (d.get("run_at") or "") > (newest[s][1].get("run_at") or ""):
            newest[s] = (p, d)
    blockers = []
    for s, (p, d) in sorted(newest.items()):
        if d.get("overall") not in ("pass", "info"):
            fails = [c["check"] for c in d.get("checks", []) if c.get("status") in ("fail", "error")]
            blockers.append({"script": s, "overall": d.get("overall"), "path": os.path.relpath(p, work),
                             "checks": fails, "error": (d.get("data") or {}).get("error")})
    for s in REQUIRED:
        if s not in newest:
            blockers.append({"script": s, "overall": None, "path": None,
                             "checks": [], "error": f"no {s} result for this file (sha256 {sha[:12]})"})
    detail = {"file": os.path.abspath(glb), "sha256": sha,
              "results": {s: {"overall": d.get("overall"), "path": os.path.relpath(p, work), "run_at": d.get("run_at")}
                          for s, (p, d) in sorted(newest.items())},
              "not_run": [s for s in QA_SCRIPTS if s not in newest], "blockers": blockers}
    return not blockers, detail


def main(a):
    work = os.path.abspath(a.work)
    results = qa_results(work)
    targets = [("from", a.src)] + ([("min_pass", a.min_pass)] if a.min_pass else [])
    for _, p in targets:
        if not os.path.isfile(p):
            raise FileNotFoundError(p)
    verdicts = {role: gate(work, p, results) for role, p in targets}
    shas = {d["sha256"] for _, d in verdicts.values()}
    other = sorted({os.path.relpath(p, work) for p, d in results if d.get("source_sha256") not in shas})
    checks, copies = [], {}
    for role, (ok, d) in verdicts.items():
        checks.append(common.check(f"qa.{role}", "pass" if ok else "fail", {s: r["overall"] for s, r in d["results"].items()},
                                   note=None if ok else "; ".join(
                                       f"{b['script']}: {b['overall'] or 'missing'}"
                                       + (f" ({', '.join(b['checks'])})" if b["checks"] else "")
                                       + (f" {b['error']}" if b.get("error") else "") for b in d["blockers"])))
    refused = any(c["status"] == "fail" for c in checks)
    if not refused:
        plan = [("final.glb", a.src)]
        if a.min_pass:
            plan += [("final_budget.glb", a.src), ("final_min_pass.glb", a.min_pass)]
        for name, src in plan:
            dst = os.path.join(work, name)
            shutil.copyfile(src, dst)
            copies[name] = {"from": os.path.abspath(src), "sha256": common.file_sha256(dst)}
            checks.append(common.check(f"copy.{name}", "pass", os.path.relpath(dst, work)))
    data = {"refused": refused, "copies": copies, "qa": {r: d for r, (_, d) in verdicts.items()},
            "other_files": other}
    common.write_result(a.out, TOOL, checks, data=data, source=a.src)
    if refused:
        print("[finalize] refused: QA does not pass for the given file(s):", file=sys.stderr)
        for role, (_, d) in verdicts.items():
            for b in d["blockers"]:
                print(f"  {role} {os.path.basename(d['file'])}: {b['script']} = {b['overall'] or 'missing'}"
                      f"{' ' + ', '.join(b['checks']) if b['checks'] else ''}"
                      f"{' (' + b['path'] + ')' if b['path'] else ''}{' ' + b['error'] if b.get('error') else ''}",
                      file=sys.stderr)
        sys.exit(1)
    for name in copies:
        print(f"[finalize] wrote {os.path.join(work, name)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", required=True, help="asset folder output/<asset>")
    p.add_argument("--from", dest="src", required=True, help="baked GLB that passed QA")
    p.add_argument("--min-pass", help="second baked GLB (budget below the floor)")
    p.add_argument("--out")
    args = p.parse_args()
    args.out = args.out or os.path.join(args.work, "evidence", "finalize.json")
    try:
        main(args)
    except Exception as exc:  # noqa: BLE001
        common.write_error(args.out, TOOL, exc, source=args.src)
        print(f"[finalize] error: {exc!r}", file=sys.stderr)
        sys.exit(1)
