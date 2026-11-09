# Nguồn

ZPS Art Assets Kit v0.10.4, commit `905dc93` (`upstream/zps-art-assets-kit-v0.10.4/src/`).
Không sửa file chép nguyên. `tests/model/test_model_source.py` so sha256 với kit.

## Chép nguyên

| File | Nguồn kit | sha256 |
|---|---|---|
| `tools/self_build/graph.py` | `zps-3d-artist/tools/self_build/graph.py` | `71cb14480dfa4905649d2e6bcf9ad804dad3bf3cc799707ba9793c9a8a54bc8a` |
| `tools/self_build/assembly.py` | `zps-3d-artist/tools/self_build/assembly.py` | `383111072fcf3e871e69007197b549771eeb7ac17204bd4f91485190c4ac5f1a` |
| `tools/self_build/gates.py` | `zps-3d-artist/tools/self_build/gates.py` | `99e46550c4efd8345cc78d6a0e9a9442db0f69e78c976ab67bcc3dbaccd3ea27` |
| `tools/self_build/render_views.py` | `zps-3d-artist/tools/self_build/render_views.py` | `508452d2e6be1eab42155a8ac2c84d50419e02c046831b128299ca4e1dd873db` |
| `tools/lib/common.py` | `zps-3d-artist/tools/lib/common.py` | `eb16952d7d211a4b4b4ee73850b457acb476d0d4814f000f9da7ffd7ddf70568` |
| `tools/lib/raster.py` | `zps-3d-artist/tools/lib/raster.py` | `084d5b80efbe4d22367b98a79cdfb2132b42b39c014c0247ca18c0c87a1df176` |
| `tools/lib/bootstrap.py` | `zps-3d-artist/tools/lib/bootstrap.py` | `da32ee001fe203a814cb35027573b0664bb43c774cbb3911eb3a60ccee1b8f52` |
| `tools/optimize/bake.py` | `zps-3d-artist/tools/optimize/bake.py` | `b5f8033ca454ef609e1820c1f52060a54d1f5da454e38b4cdae44a23696932f9` |
| `tools/optimize/optlib.py` | `zps-3d-artist/tools/optimize/optlib.py` | `64d21d0009238815039c7cc08135758a588567db31f3b0e3c4e0e8ae9763229e` |
| `tools/optimize/optbpy.py` | `zps-3d-artist/tools/optimize/optbpy.py` | `05c260ac1b62ed3c5b8d300b7d508aef54c879b0e2d87da87cca3bb32397f26e` |
| `tools/asset_checks/ac_common.py` | `zps-3d-artist/tools/asset_checks/ac_common.py` | `c1d1d62f6caa280b97caea2f13ccd7f5f7cf3d1e88797054f7ed32d07bc63fce` |
| `tools/asset_checks/mesh_check.py` | `zps-3d-artist/tools/asset_checks/mesh_check.py` | `25e6c4f4e662903a80106c4234044b24a11071b1014941d87d41e5d5ac014ea9` |
| `tools/asset_checks/uv_check.py` | `zps-3d-artist/tools/asset_checks/uv_check.py` | `70c9f479d1b6a599ec0f9b2cf2977f2a5ce9166c6ac4cdaae115b1106c6425a1` |
| `tools/asset_checks/export_check.py` | `zps-3d-artist/tools/asset_checks/export_check.py` | `e7adc725358772032cc89e4e83fdad0410d19bb27d5f52685ec3f10176157cf0` |
| `tools/asset_checks/screen_tris_check.py` | `zps-3d-artist/tools/asset_checks/screen_tris_check.py` | `68f07c9ab1b6e82f99218125d7f637abd43eeaf004bbd1be5911be3bdd53eea0` |
| `tools/asset_checks/gltf_validate.mjs` | `zps-3d-artist/tools/asset_checks/gltf_validate.mjs` | `3f0a411cc25b975b57a783a4353355c6cfdd51f30dac2e3b37a8d1c580024ab9` |
| `references/bpy_cookbook.md` | `zps-3d-artist/references/bpy_cookbook.md` | `c42f45f4a6c12e34b3425b4619f13fb04b5b87f8d716be1c9d81f8766370abe3` |

`unwrap.py` gọi `xatlas_unwrap()`, `set_uv_layer()`, `uv_occupancy()` của `bake.py`, không gọi `main()` (D24.4). `bake.py` import `optlib`, `optbpy`, `lib/` ngay đầu file, nên ba file đó đi cùng.

## Chưa chép

- `finalize.py`, `report.py`: chỉ `assemble.py` của Producer dùng (GĐ 4).
- `asset_checks/render_rig.py`: `render_review.py` làm ảnh camera game và thumbnail; không ai đọc `sheet.png` của render_rig.
- `self_build/apply_edit.py`, `fit_camera.py`, `param_fit.py`: worker model không dùng (xem spec notes GĐ 1, T6).

## Rút từ kit (không chép nguyên)

| File | Nguồn kit | sha256 nguồn | Cách rút |
|---|---|---|---|
| `config.yaml` | `zps-3d-artist/config.yaml` | `2fa8c02e553f015edafc6fb0edf2a84941b8d5aa484f4849e3f42ce656d3971e` | keys the copied tools read (paths, budgets, texture, validate, self_build); values as kit except paths.blender; no max_duplicate_verts |
| `tools/setup_deps.sh` | `zps-3d-artist/tools/setup_deps.sh` | `61a8837f13e208373e39c8662a8142599b7198a99ef313907a72889b7072a7ea` | reduced: no gltfpack/validator, model packages only, xatlas in both targets |
| `zps-3dp-check-clay.md` | `zps-3d-artist/agents/3d-critic.md` | `c3ec032a688cc0873d25e43293c7d8962a704919b5d5b5a3a5bb30545745e980` | known limits and judging order, restated in the reviewer contract |
