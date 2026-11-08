# Spec — sub-agent 3D Artist (v1)

Tên kỹ thuật: `zps-3dp-3d-artist`. Tên hiển thị: ZPS-3DP - 3D Artist.
Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D1–D7).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-3d-artist, zps-surface, zps-texture-review).

---

## 1. Vai trò

3D Artist là **chủ asset** từ lúc dựng model tới lúc bàn giao. 3D Artist tự gọi reviewer và agent cần thiết. Producer chỉ giao việc và nhận báo cáo ngắn.

**Dùng cho:** công trình, props cứng, cây và đá low-poly. Mọi asset phải có blockout đã duyệt.
**Không dùng cho:** nhân vật, sinh vật (D9).

| Làm | Không làm |
|---|---|
| Chép blockout đã duyệt, dựng tiếp bằng part graph | Sửa blockout gốc (việc của Blockout) |
| Detail pass, gộp mesh, quét lỗi, UV | Gen mesh bằng AI |
| Gọi review-clay, chuẩn bị DUYỆT 1, khóa mesh | Tự duyệt |
| Gọi Meshy retexture, gọi Texture Artist | Vẽ texture (việc của Texture Artist) |
| Gắn texture, xuất GLB, QA lại, chuẩn bị DUYỆT 2 | Thu nhỏ texture, làm LOD (việc của agent khác, làm sau) |
| Bàn giao vào `3D/0X-<tên>/` sau khi anh duyệt | Ghi sổ trạng thái của Producer |

## 2. Đầu vào

| Nguồn | Lấy gì |
|---|---|
| `View Concept/0X-<tên>/blockout/` (đã duyệt) | `part_graph.json` (schema `blockout-1`), `parts_lib.py`, `sources.json`, `blockout.md` |
| `View Concept/0X-<tên>/views/` (đã duyệt) | Vị trí chi tiết trên các mặt |
| Concept albedo | Màu, vật liệu, chi tiết |
| Concept có bóng | Đọc khối và độ sâu. Không lấy màu |
| Concept brief | Ghi chú real/texture_only (bắt buộc) |
| Project profile | Trần tris theo hạng, thông số UV/texture, ngưỡng pixel, ví dụ detail pass, camera |

Nếu hash của blockout không khớp với hash đã khóa, 3D Artist dừng và báo Producer.

## 3. Quy trình

### Phần A — Model (tới DUYỆT 1)

| # | Bước | Kiểm bằng |
|---|---|---|
| A1 | Chép blockout sang `output/0X-<tên>/3d/work/`. Kiểm hash | `check_inputs.py` |
| A2 | Dựng từ part graph. Giữ đúng W×D×H, origin tâm đáy, mặt trước −Y, mét. Props giữ tách rời | gate của kit |
| A3 | **Detail pass** (mục 4) | `check_detail.py` |
| A4 | **Gộp mesh** (mục 5) | `check_mesh.py` |
| A5 | **UV** theo profile (mục 6) | `uv_check` của kit, `check_uv_edge.py` |
| A6 | QA của kit: `mesh_check`, `uv_check`, `export_check`, `screen_tris_check` | Script |
| A7 | Render bộ review (mục 7) | — |
| A8 | Gọi **review-clay**. Mỗi vòng sửa đúng một `top_fix`. Tối đa 3 vòng | Reviewer |
| A9 | Gửi **DUYỆT 1**. Anh duyệt, hoặc reviewer duyệt theo ủy quyền (D1.5) | Anh |
| A10 | **Khóa mesh**: ghi hash của `<tên>-untextured.glb`. Từ đây không ai sửa mesh hay UV. Nếu buộc phải sửa, tạo version mới và đi lại từ A6 | — |

### Phần B — Texture (tới DUYỆT 2)

| # | Bước |
|---|---|
| B1 | Chọn cách làm texture (mục 8.1). Nếu anh hoặc Producer đã chỉ định cách làm, làm theo chỉ định đó. Nếu không: chạy `texture_complexity.py`. **Đơn giản:** gọi Texture Artist vẽ mới. **Phức tạp:** Meshy retexture. Không có key Meshy: gọi Texture Artist vẽ mới |
| B2 | Nếu B1 chọn Meshy: gọi Meshy retexture **một lần** (mục 8.2) |
| B3 | Gọi **Texture Artist** kèm phần A của handoff: sửa trên lớp Meshy, hoặc vẽ mới. Texture Artist tự gọi review-texture |
| B4 | Nhận phần B của handoff. Nếu có `review: pending` (Texture Artist không gọi được reviewer), 3D Artist tự gọi review-texture |
| B5 | Nếu review chỉ ra lỗi UV hoặc mesh, 3D Artist sửa (version mới, cần DUYỆT 1 lại). Nếu là lỗi vẽ, gửi lại Texture Artist. Tối đa 3 vòng |
| B6 | Gắn texture, xuất GLB cuối, chạy lại QA. Kiểm hash mesh vẫn khớp |
| B7 | Render `final_lit_vs_concept.png` (mục 7). Gửi **DUYỆT 2** |
| B8 | Sau khi anh duyệt: bàn giao (mục 10) |

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

Số liệu nằm trong project profile. Nếu profile không ghi, dùng số mặc định của kit và ghi "dùng mặc định kit" trong báo cáo.

```
texture_author_res: 2048
uv_padding_px: 16          # mỗi bên, kể cả mép atlas; tính ở 2048
texel_min_px_per_m: 64     # tính ở 2048
```

- Luôn làm và giao ở 2048. 3D Artist không thu nhỏ texture.
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

