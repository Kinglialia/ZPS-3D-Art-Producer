import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "src" / "zps-3dp-producer" / "scripts"
P = SCRIPTS / "producer.py"
sys.path.insert(0, str(SCRIPTS))


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


def report(verdict="FIX", counts="blocker=0; major=1; minor=0; preference=0; unclear=0",
           top_fix="structure: F1", evidence="clay_front.png, clay_side.png", rubric="massing=fail",
           findings=(), prior=(), compare=None, pick=None, extra=""):
    lines = [f"VERDICT: {verdict}", f"RUBRIC: {rubric}", f"COUNTS: {counts}"]
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


sys.modules["shared"] = sys.modules[__name__]  # tests/blockout/conftest.py also claims the module name `conftest`
