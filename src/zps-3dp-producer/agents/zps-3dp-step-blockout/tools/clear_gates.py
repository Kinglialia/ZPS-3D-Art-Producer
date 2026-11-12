"""Remove the gate JSON of earlier builds, so only the gates of the final build count.

Usage: python3 tools/clear_gates.py --work <dir>
Deletes <dir>/review/gates/*.json and nothing else. Run it before the last pass of gates.py over every part.
Prints one line. Exit 0.
"""
import argparse
import glob
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "scripts"))
from root_guard import require_root  # noqa: E402

NAME = "[blockout/clear_gates]"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    old = glob.glob(os.path.join(ap.parse_args().work, "review", "gates", "*.json"))
    for path in old:
        os.remove(path)
    print(f"{NAME} {len(old)} gate JSON removed")


if __name__ == "__main__":
    require_root()
    main()
