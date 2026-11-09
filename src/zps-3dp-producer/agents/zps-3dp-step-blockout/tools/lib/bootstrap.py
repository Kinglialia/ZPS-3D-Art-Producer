"""Make tools/setup_deps.sh's packages importable inside Blender's own Python. Stdlib only.

Blender's bundled Python cannot see a venv. setup_deps.sh installs the third-party packages the
Blender-side scripts need (pyyaml, trimesh, opencv-python-headless, scipy, xatlas, Pillow; never
numpy, which Blender bundles) into tools/.deps/blender-py<major><minor>/. Importing this module
puts that folder first on sys.path when it exists for the running interpreter's version.
Every Blender-side entry script imports it before any third-party import:

    sys.path.insert(0, os.path.join(<script dir>, "..", "lib"))
    import bootstrap  # noqa: E402,F401
"""
import os
import sys

TOOLS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def deps_dir(version=None):
    major, minor = version or sys.version_info[:2]
    return os.path.join(TOOLS_ROOT, ".deps", f"blender-py{major}{minor}")


def setup():
    """Insert deps_dir() at sys.path[0] when it exists; returns it, or None."""
    d = deps_dir()
    if not os.path.isdir(d):
        return None
    if d in sys.path:
        sys.path.remove(d)
    sys.path.insert(0, d)
    return d


DEPS = setup()
