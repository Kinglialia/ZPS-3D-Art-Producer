# Nguồn

ZPS Art Assets Kit v0.10.4, commit `905dc93` (`upstream/zps-art-assets-kit-v0.10.4/src/`).
File của kit mà script Producer chạy (không agent nào gọi thẳng). Thư mục giữ đúng cấu trúc của `zps-3d-artist/`,
để đường dẫn tương đối trong file kit vẫn đúng (`estimate.py` đọc `../estimates.json`, `finalize.py` đọc `lib/common.py`).
Không sửa file chép nguyên. `tests/texture/test_kit_source.py` so sha256 với kit.

## Chép nguyên

| File | Nguồn kit | sha256 |
|---|---|---|
| `tools/gen/gen_api.py` | `zps-3d-artist/tools/gen/gen_api.py` | `ddffe4e84a7b596f7a70f31f5602e573a7f0f064aa989298ada572f5f4cf6e52` |
| `tools/finalize.py` | `zps-3d-artist/tools/finalize.py` | `9e47c7e95e4371c6b21efc46f347d5b1674ecc84c3979ac2a288e8e14aaaaba1` |
| `tools/estimate.py` | `zps-3d-artist/tools/estimate.py` | `04ef53412b98b19c1083a2f6bf2d61e35a213c9d85fc55724fb1bb3a3c4a56fd` |
| `tools/lib/common.py` | `zps-3d-artist/tools/lib/common.py` | `eb16952d7d211a4b4b4ee73850b457acb476d0d4814f000f9da7ffd7ddf70568` |
| `estimates.json` | `zps-3d-artist/estimates.json` | `ef42c24075787bf351593d3a3007f8830ba748e985e2e2fac60c05405813ffac` |

## Ai gọi

- `gen_api.py`: chỉ `scripts/meshy_call.py` (lệnh `texture`, `keys`, `texture --dry-run`), D24.2.
- `finalize.py`: chỉ `scripts/assemble.py`, cổng QA của GLB cuối (D24.4).
- `estimate.py`: `P intake` (`show`) và lúc DUYỆT 2 (`log`), D25.I.
