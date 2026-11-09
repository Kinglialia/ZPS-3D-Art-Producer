# Tickets: GĐ 1

`S` = `src/zps-3dp-producer`. Spec branch: `feat/gd1-core`. Every commit ends with a `Ticket: <NN>` trailer.

Shared rules for every ticket:
- Read `docs/intents/gd1-core.md` first. The spec is in `docs/` (Vietnamese). Decisions D21–D26 in `docs/decisions.md` override older ones.
- Test command: `S/scripts/.deps/venv/bin/python -m pytest -q tests` from the repo root. T1 creates the venv.
- Keep `P` output short (one JSON line or a few lines). Token cost at run time matters.
- No comments that narrate code. Comment only a non-obvious why.
- Do not edit files outside **Writes**. Report anything else as a follow-up.
- Report a **Spec notes** section: any spec step that is not needed, any output nobody reads, any output that does not fit the input the next step expects, any spec contradiction. Cite the spec file and section. Do not change the spec.

## Pinned module layout (T1 creates the files; later tickets fill them)

| File | Owner after T1 | Holds |
|---|---|---|
| `S/scripts/producer.py` | T1, then each ticket adds only its own subcommand registration lines | argparse entry, `cmd_*` thin wrappers |
| `S/scripts/core/state.py` | T1 | paths, `PRODUCER_ROOT`, config load (`pipeline.toml`), status load/save, ledger, version dirs |
| `S/scripts/core/contract.py` | T2 | `parse_contract`, worker and reviewer report validation |
| `S/scripts/core/findings.py` | T2 | `findings.json` per version, PRIOR/COMPARE apply, open counts, progress, best version |
| `S/scripts/core/briefs.py` | T1 moves base code; T2, T3, T4 extend in sequence | `worker_brief`, `review_brief` |
| `S/scripts/core/loop.py` | T3 | ingest state machine: rounds, early stop, need_evidence, redo reset, gates, approve, rejected marking |
| `S/scripts/core/policy.py` | T3 | `policy.yaml`, `approvals set`, `delegate`, decision dedupe |
| `S/scripts/core/hashes.py` | T4 | profile hash, `inputs`, stale versions, warnings |
| `S/scripts/core/limits.py` | T4 | `[limits]`, `uses`, slot count |
| `S/scripts/core/preflight.py` | T4 | `P preflight`, `production/preflight.json` |
| `S/scripts/core/intake.py` | T5 | intake scan, card and profile checks wiring, pilot rule |
| `S/scripts/core/board.py`, `S/scripts/board/` | T7 | local board server and renderer |

## T1. Scaffold and module split

- **Builds.** The base skill lives in the repo as `zps-3dp-producer`, split into the pinned modules, with the same behavior as the base. A venv and pytest run.
- **Blocked by.** None.
- **Writes.** `S/**`, `tests/**`, `pyproject.toml` or `pytest.ini` at repo root.
- **Acceptance.**
  - Base source: `/Users/trungnk/Downloads/producer-skill.zip` (extracted copy in the brief). Copy `SKILL.md`, `references/`, `templates/`, `scripts/producer.py` into `S/`.
  - Rename skill to `zps-3dp-producer`, display name `ZPS-3DP · Producer` (`docs/producer.md` head).
  - Split `producer.py` into the pinned modules. Empty modules owned by later tickets exist with a one-line docstring. `cmd_intake` calls `core.intake.run(args, cfg)`; `cmd_serve`/`cmd_dashboard` call `core.board`. Base behavior of those stays inside those modules until T5/T7 replace it.
  - `S/scripts/setup_deps.sh` creates `S/scripts/.deps/venv` with `pyyaml`, `pytest`, `Pillow`. It is idempotent.
  - `S/templates/pipeline.toml` declares the 6 steps of `docs/producer.md` §3 (ids, agent `step-<step>`, reviewer `check-<step>`, gates `review`/`review_human`/`checks_human`, `uses`) and `[limits]` §12. Steps after `blockout` carry `enabled = false`.
  - A smoke test runs `P init` and `P new` in a temp dir and asserts the created files and `status.json` fields.
- **Verify.** `bash S/scripts/setup_deps.sh && S/scripts/.deps/venv/bin/python -m pytest -q tests`

## T2. Contract and findings

