"""The Meshy layer of one meshy_call.py call is usable: its topology gate passed on the locked mesh (D30.3; checklist 75).

Usage: python3 T/check_meshy.py --final F --locked <locked GLB> --call V/work/meshy/call-<k> --albedo-out <png>
meshy_call.py already compared the Meshy GLB with the locked mesh (triangle count, the set of per-triangle UV triples)
and the base_color size with texture_res, in <call>/topology.json. This tool does not compare again. It passes when that
gate passed, it was run on this locked GLB (sha256), and glb.glb and base_color.png are the files it checked (sha256).
Then <call>/base_color.png, the albedo of the Meshy task, is written to --albedo-out unchanged in size (the Meshy layer
for SỬA mode). A fail keeps no albedo: drop that call. Hard gate: never ACCEPTED_FAIL.
Writes F/review/checks/meshy.json. Prints one line. Exit 0, 1 fail, 2 error.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import tex  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def compare(locked, call):
    topo = os.path.join(call, "topology.json")
    if not os.path.isfile(topo):
        return [tex.check("meshy.topology", "fail", None, "pass", note="không có topology.json: chạy lại meshy_call")]
    r = json.load(open(topo, encoding="utf-8"))
    d = r.get("data") or {}
    files = {"glb_sha256": "glb.glb", "base_color_sha256": "base_color.png"}
    changed = [n for k, n in files.items() if not os.path.isfile(os.path.join(call, n))
               or sha256(os.path.join(call, n)) != d.get(k)]
    return [*r.get("checks", []),
            tex.check("meshy.topology", "pass" if r.get("overall") == "pass" else "fail", r.get("overall"), "pass"),
            tex.check("meshy.locked_mesh", "pass" if d.get("locked_sha256") == sha256(locked) else "fail",
                      d.get("locked_sha256"), sha256(locked), note="sha256 của mesh đã khóa lúc meshy_call kiểm"),
            tex.check("meshy.files_unchanged", "fail" if changed else "pass", changed, [])]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("--final", "--locked", "--call", "--albedo-out"):
        p.add_argument(k, required=True)
    a = p.parse_args()
    out = os.path.join(a.final, "review", "checks", "meshy.json")
    try:
        checks = compare(a.locked, a.call)
        if all(c["status"] == "pass" for c in checks):
            from PIL import Image
            os.makedirs(os.path.dirname(os.path.abspath(a.albedo_out)), exist_ok=True)
            Image.open(os.path.join(a.call, "base_color.png")).convert("RGB").save(a.albedo_out)
    except Exception as e:  # noqa: BLE001
        tex.write_error(out, "check_meshy", e)
        print(f"[check_meshy] error: {e!r}")
        sys.exit(2)
    r = tex.write_result(out, "check_meshy", checks, {"hard_gate": True, "call": os.path.abspath(a.call)})
    bad = [c["check"] for c in checks if c["status"] == "fail"]
    print(f"[check_meshy] {'fail ' + ', '.join(bad) + ': bỏ lớp Meshy này' if bad else 'giữ lớp Meshy'} -> {out}")
    sys.exit(1 if r["overall"] == "fail" else 0)


if __name__ == "__main__":
    require_root()
    main()
