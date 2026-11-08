# Spec — sub-agent 3D Artist (v1)

Tên kỹ thuật: `zps-3dp-3d-artist`. Tên hiển thị: ZPS-3DP - 3D Artist.
Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D1–D14).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-3d-artist, zps-surface, zps-texture-review).

---

## 1. Vai trò

3D Artist làm hai bước của pipeline (D14.2): `model` (tới DUYỆT 1) và `assemble` (tới DUYỆT 2). Producer giao việc, giao reviewer và đếm vòng sửa (D14.1). 3D Artist không gọi reviewer, không gọi agent khác. Chỉ đọc file và thư mục brief chỉ định.

**Dùng cho:** công trình, props cứng, cây và đá low-poly. Mọi asset phải có blockout đã duyệt.
**Không dùng cho:** nhân vật, sinh vật (D9).

| Làm | Không làm |
|---|---|
| Chép blockout đã duyệt, dựng tiếp bằng part graph | Sửa blockout gốc (việc của Blockout) |
| Detail pass, gộp mesh, quét lỗi, UV | Gen mesh bằng AI |
| Chuẩn bị bộ render DUYỆT 1, khóa mesh | Tự duyệt. Gọi reviewer |
| — | Chọn Meshy hay vẽ mới, gọi Meshy, vẽ texture (việc của Texture Artist, bước `texture`) |
| Bước `assemble`: gắn texture, xuất GLB, QA lại, render `final_lit_vs_concept`, chuẩn bị DUYỆT 2 | Thu nhỏ texture, làm LOD (việc của agent khác, làm sau) |
| Viết README và `notes` của kết quả cuối | Chép vào `deliver/` (script làm khi duyệt, D14.8). Ghi trạng thái |

## 2. Đầu vào

| Nguồn | Lấy gì |
|---|---|
| `final/` đã duyệt của bước `blockout` (brief chỉ định) | `part_graph.json` (schema `blockout-1`), `parts_lib.py`, `sources.json`, `blockout.md` |
| `final/` đã duyệt của bước `views_rest` (brief chỉ định) | Vị trí chi tiết trên các mặt |
| Concept albedo | Màu, vật liệu, chi tiết |
| Concept có bóng | Đọc khối và độ sâu. Không lấy màu |
| Concept brief | Ghi chú real/texture_only (bắt buộc) |
| Preset, profile, thẻ asset (D13) | Hạng và trần tris, `texture_res`, thông số UV, ngưỡng pixel, ví dụ detail pass, camera |

Nếu hash của blockout không khớp với hash đã khóa, 3D Artist dừng và báo Producer.

## 3. Quy trình

### Phần A — Model (tới DUYỆT 1)

| # | Bước | Kiểm bằng |
|---|---|---|
| A1 | Chép `final/` của blockout đã duyệt sang `work/` của version này. Kiểm hash | `check_inputs.py` |
| A2 | Dựng từ part graph. Giữ đúng W×D×H, origin tâm đáy, mặt trước −Y, mét. Props giữ tách rời | gate của kit |
| A3 | **Detail pass** (mục 4) | `check_detail.py` |
| A4 | **Gộp mesh** (mục 5) | `check_mesh.py` |
| A5 | **UV** theo profile (mục 6) | `uv_check` của kit, `check_uv_edge.py` |
| A6 | QA của kit: `mesh_check`, `uv_check`, `export_check`, `screen_tris_check` | Script |
| A7 | Render bộ review (mục 7) | — |
| A8 | Ghi báo cáo contract. Producer giao review-clay. Nếu FIX, Producer giao lại: sửa đúng một `TOP_FIX` | Reviewer |
| A9 | Duyệt theo `approvals.model` (D14.4). Script chép sang `deliver/<id>/model/` | Anh hoặc chính sách |
| A10 | **Khóa mesh**: ghi hash của `<tên>-untextured.glb`. Từ đây không ai sửa mesh hay UV. Nếu buộc phải sửa, tạo version mới và đi lại từ A6 | — |

### Bước `assemble` (tới DUYỆT 2)

Bước `texture` (Texture Artist) nằm giữa `model` và `assemble`. Brief của `assemble` trỏ tới `final/` đã duyệt của `model` và `texture`.

| # | Việc | Kiểm bằng |
|---|---|---|
| C1 | Kiểm hash mesh khớp hash đã khóa ở A10. Nếu không khớp: `STATUS: BLOCKED` | `check_inputs.py` |
| C2 | Gắn texture, xuất GLB cuối (1 mesh / 1 node / 1 material, unlit), lưu `.blend` | — |
| C3 | Chạy lại QA của kit trên GLB cuối | Script |
| C4 | Render bộ DUYỆT 2 và `final_lit_vs_concept.png` (mục 7) | — |
| C5 | Viết README và `texture/notes.md` (mục 10). Ghi báo cáo contract | — |
| C6 | Producer giao review-texture (bản cuối trên model). `TOP_FIX: repaint` → Producer đưa về bước `texture`; `fix_uv_mesh` → về bước `model` | Reviewer |
| C7 | Duyệt theo `approvals.assemble` (luôn là anh). Script chép sang `deliver/<id>/` | Anh |

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
8. **Bevel:** tùy chọn trong profile. Nếu bật, bevel dùng cùng ngưỡng pixel.

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
2. **Không weld. Không boolean.** Union manifold3d chỉ dùng ở gate khi dựng từng part.
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
- `check_uv_edge.py` (mới): khoảng cách từ đảo UV tới mép atlas ≥ padding, và texel ≥ mức tối thiểu. Script báo cả số ở 2048 và số tương ứng ở 1024.

## 7. Bộ render review

