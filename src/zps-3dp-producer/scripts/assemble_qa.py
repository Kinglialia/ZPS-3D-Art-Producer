"""Blender side of assemble.py in one session (D37.4): GLB export, the kit QA checks, the compare render.

Usage: BLENDER -b --python scripts/assemble_qa.py -- --glb <locked GLB> --albedo <png> --name <id> --out <final/model>
          --probe <GLB copy for the checks> --spec <model spec> --qa-spec <spec the checks read> --checks a,b
          --qa-dir <dir> --result <session.json> [--cameras <renders.json> --views v1,v2 --outdir <dir>]
Stages run in this order: export (assemble_glb.build), copy of the GLB to --probe, the checks spec (the model spec with
`export` pointing at the probe), each check, the render of render_texture.py in camera mode.
Each frozen kit script resets the scene and reads sys.argv, so the driver sets sys.argv per stage and calls the main of
the script. A check writes its result JSON to <qa-dir>/<check>.json as it does alone.
A stage that fails does not stop the next one, except the export. <session.json> holds the export data and one line per
stage: "ok" or "error: ...". Exit 0, 1 when the export fails.
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import traceback

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(SCRIPTS, "..", "agents")
MODEL_TOOLS = os.path.abspath(os.path.join(TOOLS, "zps-3dp-step-model", "tools"))
RENDER_TEXTURE = os.path.abspath(os.path.join(TOOLS, "zps-3dp-step-texture", "tools", "render_texture.py"))
sys.path.insert(0, SCRIPTS)
from root_guard import require_root  # noqa: E402


def stage(result: dict, name: str, fn):
    try:
        fn()
        result["stages"][name] = "ok"
    except SystemExit as e:
        result["stages"][name] = "ok" if e.code in (None, 0) else f"error: exit {e.code!r}"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        result["stages"][name] = f"error: {e!r}"


def write_checks_spec(a):
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    spec["export"] = {"path": os.path.relpath(a.probe, os.path.dirname(os.path.abspath(a.qa_spec))), "skip_export": True,
                      "expect_unlit": True}
    with open(a.qa_spec, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)


def check(a, name: str):
    import ac_common
    mod = importlib.import_module(name)
    sys.argv = ["blender", "--", "--input", a.probe, "--spec", a.qa_spec, "--out", os.path.join(a.qa_dir, f"{name}.json")]
    ac_common.run_main(mod.main, name)


def render(a, glb: str):
    # The texture tools' `bootstrap` has the model tools' name and is already imported; its deps are a subset.
    spec = importlib.util.spec_from_file_location("render_texture", RENDER_TEXTURE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.argv = ["blender", "--", "--glb", glb, "--cameras", a.cameras, "--views", a.views, "--outdir", a.outdir]
    mod.main()


def main():
    p = argparse.ArgumentParser()
    for k in ("--glb", "--albedo", "--name", "--out", "--probe", "--spec", "--qa-spec", "--checks", "--qa-dir", "--result"):
        p.add_argument(k, required=True)
    for k in ("--cameras", "--views", "--outdir"):
        p.add_argument(k, default="")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    for sub in ("lib", "optimize", "asset_checks"):
        sys.path.insert(0, os.path.join(MODEL_TOOLS, sub))
    import bootstrap  # noqa: F401  # model deps first: they hold what the checks need and the render needs less
    import assemble_glb
    result = {"stages": {}}

    def save():
        os.makedirs(os.path.dirname(os.path.abspath(a.result)), exist_ok=True)
        with open(a.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)

    try:
        result["export"] = assemble_glb.build(a.glb, a.albedo, a.name, a.out)
        os.makedirs(os.path.dirname(os.path.abspath(a.probe)), exist_ok=True)
        shutil.copy2(result["export"]["glb"], a.probe)
        result["stages"]["export"] = "ok"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        result["stages"]["export"] = f"error: {e!r}"
        save()
        print(json.dumps({"error": repr(e)}))
        sys.exit(1)
    stage(result, "spec", lambda: write_checks_spec(a))
    save()
    for name in filter(None, a.checks.split(",")):
        stage(result, name, lambda name=name: check(a, name))
        save()
    if a.views:
        stage(result, "compare", lambda: render(a, result["export"]["glb"]))
        save()


if __name__ == "__main__":
    require_root()
    main()