- **Builds.** `P ingest` reads worker and reviewer reports per `docs/producer.md` §6.1–6.2 and keeps `<step>/vN/findings.json`.
- **Blocked by.** T1.
- **Writes.** `S/scripts/core/contract.py`, `S/scripts/core/findings.py`, `S/scripts/core/briefs.py`, `S/scripts/core/loop.py` (wire findings into ingest only), `S/references/contracts.md`, `tests/test_contract.py`, `tests/test_findings.py`.
- **Acceptance.** Checklist rows 25, 50, 67, 88, 89, 97, 99 (PICK parse only), 44 (PROFILE_HASH presence only; value check is T4).
  - Finding ids `F<n>` stay fixed across rounds; new findings get the next free id.
  - Finding fields per kit `issue-fields` (D25.A); missing field → ingest rejects with a short error.
  - Severity includes `preference` (never blocks PASS); status includes `superseded` (not counted as progress).
  - `TOP_FIX` single for `structure` (exactly one id), batch for `param`, `regen`, `repaint` (all open of that kind); allowed kinds per step from `pipeline.toml`.
  - `PRIOR` consistent with `COMPARE` (`resolved` needs `better`; `worse` means `regressed`).
  - Review brief embeds the open finding list as a pre-filled PRIOR template (checklist 49 fallback, cheaper than a re-run).
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests`

## T3. Fix loop, gates, policy

- **Builds.** The ingest state machine of `docs/producer.md` §3, §4, §7, §8.
- **Blocked by.** T2.
- **Writes.** `S/scripts/core/loop.py`, `S/scripts/core/policy.py`, `S/scripts/core/briefs.py`, `S/scripts/producer.py` (subcommands `approvals`, `delegate` only), `S/templates/policy.yaml`, `tests/test_loop.py`, `tests/test_policy.py`.
- **Acceptance.** Checklist rows 20, 24, 26, 27, 38, 39, 40, 43, 54, 59, 65, 66, 70 (local part), 94 (label only), 99 (copy picked variant to `final/`), 101.
  - Steps with `enabled = false` are never dispatched; approving the last enabled step leaves the asset at a clear `done_gd1` style state, not at a disabled step's `todo`.
  - Remove `final_human_gate` default.
  - Max 3 rounds per feedback round; `redo` resets counters and copies open findings to the new round.
  - Progress: ≥1 old blocker/major resolved and regressed < resolved. From round 2, no progress → `waiting_human` with reason.
  - Best version: fewest open blocker+major, tie → older. Fix brief points to the best version and lists failed gate/check JSON files of it (D26.4).
  - need_evidence: only with no open blocker/major; writes `vN/review/evidence-<k>/`; no new version; `final/` hash unchanged or result discarded; not counted in rounds or `resume_rounds`; second request in one feedback round → `waiting_human`.
  - ESCALATE → `waiting_human` at once. Round 3 still FIX → best version, `waiting_human`, label `chưa đạt`.
  - `policy.yaml`: keys only `blockout`, `views_rest`, `model`; `model reviewer` needs `--confirm-spend`; delegate > approvals > human; ledger records who approved.
  - Approve marks other versions `rejected`, moves no folder; copies to `deliver/` only for `assemble`.
  - One Approve/Needs-fix per (asset, step, version); a later one is ignored with a message; notes accepted many times.
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests`

## T4. Hashes, inputs, limits, preflight

- **Builds.** `docs/producer.md` §10 (profile hash), §11, §12, §14 1b.
- **Blocked by.** T3.
- **Writes.** `S/presets/topdown-mobile-lowpoly.yaml` (body from `docs/project-profile.md` §2), `S/templates/settings.snippet.json` (venv python), `S/templates/pipeline.toml` and `S/scripts/core/state.py` (drop unused `[intake].min_images`, `[intake].type`), `S/scripts/core/hashes.py`, `S/scripts/core/limits.py`, `S/scripts/core/preflight.py`, `S/scripts/core/briefs.py`, `S/scripts/core/loop.py` (hash checks at ingest only), `S/scripts/producer.py` (subcommand `preflight` only), `tests/test_hashes.py`, `tests/test_limits.py`, `tests/test_preflight.py`.
- **Acceptance.** Checklist rows 44, 53, 55, 60, 71, 72 (warning part), 90.
  - Profile hash on normalized YAML, drop `paths` and keys starting with `_`.
  - `P brief` runs `check_profile.check` and refuses a brief when the profile is invalid (checklist 21).
  - Brief writes `PROFILE_HASH`; ingest rejects a missing or different value.
  - `inputs` per version; stale = input differs from current approved version of the previous step; concept hash by file content.
  - Slots count real running processes (a PID file per Blender job, checked alive), not the `running` state.
  - Preflight checks Blender, the kit `preflight.py` when present, codex CLI, Meshy key presence (never prints keys); writes `production/preflight.json`; `P next` does not dispatch a step whose feature is off.
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests`

## T5. Intake checks

- **Builds.** `docs/producer.md` §9 and `docs/project-profile.md` §5.
- **Blocked by.** T1.
- **Writes.** `S/SKILL.md`, `S/references/setup.md` (point `P` at the venv python, since YAML is now needed), `S/scripts/core/intake.py`, `S/scripts/check_card.py`, `S/scripts/check_profile.py`, `S/templates/asset-card.yaml`, `S/templates/PROJECT-PROFILE.yaml`, `S/templates/GUIDELINE.md`, `tests/test_intake.py`.
- **Acceptance.** Checklist rows 21, 29, 35, 58 (intake part).
  - Required files in `_approved/<id>/`; `type` from the card; `character`, `creature` rejected as not supported in v1.
  - `has_map: true` needs `<id>.layout.md`; `has_map: false` needs `size_m: {w, d, h}` in metres.
  - Profile with `approvals` or `review_board` is an error; missing `has_map` is an error.
  - `pilot_asset: null` → `intake --all` refuses; single named asset only when no other asset runs.
  - Errors grouped, short.
  - `P init` adds `.env` to the project `.gitignore`.
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests`

