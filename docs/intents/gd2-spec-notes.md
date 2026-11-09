# GĐ 2: spec notes for the user

Points the build found in the spec. Each one names the source and what the code does. Nothing in `docs/` outside `docs/intents/` and the checklist results was changed.

## Mismatched inputs and outputs

1. `concept-views.md` §6 puts `front.png`, `views.json`, `concept_colors.json`, `bg_color.json` in `views_rest/final/`. §3 step 1 and D22.14 say the front is not copied. Code follows D22.14: these files stay in `views_front/final/`. When GĐ 3 and GĐ 4 enable `model` and `texture`, their `inputs` in `pipeline.toml` must name both `views_front` and `views_rest`.
2. §3 renders guides in `views_front`, but its output list has no guides. `views_rest` and both reviewers need `<view>_guide.png`, `<view>_id.png`, `views.json`. Code puts them in `views_front/final/guides/`, so the approval hash locks them.
3. §3 lists `report` (the worker contract) inside `final/`. `contracts.md` puts `report-worker.md` in `vN/`. Code follows `contracts.md`.
4. `pipeline.toml` gave `views_front` only `uses = ["codex_image"]`, but step 2 renders in Blender. Code adds `blender`, so the brief has the `BLENDER:` and PID lines.
5. §3 marks `report/VIEWS.md` of `views_front` "nếu có", but the review board needs it when the asset reaches `waiting_human` (D20.16). Code makes it a required output.
6. §2 gives the worker the concept albedo and the card. The prompt needs material names, which only `<id>.material.md` has. Code adds that file to the views brief. The brief does not name `concept_shadow.png` (the kit uses it for mood only).
7. D15.1 puts `image_gen: {codex_model, reasoning}` in the preset, but the preset had no such key. Code adds it, and the brief stops when it is missing.
8. Blockout `outputs` do not name `final/parts/`, but `render_blockout_views.py` needs `parts/<part>.glb` of every part. The views `check_inputs.py` catches a missing part.
9. The brief only named the step right before. `views_rest` needs both `blockout` and `views_front`. Code adds `inputs` per step (default: the step before).

## Outputs nobody reads correctly

10. A reviewer `note_exception` or `note_texture` on the version that passes never reaches README `NGOẠI LỆ` or `TEXTURE NOTE`, because the worker writes the README before the review. The texture brief (GĐ 4) must read open `note_*` findings in `views_rest/vN/findings.json`, or `approve` must append them to the README.
11. README §4 "Trạng thái duyệt và ngày": the worker can only write "chờ duyệt". Nothing updates it after approval; `status.json` holds the truth. Suggest: drop §4, or let `approve` write it.

## Unneeded steps

12. §10 copies the kit `sheet.py`. Only Way B (one image for all views) uses it, and the Producer runs Way A. Not copied.
13. §10 says `measure_views.py` is copied "có sửa". The task rule says copied kit files stay unchanged. Code copies it unchanged; `tools/measure.py` replaces `flood_background` at import (G1).

## Contradictions and gaps

14. §8 asks the reviewer to judge silhouette by "số trong `report.json`". The kit crops both images to the bbox and resizes them, so IoU and detail % are bbox-normalised: the trap of pilot run 2, lỗi 7. The reviewer uses them to find a fault; `acceptance` is a visible feature on the same view, or a dE.
15. §5 and §8: `note_*` kinds "không gây FIX", but no rule sets their priority. A `major` note makes a report that no `TOP_FIX` can satisfy. Code: `note_*` must be `minor`.
16. §8 has no tie rule for `regen` against `regen_front`. Code: `regen_front` first, because a new front voids the other views.
17. D22.4 says only "script chạy `redo --step views_front`". Code decides: the `regen_front` finding moves to the approved front as its `TOP_FIX` with a new id; the front worker is new (not resumed); a second `regen_front` in one feedback round goes to the human, as `need_evidence` does (D20.15).
18. D22.4 "`views_rest` chạy lại sau đó" does not say fix round or new build. Code: a new build, because the front is the colour standard. Cost: 4 more Codex calls (3 when symmetric).
19. §9 "brief trỏ tới version đã duyệt trước đó": `redo` removes approvals of later steps, so that version was lost. Code keeps it in `status.json` `prior`. §9.3 for `views_rest` depends on the front staying the same, which the spec does not say. Code compares the front sha256 with `VIEWS_sheet.json`.
20. §4 asks for a long side > 1040 px. If Astra makes 1024 x 1024 by default, every square image fails. `gen_image_codex.py` asks for 1536 x 1024 or 1024 x 1536 in the frame. Needs a paid run to confirm.
21. The kit process (Step 3, Way A) has the artist approve the front. The Producer gives `views_front` gate `review` (D14.3), so the reviewer approves it. The spec chose this; noted only.
22. D8.3 retries 3 times, but kit `gen-craft.md` says stop at once on a quota or billing error. `gen_image_codex.py` retries any failure 3 times (no extra cost when the call is refused), except a missing `codex`.
23. `references/setup.md` still describes the base skill agents (`modeller`, `texturer`, `reviewer`, `external_command`). A pilot must install `agents/zps-3dp-step-views/` with `tools/` and `references/`, and `agents/zps-3dp-check-views.md`.
24. `diff_guides.py` threshold: on the hut, a 0.6 m back window with 5 cm relief moved from `offset_uv` −0.5 to 0.5 gives top 0.48% against the 0.5% limit; with 2 cm relief, 0.24%. Back is 6.3%. Above the limit the top view is generated again (one extra call, the safe side).
25. The spec has no way forward for an asset parked at `done_enabled` when a later GĐ enables the next step (the run 3 pilot asset). Code: `P next` names it, and `P retry <id>` moves it to the next step. Its `rubric.md`, and `production/pipeline.toml` and `production/rubrics/` of an existing project, predate GĐ 2: `P validate` names the missing `## views_front`, `## views_rest`; copy them and the new `[[steps]]` blocks from `templates/`.
