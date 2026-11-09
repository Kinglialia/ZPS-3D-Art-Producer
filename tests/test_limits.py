import os
import subprocess
from argparse import Namespace

import pytest

from shared import write_profile
from core import briefs, intake, limits
from core.state import load_cfg, load_st, save_st


def dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


@pytest.fixture
def proj(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    intake.init(Namespace(project="Pilot", concepts="concepts"))
    write_profile(tmp_path)
    p = tmp_path / "production/pipeline.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("blender = 2", "blender = 1"), encoding="utf-8")
    for aid, prio in (("a-hut", 1), ("b-barn", 2)):
        intake.new(Namespace(id=aid, title=aid, type="asset", priority=prio, deadline=None), load_cfg())
        intake.ready(Namespace(ids=[aid]))
    capsys.readouterr()
    return tmp_path


def pid_file(root, name, pid):
    d = root / "production/pids/blender"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.pid").write_text(f"{pid}\n", encoding="utf-8")


def next_lines(capsys):
    limits.show_next(Namespace(session=False))
    return [l for l in capsys.readouterr().out.splitlines() if l.startswith("[")]


def test_slots_count_live_pid_files_only_so_a_crashed_blender_job_frees_its_slot(proj):
    pid_file(proj, "x-live", os.getpid())
    pid_file(proj, "y-dead", dead_pid())
    (proj / "production/pids/blender/z-junk.pid").write_text("not a pid", encoding="utf-8")
    assert (limits.used("blender"), limits.used("meshy")) == (1, 0)


def test_next_offers_dispatch_only_while_a_slot_is_free_and_counts_its_own_offers(proj, capsys):
    assert next_lines(capsys) == ["[a-hut] blockout/todo → giao worker → `brief a-hut`",
                                  "[b-barn] blockout/todo → chờ slot blender"]
    pid_file(proj, "x-live", os.getpid())
    assert next_lines(capsys)[0] == "[a-hut] blockout/todo → chờ slot blender"


def test_a_running_asset_without_a_blender_process_holds_no_slot(proj, capsys):
    briefs.run(Namespace(id="a-hut"))
    pid_file(proj, "a-hut", dead_pid())
    assert next_lines(capsys) == ["[a-hut] blockout/running → đang chờ subagent (mất kết nối thì `brief a-hut` để giao lại)",
                                  "[b-barn] blockout/todo → giao worker → `brief b-barn`"]


def test_worker_brief_tells_the_worker_where_to_write_the_blender_pid(proj, capsys):
    briefs.run(Namespace(id="a-hut"))
    text = (proj / "production/assets/a-hut/blockout/v1/brief-worker.md").read_text(encoding="utf-8")
    assert ("- Mỗi lệnh Blender: `<lệnh> & echo $! > production/pids/blender/a-hut.pid; wait $!; "
            "rm -f production/pids/blender/a-hut.pid`.") in text.splitlines()
    assert (proj / "production/pids/blender").is_dir()


def test_done_enabled_counts_as_finished_in_next(proj, capsys):
    for aid in ("a-hut", "b-barn"):
        st = load_st(aid)
        st["state"] = "done_enabled"
        save_st(st)
    limits.show_next(Namespace(session=False))
    assert capsys.readouterr().out.splitlines()[0].startswith("0 asset đang chạy · 2 done · ")