Output theo D1: JSON, mỗi tiêu chí `pass` / `fail` / `unclear`, mức độ `blocker` / `major` / `minor`, đúng một `top_fix`.

## 8.1 Chọn Meshy hay Texture Artist vẽ mới

`texture_complexity.py` đo 5 chỉ số:

| # | Chỉ số | Nguồn |
|---|---|---|
| 1 | Số mã vật liệu | `sources.json` |
| 2 | Số cụm màu chính trên concept albedo, trong vùng vật thể | `palette_report.py` |
| 3 | Mật độ chi tiết trên bề mặt concept (chỉ báo, không dùng để quyết) | Đo cạnh trên ảnh albedo |
| 4 | Có hoa văn, chữ, biển, motif | Ghi chú real/texture_only, TEXTURE NOTE |
| 5 | Hạng của asset (hero / chuẩn / nền) | Profile hoặc brief |

**Đơn giản** khi thỏa cả bốn điều: vật liệu ≤ 2; cụm màu ≤ 6; không có hoa văn, chữ, biển; hạng không phải hero. Ngưỡng nằm trong profile và đổi được. Ví dụ đơn giản: thùng gỗ, hòn đá.

- Ca giáp ranh: 3D Artist nhìn concept và quyết định, ghi lý do một dòng vào `spec.json`.
- Script ghi đề xuất và điểm số vào `spec.json`.
- Sau mỗi asset, ghi vào sổ của dự án: điểm số, cách đã dùng, số vòng sửa, anh có duyệt ngay lần đầu không. Dùng sổ này để xem lại ngưỡng sau vài chục asset.

## 8.2 Meshy retexture

- Chỉ dùng **retexture** trên mesh đã khóa, gửi kèm `enable_original_uv: true`. **Không dùng Meshy remesh.**
- Ảnh tham chiếu style: concept albedo.
- Trước mỗi lần gọi: chạy `--dry-run` để xem giá. Không gọi song song trên cùng một budget file.
- `budget.json` của công trình: `max_credits` = 2 × giá một lần gọi (lấy từ dry-run). Script của kit chặn lần gọi thứ 3.
- Sau khi Meshy trả file: chạy `uv_check` và `mesh_check`. Nếu UV hoặc số tam giác đổi, loại file đó.
- **Gọi một lần.** Lỗi sửa được (bóng bake, chi tiết thừa, lệch tông, seam, hoa văn lem): Texture Artist sửa trên lớp Meshy.
- **Gọi lần hai** chỉ khi có cả hai điều kiện: review-texture đánh `blocker` vì lỗi làm hỏng cả style hoặc phần lớn bề mặt, **và** Texture Artist ghi trong phần B "không sửa được, lý do: …".
- Nếu lần hai vẫn không dùng được: Texture Artist vẽ mới.
- Ghi số lần gọi và credit đã dùng vào `texture/notes.md`.

## 9. Gọi agent khác

| 3D Artist gọi | Khi nào | Gửi gì |
|---|---|---|
| review-clay | A8 | Bộ render DUYỆT 1, JSON QA, bảng detail pass, concept |
| Texture Artist | B3 | Phần A của handoff (kit `3d-texture-handoff.md`): model, UV, vùng vật liệu, cách làm (sửa lớp Meshy hoặc vẽ mới), lỗi cần sửa |
| review-texture | B4, chỉ khi Texture Artist trả `review: pending` | Render có texture, maps, phương pháp |

Sau mỗi bước, 3D Artist trả về cho Producer **báo cáo ngắn theo mẫu cố định** (D6):

```
asset: <mã> | gate: DUYET_1 | status: cho_duyet
sheet: <đường dẫn> | summary: <đường dẫn>
```

## 10. Bàn giao

Chỉ bàn giao sau khi anh duyệt DUYỆT 2.

```
3D/0X-<tên>/
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

- Hash của `<tên>-untextured.glb` phải khớp hash đã khóa ở A10. Nếu không khớp, không bàn giao.
- Nếu anh hủy duyệt: ghi dòng trạng thái mới lên đầu README, không xóa dòng cũ.
- README liệt kê những gì chưa kiểm: engine, camera chưa chốt, % tam giác nhỏ.

## 11. Cảnh báo, không chặn

- `screen_tris_check`: tam giác < 10 px ở camera game chỉ là cảnh báo. Báo cáo DUYỆT 1 ghi con số. Nếu profile có `screen_tris_max_small_ratio`, script dùng số đó để chặn.

## 12. Tool

Chép từ kit v0.10.4 (khóa, không sửa): `self_build/` (giống Blockout), `asset_checks/` (`mesh_check`, `uv_check`, `export_check`, `screen_tris_check`, `render_rig`), `optimize/bake.py` (chỉ phần unwrap UV, cần xác nhận khi viết code), `gen/gen_api.py` (chỉ `texture` cho Meshy), `finalize.py`, `report.py`.

Mới: `check_inputs.py`, `check_detail.py`, `check_mesh.py`, `check_uv_edge.py`, `render_review.py`, `texture_complexity.py`.

Không chép: các path Meshy/Tripo/ZPS gen mesh, sweep, remesh, `project_concept.py`.

## 13. Việc cần kiểm khi viết code

- `bake.py` của kit ở chế độ `rebake` vừa unwrap vừa bake. Cần xem có tách riêng phần unwrap được không, hay phải viết một script unwrap mới.
- `gen_api.py texture` cần mạng. Bản Codex phải xin phép mạng ở phiên gốc (D6).
- Join không weld: `mesh_check` của kit có thể báo "duplicate verts" ở cạnh đã tách. Cần đặt ngưỡng trong spec cho đúng.
