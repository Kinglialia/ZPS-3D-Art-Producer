# GĐ 1: spec notes for the user

Points the build found in the spec. Each one names the source. Nothing in `docs/` was changed.

## From T1 (scaffold)

1. `pipeline.toml` declares 6 steps, but the base code had no way to stop at a disabled step. Fixed in T3.

## From T5 (intake)

1. `paths.approved` is in both `pipeline.toml` and the profile (`project-profile.md` §3). The spec does not say which wins. Code reads `pipeline.toml`.
2. `producer.md` §13.3: `check_card.py` ships with GUIDELINE for the Concept Artist, but it needs PyYAML and `has_map` from the profile. It works only on the Producer machine (paths filled in at `P init`).
3. GUIDELINE tag list (`concept | model | texture | review | none`) has no `blockout` tag. Art direction docs cannot reach the blockout step.
4. `producer.md` §9 "type có rubric": only `default` and `building` rubrics exist, and other types fall back to `default`. The check cannot fail, so it is not useful.
5. `project-profile.md` §2 presets had no owner. Moved to T4.
6. `hidden_sides` "chưa biết" has no machine form. Code needs at least one non-empty string.
7. `producer.md` §9 pilot rule does not say if a finished pilot still blocks. Code: finished assets do not block.
8. Batch estimate (`producer.md` §9, D25.I, checklist 95) has no GĐ 1 ticket. Deferred.

## From T2 (contract and findings)

1. `producer.md` §6.1 `PRIOR` format has no evidence slot, but checklist row 88 needs evidence for `resolved`. Code adds `| evidence: <label>` to each PRIOR line.
2. `producer.md` §8 puts `review/` next to `final/`; `agents/blockout.md` §4 puts `review/` inside `final/`. One must change.
3. Checklist row 67: no field ties a finding to a rubric key. Code checks counts only (unclear keys ≤ open unclear findings).
4. `COUNTS` can be computed from FINDINGS and PRIOR, so it is redundant. Code checks it against the findings.
5. `FIXED:` in the worker report (§6.2) is read by no script, only by the reviewer.
6. `need_evidence` TOP_FIX id form is not stated in §6.1.
7. §6.1 `note_*` finding kinds "do not cause FIX", but a blocker/major note would force FIX with no valid TOP_FIX. Not reachable in GĐ 1.
8. Worker reply to Producer cut to the `STATUS` line only (token saving; the script reads the file).

## From T6 (blockout agents and tools)

1. **`apply_edit.py` of the kit does not fit the Producer fix flow** (`agents/blockout.md` §3 step 9). It needs `diagnoses/`, a fresh render per finding and a kit `spec.json`, which the Producer never writes. Its `param` mode runs automatic fitting, not the 2–3 variants the reviewer picks (D26.2). The agent now fixes per finding with a snapshot, edit, assembly, gates, `check_fix`, and restore on fail. `apply_edit.py` is copied but not used.
2. Kit bug: `blender -b --python assembly.py` fails (`No module named 'yaml'`), because `assembly.py` never loads the deps. Plain Python works. Custom parts that need Blender need a launcher with the deps path.
3. `agents/blockout.md` §6 asks for 4 ortho views and top. Kit `render_views --mode critic` gives front, back, left, right, 3/4, and no top.
4. `agents/blockout.md` §6 lists `overlay_*`, but the kit makes overlays only from a `spec.json` with concept views. The agent now builds that file from `concept_mask.py` masks. The spec does not describe this step.
5. Marker "nhô hoặc lõm ≥ 2 cm": assembly is a union only, so a recess cannot be built from primitives. A recess needs a custom part.
6. `agents/blockout.md` §5 says `check_inputs.py` checks hashes; D22.12 says existence only. Code follows D22.12.
7. Which `scale_refs` entry is the character and which `scale_overrides` entry is the door is the agent's judgment. No script checks it.
8. Worker brief said JSON goes to `work/`; `agents/blockout.md` §4 and D26.4 say `final/review/`. Fixed in T3 (brief).
9. Install copies agent files flat into `.claude/agents/`, which breaks the `references/` links of the blockout agent. Fixed later at install time.

## From T3 (fix loop, gates, policy)

1. D22.8 (one decision per version) and `producer.md` §4 ("bấm Cần sửa được bất cứ lúc nào") conflict after an approval. Chosen: dedupe blocks a second click on the same waiting version; `redo` after approval is allowed and opens a new version (T4).
2. `producer.md` §7.4 "từ vòng 2" does not say if a round is a fix or a review. Code follows D11.1: a round is a fix. Early stop fires at the review of v3; the 3-round cap fires at the review of v4.
3. D25.H lists three cases for the "chưa đạt" label. Code also uses it after the second `need_evidence` request.
4. D22.1: the fix brief takes the findings of the best version. Findings first seen on a later, worse version drop out.
5. `producer.md` §7.8: Needs fix at `assemble` goes to `texture` or `model`, both disabled in GĐ 1.
6. `pipeline.toml` short agent names (`step-blockout`) differ from the real agent names. Brief now prints the full name (T4).
7. D11.6 asks for a history of each feedback round. Nothing reads it; the ledger already holds it. Not added.
8. Added: `P delegate model` also needs `--confirm-spend` (same Meshy cost as `approvals set model reviewer`).

## From T4 (hashes, limits, preflight)

1. `producer.md` §11 concept hash "các file `_approved/<id>/`" includes the card, which has its own hash too. Code excludes the card from the concept hash, so "concept đổi" and "thẻ đổi" stay separate.
2. `producer.md` §11: `inputs.concept`, `inputs.card`, `inputs.art_direction` per version have no reader in GĐ 1. Warnings use one `sources` record per asset.
3. `producer.md` §12, D21.9: slots count real processes, but the spec does not say who writes the PID. The brief now gives the agent a PID line.
4. Checklist row 90 names xatlas, but no step `uses` it. Preflight records it and does not block on it.
5. `project-profile.md` §3 says no `env_file` means paint only; D24.3 says the default is `.env`. Code defaults to `.env`.
6. Reviewer reports carry no `PROFILE_HASH` (§6.2), so a profile change between worker and reviewer shows only as a warning.
7. Kit `preflight.py` reports `fail` unless the kit has its own venv with numpy and trimesh.
8. `producer.md` §14 1b: preflight "once per session" and "again after a tool or config change". The cache has no automatic expiry. SKILL.md tells the Producer to re-run it after a change.
