# GĐ 6: spec notes for the user

Points the build found in the spec. Each one names the source and what the code does. Nothing in `docs/` outside `docs/intents/`, `docs/EDITIONS.md` and the checklist results was changed.

## Editions and build

1. D24.5 caps every description at 300 characters for Codex. The Producer description had 493, and both editions share `SKILL.md`. Code: one shorter description (297) for both. The trigger quality of the shorter text needs the live eval.
2. D23.2 puts the fixed sentence first in the description of step and check agents. The Producer and Project Setup cannot open with "Chỉ chạy khi Producer giao file brief". Code: the sentence check covers agents only; the 300 cap covers every skill and agent.
3. Codex has no agent definition files like `.claude/agents/`. Code: Codex agents stay in `agents/` of the skill; `P brief` prints `agent_file`, and the adapter passes it to `spawn_agent`. The `tools:` line of an agent file has no effect on Codex.
4. The install root of the Codex edition is `.agents/skills` in the project, from the kit's `~/.agents/skills`. Project-level skills on Codex are not checked by a run.
5. A flat agent install broke `references/` links (GĐ 1 T6.9, GĐ 3 note 27). Code: agent files reach their references through `R` = `T/../references`, and `T` is the absolute `TOOLS:` line of the brief. The build fails on a bare `references/` path or a missing `T/` or `R/` file.
6. `craft.md` of the blockout agent quoted the kit link `[technique](technique.md)`, which the Producer does not ship. Code: the link points at the technique section inside `craft.md`. `craft.md` is a Producer file drawn from the kit, not a byte copy.
7. `templates/agents/` (modeller, reviewer, texturer) and the setup steps for them came from the base skill. Nothing read them. Removed. `setup.md` also named `gate = "none"` and `"human"`, which `load_cfg` refuses; the new text names the three real gates.
8. The kit copies kit skill names into the Codex edition with `-codex`. The Producer build renames only its own skills and agents, so `SOURCE.md` keeps the kit paths. The kit sibling of `P preflight` uses the edition suffix (`zps-3d-artist-codex`).

## Models and tokens (rows 61, 63, 79)

9. D22.9 asks the ledger for the real model per dispatch. The Claude Code Agent tool takes `opus`, `sonnet`, `haiku` and picks the model itself; the script cannot see the model id. Code: the ledger records the name passed to the tool. Codex: no model names were confirmed, so `models` is `null` and the ledger writes "model của phiên". Fill `editions/codex/edition.json` after a live run.
10. Neither runtime is known to report tokens per dispatch. Code: `P ingest --tokens N` stores the number on the last dispatch; `P compare` prints "không có số" when no dispatch has one, and "(thiếu k lần)" when some miss.

## Codex sandbox (row 91)

11. `P preflight` and `assemble.py` start Blender themselves, so the rule file adds two venv rules, as the kit does for its spawners. Like the kit, the Blender rule allows every installed Producer script except the network scripts (`meshy_call.py`, `gen_image_codex.py`, `gen_api.py`, `generate_image.py`).
12. The brief's PID line wraps each Blender command in `<cmd> & echo $! > f; wait $!; rm -f f`, and blockout custom parts prefix `PYTHONPATH=…`. A Codex prefix rule matches one argv. Whether Codex matches the Blender part of such a shell line is unknown. If it does not, Codex asks the user for each Blender command, and `[limits] blender` needs another PID source on Codex.
13. The kit's self-test runs `codex execpolicy check`. The tests never run `codex`; they use a fake `codex` that matches prefix rules. The real check runs when the user runs `codex_rules.py` with Codex installed.

## Project Setup (row 82)

14. `project-profile.md` §5 has Project Setup "ghi `production/policy.yaml`", and `policy.yaml` says only scripts write it. Code: Setup writes through `P approvals set`, which now also takes `review_board local|local+remote`.
15. The Codex equivalent of `disable-model-invocation: true` is `agents/openai.yaml` with `allow_implicit_invocation: false`, as the kit does for Art Learning. Not checked by a run.

## A/B (rows 62, 96, 98)

16. `PRODUCER_ROOT=production-<runtime>` must be set per session; a `PRODUCER_ROOT=… <P>` prefix would not match the Claude Code allow rule of `P`. The adapters tell the user to start the session with the variable. A folder named `production-<runtime>` refuses writes from the other runtime; the source tree (`src`) is exempt.
17. `ROOT` is a module constant imported by name in every core module. The pair board runs `producer.py ab side` with the side's `PRODUCER_ROOT` and `PRODUCER_RUNTIME`, so each decision uses the normal code and lands in that runtime's folder and ledger.
18. Review-board §8 hides runtime and model names. Text written by agents can name them (for example "gen bằng Codex" in a README). Code: every string on the pair page, and every reply, passes a filter for runtime names, model names and `production-*`, `deliver-*`. URLs carry the label, not the root. Asset ids and offer keys pass unchanged, because the page sends them back; they hold the asset id, step, version and offer count, not the runtime.
19. Review-board §8 shows "two versions at the same step". Runs are staggered (§16), so one side can be at an earlier step. Code: each side shows its current card; reveal needs DUYỆT 2 on both sides.
20. "Mở nhãn sau khi anh đã duyệt hết": code also needs a "Bản nào tốt hơn" choice for every asset, or the choice would no longer be blind.
21. `P compare` without `--reveal` shows each asset with labels A and B only. Per-runtime totals, tokens by model and Elo appear only with `--reveal`, because a model name or a per-runtime total would reveal the labels.
22. §16 lists "số lần reviewer chấm lệch so với quyết định của anh". Code: an offer after a reviewer PASS that the user sends back, or an offer after FIX or ESCALATE that the user approves. An offer with no answer counts as silence, not agreement.
23. "Duyệt ngay lần đầu" needs the answer to the first offer of a step; `decisions` is cleared per offer (D22.8). Code: `offer_log` in `status.json`. Assets started before GĐ 6 have no log, so their numbers show `-` or "không có số".
24. "Tỉ lệ pass lần đầu của script kiểm": code reads v1 `final/review/{gates,checks}/*.json` (D26.4 files), and `report-script.md` for a script step. Steps that write no such file are left out.
25. Wall time runs from the first dispatch of a step to its approval, and from asset creation to DUYỆT 2. Both include the time the asset waited for the user, as `estimate.py log` does.
26. D26.1 names no criteria and no reviewer for the pair compare. Code: a new read-only agent `zps-3dp-check-ab` and five criteria in `core/ab.py` drawn from GPTEval3D (concept, geometry, texture, coherence, game_read). The rubric keys are pass/fail per step and some compare with the pilot, so they do not fit a pair vote.
27. The pair reviewer sees copies of the final images under `ab/judge/<id>/o<k>/{X,Y}/`, never a runtime folder. Ask 1 has X = A; ask 2 has X = B.
28. Elo between two players over one batch depends on order when updated step by step. Code: the Bradley-Terry gap from the score share, a tie counts half, plus 0.5 per side so a one-sided batch stays finite.
29. GĐ 3 note 19: `deliver/` per runtime is done through `PRODUCER_ROOT` (`production-codex` → `deliver-codex`).
