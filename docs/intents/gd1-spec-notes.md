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
