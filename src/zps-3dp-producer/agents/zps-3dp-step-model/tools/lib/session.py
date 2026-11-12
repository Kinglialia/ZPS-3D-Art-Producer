"""Run the main() of several tools in one Blender session (D37.4). Each tool reads sys.argv and may call sys.exit, so the
driver sets sys.argv per stage and catches SystemExit. Pure Python."""
import os
import sys

import common


def call(main, *argv):
    """main() with sys.argv as `blender -- argv`; its sys.exit ends that stage, not the session."""
    saved, sys.argv = sys.argv, ["blender", "--", *map(str, argv)]
    try:
        main()
    except SystemExit:
        pass
    finally:
        sys.argv = saved


def ok(result):
    """True when the result JSON exists and its overall is neither fail nor error."""
    try:
        return common.read_json(result)["overall"] not in ("fail", "error")
    except (OSError, ValueError, KeyError):
        return False


def stage(main, result, *argv):
    """Run one stage. A result JSON of an earlier run never counts: it is removed first. Returns ok(result)."""
    if os.path.isfile(result):
        os.remove(result)
    call(main, *argv)
    return ok(result)
