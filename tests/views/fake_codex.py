"""Stand-in for the `codex` CLI: tests never call the real one. Behaviour per FAKE_CODEX_MODE:
ok | small | home | none | fail:<n> (first n calls report an error, then ok). Logs each call to FAKE_CODEX_LOG."""
import json
import os
import re
import shlex
import sys
from pathlib import Path


def install(bin_dir: Path) -> str:
    """Write `codex` into bin_dir and return a PATH where only this fake can be found."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "codex"
    exe.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(__file__)} \"$@\"\n")
    exe.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def main():
    from PIL import Image
    prompt = sys.stdin.read()
    log = Path(os.environ["FAKE_CODEX_LOG"])
    calls = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    pid_file = Path(os.environ["FAKE_CODEX_PID_FILE"])
    entry = {"argv": sys.argv[1:], "prompt": prompt, "ppid": os.getppid(),
             "pid_file": pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else None}
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    out = Path(re.search(r"^OUTPUT_PATH: (.+)$", prompt, re.M).group(1))
    result = Path(re.search(r"^RESULT_PATH: (.+)$", prompt, re.M).group(1))
    w, h = map(int, re.search(r"^SIZE: (\d+)x(\d+)$", prompt, re.M).groups())
    mode = os.environ.get("FAKE_CODEX_MODE", "ok")
    if mode.startswith("fail:") and len(calls) < int(mode[5:]):
        result.write_text(json.dumps({"path": None, "width": 0, "height": 0, "error": "quota exceeded"}))
        return
    if mode == "none":
        return
    if mode == "small":
        w = h = 1024
    if mode == "home":
        d = Path(os.environ["CODEX_HOME"]) / "generated_images" / "sess"
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (10, 120, 200)).save(d / "img.png")
        return
    Image.new("RGB", (w, h), (200, 120, 10)).save(out)
    result.write_text(json.dumps({"path": str(out), "width": w, "height": h, "error": None}))


if __name__ == "__main__":
    main()