## T6. Blockout agents and tools

- **Builds.** `docs/agents/blockout.md` (all) and the blockout reviewer.
- **Blocked by.** T1.
- **Writes.** `S/agents/zps-3dp-step-blockout/**`, `S/agents/zps-3dp-check-blockout.md`, `tests/blockout/**`.
- **Acceptance.** Checklist rows 1, 2, 3, 4, 5, 47, 51, 83, 100.
  - Layout exactly as `docs/agents/blockout.md` §8. Copied kit files unchanged; `SOURCE.md` lists each with sha256.
  - New pure checks (`check_inputs`, `check_schema`, `check_base`, `check_support`, `check_layout`, `check_materials`, `check_markers`, `check_fix`) run with plain Python, read JSON, write one JSON result, exit non-zero on fail, print one line.
  - `render_review.py` opens Blender once.
  - Agent descriptions start with the fixed sentence of `docs/producer.md` §3.
  - Reviewer file carries the common rules (D1, D25.B): finding ids, PRIOR, COMPARE, TOP_FIX single/batch, EVIDENCE_OPENED, reply only VERDICT and COUNTS.
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests/blockout`. Blender smoke `root-only`: `bash S/agents/zps-3dp-step-blockout/tools/setup_deps.sh` then the smoke test marked `blender`.

## T7. Minimal local board

- **Builds.** `docs/review-board.md` §2, §3 (view only), §5 version pin, §7 single renderer; local only.
- **Blocked by.** T3.
- **Writes.** `S/scripts/core/board.py`, `S/scripts/board/**`, `tests/test_board.py`.
- **Acceptance.** Checklist row 64; review-board §2 items: one-line header, sheet image, full-size images, model viewer, 3-line summary, one-line reason, open findings one per line, `preference` group, `chưa đạt` label, `cũ` label, Approve / Needs fix / Note buttons, dedupe message.
  - `model-viewer@3.5.0` from jsdelivr, version in one constant in the shared JS.
  - Server binds 127.0.0.1 only; serves only files under the production root and `_approved/`.
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests`; UI check with `agent-browser` on the root.

## T8. Synthetic pilot and end-to-end test

- **Builds.** A synthetic asset and one test that runs the whole blockout flow.
- **Blocked by.** T4, T5, T6, T7.
- **Writes.** `tests/fixtures/pilot/**`, `tests/test_e2e_blockout.py`.
- **Acceptance.**
  - Fixture: a box house with a gable roof and a door, `has_map: false`, `size_m`, simple generated concept PNGs, valid profile and card.
  - Test: `P init` → `P intake <id>` → `P brief` → fake worker report → `P ingest` → fake reviewer FIX with 4 major findings → batch fix round → reviewer resolves 2 (progress) → round 3 no progress → `waiting_human`; then `P feedback redo` resets; then PASS → `waiting_human` → approve → `rejected` marks. Assert literal values.
  - A second test runs the real blockout checks and `gates.py` on a fixture `part_graph.json` (`blender` marker).
  - Total non-Blender suite time under 10 s.
- **Verify.** `S/scripts/.deps/venv/bin/python -m pytest -q tests`; `root-only` for the `blender` marker.
