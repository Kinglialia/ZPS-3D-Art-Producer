# GĐ 5: spec notes for the user

Points the build found in the spec. Each one names the source and what the code does. Nothing in `docs/` outside `docs/intents/` and the checklist results was changed.

## Annotation

1. `review-board.md` §6 step 2 has the Producer download the annotated image from the page (Artifact `read` with `path`). Code: the script draws each region on the local original image from the region JSON, for the local board and the remote page alike. Reasons: one drawing path, no download call, nothing for the Producer to handle, and an iPhone never exports a full-size canvas. The page sends only the JSON.
2. §4 does not say which button carries the regions. Code: any button. Regions become `H<n>` on the version that takes the decision when the asset waits for the user, or with Cần sửa. In other states the folder is saved and no finding is written, because a version under work or review would break the reviewer's `PRIOR` contract.
3. §4 "Bước không có reviewer (`assemble`): anh tự đóng finding khi duyệt". Code: Duyệt at a step without reviewer sets the open `H` findings of that version to `resolved`.
4. Cần sửa at `assemble` sends the regions to the step the user picks (`texture` or `model`). The folder keeps the name of the card the user saw (`assemble-v1-<k>`).
5. §4 JSON `[{n, image, shape, coords, note}]` names no shape of `coords`. Code: `circle` and `rect` are a box `[x0, y0, x1, y1]`; `free` is `[[x, y], …]`, 2 to 500 points. `image` is the image name on the card (`review/game_cam.png`), never a path; the script refuses any name not on the card. Limits: 50 regions, 500 characters per note. `regions.json` adds `id` = `H<n>`.

## One decision per offer

6. D22.8 says one decision per (asset, step, version); GĐ 1 changed it to one per offer. Code: every offer gets `offer_key`, the pages send the key they show, and the script skips a decision on an old key or on a key that already has a decision, from any source. This also closes a local bug: a board tab left open from an earlier offer could approve the version offered later.
7. §2 "Lần bấm sau bị bỏ qua": the order is the order the script applies them, not the click time. A phone click pulled after a local click on the same offer is skipped, even if the phone click came first.

## Remote page

8. Artifact assets have no names, so a row cannot point at an image by path alone. Code: the Producer writes one `files/<push>` row (`{path: asset id}`) from the upload result; the page joins it. This is the only value the Producer copies by hand. Published `files` next to the page would give fixed paths, but a text file is capped at 16 MB (GLB about 12 MB, under the 15 MB of §5) and `.glb` was refused in the 2026-11-08 trial.
9. ArtifactData refuses to overwrite a row without `if_version`. Code: each push writes new rows (`offers/<push>~<id>`, `pushes/<push>`); the page reads the newest `pushes` row. Rows accumulate (about two per asset per push, cap 25,000).
10. No command sets `review_board`; `producer.md` §4 says only scripts write `policy.yaml`, and Project Setup does not exist yet. Code: `policy.load` checks the value; `P board prepare` refuses unless it is `local+remote`.
11. Page access: db rule `read: view`, `write: owner`. Only the artifact owner's clicks become rows; the Producer writes as the user. A colleague the page is shared with can look but not decide.
12. The ArtifactData `out_dir` file shape is not documented. `P board pull` accepts a file with the row at the top level or under `data`. Check on the first real pull.

## `P show`

13. §5 "tóm tắt report các bước": `P show <id>` writes one card per step that has a version, newest step first. Cards of earlier steps carry no reason or label of the current offer. The static page has no buttons; decisions go through chat or `P serve`.
14. `P show` without `--bundle` also embeds the GLB (≤ 15 MB): Chrome refuses to fetch a `file://` GLB from a `file://` page, so a linked GLB never loads.
15. §5 "crop giữ nguyên" has no machine form. Code: an image under `review/evidence-<k>/` or named `crop*`, `*_crop*`, `foot_*` keeps its bytes. "GLB nhỏ" = 15 MB, the same limit as the remote page. Scaled images are JPEG q85, or PNG when they have alpha.

## Not in scope, noted

16. GĐ 4 note 3 (Meshy or VẼ MỚI on the board): done. The Duyệt button reads "Gọi Meshy thêm (N credit)" and a "VẼ MỚI" button sends `paint`. The CLI keeps `P meshy <id> paint`.
17. Verification limits: touch ran as CDP touch events in Chrome with iPhone 14 emulation, not on an iPhone. The remote page ran with a stub `claude.use("db")` on a local server, not on claude.ai. Checklist rows 12, 32 and 34 stay open for a real run.
18. Checklist row 62 (A/B board): only the local half. With `PRODUCER_ROOT=production-codex`, the board payload, the `P show` page and its file name hold no runtime name. `P ab board` is GĐ 6.

## Review fixes

19. `offer_key` is `<asset>-<step>-v<n>-<k>`. Before, two assets at the same step and version shared a key, and the remote page blocked the second asset after the first decision.
20. A send that dies (a bad image, a missing lock file) writes nothing: no `H` finding, no feedback folder, no `feedback.md` line. The order is validate, decide, then write. A redo writes the folder first, because its findings point at the PNG.
21. The board reply is `{applied, message}`. `applied` is false for a skipped click, and the page then keeps the marks and the draft. The remote page sets `applied: true` when the row is queued; a skip there shows in `P board pull`.
22. `P show --bundle` scales a crop above 2 MB like any other image and refuses a file above 25 MB.
23. Briefs list the annotated image with region numbers and ids. The region text stays in the finding (`repair`, `acceptance`) and shows once in the reviewer PRIOR line.
