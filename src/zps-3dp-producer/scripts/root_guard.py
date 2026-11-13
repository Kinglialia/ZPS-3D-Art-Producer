"""A tool that writes files runs only from the project root (D27.7, D30.12). Standard library only: the Blender-run
tools import it too. The project root is the folder whose `production/pipeline.toml` (`<root>/pipeline.toml`)
`producer.py init` made."""
import json
import os
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# build.py rewrites the skill name and the Claude skills path in the Codex edition; the split keeps the Claude folder.
CLAUDE_SKILL = os.path.join(".claude", "skills", "zps-3dp-" "producer")


def default_root() -> str:
    """PRODUCER_ROOT wins. Without it the Codex edition works in `production-codex` when the Claude edition is installed
    in the same project: the two editions never share a folder, and a session that cannot set an environment variable
    (the Codex desktop app) needs no setup. Every other case is `production`."""
    if os.environ.get("PRODUCER_ROOT"):
        return os.environ["PRODUCER_ROOT"]
    try:
        with open(os.path.join(SKILL, "runtime.json"), encoding="utf-8") as f:
            codex = json.load(f).get("runtime") == "codex"
    except (OSError, ValueError, AttributeError):
        codex = False
    return "production-codex" if codex and os.path.isdir(CLAUDE_SKILL) else "production"


MARK = os.path.join(default_root(), "pipeline.toml")


def require_root():
    """Exit 2 before any write when the working folder is not the project root."""
    if not os.path.isfile(MARK):
        sys.stderr.write(f"LỖI: không thấy {MARK}: chạy lệnh từ gốc project\n")
        sys.exit(2)
