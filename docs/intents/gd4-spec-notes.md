# GĐ 4: spec notes for the user

Points the build found in the spec. Each one names the source and what the code does. Nothing in `docs/` outside `docs/intents/` and the checklist results was changed.

## Meshy and the questions to the user

1. `producer.md` §6.3 says no `env_file` means VẼ MỚI; D24.3 and `P preflight` default to `.env` (GĐ 1 note T4.5). Code: the texture brief reads `paths.env_file` of the profile itself. No key → `MODE: VẼ MỚI`, no budget. Key set but no `MESHY_API_KEY` → `blocked`. Preflight no longer stops the texture step for Meshy, or a VẼ MỚI project could never texture.
2. §6.3 point 3 asks the "mesh đổi" question for every new mesh hash. When the old budget spent nothing (the user chose VẼ MỚI, or the worker never called), the question is noise. Code asks only when a budget of another hash has `used_credits > 0`; else the new mesh gets one call.
3. §6.3 "Anh duyệt" names no way to answer the two-way question (Meshy or VẼ MỚI). Code: Duyệt (CLI or board) = one more call; `P meshy <id> paint --by "<nguyên văn>"` = VẼ MỚI. VẼ MỚI does not go through `redo`, because a mode choice is not a new feedback round (D25.H keeps the counter). GĐ 5 board should show both buttons.
4. §6.1 gives `meshy_regen` no fix kind and no tie rule. Code: batch kind; same priority: `fix_uv_mesh` first, then `meshy_regen`, then `repaint`. After the user's approval the fix round restarts from the version the reviewer judged, not the best version, because its `findings.json` holds the `meshy_regen` finding the next reviewer must PRIOR.
5. `UNFIXABLE: yes` in a VẼ MỚI build has no Meshy call to approve. Code: `blocked` with the worker's reason.
6. §6.3 covers a wait or download error after the task exists, not a task that Meshy ends `FAILED`. Waiting again on that `task_id` can never succeed, and Meshy refunds a failed task (docs.meshy.ai Retexture API, read 2026-11-09; the official skill's `delivery.md` says the same). Code: refund the local budget, keep `task.json` as `task-ended.json`, stop as BLOCKED at once. A new paid task is the user's call.
7. Checklist 102, by reading only (no call): the kit payload matches docs.meshy.ai: `POST /openapi/v1/retexture`, `model_url` as an `application/octet-stream` data URI, `image_style_url`, `enable_original_uv: true`, `enable_pbr: false`, `target_formats: ["glb"]`, task id in `result`, `GET /retexture/:id`, `model_urls.glb`. Price on docs.meshy.ai/en/api/pricing: 10 credit per retexture at 2K or 4K, 15 at 8K. The kit sends no `ai_model` (Meshy uses `latest`) and no texture resolution. The official skill (`meshy-dev/meshy-3d-agent`) drives the `meshy` CLI and has no `reference.md`; its `pipelines.md` names `--ai-model meshy-n1` for an image style ("a 2K base color texture"). Decide `ai_model` and resolution before the first paid call; `check_meshy.py` scales the Meshy image to `texture_res`.
8. `[limits] meshy = 1` with `uses = [..., "meshy"]` holds the Meshy slot for the whole texture step, so a second asset waits even while the first one paints. Accepted for the pilot.

## Assemble

9. §6.4 point 4 sets no pixel threshold. Code: unlit Workbench renders with the texture step's recorded cameras, mean |RGB| ≤ 6/255 over the object, silhouette mismatch ≤ 2 %. Blender run on a box: the correct path measures 0.0 (same image, same cameras, same renderer); an albedo written in linear values measures 65 and blocks.
10. Checklist row 77 asks for "a GLB with a wrong colour space". A Blender image node set to Non-Color may be reset to sRGB by the glTF importer, so that fault could pass unseen; it was not tested. The test injects a fault that lives in the file bytes: the albedo pixels written in linear values.
11. §6.4 point 3 runs the kit QA on the final GLB. The glTF validator of `export_check` writes `<glb>.validator.json` beside its input, which put a stray file in the package. Code runs the QA on a byte copy in `work/qa_input/`; `finalize.py` accepts it because the sha256 is the same.
12. §6.4 point 5 says "report reviewer" without naming the step. Code copies the approved texture reviewer report as `review/report-review-texture.md`; assemble has no reviewer.
13. §6.4 point 6 takes NGOẠI LỆ and TEXTURE NOTE from the views README and "Blockout tự quyết" from `blockout.md`, by heading text. A file without that heading gives "không có". The approved version of each step gives "việc còn mở", the user's `H<n>` first.
14. §8 and GĐ 2 note 11 (README status line): `assemble.py` writes "Trạng thái: chờ DUYỆT 2 · <ngày>"; DUYỆT 2 rewrites that line in `deliver/<id>/README.md` only, so `assemble/vN/final/` keeps the hash it was approved with.
15. §6.4 "fail → blocked, không có vòng sửa" does not say what `retry` does. Code: `retry` runs the script again as a new version, so the failed run keeps its report and findings for the board.
16. §7.8 Needs-fix at `assemble`: the CLI refuses `redo` without `--step texture|model`; the board shows a step selector (`redo_steps`).

## Texture tools

17. `texture-artist.md` §5 caps a crop at 1024 px; `gen_image_codex.py` (GĐ 2) needs a long side over 1040 px. Code: `crop_edit.py cut` also writes `send.png`, the crop scaled to a 1536 px long side; `paste` checks the edit has exactly that size and scales it back. Paint guides are 1536 × 1024 for the same reason.
18. §4 step 2 puts the 8 views at elevation ±30°. On a building on the ground the −30° views see the underside. Code follows the spec; `project_views.py` weights by cos², so those views only paint faces that look down.
19. §10 copies `project_concept.py` "có sửa". The task rule keeps kit copies unchanged, and the kit tool fits one concept to a bbox, not 8 known cameras. Code: own `project_views.py` drawn from it (`SOURCE.md` "Rút từ kit"). `render_model.py`, `inspect_model.py` are not copied: `render_texture.py` must record its cameras for `assemble.py`.
20. §6 "Ngưỡng mặc định nằm trong profile": the profile schema has no texture thresholds. Code: defaults in `tex_measure.py` (side spread 3 L*, top tolerance 3 L*, shaded share 2 %, dE 3, seam p90 4, unpainted 0.1 %, empty padding 1 %); profile `overrides.texture` replaces any of them. Group 3 has no threshold in the spec, so `read.*` is info.
21. §6 group 2 compares each code with the pilot. The pilot package has no ID map, so there is no per-code colour to compare: `material.dE_pilot` is `not_checked` also with a pilot.
22. §2.2 "chạy `uv_check` và `mesh_check` sau Meshy": the kit checks measure one mesh and cannot say whether UV or triangles changed. Code: `check_meshy.py` compares the Meshy GLB with the locked GLB triangle by triangle.
23. §9 asks for "alpha bật" on the textured renders. Code: `unlit_*` have alpha (the compare needs it); `lit_*` are opaque on a grey background, like the clay renders.
24. Material regions come from the model's `parts/` and `review/join.json`, which the model step does not list in `outputs`. `check_inputs.py` of the texture worker stops when they are missing.

## Batch estimate

25. D25.I "tổng credit Meshy của lô đưa anh duyệt một lần" names no mechanism. Code: `P intake` prints the total (10 credit per asset); SKILL.md has the Producer record the user's answer with `P rule`. Nothing blocks a batch without it.
26. `estimate.py log` uses method `self` (the Producer always self-builds) and the minutes from asset creation to DUYỆT 2, which include the time the asset waited for the user.

## For a project that already runs

27. `production/pipeline.toml`, `production/rubrics/` and asset `rubric.md` files predate GĐ 4: copy the `texture` and `assemble` `[[steps]]` blocks and the new `## texture` keys from `templates/`. `references/setup.md` still describes the base skill agents: install `agents/zps-3dp-step-texture/` with `tools/` and `references/`, run its `tools/setup_deps.sh`, install `agents/zps-3dp-check-texture.md`.
