# Nguồn

ZPS Art Assets Kit v0.10.4, commit `905dc93` (`upstream/zps-art-assets-kit-v0.10.4/src/`).
Không sửa file chép nguyên. `tests/texture/test_texture_source.py` so sha256 với kit.

## Chép nguyên

| File | Nguồn kit | sha256 |
|---|---|---|
| `tools/lib/bootstrap.py` | `zps-3d-artist/tools/lib/bootstrap.py` | `da32ee001fe203a814cb35027573b0664bb43c774cbb3911eb3a60ccee1b8f52` |
| `tools/palette_report.py` | `.art-production-support/shared/scripts/palette_report.py` | `2c170469cf7b242376d6a97c9c4688262d2de489d90546ebc25c874ee91b92d7` |

`gen/gen_api.py` của kit không nằm ở đây: chỉ `scripts/meshy_call.py` của Producer chạy nó (D24.2), bản chép ở
`scripts/kit/tools/gen/gen_api.py`.

## Rút từ kit (không chép nguyên)

| File | Nguồn kit | sha256 nguồn | Cách rút |
|---|---|---|---|
| `tools/project_views.py` | `zps-3d-artist/tools/texture/project_concept.py` | `797948a6746bee5d68b495c66c662c570d1b48cb2d92e88c0b1968e47bb9a2c9` | orthographic projection and occlusion of the kit; cameras of render_paint_views.py (8 views, any angle) instead of a bbox fit to one concept; one view per face (best cos, island hysteresis) and bilinear sampling instead of cos weights, because the 8 paintings are made one by one; each painting checked against its guide; z-buffer in numpy instead of a BVH ray; unseen texels filled by face, then code + side, then base fill, instead of facet fit, palette and inpaint |
| `tools/setup_deps.sh` | `zps-3d-artist/tools/setup_deps.sh` | `61a8837f13e208373e39c8662a8142599b7198a99ef313907a72889b7072a7ea` | reduced: venv numpy, pyyaml, Pillow; Blender target pyyaml, Pillow |
| `zps-3dp-check-texture.md` | `zps-texture-review/references/texture-checks.md` | `39eba7b01a1036fdebca1937e305748a1fa1388af75528eccf5c403f2c4c7329` | diagnosis order (colour space, alpha, normal before repaint; UV and padding before blur), restated in the reviewer contract |

## Chưa chép

- `render_model.py`, `inspect_model.py` (`.art-production-support/shared/scripts`): `render_texture.py` làm bộ render có
  texture và ghi camera vào `renders.json`, vì `assemble.py` phải render lại đúng các camera đó.
- `project_concept.py` nguyên bản: chiếu một concept theo khung bbox, không nhận camera của paint view.
