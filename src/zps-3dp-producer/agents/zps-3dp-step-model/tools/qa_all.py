"""The four kit QA checks in one Blender session (D37.4). Runs in Blender.

Usage: BLENDER -b --python tools/qa_all.py -- --final F
For each of mesh_check, uv_check, export_check, screen_tris_check: the main of asset_checks/<check>.py with
--input F/<id>-untextured.glb --spec F/spec.json --out F/review/checks/qa_<check>.json, the arguments it takes alone.
ac_common.run_main writes an error JSON when a check raises; the next check still runs, because the four are independent.
This repeats the pattern of scripts/assemble_qa.py and imports nothing from scripts/: the model tools must run from the
agent folder alone.
Exit 0 when no check is fail or error, 1 otherwise.
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("asset_checks", "lib"):
    sys.path.insert(0, os.path.join(HERE, sub))
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

CHECKS = ("mesh_check", "uv_check", "export_check", "screen_tris_check")


def main():
    import common
    import session
    p = common.make_parser(__doc__)
    p.add_argument("--final", required=True)
    final = p.parse_args(common.script_argv()).final
    import ac_common
    glb = os.path.join(final, f"{common.read_json(os.path.join(final, 'spec.json'))['asset']}-untextured.glb")
    passed = []
    for name in CHECKS:
        mod = importlib.import_module(name)
        out = os.path.join(final, "review", "checks", f"qa_{name}.json")
        passed.append(session.stage(lambda mod=mod, name=name: ac_common.run_main(mod.main, name), out,
                                    "--input", glb, "--spec", os.path.join(final, "spec.json"), "--out", out))
    sys.exit(0 if all(passed) else 1)


if __name__ == "__main__":
    require_root()
    main()
