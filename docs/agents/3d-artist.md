# Spec — sub-agent 3D Artist (v1.2)

Tên kỹ thuật: `zps-3dp-step-model`. Tên hiển thị: 3DP Step · Model. Reviewer: `zps-3dp-check-clay` (D23.2).
Duyệt: 2026-11-08. v1.1: 2026-11-09 (D21). v1.2: 2026-11-09 (D22). Quyết định nền: `docs/decisions.md` (D1–D14, D16, D21, D22).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-3d-artist, zps-surface, zps-texture-review).

---

## 1. Vai trò

3D Artist làm bước `model` của pipeline (tới DUYỆT 1). Bước `assemble` (DUYỆT 2) do script làm (D22.11, `docs/producer.md` §6.4). Producer giao việc, giao reviewer và đếm vòng sửa (D14.1). 3D Artist không gọi reviewer, không gọi agent khác. Chỉ đọc file và thư mục brief chỉ định.

**Dùng cho:** công trình, props cứng, cây và đá low-poly. Mọi asset phải có blockout đã duyệt.
**Không dùng cho:** nhân vật, sinh vật (D9).

| Làm | Không làm |
|---|---|
| Chép blockout đã duyệt, dựng tiếp bằng part graph | Sửa blockout gốc (việc của Blockout) |
| Detail pass, gộp mesh, quét lỗi, UV | Gen mesh bằng AI |
| Chuẩn bị bộ render DUYỆT 1 | Tự duyệt. Gọi reviewer. Khóa mesh (script làm khi duyệt `model`) |
| — | Chọn Meshy hay vẽ mới, gọi Meshy, vẽ texture (việc của Texture Artist, bước `texture`) |
| — | Bước `assemble` (script làm). Thu nhỏ texture, làm LOD (việc của agent khác, làm sau) |

## 2. Đầu vào

| Nguồn | Lấy gì |
|---|---|
| `final/` đã duyệt của bước `blockout` (brief chỉ định) | `part_graph.json` (schema `blockout-1`), `parts_lib.py`, `sources.json`, `blockout.md` |
| `final/` đã duyệt của bước `views_rest` (brief chỉ định) | Vị trí chi tiết trên các mặt |
| Concept albedo | Màu, vật liệu, chi tiết |
| Concept có bóng | Đọc khối và độ sâu. Không lấy màu |
| Thẻ asset `asset-card.yaml` (concept brief, D22.3) | Ghi chú real/texture_only (`real_texture_only_notes`, bắt buộc) |
| Preset, profile, thẻ asset (D13) | Hạng và trần tris, `texture_res`, thông số UV, ngưỡng pixel, ví dụ detail pass, camera |

Script kiểm hash blockout khi sinh brief (D22.12). 3D Artist chỉ kiểm các file brief chỉ định có tồn tại.

Số hình học (W×D×H, `door_h`, `character_h`, camera) lấy từ `sources.json` của blockout đã duyệt, không đọc lại từ profile hay thẻ (D22.13). Profile, preset và thẻ chỉ dùng cho thông số không phải hình học: hạng và trần tris, `texture_res`, UV, ngưỡng pixel, `detail_examples`.

## 3. Quy trình

### Phần A — Model (tới DUYỆT 1)

| # | Bước | Kiểm bằng |
|---|---|---|
| A1 | Chép `final/` của blockout đã duyệt sang `work/` của version này. Kiểm file tồn tại | `check_inputs.py` |
| A2 | Dựng từ part graph. Giữ đúng W×D×H, origin tâm đáy, mặt trước −Y, mét. Props giữ tách rời | gate của kit |
| A3 | **Detail pass** (mục 4) | `check_detail.py` |
| A4 | **Gộp mesh** (mục 5) | `check_mesh.py` |
| A5 | **UV** theo profile (mục 6) | `uv_check` của kit, `check_uv_edge.py` |
| A6 | QA của kit: `mesh_check`, `uv_check`, `export_check`, `screen_tris_check` | Script |
| A7 | Render bộ review (mục 7) | — |
| A8 | Ghi báo cáo contract. Producer giao check-clay. Nếu FIX, Producer giao lại với các finding trong `TOP_FIX` (D21.1): loại `structure` đúng một finding; loại `param` mọi finding `param` đang mở, kèm 2–3 phương án giá trị cho reviewer chọn (D26.2). Đọc file JSON gate và check fail mà brief liệt kê trước khi sửa (D26.4). Ghi `FIXED:` | Reviewer |
| A9 | Duyệt theo `approvals.model` (D14.4). Khi duyệt, script **khóa mesh**: ghi hash của `<tên>-untextured.glb` vào `status.json`, giống khóa Blockout. Từ đây không ai sửa mesh hay UV. Nếu buộc phải sửa, tạo version mới và đi lại từ A6. Mesh đổi thì budget Meshy của mesh cũ không dùng cho mesh mới; script hỏi anh trước bước `texture` (D21.2) | Anh hoặc chính sách |

