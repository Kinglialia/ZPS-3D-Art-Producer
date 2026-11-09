# Nguồn

ZPS Art Assets Kit v0.10.4, commit `905dc93` (`upstream/zps-art-assets-kit-v0.10.4/src/`).
Không sửa file chép nguyên. `tests/blockout/test_source.py` so sha256 với kit.

## Chép nguyên

| File | Nguồn kit | sha256 |
|---|---|---|
| `tools/self_build/graph.py` | `zps-3d-artist/tools/self_build/graph.py` | `71cb14480dfa4905649d2e6bcf9ad804dad3bf3cc799707ba9793c9a8a54bc8a` |
| `tools/self_build/assembly.py` | `zps-3d-artist/tools/self_build/assembly.py` | `383111072fcf3e871e69007197b549771eeb7ac17204bd4f91485190c4ac5f1a` |
| `tools/self_build/gates.py` | `zps-3d-artist/tools/self_build/gates.py` | `99e46550c4efd8345cc78d6a0e9a9442db0f69e78c976ab67bcc3dbaccd3ea27` |
| `tools/self_build/apply_edit.py` | `zps-3d-artist/tools/self_build/apply_edit.py` | `3a6c89c008c8f00786cf45b4257922f074b8db8ff7c89945439adac25135cef8` |
| `tools/self_build/render_views.py` | `zps-3d-artist/tools/self_build/render_views.py` | `508452d2e6be1eab42155a8ac2c84d50419e02c046831b128299ca4e1dd873db` |
| `tools/self_build/fit_camera.py` | `zps-3d-artist/tools/self_build/fit_camera.py` | `3c8a2d9a62718c3bdec154eef1095448b8f1f7a3bf3251a0edab68ff3b4ef448` |
| `tools/self_build/param_fit.py` | `zps-3d-artist/tools/self_build/param_fit.py` | `13cd6a76c0a5826d766db3fdc6b7133742ae8ade91f7564224e82b283a1d9c25` |
| `tools/lib/common.py` | `zps-3d-artist/tools/lib/common.py` | `eb16952d7d211a4b4b4ee73850b457acb476d0d4814f000f9da7ffd7ddf70568` |
| `tools/lib/raster.py` | `zps-3d-artist/tools/lib/raster.py` | `084d5b80efbe4d22367b98a79cdfb2132b42b39c014c0247ca18c0c87a1df176` |
| `tools/lib/bootstrap.py` | `zps-3d-artist/tools/lib/bootstrap.py` | `da32ee001fe203a814cb35027573b0664bb43c774cbb3911eb3a60ccee1b8f52` |
| `tools/render_blockout_views.py` | `zps-concept-views/scripts/render_blockout_views.py` | `c22e9d5579d8adbcea9646208a926b7d4d57a412df5f87afcd852f5d9afe0cd9` |
| `references/bpy_cookbook.md` | `zps-3d-artist/references/bpy_cookbook.md` | `c42f45f4a6c12e34b3425b4619f13fb04b5b87f8d716be1c9d81f8766370abe3` |

## Rút từ kit (không chép nguyên)

| File | Nguồn kit | sha256 nguồn | Cách rút |
|---|---|---|---|
| `references/craft.md` | `zps-3d-artist/references/blockout.md` | `94499c3c5857c95267797f9c5e2c1bf4d57cfce1476cfdd1e7deb2c6810a0ec7` | blockout.md §A + Image evidence + Preflight; technique.md §1–2, verbatim excerpts |
| `references/craft.md` | `zps-3d-artist/references/technique.md` | `9238c6d1cc2c25c5b15434ecbe2f09c44fa6a7608b90f5baad8311a70d96a615` | blockout.md §A + Image evidence + Preflight; technique.md §1–2, verbatim excerpts |
| `config.yaml` | `zps-3d-artist/config.yaml` | `2fa8c02e553f015edafc6fb0edf2a84941b8d5aa484f4849e3f42ce656d3971e` | paths.blender, optimize.raster_size, self_build block; values as kit except paths.blender |
| `tools/setup_deps.sh` | `zps-3d-artist/tools/setup_deps.sh` | `61a8837f13e208373e39c8662a8142599b7198a99ef313907a72889b7072a7ea` | reduced: no gltfpack/validator, blockout packages only, manifold3d in the Blender target |
