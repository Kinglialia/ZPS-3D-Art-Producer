"""D42.4: a file copied from the kit stays in the skill only while a tool or an agent file of its step calls it.
Copies nobody calls were 5 files in v0.7; the review of 2026-11-11 removed them by hand, this test keeps the rule."""
import re
from pathlib import Path, PurePosixPath

import pytest

from shared import P

AGENTS = P.parents[1] / "agents"
ROW = re.compile(r"^\| `([^`]+)` \| `[^`]+` \| `[0-9a-f]{64}` \|$", re.M)
SCANNED = (".py", ".sh", ".mjs", ".md", ".yaml")
SKIP_DIRS = {".deps", "__pycache__"}
NO_CALLER: dict[tuple[str, str], str] = {}


def copied(agent: Path) -> list[str]:
    """The files of the 'Chép nguyên' table of SOURCE.md, as written there."""
    section = (agent / "SOURCE.md").read_text(encoding="utf-8").split("## Chép nguyên", 1)[1]
    return ROW.findall(re.split(r"^## ", section, maxsplit=1, flags=re.M)[0])


def names(rel: str) -> re.Pattern:
    """How another file names this one: `import m`, `from m import`, `m.py`, the module name in backticks (the model agent
    file lists the QA checks as `mesh_check` and runs `asset_checks/<q>.py`), or the file name of a non-Python file."""
    p = PurePosixPath(rel)
    if p.suffix != ".py":
        return re.compile(re.escape(p.name))
    m = re.escape(p.stem)
    return re.compile(rf"\b(?:import|from)\s+(?:[\w.]*\.)?{m}\b|\b{m}\.py\b|`{m}`")


def callers(agent: Path, rel: str) -> list[str]:
    """Files of the step (tools, agent files, references) that name the copied file, itself and SOURCE.md left out."""
    pat, me = names(rel), (agent / rel).resolve()
    out = []
    for f in sorted(agent.rglob("*")):
        if (f.suffix in SCANNED and f.is_file() and not SKIP_DIRS & set(f.relative_to(agent).parts)
                and f.name != "SOURCE.md" and f.resolve() != me and pat.search(f.read_text(encoding="utf-8"))):
            out.append(f.relative_to(agent).as_posix())
    return out


CASES = [(a.name, rel) for a in sorted(AGENTS.glob("zps-3dp-step-*")) for rel in copied(a)]


def test_every_step_lists_copied_files():
    assert {a for a, _ in CASES} == {p.name for p in AGENTS.glob("zps-3dp-step-*")}


@pytest.mark.parametrize("agent,rel", CASES)
def test_a_copied_kit_file_has_a_caller_in_its_step(agent, rel):
    found = callers(AGENTS / agent, rel)
    if (agent, rel) in NO_CALLER:
        assert not found, f"{rel} has a caller now ({found[0]}): remove its entry from NO_CALLER"
    else:
        assert found, f"{agent}: nothing calls {rel}; remove the copy and its SOURCE.md row, or add a caller (D42.4)"


def test_the_scan_fails_on_a_copied_file_that_nobody_calls(tmp_path):
    """A test that cannot fail proves nothing: the same scan on a step with an unused copy finds no caller."""
    a = tmp_path / "zps-3dp-step-x"
    (a / "tools/lib").mkdir(parents=True)
    (a / "SOURCE.md").write_text("## Chép nguyên\n\n| File | Nguồn kit | sha256 |\n|---|---|---|\n"
                                 f"| `tools/lib/used.py` | `k/used.py` | `{'0' * 64}` |\n"
                                 f"| `tools/lib/dead.py` | `k/dead.py` | `{'1' * 64}` |\n\n## Rút từ kit\n", encoding="utf-8")
    for f in ("used", "dead"):
        (a / f"tools/lib/{f}.py").write_text("X = 1\n", encoding="utf-8")
    (a / "tools/run.py").write_text("from lib import used\n", encoding="utf-8")
    assert copied(a) == ["tools/lib/used.py", "tools/lib/dead.py"]
    assert callers(a, "tools/lib/used.py") == ["tools/run.py"]
    assert callers(a, "tools/lib/dead.py") == []
