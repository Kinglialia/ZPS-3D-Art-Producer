"""Stand-in for the `codex` CLI: tests never call the real one. Behaviour per FAKE_CODEX_MODE:
ok | small | home | home_two | none | fail:<n> (first n calls report an error, then ok) | slow:<s> (sleep, then ok) |
hang_after_image (saves under CODEX_HOME, never returns) | error_with_bystander (reports an error; another asset's image
sits under CODEX_HOME) | ok_but_error (valid image, result.json also carries an error) | truncated (cut-off PNG).
Logs each call to FAKE_CODEX_LOG."""
import io
import json
import os
import re
import shlex
import sys
import time
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
    pid_base = Path(os.environ["FAKE_CODEX_PID_FILE"])
    own = sorted(pid_base.parent.glob(f"{pid_base.stem}-{os.getppid()}.pid"))
    entry = {"argv": sys.argv[1:], "prompt": prompt, "ppid": os.getppid(),
             "api_keys": sorted(k for k in os.environ if k.endswith("_API_KEY")),
             "pid_file": own[0].read_text(encoding="utf-8").strip() if own else None,
             "pid_name": own[0].name if own else None}
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
    home = Path(os.environ.get("CODEX_HOME", "")) / "generated_images" / "sess"
    if mode.startswith("slow:"):
        time.sleep(float(mode[5:]))
    if mode == "hang_after_image":
        home.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (10, 120, 200)).save(home / "img.png")
        time.sleep(60)
    if mode == "error_with_bystander":
        home.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (1, 1, 1)).save(home / "other-asset.png")
        result.write_text(json.dumps({"path": None, "width": 0, "height": 0, "error": "content policy"}))
        return
    if mode == "truncated":
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (5, 5, 5)).save(buf, "PNG")
        out.write_bytes(buf.getvalue()[:300])
        result.write_text(json.dumps({"path": str(out), "width": w, "height": h, "error": None}))
        return
    if mode == "home_two":
        home.mkdir(parents=True, exist_ok=True)
        for name in ("a.png", "b.png"):
            Image.new("RGB", (w, h), (10, 120, 200)).save(home / name)
        return
    if mode == "small":
        w = h = 1024
    if mode == "home":
        d = Path(os.environ["CODEX_HOME"]) / "generated_images" / "sess"
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (10, 120, 200)).save(d / "img.png")
        return
    Image.new("RGB", (w, h), (200, 120, 10)).save(out)
    result.write_text(json.dumps({"path": str(out), "width": w, "height": h,
                                  "error": "could not confirm size" if mode == "ok_but_error" else None}))


if __name__ == "__main__":
    main()
