# GĐ 3: spec notes for the user

Points the build found in the spec. Each one names the source and what the code does. Nothing in `docs/` outside `docs/intents/` and the checklist results was changed.

## Mismatched inputs and outputs

1. `3d-artist.md` §2 names only `views_rest` for the view set. The front stays in `views_front/final/` (D22.14). Code: `model` reads `blockout`, `views_front`, `views_rest`.
2. §2 names the concept albedo, the shadow concept and the card, not `<id>.material.md` or `<id>.layout.md`. Code: `concept = ["concept_albedo.png", "concept_shadow.png", "asset-card.yaml"]`. Layout numbers reach the model only through `sources.json` (D22.13).
3. §3 A1 copies the whole blockout `final/` into `work/`. The kit tools build in the folder that holds `part_graph.json`, and a copied `review/` would put the blockout's failing JSON in the fix brief (D26.4). Code: the worker copies `part_graph.json` and `parts_lib.py` into `final/`.
4. §3 output list has no names for `parts_*` and "sheet DUYỆT 1", and puts `report` in `final/`. `contracts.md` puts `report-worker.md` in `vN/`. Code: outputs `review/model_sheet.png` and `review/renders/renders.json` (it lists `parts_front`, `parts_34`); the report stays in `vN/`.
5. §4 "Profile được đổi hai ngưỡng này" (3 px, 16 px) has no profile key in `project-profile.md`. Code: `overrides.detail.{relief_min_px, alpha_min_px, bevel}`, merged like every other `overrides` value.
6. D22.13 takes the camera from `sources.json`, but `sources.json` has no screen size. Code: `target_px_height` comes from the preset camera.
7. `includes_base: false` makes `layout.w/d/h` leave the base out, so `sources.json` has no size of the whole model. Code: `make_spec.py` then takes the union extents of the approved blockout `assembly.json`.
8. §11 lists `asset_checks/render_rig`, `finalize.py`, `report.py`, and all of `self_build/`. The model worker uses none of `render_rig` (`render_review.py` makes the game view and the thumbnail), `finalize.py`, `report.py` (only GĐ 4 `assemble.py`), `apply_edit.py`, `fit_camera.py`, `param_fit.py`. Not copied; `SOURCE.md` names them.
9. §11 lists no tool that writes the kit task spec, but every kit QA check needs `--spec`. Code adds `make_spec.py`, plus `join_mesh.py` for §5 (the spec names no join tool).

## Outputs nobody reads

10. `final/<id>.blend` has no reader in GĐ 3. GĐ 4 `assemble.py` can attach the texture to the locked GLB. Kept, because §3 lists it and the artist opens it.
11. Kit `assembly.py` also writes `final/assembled.glb` (the union) next to the model GLB. Nothing reads it at this step. The board now shows the GLB the step declares in `outputs`, so the user sees the untextured mesh, not the union.
12. `FIXED:` is still read by no script (GĐ 1 note T2.5).

## Unneeded steps

13. §5.3 asks `check_mesh.py` to find hidden faces and flipped normals. Kit `mesh_check` already measures `hidden_face_ratio` and `flipped_faces` on the same GLB. Code: `check_mesh.py` adds only what the kit lacks: one node, one mesh, one material, and coplanar overlapping faces.
14. §12 and D24.6 worry about `duplicate_verts` after a join without weld. Kit `load_input` welds exact duplicates of a GLB at 1e-6 m before it measures, so the exported GLB reads 0 (Blender run). The threshold question cannot come up on a GLB input.

## Contradictions and gaps

15. §4 "tris cuối lớn hơn tris của blockout": the blockout union retriangulates every contact (hut: 52 tris for the 68 part tris) and the join deletes hidden faces (hut plus a step: 62). Neither raw number shows what the detail pass added. Code compares the part builds (80 against 68).
16. §5 "xóa mặt bị che" with kit `optbpy.visibility` deletes the base top of the hut: its four sample points all sit under the walls, so the ring of base around the walls became a hole. Code samples seven points per face (centre, near each corner, near each edge midpoint).
17. §6 asks for padding "mỗi bên, kể cả mép atlas". Kit `xatlas_unwrap()` pads between charts only and leaves about 0.5 px at the border (Blender run). Code: `unwrap.py` scales the UVs into [m, 1 − m], m = padding / resolution. Cost: 1.6 % of the texel density at 2048 with 16 px.
18. §7 "clay có ánh sáng (sun + sky)": every kit render tool is Workbench. Code: Workbench studio light with shadows from `spec.json` `sun`. Engine light is checked at `texture` (`final_lit_vs_concept.png`).
19. §7 criterion 6 compares tris/m² with the pilot, but `deliver/<pilot>/` exists only after a GĐ 4 DUYỆT 2, and `producer.md` §6.4 does not name the GLB path in the package. Code: the brief line `PILOT:` names `deliver/<pilot>/`; `check_detail.py` takes the first GLB under it. D22.10 wants one `deliver/` per runtime, but `approve` and `PILOT` both use the folder next to `production/`; two runtime folders side by side would share it. Both use one constant (`state.DELIVER`), so GĐ 6 changes one line.
20. `producer.md` §6.1 gives `fix_uv_mesh` no fix kind. Code: batch; every listed id goes to the approved model as a `structure` finding. The model reviewer then compares several carried ids, while its own `structure` TOP_FIX stays one id.
21. `regen_front` "lần thứ hai → `waiting_human`" was a GĐ 2 code decision (from D20.15). Code applies it to `fix_uv_mesh` too, and counts each kind apart. Status files from GĐ 2 that hold an integer read as `regen_front`.
22. D21.2 and A9 need "mesh đổi" at GĐ 4. Code clears `locked.model` when `model` reopens and keeps no history. GĐ 4 can tell a new mesh from the budget files of other hashes in `texture/`.
23. D20.3 copies `ISSUES` of the approved model report into the texture brief. `ISSUES` is "tối đa 2 vấn đề" for the reviewer too, so a reviewer-only remark also reaches the texture worker. The worker file says `ISSUES` is for the texture step.
24. The rubric template comment says 4–7 criteria per step; check-clay has 8 (§7). Code keeps 8.
25. Existing projects have `production/rubrics/` and asset `rubric.md` files with the old `## model` keys (`silhouette`, `concept_match`, …), and `production/pipeline.toml` without `inputs`, `issues`, `lock`, `pilot`, `outputs` for `model` and `texture`. `P validate` checks section names only. Copy the new `## model` sections and `[[steps]]` blocks from `templates/` before the first model brief.
26. `references/setup.md` still describes the base skill agents (GĐ 2 note 23). A pilot must install `agents/zps-3dp-step-model/` with `tools/`, `references/`, `config.yaml`, run its `tools/setup_deps.sh` (it adds xatlas and OpenCV to Blender's target), and install `agents/zps-3dp-check-clay.md`.
27. The model worker reads the part graph contract of the blockout agent (`../zps-3dp-step-blockout/references/part-graph.md`). A flat install into `.claude/agents/` breaks this path, as GĐ 1 note T6.9 says for `references/`.
28. After "fix_uv_mesh lần 2" the user may `redo` texture. That fix brief tells the texture worker that mesh and UV are fixed in `model`; a mesh fix needs `--step model`. Only the GĐ 5 board can ask which step.
