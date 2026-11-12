"""Join and unwrap in one Blender session (D37.4). Runs in Blender.

Usage: BLENDER -b --python tools/build_model.py -- --final F
Calls the main of join_mesh.py, then the main of unwrap.py, each as it runs alone: F/review/join.json and
F/review/unwrap.json, F/<id>.blend and F/<id>-untextured.glb are the files those tools write.
The unwrap needs the joined mesh, so it runs only when join.json is not fail or error. Both result files of an earlier
run are removed first, so a failed join leaves no old unwrap.json behind.
Exit 0 when both stages pass, 1 otherwise.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "lib")]
sys.path.append(os.path.join(HERE, "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402


def main():
    import common
    import join_mesh
    import session
    import unwrap
    p = common.make_parser(__doc__)
    p.add_argument("--final", required=True)
    final = p.parse_args(common.script_argv()).final
    review = os.path.join(final, "review")
    unwrap_json = os.path.join(review, "unwrap.json")
    if os.path.isfile(unwrap_json):
        os.remove(unwrap_json)
    done = session.stage(join_mesh.main, os.path.join(review, "join.json"), "--final", final)
    done = done and session.stage(unwrap.main, unwrap_json, "--final", final)
    sys.exit(0 if done else 1)


if __name__ == "__main__":
    require_root()
    main()