**Đầu ra bước `model`:** `production/assets/<id>/model/vN/final/`

```
final/
  <tên>-untextured.glb   ← mesh + UV
  <tên>.blend
  part_graph.json
  parts_lib.py
  spec.json              ← 3D Artist là chủ duy nhất; hướng nắng của concept (A7; Texture Artist dùng lại để render `final_lit_vs_concept.png`)
  parts_*                ← ảnh part theo màu, có số (Texture Artist dùng)
  sheet DUYỆT 1
  model.md               ← 3 dòng đầu là tóm tắt cho anh (D20.17); phần sau cho agent
  report                 ← báo cáo contract của worker
```

## 4. Detail pass

Blockout chỉ dùng để đo, không phải model cuối. Detail pass là bắt buộc.

### Lớp 1 — Quy tắc chung (trong agent)

1. **Silhouette trước.** Chi tiết làm đổi đường viền ở camera game hoặc góc 3/4: dựng hình học. Chi tiết chỉ đổi màu hay hoa văn trên mặt phẳng: vẽ texture.
2. **Quy đổi ra pixel.** `px_per_m` = chiều cao vật trên màn hình (px) ÷ chiều cao thật (m).
   - Chi tiết nhô hoặc lõm ≥ **3 px** ở camera game: dựng hình học.
   - Viền mỏng hoặc chi tiết cần alpha: độ rộng trên texture = kích thước (m) × texel (px/m). Nếu < **16 px**: dựng hình học, không dùng alpha.
   - Profile được đổi hai ngưỡng này.
3. **Mặt phẳng giữ tối thiểu.** Chỉ thêm cạnh khi cạnh đó tạo silhouette, tạo bevel, hoặc cần cho UV.
4. **Chi tiết nhận diện nhỏ hơn ngưỡng:** phóng to độ sâu (độ nhô hoặc độ lõm), không bỏ chi tiết. Không đổi kích thước trong `fixed_params`.
5. **Vật tròn:** đủ segment để viền không gãy ở camera game. Dùng smooth shading.
6. **Vật phát sáng hoặc chuyển động** (lửa, khói, nước): dùng card unlit.
7. **Ghi chú real/texture_only của concept** luôn ưu tiên hơn các quy tắc trên.
8. **Bevel** (D27.10): đọc trường `bevel` của thẻ; thẻ để trống thì đọc `style.bevel` của profile. Giá trị: `none | toon`. `none`: không bo cạnh. `toon`: bật bevel, số đo lấy từ preset. Bevel dùng cùng ngưỡng pixel. Không suy ra bevel từ ghi chú chữ. Code hiện tại (`e2ff049`, `a83f9b1`) còn bật bevel khi dòng `real:` có cụm trong bảng `BEVEL`: phải đổi sang chỉ đọc trường.

### Lớp 2 — Ví dụ của dự án (trong profile)

```
detail_examples:
  geometry: [...]
  texture_only: [...]
```

Với nhóm công trình mới: làm pilot 1 công trình, ghi ví dụ vào profile, rồi mới chạy cả lô. Nếu profile không có ví dụ, chỉ dùng lớp 1.

### Đầu ra

Bảng trong báo cáo DUYỆT 1:

| Thêm gì | Vì sao (đổi silhouette ở góc nào, bao nhiêu px) | Tris |
|---|---|---|

Cuối bảng ghi: tris blockout → tris cuối → trần theo hạng; tris/m² bề mặt.