Một script `render_review.py`, mở Blender một lần. 3D Artist có bản riêng, chép từ Blockout rồi thêm phần ánh sáng (D2).

| Ảnh | Dùng ở | Mục đích |
|---|---|---|
| `clay_*`, `normal_*`, `overlay_*`, `parts_*` (`render_views.py` của kit) | DUYỆT 1 | Khối, normal, silhouette, số thứ tự part |
| Clay có ánh sáng (sun + sky): 3/4 trước, cận mặt trước, 3/4 sau, camera game | DUYỆT 1 | Z-fighting, normal ngược, bóng chéo |
| `clay_lit_concept.png`: cùng góc và hướng nắng với concept có bóng, đặt cạnh concept đó | DUYỆT 1 | Độ chìa mái, độ sâu hốc, bóng đổ chính. Không so màu. Nếu không có concept có bóng thì bỏ qua |
| Wireframe 3/4 | DUYỆT 1 | Mặt phẳng không thừa cạnh |
| Thumbnail ở kích thước thật trên màn hình | DUYỆT 1 | Còn đọc được khối chính |
| Lineup với nhân vật | DUYỆT 1 | Tỉ lệ |
| Có texture, có ánh sáng, alpha bật: 3/4, cận trước, 3/4 sau, camera game | DUYỆT 2 | Lỗi texture trên model |
| `final_lit_vs_concept.png`: model có texture, cùng góc và hướng nắng với concept có bóng, đặt cạnh concept đó | DUYỆT 2, bàn giao | Anh so sánh và duyệt |

Hướng nắng của concept có bóng: 3D Artist ước lượng ở bước A7, ghi vào `spec.json`, và dùng lại ở B7.

**review-clay** (Opus, chỉ đọc, context mới mỗi lần):

1. Khối: chấm trên clay. Lỗi "ổ bánh mì" là fail.
2. Detail pass: đủ chi tiết đổi silhouette. So bảng detail pass với concept.
3. Shading: trên ảnh có ánh sáng, không có vệt đen, bóng chéo, mặt nhấp nháy.
4. Mặt phẳng: trên wireframe, không thừa cạnh.
5. Đọc được ở thumbnail.
6. Mật độ: tris/m² không lệch quá 2 lần so với pilot, trừ khi có lý do.
7. Đúng blockout: bbox và `fixed_params` không đổi.
8. Khối đọc như concept có bóng: độ chìa mái, độ sâu hốc, bóng đổ chính.

Output theo contract reviewer (D14.10, `docs/producer.md` §6). `TOP_FIX` của bước `model`: `structure`, `param`, `need_evidence`.

## 9. Báo cáo cho Producer

3D Artist không gọi agent khác (D14.1). Mỗi bước kết thúc bằng báo cáo contract của worker (`STATUS / OUTPUT / RUBRIC / ISSUES`, `docs/producer.md` §6). Nếu cần anh trả lời: `STATUS: NEEDS_CONTEXT` kèm câu hỏi.

## 10. Kết quả cuối (bước `assemble`)

3D Artist ghi vào `production/assets/<id>/assemble/vN/final/`. Khi anh duyệt DUYỆT 2, script chép sang `deliver/<id>/` (D14.8).

```
final/
  README.md              ← dòng đầu: trạng thái duyệt + ngày; cách làm; ngoại lệ; việc còn mở; những gì chưa kiểm
  model/
    <tên>.glb            ← có texture, 1 mesh / 1 node / 1 material, unlit
    <tên>.blend
    <tên>-untextured.glb ← mesh + UV đã khóa
    spec.json
  texture/
    albedo_2048.png
    notes.md             ← phương pháp, số lần gọi Meshy, Texture Artist đã sửa gì
  review/
    final_lit_vs_concept.png, sheet DUYỆT 1, sheet DUYỆT 2, crop chi tiết, JSON reviewer
```

- Hash của `<tên>-untextured.glb` phải khớp hash đã khóa ở A10. Nếu không khớp: `STATUS: BLOCKED`.
- Nếu anh hủy duyệt: ghi dòng trạng thái mới lên đầu README, không xóa dòng cũ.
- README liệt kê những gì chưa kiểm: engine, camera chưa chốt, % tam giác nhỏ.

## 11. Cảnh báo, không chặn

- `screen_tris_check`: tam giác < 10 px ở camera game chỉ là cảnh báo. Báo cáo DUYỆT 1 ghi con số. Nếu profile có `screen_tris_max_small_ratio`, script dùng số đó để chặn.

## 12. Tool

Chép từ kit v0.10.4 (khóa, không sửa): `self_build/` (giống Blockout), `asset_checks/` (`mesh_check`, `uv_check`, `export_check`, `screen_tris_check`, `render_rig`), `optimize/bake.py` (chỉ phần unwrap UV, cần xác nhận khi viết code), `finalize.py`, `report.py`.

Mới: `check_inputs.py`, `check_detail.py`, `check_mesh.py`, `check_uv_edge.py`, `render_review.py`.

`gen_api.py` (Meshy) và `texture_complexity.py` chuyển sang Texture Artist (D14.2).

Không chép: các path Meshy/Tripo/ZPS gen mesh, sweep, remesh, `project_concept.py`.

## 13. Việc cần kiểm khi viết code

- `bake.py` của kit ở chế độ `rebake` vừa unwrap vừa bake. Cần xem có tách riêng phần unwrap được không, hay phải viết một script unwrap mới.
- `gen_api.py texture` cần mạng. Bản Codex phải xin phép mạng ở phiên gốc (D6).
- Join không weld: `mesh_check` của kit có thể báo "duplicate verts" ở cạnh đã tách. Cần đặt ngưỡng trong spec cho đúng.
