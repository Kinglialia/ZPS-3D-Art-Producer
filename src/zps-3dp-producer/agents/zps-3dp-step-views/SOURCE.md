# Nguồn

ZPS Art Assets Kit v0.10.4, commit `905dc93` (`upstream/zps-art-assets-kit-v0.10.4/src/`).
Không sửa file chép nguyên. `tests/views/test_views_source.py` so sha256 với kit.

## Chép nguyên

| File | Nguồn kit | sha256 |
|---|---|---|
| `tools/render_blockout_views.py` | `zps-concept-views/scripts/render_blockout_views.py` | `c22e9d5579d8adbcea9646208a926b7d4d57a412df5f87afcd852f5d9afe0cd9` |
| `tools/measure_views.py` | `zps-concept-views/scripts/measure_views.py` | `2bd804171ee19272248e789932916f861331186b0f4f205723087d4d6a2ce046` |
| `tools/palette_report.py` | `.art-production-support/shared/scripts/palette_report.py` | `2c170469cf7b242376d6a97c9c4688262d2de489d90546ebc25c874ee91b92d7` |
| `tools/lib/common.py` | `zps-3d-artist/tools/lib/common.py` | `eb16952d7d211a4b4b4ee73850b457acb476d0d4814f000f9da7ffd7ddf70568` |

## Sửa ngoài file kit

- G1 (`docs/review-kit-v0.10.4-vs-process.md`): `concept-views.md` §10 ghi `measure_views.py` "có sửa". File kit giữ nguyên. `tools/measure.py` nạp nó như module và thay `flood_background` bằng hàm giữ mọi pixel gần màu nền trên toàn ảnh.
- Không chép `sheet.py`: chỉ Way B (một ảnh nhiều view) dùng nó, và Producer chỉ chạy Way A.

## Rút từ kit (không chép nguyên)

| File | Nguồn kit | sha256 nguồn | Cách rút |
|---|---|---|---|
| `references/views.md` | `zps-concept-views/references/process.md` | `2c8e1d4946dca8779ac185f061ea98602f569420837d674861bc66c2957e9798` | Step 3 rules and prompts (Way A), verbatim; step 4 concept colours |
| `references/views.md` | `.art-production-support/shared/gen-craft.md` | `07f6bfc95b72a63f0aced1b5596d2c6dc2efa3b95d1441258904e3c809202864` | Lighting and shadows; Typical faults table, verbatim |
| `zps-3dp-check-views.md` | `.art-production-support/rules/art-quality.md` | `855d0c3de045222c4f320ebbf257a9af43290c3a3546c673a64584dd2e691039` | §1 element inventory, restated |