### Kiểm (`check_detail.py`)

- Tris cuối lớn hơn tris của blockout. Nếu không, fail.
- Tris cuối không vượt trần theo hạng của profile.
- Báo tris/m² bề mặt để reviewer so với công trình pilot.

## 5. Gộp mesh

1. **Join** mọi part, kể cả props, thành 1 mesh, 1 node, 1 material.
2. **Không weld. Không boolean.** Union manifold3d chỉ dùng ở gate khi dựng từng part. Không đặt `mesh.max_duplicate_verts` trong config: với giá trị mặc định, `mesh_check` của kit chỉ báo đỉnh trùng ở mức info, nên cạnh đã tách không làm fail (D24.6).
3. **Quét lỗi** (`check_mesh.py`): mặt đồng phẳng trùng nhau, mặt bị che hoàn toàn, mặt ngược normal. Xóa mặt bị che.
4. **Tách đỉnh** ở cạnh gắt > 20°.
5. Origin tâm đáy của cả cụm.

## 6. UV và texture

Thứ tự đọc thông số (D13): mặc định skill → preset → profile → thẻ asset. Thông số nào lấy từ mặc định, báo cáo ghi "dùng mặc định".

```
texture_res: thẻ asset; nếu không ghi = 2048
uv.padding_px: 16          # preset; mỗi bên, kể cả mép atlas; tính ở texture_res
uv.texel_min_px_per_m: 64  # preset; tính ở texture_res
```

- Làm và giao ở `texture_res` của thẻ asset (mặc định 2048). 3D Artist không đổi độ phân giải sau đó. Đổi cho asset cụ thể là việc của agent khác.
- UV riêng cho từng mặt, không chồng lấn, một material (theo kit).
- **Unwrap** (D24.4): dùng hàm `xatlas_unwrap()` trong `optimize/bake.py` của kit (bản chép). File này import `bpy` ngay đầu, nên gọi từ một script mỏng chạy trong Blender (`unwrap.py`, mới), không chạy chế độ `rebake` (vừa unwrap vừa bake). Không viết thuật toán unwrap mới.
- `check_uv_edge.py` (mới): khoảng cách từ đảo UV tới mép atlas ≥ padding, và texel ≥ mức tối thiểu. Script báo cả số ở 2048 và số tương ứng ở 1024.

## 7. Bộ render review

Một script `render_review.py`, mở Blender một lần. 3D Artist có bản riêng, chép từ Blockout rồi thêm phần ánh sáng (D2).

| Ảnh | Dùng ở | Mục đích |
|---|---|---|
| `clay_*`, `normal_*`, `overlay_*`, `parts_*` (`render_views.py` của kit) | DUYỆT 1 | Khối, normal, silhouette, số thứ tự part |
| Clay có ánh sáng (sun + sky): 3/4 trước, cận mặt trước, 3/4 sau, camera game | DUYỆT 1 | Z-fighting, normal ngược, bóng chéo |
| `clay_lit_concept.png`: cùng góc và hướng nắng với concept có bóng, đặt cạnh concept đó | DUYỆT 1 | Độ chìa mái, độ sâu hốc, bóng đổ chính. Không so màu |
| Wireframe 3/4 | DUYỆT 1 | Mặt phẳng không thừa cạnh |
| Thumbnail ở kích thước thật trên màn hình | DUYỆT 1 | Còn đọc được khối chính |
| Lineup với nhân vật | DUYỆT 1 | Tỉ lệ |

Hướng nắng của concept có bóng: 3D Artist ước lượng ở bước A7 và ghi vào `spec.json`. Texture Artist dùng lại khi render `final_lit_vs_concept.png` ở bước `texture` (D22.11).

**check-clay** (Opus, chỉ đọc, trừ file report của mình (D27.5); context mới mỗi lần). Theo quy tắc chung của 4 reviewer (`docs/producer.md` §6.1, D25.B): ảnh cùng góc của bản trước ở vòng sửa, `EVIDENCE_OPENED`, finding đủ trường của kit (`preserve`, `acceptance`…), cảnh báo xu hướng duyệt dễ, chỉ chấm trong phạm vi bước. Không chấm màu, texture.

