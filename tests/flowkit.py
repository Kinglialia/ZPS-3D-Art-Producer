"""Drive the real CLI with fake agents through all five steps. The model step writes a real GLB (the box of glbkit), so
the Meshy wrapper and its fake HTTP layer see a valid mesh; the texture worker calls meshy_call.py for real."""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import glbkit
from shared import PILOT, finding, fixed_line, judged_all, pilot_project, report, run

AID = "pilot-house"
A = f"production/assets/{AID}"
FAKE_MESHY = Path(__file__).parent / "texture" / "fake_meshy"
PROJECT_KEY, SHELL_KEY = "msy-project-0123456789", "msy-shell-9876543210"
OUTPUTS = {
    "blockout": ("part_graph.json", "parts_lib.py", "assembled.glb", "sources.json", "blockout.md"),
    "views": ("front.png", "back.png", "left.png", "right.png", "top.png", "guides/views.json", "bg_color.json",
              "README.md", "report/report.json", "report/VIEWS.md", "report/VIEWS_sheet.png"),
    "model": (f"{AID}.blend", "part_graph.json", "parts_lib.py", "spec.json", "model.md", "review/model_sheet.png",
              "review/renders/renders.json"),
    "texture": ("albedo_2048.png", "notes.md", "final_lit_vs_concept.png", "review/renders.json",
                "review/checks/tex_measure.json"),
    "assemble": ("README.md", f"model/{AID}.glb", f"model/{AID}.blend", "texture/albedo_2048.png", "texture/notes.md",
                 "review/compare.json"),
}


RESULTS = {
    "blockout": tuple(f"review/checks/{k}.json" for k in ("inputs", "schema", "materials", "layout", "base", "markers",
                                                          "support", "proportion")),
    "views": ("review/checks/measure.json", "review/checks/package.json"),
    "model": ("review/join.json", "review/unwrap.json", *(f"review/checks/{k}.json" for k in (
        "detail", "mesh", "uv_edge", "qa_mesh_check", "qa_uv_check", "qa_export_check", "qa_screen_tris_check"))),
    "texture": ("review/checks/inputs.json",),
}
RESULT_DIRS = ("review/checks/", "review/gates/")


def put(final: Path, o: str, text: str):
    """One output of a fake worker. A result JSON (D36.4) is a valid pass: failed_checks reads every one of them."""
    p = final / o
    p.parent.mkdir(parents=True, exist_ok=True)
    result = o.startswith(RESULT_DIRS) or o in ("review/join.json", "review/unwrap.json")
    p.write_text(json.dumps({"tool": "fake", "overall": "pass", "checks": []}) if result else text, encoding="utf-8")


def put_all(final: Path, step: str, outputs, name: str, tag: str = "", files: bool = True):
    for o in (*outputs, *RESULTS.get(step, ())):
        put(final, o, f"{o} {name}{tag}\n")
    if step == "blockout" and final.name == "final":
        blockout_files(final, name, tag, files=files)


def blockout_files(final: Path, name: str, tag: str = "", roof_h: float | None = None, files: bool = True):
    """The files of a blockout that pass gate_all.py: the pilot graph and the sources.json init_sources.py writes for the
    pilot card. Ingest runs gate_all for real (L15), so the placeholder text of the other steps would fail check_schema.
    roof_h 1.3 makes the built height 8 % over the card (layout.bbox fails)."""
    g = json.loads((PILOT / "part_graph.json").read_text(encoding="utf-8"))
    if roof_h:
        g["params"]["roof_h"] = roof_h
    (final / "part_graph.json").write_text(json.dumps(g), encoding="utf-8")
    d = Path(final).parents[5] / "concepts/_approved" / AID
    card, mat = d / "asset-card.yaml", d / f"{AID}.material.md"
    sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()  # noqa: E731
    (final / "sources.json").write_text(json.dumps({
        "files": {"layout": str(card), "layout_sha256": sha(card), "material": str(mat), "material_sha256": sha(mat)}
        if files else {"layout": "", "layout_sha256": "x", "material": "", "material_sha256": "x"},
        "layout": {"w": 4, "d": 4, "h": 3.7, "includes_base": True, "source": "asset-card.yaml size_m"},
        "character_h": 1.6, "door_h": 1.8, "door_h_source": "asset-card.yaml scale_overrides cửa height_m",
        "materials": ["STONE", "TIMBER", "TEAL"], "camera": {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40}}),
        encoding="utf-8")
    for o in ("parts_lib.py", "assembled.glb", "blockout.md"):
        (final / o).write_text(f"{o} {name}{tag}\n", encoding="utf-8")


def counts(blocker=0, major=0):
    return f"blocker={blocker}; major={major}; minor=0; preference=0; unclear=0"


def brief_lines(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}: (.+)$", text, re.M)
    return m.group(1) if m else None


