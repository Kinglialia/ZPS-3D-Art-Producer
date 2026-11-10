# Hợp đồng `blockout-1`

`part_graph.json` là hợp đồng giữa Blockout và 3D Artist (`docs/agents/blockout.md` §9). `check_schema.py` kiểm mọi mục dưới đây. `graph.py` của kit dựng hình.

## Cấp file

```json
{
  "schema": "blockout-1", "version": "v01", "units": "m", "up": "+Z", "front": "-Y",
  "params": {"base_w": 4.0, "base_d": 4.0, "base_h": 0.3, "wall_h": 2.4, "door_h": 1.8},
  "fixed_params": ["base_w", "base_d", "door_h"],
  "_fixed_reason": "base_w, base_d từ size_m; door_h từ scale_overrides",
  "parts": []
}
```

- Mọi kích thước là tên trong `params`. Part không ghi số trực tiếp trong `dims`. Số thực ghi `1.0`, không ghi `1` (số nguyên là số segment).
- `fixed_params`: danh sách tên. Kích thước lấy từ MAP-LAYOUT hoặc `size_m`, `door_h`, `character_h` nằm ở đây. Mỗi số đếm của thẻ (`counts`, dòng `COUNTS:` của brief) là một param cùng tên với khóa ở đây, ví dụ `"doors": 1`; gate so giá trị này với thẻ. Ghi lý do vào `_fixed_reason`. `param_fit.py` không đổi các param này; `check_fix.py` báo fail nếu một vòng sửa đổi chúng.

## Mỗi part

| Field | Bắt buộc | Giá trị |
|---|---|---|
| `name` | có | duy nhất |
| `primitive` | có (trừ `mirror_of`) | `box` (dims w,d,h), `wedge` (dims w,d,h; dốc lên về +Y), `cylinder` (dims radius,height), `custom` |
| `dims` / `fn` + `args` | có | `custom`: tên một hàm trong `FUNCTIONS` của `tools/custom_lib.py`, hoặc một hàm của `custom_parts.py` của asset (`check_schema` kiểm); trả `bmesh` đặt tâm tại bbox; 3 arg đầu là w,d,h hoặc ghi thêm `dims`. Mỗi arg là một số hoặc tên một param |
| `attach` | có | `null` chỉ cho part đầu tiên (gốc) |
| `material` | có | mã trong `sources.json` `materials` |
| `role` | có | `mass` (khối chính) hoặc `marker` (mốc đo, nhô ≥ 2 cm) |
| `tag` | không | `base` (nền), `roof` (mái) |
| `segments` | không | 8–24 (số hoặc tên param nguyên) |
| `axis` | không | `X`, `Y`, `Z` (cylinder, mặc định Z) |
| `rotation_deg` | không | 0, 90, 180, 270 |

- Part `mirror_of` tự ghi `material`, `role`, và `tag` nếu part nguồn có `tag`. Kit chỉ chép field hình dạng sang part mirror.
- Liệt kê theo thứ tự dựng, khối lớn trước. Part cha đứng trước part con. Mọi part nối về part gốc qua `attach.to` (hoặc `mirror_of.of`): không part mồ côi, không vòng lặp.
- Không ghi vị trí. Vị trí chỉ đến từ `attach`:

| `type` | Nghĩa | Field |
|---|---|---|
| `on_top` | Đáy con nằm trên mặt trên của cha | `offset_uv` (−1..1, mặc định [0,0]) |
| `center_on_face` | Con áp sát một mặt của cha, ở ngoài | `face` (±X/±Y/±Z), `offset_uv` |
| `flush_edge` | Áp một mặt, thẳng một cạnh | `face`, `edge` (vuông góc `face`), `inset` (m) |
| `inset_into` | Chìm vào mặt cha một độ sâu | `face`, `offset_uv`, `depth` (m) |
| `through_axis` | Xuyên qua cha theo một trục | `axis`, `offset_uv` |
| `mirror_of` | Bản đối xứng qua mặt giữa của part gốc | `of`, `plane` (X/Y) |

`offset_uv` theo thứ tự: mặt ±X → (Y, Z); mặt ±Y → (X, Z); mặt ±Z → (X, Y). −1/+1 là sát mép mặt cha.

Mặt trước nhìn về −Y. Bên trái của chính công trình là +X (quy ước view của kit).

Quy tắc dựng (từ `self_build.md` của kit): bevel 1–2 segment; tránh hai mặt trùng phẳng khi một part nằm trong part khác (lệch khoảng 0.001 m); không vật liệu, không texture.

## `sources.json`

Khóa `check_inputs.py` đòi: `files.{layout, layout_sha256, material, material_sha256}`, `layout.{w, d, h, includes_base, source}`, `door_h`, `door_h_source`, `character_h`, `materials` (danh sách mã), `camera` (`null` hoặc `{azimuth_deg, elevation_deg, fov_v_deg}`). Ví dụ ở `docs/agents/blockout.md` §2.

