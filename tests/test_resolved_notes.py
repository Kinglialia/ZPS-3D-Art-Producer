"""D27.8: a later worker names the notes of an earlier step it did (RESOLVED_NOTES); its reviewer confirms them
(RESOLVED_CONFIRMED). Pilot run: the README kept "3 board rows on the back" open after the model step built them."""
import json

from flowkit import A, AID, Flow, counts, mf
from shared import pilot_project, report

MINOR = "blocker=0; major=0; minor=2; preference=0; unclear=0"


def to_model(root):
    f = Flow(root)
    pilot_project(root)
    f.p("intake", AID)
    f.p("ready", AID)
    f.work("b1")
    f.review("b1", verdict="PASS", counts=counts(), top_fix=None)
    f.human("approve b1", "đạt", "--action", "approve")
    f.work("vf1")
    f.review("vf1", verdict="PASS", counts=counts(), top_fix=None)
    f.work("vr1")
    f.review("vr1", verdict="PASS", counts=MINOR, top_fix=None,
             findings=[mf(1, "note_texture", "back: 3 hàng ván", "minor"), mf(2, "note_texture", "left: rêu", "minor")])
    f.human("approve vr1", "đạt", "--action", "approve")
    return f


def test_the_model_worker_is_asked_which_notes_it_did_and_its_reviewer_confirms_only_those(tmp_path):
    f = to_model(tmp_path)
    f.work("m1", extra="RESOLVED_NOTES: views_rest v1 F1\n")
    assert "RESOLVED_NOTES: <ghi chú bạn đã làm, trong: views_rest v1 F1, views_rest v1 F2> | none" in (
        f.cp["m1 brief"]["text"].splitlines())
    out = f.brief("m1 review brief")
    rows = f.cp["m1 review brief"]["text"].splitlines()
    assert ("RESOLVED_CONFIRMED: <mục có bằng chứng trên ảnh, trong RESOLVED_NOTES: views_rest v1 F1> | none" in rows,
            "- Ghi chú bước trước worker ghi đã làm (RESOLVED_NOTES): views_rest v1 F1; region, acceptance trong "
            f"`{A}/views_rest/v1/findings.json`." in rows) == (True, True)
    assert max(len(f.cp[k]["text"].replace(str(tmp_path.resolve()), "").encode()) for k in ("m1 brief", "m1 review brief")
               ) < 4352
    rep = tmp_path / out["report"]
    body = dict(verdict="PASS", counts=counts(), top_fix=None, evidence="lit_34_front.png")
    rep.write_text(report(**body, extra="RESOLVED_CONFIRMED: views_rest v1 F2\n"), encoding="utf-8")
    assert f.p("ingest", AID, ok=False) == (
        f"LỖI: {A}/model/v1/review-out.md sai contract: RESOLVED_CONFIRMED views_rest v1 F2 không có trong "
        "RESOLVED_NOTES của worker\n")
    rep.write_text(report(**body, extra="RESOLVED_CONFIRMED: views_rest v1 F1\n"), encoding="utf-8")
    f.p("ingest", AID)
    doc = json.loads((tmp_path / A / "model/v1/findings.json").read_text(encoding="utf-8"))
    assert doc["resolved_notes"] == ["views_rest v1 F1"]