class Flow:
    def __init__(self, root: Path):
        self.root, self.cp, self.sent = root, {}, None

    def p(self, *args, ok=True):
        return run(self.root, *args, ok=ok)

    def st(self):
        return json.loads((self.root / A / "status.json").read_text(encoding="utf-8"))

    def keep(self, name, out, **kw):
        self.cp[name] = {"out": out, "st": self.st(), **kw}

    def lost(self):
        """The agent of the open dispatch is gone. `P brief` prints the stored line while an agent is out (C13), so a test
        that needs a new brief ends the dispatch first, as a stop or a stall does."""
        p = self.root / A / "status.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        for rec in st["dispatches"]:
            if "ingested" not in rec and "ended" not in rec:
                rec["ended"] = rec["at"]
        p.write_text(json.dumps(st), encoding="utf-8")

    def brief(self, name):
        """D30.5: a feedback that moved the asset already printed the next dispatch (or the texture gate's stop line)."""
        raw, self.sent = self.sent or self.p("brief", AID), None
        try:
            out = json.loads(raw)
        except ValueError:
            self.keep(name, raw)
            return None
        text = (self.root / out["brief"]).read_text(encoding="utf-8") if out.get("brief") else None
        self.keep(name, out, text=text)
        return out

    def outputs(self, vd: Path, step: str, name: str, mesh_size=(1.0, 1.0, 1.0)):
        put_all(vd / "final", step, OUTPUTS[step], name)
        if step == "model":
            glbkit.write(vd / "final" / f"{AID}-untextured.glb", *glbkit.box(mesh_size))
        if step == "texture":
            used = "paint" if "MODE: VẼ MỚI" in (self.cp[name + " brief"]["text"] or "") else "meshy"
            (vd / "final/texture_spec.json").write_text(json.dumps({"proposed": "meshy", "used": used}), encoding="utf-8")
        if step == "assemble":
            (vd / "final/review/compare.json").write_text(json.dumps({"tris": 12}), encoding="utf-8")

    def meshy(self, name, vd: Path, mode=""):
        text = self.cp[name + " brief"]["text"]
        model = self.root / A / f"model/v{self.st()['approved']['model']}/final/{AID}-untextured.glb"
        env = {**os.environ, "PYTHONPATH": str(FAKE_MESHY), "FAKE_MESHY_LOG": str(self.root / "meshy.jsonl"),
               "FAKE_MESHY_MODE": mode, "MESHY_API_KEY": SHELL_KEY}
        cmd = [sys.executable, brief_lines(text, "MESHY"), "texture", *shlex.split(brief_lines(text, "MESHY_ARGS")),
               "--model", str(model), "--style-image", str(self.root / "concepts/_approved" / AID / "concept_albedo.png"),
               "--out", str(vd / "work/meshy/call-1")]
        r = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, env=env)
        self.cp[name + " meshy"] = {"rc": r.returncode, "out": r.stdout}

    def work(self, name, issues="none", meshy=None, unfixable=False, mesh_size=(1.0, 1.0, 1.0), extra="", fixed=True):
        """fixed: a fix round names every open finding of its base in FIXED, so its review is `full` (D31.2)."""
        out = self.brief(name + " brief")
        vd = (self.root / out["report"]).parent
        step = self.st()["stage"]
        if meshy is not None:
            self.meshy(name, vd, meshy)
        self.outputs(vd, step, name, mesh_size)
        ph = brief_lines(self.cp[name + " brief"]["text"], "PROFILE_HASH")
        (self.root / out["report"]).write_text(
            f"STATUS: DONE\nRUBRIC: mass=pass\nISSUES: {issues}\nPROFILE_HASH: {ph}\n"
            + ("UNFIXABLE: yes\n" if unfixable else "") + (fixed_line(self.root, AID) if fixed else "") + extra,
            encoding="utf-8")
        self.keep(name + " worker", self.p("ingest", AID, "--agent-id", f"w-{name}"))

    def review(self, name, evidence="lit_34_front.png, albedo_2048.png, tex_measure.json", **kw):
        out = self.brief(name + " review brief")
        rep = self.root / out["report"]
        rep.write_text(judged_all(rep, report(**{"evidence": evidence, "rubric": "mass=pass"} | kw)), encoding="utf-8")
        self.keep(name + " review", self.p("ingest", AID))

    def assemble(self, name, fail=None):
        out = self.brief(name + " brief")
        vd = (self.root / out["report"]).parent
        self.outputs(vd, "assemble", name)
        ph = shlex.split(out["command"])[-1]
        head = (f"STATUS: BLOCKED\nOUTPUT: {vd}/final/\nISSUES: {fail}\nPROFILE_HASH: {ph}\n" if fail else
                f"STATUS: DONE\nOUTPUT: {vd}/final/\nISSUES: none\nPROFILE_HASH: {ph}\n")
        body = ("EVIDENCE_OPENED: work/evidence/compare.json\nFINDINGS:\n" + finding(
            "F1", "blocker", "compare", region="34_front", viewing_condition="unlit, 512 px",
            evidence="work/evidence/compare.json: mean_abs 41.2", consequence="GLB trong engine khác render bước texture",
            repair="kiểm color space của albedo", preserve="mesh đã khóa", acceptance="compare.34_front mean_abs ≤ 6")
                + "\n" if fail else "EVIDENCE_OPENED: work/evidence/compare.json\nFINDINGS: none\n")
        (self.root / out["report"]).write_text(head + body, encoding="utf-8")
        self.keep(name + " ingest", self.p("ingest", AID))

    def human(self, name, *args, ok=True):
        out = self.p("feedback", AID, *args, ok=ok)
        self.keep(name, out)
        self.sent = out.split("\n", 1)[1] if ok and out.count("\n") > 1 else None


def to_texture(root: Path, env_line=f"MESHY_API_KEY={PROJECT_KEY}\n", prepare=None) -> Flow:
    """Blockout, views and model approved with one round each. D30.5: the model approval dispatches the texture step
    at once (the texture gate runs there), so `prepare` changes the project before that approval."""
    f = Flow(root)
    pilot_project(root)
    if env_line is not None:
        (root / ".env").write_text(env_line, encoding="utf-8")
    f.p("intake", AID)
    f.p("ready", AID)
    for name, human in (("b1", True), ("v1", True), ("m1", True)):
        f.work(name)
        f.review(name, verdict="PASS", counts=counts(), top_fix=None)
        if name == "m1" and prepare:
            prepare()
        if human:
            f.human(f"approve {name}", "đạt", "--action", "approve")
    return f


def mf(n, kind, region, prio="major", evidence="lit_34_front.png: lệch"):
    return finding(f"F{n}", prio, kind, region=region, evidence=evidence)