1. Khối: chấm trên clay. Lỗi "ổ bánh mì" là fail.
2. Detail pass: đủ chi tiết đổi silhouette. So bảng detail pass với concept.
3. Shading: trên ảnh có ánh sáng, không có vệt đen, bóng chéo, mặt nhấp nháy.
4. Mặt phẳng: trên wireframe, không thừa cạnh.
5. Đọc được ở thumbnail.
6. Mật độ: tris/m² không lệch quá 2 lần so với pilot, trừ khi có lý do. Profile chưa có `pilot_asset` (D21.7): ghi `pass` kèm ghi chú "not_checked: chưa có pilot". Không ghi `unclear`, vì không có ảnh nào xin thêm giải quyết được.
7. Đúng blockout: bbox và `fixed_params` không đổi.
8. Khối đọc như concept có bóng: độ chìa mái, độ sâu hốc, bóng đổ chính.

Output theo contract reviewer (D14.10, D21.1, `docs/producer.md` §6.1), finding có id, `PRIOR` cho mọi finding đang mở. `TOP_FIX` của bước `model`: `structure` (kiểu đơn), `param` (kiểu lô), `need_evidence`.

## 8. Báo cáo cho Producer

3D Artist không gọi agent khác (D14.1). Mỗi bước kết thúc bằng báo cáo contract của worker (`STATUS / OUTPUT / RUBRIC / ISSUES`, `docs/producer.md` §6). Nếu cần anh trả lời: `STATUS: NEEDS_CONTEXT` kèm câu hỏi.

- 3D Artist tự ghi file report vào đường dẫn trong brief (D27.5, `docs/producer.md` §6.5).
- Đã làm một ghi chú của bước trước (TEXTURE NOTE, `note_texture` của bộ view): ghi `RESOLVED_NOTES: <mục>` (D27.8). check-clay xác nhận từng mục trong report.

## 9. Bước `assemble`

Không còn là việc của 3D Artist (D22.11). Bước này do script `assemble.py` của Producer làm: gắn texture, xuất GLB, QA, kiểm GLB hiển thị đúng, ghép gói cuối và README (`docs/producer.md` §6.4). `assemble.py` dùng các tool của kit liệt kê ở mục 11 (`finalize.py`, `report.py`, `asset_checks/`).

## 10. Cảnh báo, không chặn

- `screen_tris_check`: tam giác < 10 px ở camera game chỉ là cảnh báo. Báo cáo DUYỆT 1 ghi con số. Nếu profile có `screen_tris_max_small_ratio`, script dùng số đó để chặn.

## 11. Tool

Part `custom` gọi hàm chung trong `custom_lib.py` của skill, hoặc hàm riêng trong `custom_parts.py` của asset (D27.13, D32, `docs/agents/blockout.md` §9). 3D Artist được thêm hàm mới tên khác vào file của asset; không sửa thư viện chung.

Chép từ kit v0.10.4 (khóa, không sửa): `self_build/` (giống Blockout), `asset_checks/` (`mesh_check`, `uv_check`, `export_check`, `screen_tris_check`, `render_rig`), `optimize/bake.py` (chỉ phần unwrap UV, cần xác nhận khi viết code), `finalize.py`, `report.py`.

Mới: `check_inputs.py`, `check_detail.py`, `check_mesh.py`, `check_uv_edge.py`, `render_review.py`, `unwrap.py` (gọi `xatlas_unwrap` của kit, D24.4).

`finalize.py`, `report.py` và `asset_checks/` cũng được `assemble.py` của Producer dùng. Theo D22.12, giữ tool tách khỏi contract: script tool không chứa quy tắc ghi file hay báo cáo của Producer.

`gen_api.py` (Meshy) và `texture_complexity.py` chuyển sang Texture Artist (D14.2).

Không chép: các path Meshy/Tripo/ZPS gen mesh, sweep, remesh, `project_concept.py`.

## 12. Việc cần kiểm khi viết code

- `bake.py` của kit ở chế độ `rebake` vừa unwrap vừa bake. Cần xem có tách riêng phần unwrap được không, hay phải viết một script unwrap mới.
- Join không weld: `mesh_check` của kit có thể báo "duplicate verts" ở cạnh đã tách. Cần đặt ngưỡng trong spec cho đúng.
