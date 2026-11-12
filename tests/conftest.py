import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer" / "scripts"
P = SCRIPTS / "producer.py"
sys.path.insert(0, str(SCRIPTS))

PROFILE = {
    "project": "Pilot", "preset": "topdown-mobile-lowpoly",
    "paths": {"approved": "concepts/_approved", "production": "production", "deliver": "deliver", "env_file": ".env"},
    "has_map": False, "pilot_asset": None,
    "scale_refs": [{"name": "nhân vật", "height_m": 1.6, "_source": "anh chốt 2026-11-09"}],
    "hidden_side_rules": ["tường trơn"],
    "style": {"light_convention": "unlit_flat", "top_vs_side_L": 0, "view_bg": None},
    "texture_simple": {"max_materials": 2, "max_color_clusters": 6},
}
PROFILE_HASH = "786cfc66bdd2"
# Claude Code refuses a subagent Write to a file of this name: https://github.com/anthropics/claude-code/issues/44657
SUBAGENT_WRITE_BLOCKED = re.compile(r"^(report|summary|findings|analysis).*\.md$", re.I)


def write_profile(root, profile=None):
    (Path(root) / "production/PROJECT-PROFILE.yaml").write_text(
        yaml.safe_dump(PROFILE if profile is None else profile, allow_unicode=True, sort_keys=False), encoding="utf-8")


PILOT = Path(__file__).parent / "fixtures/pilot"


def pilot_project(root: Path):
    import shutil
    run(root, "init", "--project", "Pilot", "--concepts", "concepts")
    shutil.copytree(PILOT / "_approved", root / "concepts/_approved", dirs_exist_ok=True)
    shutil.copy(PILOT / "PROJECT-PROFILE.yaml", root / "production/PROJECT-PROFILE.yaml")


def blockout_only(root):
    """GĐ 1 tests drive one step; turning views off keeps `done_enabled` right after blockout."""
    p = Path(root) / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "views"\n', 'id = "views"\nenabled = false\n', 1),
                 encoding="utf-8")


def views_only(root):
    """GĐ 2 tests end at the view set; turning model off keeps `done_enabled` right after views."""
    p = Path(root) / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "model"\n', 'id = "model"\nenabled = false\n', 1),
                 encoding="utf-8")


def model_only(root):
    """GĐ 3 tests end at DUYỆT 1; turning texture off keeps `done_enabled` right after model."""
    p = Path(root) / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('id = "texture"\n', 'id = "texture"\nenabled = false\n', 1),
                 encoding="utf-8")


def brief_hash(text: str) -> str:
    return re.search(r"^PROFILE_HASH: ([0-9a-f]{12})$", text, re.M).group(1)


def run(cwd, *args, ok=True):
    r = subprocess.run([sys.executable, str(P), *args], cwd=cwd, capture_output=True, text=True)
    assert (r.returncode == 0) is ok, r.stderr
    return r.stdout if ok else r.stderr


def finding(fid="F1", prio="major", kind="structure", evidence="clay_front: mái thấp 0.4 m", **over):
    f = {"region": "mái", "viewing_condition": "front ortho, 512 px", "evidence": evidence,
         "consequence": "sai silhouette", "confidence": "high", "repair": "nâng mái 0.3 m",
         "preserve": "chiều cao tường", "acceptance": "đỉnh mái 3.2 m trên clay_front"} | over
    rows = [("region", "viewing_condition", "evidence"), ("consequence", "confidence"), ("repair", "preserve", "acceptance")]
    body = ["  " + " | ".join(f"{k}: {f[k]}" for k in row if k in f) for row in rows]
    return "\n".join([f"- {fid} [{prio}] {kind}", *[b for b in body if b.strip()]])


def fixed_line(root, aid) -> str:
    """D31.2: a fake fix-round worker names every open finding of its base in FIXED, so its review is `full` and a PASS
    passes, as before review scopes; tests of the `fix` scope write FIXED themselves."""
    import json
    a = Path(root) / "production/assets" / aid
    st = json.loads((a / "status.json").read_text(encoding="utf-8"))
    p = a / st["stage"] / f"v{st.get('fix_base')}" / "findings.json"
    ids = [i for i, f in json.loads(p.read_text(encoding="utf-8"))["findings"].items()
           if f["status"] in ("open", "regressed")] if st.get("fix_base") and p.is_file() else []
    return f"FIXED: {', '.join(ids)}\n" if ids else ""


def report(verdict="FIX", counts=None, top_fix="structure: F1", evidence="clay_front.png, clay_side.png", rubric="massing=fail",
           findings=(), prior=(), compare=None, pick=None, extra=""):
    lines = [f"VERDICT: {verdict}", f"RUBRIC: {rubric}"]
    if counts:
        lines.append(f"COUNTS: {counts}")
    if top_fix:
        lines.append(f"TOP_FIX: {top_fix}")
    lines.append(f"EVIDENCE_OPENED: {evidence}")
    if compare:
        lines.append(f"COMPARE: {compare}")
    if pick:
        lines.append(f"PICK: {pick}")
    lines += ["FINDINGS:", *findings]
    if prior:
        lines += ["PRIOR:", *prior]
    return "\n".join(lines) + "\n" + extra


def judged_all(report_path, text: str) -> str:
    """The text of a fake reviewer that judged every key of the step's rubric section: a key the test does not name is
    pass."""
    vd = Path(report_path).parent
    rubric, line = vd.parents[1] / "rubric.md", re.search(r"^RUBRIC: (.*)$", text, re.M)
    if not (line and rubric.is_file()):
        return text
    m = re.search(rf"^## {re.escape(vd.parent.name)}[ \t]*$(.*?)(?=^## |\Z)", rubric.read_text(encoding="utf-8"), re.M | re.S)
    named = {kv.split("=")[0].strip() for kv in line.group(1).split(";")}
    add = [f"{k}=pass" for k in re.findall(r"^- ([a-z0-9_]+):", m.group(1) if m else "", re.M) if k not in named]
    return text.replace(line.group(0), "; ".join([line.group(0), *add]), 1) if add else text


@pytest.fixture(scope="session", autouse=True)
def project_cwd(tmp_path_factory):
    """D30.12: a tool that writes runs only from a project root, so a test that runs one without `cwd=` runs it from
    an empty project, not from the repo. Session scope: module fixtures run their tools before function fixtures."""
    d = tmp_path_factory.mktemp("cwd")
    (d / "production").mkdir()
    (d / "production/pipeline.toml").touch()
    old, root = os.getcwd(), os.environ.pop("PRODUCER_ROOT", None)
    os.chdir(d)
    yield d
    os.chdir(old)
    if root is not None:
        os.environ["PRODUCER_ROOT"] = root


sys.modules["shared"] = sys.modules[__name__]  # tests/blockout/conftest.py also claims the module name `conftest`
