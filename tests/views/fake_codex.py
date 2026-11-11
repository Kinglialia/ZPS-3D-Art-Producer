"""Stand-in for the `codex` CLI: tests never call the real one. Behaviour per FAKE_CODEX_MODE:
ok | small | home | home_two | none | fail:<n> (first n calls report an error, then ok) | slow:<s> (sleep, then ok) |
hang_after_image (saves under CODEX_HOME, never returns) | error_with_bystander (reports an error; another asset's image
sits under CODEX_HOME) | ok_but_error (valid image, result.json also carries an error) | truncated (cut-off PNG) |
jpeg (JPEG bytes at the .png path) | home_jpeg (a JPEG under CODEX_HOME) | break_once:<name> | miss_once:<name> |
fail_for:<name> (that file always reports an error).
Each mode applies to every OUTPUT_PATH of the prompt. An --image file that does not exist exits 1, as codex does.
Logs each call to FAKE_CODEX_LOG with the parsed image list and the output names.
FAKE_CODEX_MODEL set: prints the `codex exec` header with that `model:` line on stderr.
`codex --version` prints FAKE_CODEX_VERSION (default codex-cli 0.164.0). `codex exec --help` prints the option lines of
the real codex-cli 0.164.0 help, without the flags in FAKE_CODEX_HELP_DROP (comma-separated). Neither call is logged."""
import io
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

HELP = """Run Codex non-interactively

Usage: codex exec [OPTIONS] [PROMPT]

Options:
  -c, --config <key=value>
  -i, --image <FILE>...
  -m, --model <MODEL>
  -s, --sandbox <SANDBOX_MODE>
          [possible values: read-only, workspace-write, danger-full-access]
      --approve-for-me
      --dangerously-bypass-approvals-and-sandbox
  -C, --cd <DIR>
      --skip-git-repo-check
  -h, --help
  -V, --version
"""


def install(bin_dir: Path) -> str:
    """Write `codex` into bin_dir and return a PATH where only this fake can be found."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "codex"
    exe.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(__file__)} \"$@\"\n")
    exe.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def main():
    if sys.argv[1:] == ["--version"]:
        print(os.environ.get("FAKE_CODEX_VERSION", "codex-cli 0.164.0"))
        return
    if sys.argv[1:] == ["exec", "--help"]:
        drop = [f for f in os.environ.get("FAKE_CODEX_HELP_DROP", "").split(",") if f]
        print("\n".join(l for l in HELP.splitlines() if not any(re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", l)
                                                            for f in drop)))
        return
    prompt = sys.stdin.read()
    log = Path(os.environ["FAKE_CODEX_LOG"])
    calls = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    pid_base = Path(os.environ["FAKE_CODEX_PID_FILE"])
    own = sorted(pid_base.parent.glob(f"{pid_base.stem}-{os.getppid()}.pid"))
    images = image_args(sys.argv[2:])
    jobs = list(zip(re.findall(r"^OUTPUT_PATH: (.+)$", prompt, re.M), re.findall(r"^RESULT_PATH: (.+)$", prompt, re.M)))
    entry = {"argv": sys.argv[1:], "prompt": prompt, "ppid": os.getppid(), "images": images,
             "outs": [Path(o).name for o, _ in jobs],
             "api_keys": sorted(k for k in os.environ if k.endswith("_API_KEY")),
             "pid_file": own[0].read_text(encoding="utf-8").strip() if own else None,
             "pid_name": own[0].name if own else None}
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    if missing := [i for i in images if not Path(i).is_file()]:
        sys.exit(f"Error: failed to read image {missing[0]}")
    if os.environ.get("FAKE_CODEX_MODEL"):
        print(f"OpenAI Codex v0.0.0\n--------\nworkdir: {os.getcwd()}\nmodel: {os.environ['FAKE_CODEX_MODEL']}\n"
              "provider: openai\n--------", file=sys.stderr)
    w, h = map(int, re.search(r"^SIZE: (\d+)x(\d+)$", prompt, re.M).groups())
    mode = os.environ.get("FAKE_CODEX_MODE", "ok")
    for out, result in jobs:
        before = sum(Path(out).name in c["outs"] for c in calls)
        make(Path(out), Path(result), w, h, mode, len(calls), before)


def image_args(argv: list[str]) -> list[str]:
    """`--image=<f>` takes one file; `-i`/`--image` followed by files takes each value up to the next option."""
    out, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--image="):
            out.append(a.split("=", 1)[1])
        elif a in ("-i", "--image"):
            while i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                i += 1
                out.append(argv[i])
        i += 1
    return out


def make(out: Path, result: Path, w: int, h: int, mode: str, n_calls: int, before: int):
    """One OUTPUT_PATH of the call. before = earlier calls that asked for this file. break_once:<name> and
    miss_once:<name> cut off or skip that file on its first call only."""
    from PIL import Image
    if (mode.startswith("fail:") and n_calls < int(mode[5:])) or mode == f"fail_for:{out.name}":
        result.write_text(json.dumps({"path": None, "width": 0, "height": 0, "error": "quota exceeded"}))
        return
    if mode == "none" or (mode == f"miss_once:{out.name}" and before == 0):
        return
    if mode == f"break_once:{out.name}" and before == 0:
        mode = "truncated"
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
    if mode == "jpeg":
        Image.new("RGB", (w, h), (200, 120, 10)).save(out, "JPEG")
        return
    if mode == "home_two":
        home.mkdir(parents=True, exist_ok=True)
        for name in ("a.png", "b.png"):
            Image.new("RGB", (w, h), (10, 120, 200)).save(home / name)
        return
    if mode == "small":
        w = h = 1024
    if mode in ("home", "home_jpeg"):
        home.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (10, 120, 200)).save(home / ("img.jpg" if mode == "home_jpeg" else "img.png"),
                                                       quality=100)
        return
    Image.new("RGB", (w, h), (200, 120, 10)).save(out)
    result.write_text(json.dumps({"path": str(out), "width": w, "height": h,
                                  "error": "could not confirm size" if mode == "ok_but_error" else None}))

if __name__ == "__main__":
    main()