- `has_map: true`: `files.layout` là `_approved/<id>/<id>.layout.md`.
- `has_map: false`: `files.layout` là `_approved/<id>/asset-card.yaml`; `layout.w/d/h` bằng `size_m`; `character_h` từ `scale_refs` của profile; `door_h` từ `scale_overrides` của thẻ, hoặc đo trên concept với `character_h` làm thước, cách đo ghi vào `door_h_source`. Asset không có cửa (prop): `door_h: null`, `door_h_source` ghi lý do, ví dụ "không có cửa".
- Hàm `custom` nhận mọi param dạng số thực: ép `int(...)` cho số đoạn, số cạnh.

## Hàm `custom` (D32)

- Hàm chung trong `tools/custom_lib.py` (đọc docstring để biết tham số):
  - `vault(w, d, h, arch_h, seg, planks=1, gap=0, depth=0, r=0, bseg=2)`: khối vòm theo X (mái vòm, nắp, đường hầm); `planks` ≥ 2 chia vòm thành dải bằng rãnh.
  - `grooved_box(w, d, h, gap, depth, rows, z0=0, pitch=0)`: hộp có `rows - 1` rãnh ngang quanh 4 mặt (tường ván, hàng đá); `pitch` 0 chia đều.
  - `bevel_box(w, d, h, r, seg, mask)`: hộp bo các cạnh chọn theo `mask`.
- Hàm riêng của asset: file dòng `CUSTOM_PARTS:` của brief (`production/assets/<id>/custom_parts.py`). Chỉ import `math`, `bmesh`, `mathutils`; không `open`, `exec`, `eval`, `os`, `subprocess`, `sys`, module mạng, tên `__…__`. Tên không trùng hàm chung. Chỉ thêm hàm, không sửa hàm một version đã dùng. `build_parts.py` từ chối file sai trước khi chạy.
- `build_parts.py` ghi `parts_lib.py` = `custom_lib.py` + dòng `# ---- custom_parts.py …` + `custom_parts.py`. Đó là code đã chạy, và reviewer đọc nó.
- File của asset giữ tới DUYỆT 2 (bước model và mọi `redo` dựng lại từ part graph), rồi D29 xóa nó cùng các bản `parts_lib.py`.
- Hai mặt trùng khít tuyệt đối làm gate union lỗi: để lệch 1 mm khi acceptance cho phép.
- `includes_base: false`: `check_layout.py` bỏ các part `tag: base` khi đo bbox.

## Kết quả script

Mọi tool ghi một file JSON cùng dạng kit (`lib/common.write_result`): `overall` (`pass | fail | info | not_checked | error`), `checks[]` (`check`, `status`, `value`, `threshold`, `note`), `data`. Tool in một dòng. Mã thoát của `check_*.py`: 0 pass hoặc not_checked, 1 fail, 2 lỗi.

| File | Ghi bởi |
|---|---|
| `final/assembly.json`, `final/parts/`, `final/assembled.glb` | `assembly.py` |
| `final/review/gates/<part>.json` | `gates.py --out` |
| `final/review/checks/<tên>.json`, `fix_<F>.json` | `check_*.py` |
| `final/review/renders/` (`renders.json`, `clay_*`, `normal_*`, `parts_*`, `overlay_*`) | `render_views.py --outdir` |
| `final/review/review.json`, `game_cam.png`, `lineup.png`, `foot_front_*.png` | `render_review.py` |

## `blockout.md`

Review page hiện ba dòng đầu (bỏ dòng trống) làm tóm tắt. Dòng đầu: `# Blockout <id> v<N>`. Hai dòng sau là mục 1 và 2, mỗi mục một dòng. Các mục khác theo sau, đúng thứ tự:

1. Thành phần đếm trên concept (ví dụ "4 trụ, 1 cửa, 3 thùng").
2. Bbox so với MAP-LAYOUT (`has_map: true`) hoặc `size_m` của thẻ asset (`has_map: false`).
3. Version, hash của `part_graph.json` + `parts_lib.py`.
4. Bảng đo: param, giá trị, nguồn, cách đo.
5. Ghi chú real/texture_only, chép nguyên từ concept.
6. **Blockout tự quyết**: từng chỗ phần khuất hoặc kích thước mà mô tả không có, kèm lý do.
7. Mâu thuẫn giữa các nguồn, và lựa chọn đã dùng.
8. Số lỗi mesh còn lại (non-manifold, zero-area) từ `assembly.json` `union.health`. Blockout không bắt buộc mesh sạch.
9. Thay đổi so với version trước (từ v02): part nào, param nào đổi, vì sao.
10. Trạng thái duyệt: chờ duyệt / anh duyệt / reviewer duyệt theo ủy quyền, kèm ngày.
