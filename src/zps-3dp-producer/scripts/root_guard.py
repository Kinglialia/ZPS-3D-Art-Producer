"""A tool that writes files runs only from the project root (D27.7, D30.12). Standard library only: the Blender-run
tools import it too. The project root is the folder whose `production/pipeline.toml` (`$PRODUCER_ROOT/pipeline.toml`)
`producer.py init` made."""
import os
import sys

MARK = os.path.join(os.environ.get("PRODUCER_ROOT", "production"), "pipeline.toml")


def require_root():
    """Exit 2 before any write when the working folder is not the project root."""
    if not os.path.isfile(MARK):
        sys.stderr.write(f"LỖI: không thấy {MARK}: chạy lệnh từ gốc project\n")
        sys.exit(2)
