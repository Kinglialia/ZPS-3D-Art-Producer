# Spec — sub-agent Texture Artist (v1)

Tên kỹ thuật: `zps-3dp-texture-artist`. Tên hiển thị: ZPS-3DP - Texture Artist. Reviewer: `zps-3dp-review-texture`.
Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D1, D6, D7, D8, D10, D11).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-surface, zps-texture-review, zps-3d-artist `project_concept.py`).

---

## 1. Vai trò

3D Artist gọi Texture Artist, gửi kèm **phần A** của handoff (mẫu `3d-texture-handoff.md` của kit). Texture Artist làm texture albedo 2048 cho một mesh đã khóa, tự gọi review-texture, rồi trả **phần B** cho 3D Artist.

**Dùng cho:** công trình, props cứng, cây và đá low-poly (D9). Version sau có dùng chung cho nhóm nhân vật hay không: chưa chốt.

| Làm | Không làm |
|---|---|
| Chế độ SỬA: sửa trên lớp Meshy | Sửa mesh, UV, tách material slot (ghi vào phần B cho 3D Artist) |
| Chế độ VẼ MỚI: tô nền, vẽ paint view, chiếu lên UV, sửa seam | Đổi thiết kế, thêm motif mới |
| Tự kiểm bằng `tex_measure.py`, gọi review-texture | Gắn texture vào model, xuất GLB (việc của 3D Artist) |
| Ghi phần B | Tự duyệt. Thu nhỏ texture |

## 2. Đầu vào (phần A của handoff)

- Mesh đã khóa (`<tên>-untextured.glb`) và hash.
- Chế độ: SỬA hoặc VẼ MỚI. Lý do (D10, Producer chỉ định, không có key Meshy, Meshy hỏng).
- Chế độ SỬA: lớp texture Meshy.
- Bảng part → mã vật liệu, ảnh `parts_*`.
- Concept albedo, `concept_colors.json`, gói View Concept (views chỉ làm ảnh tham chiếu, TEXTURE NOTE).
- Thẻ asset: `texture_res` (mặc định 2048). Profile: quy ước ánh sáng (`style.light_convention`), `visual_checks`. Preset và mặc định skill: ngưỡng 4 nhóm (D13).
- Lỗi cần sửa (từ review-texture hoặc từ anh), nếu đây là vòng sửa.

Nếu hash mesh không khớp, Texture Artist dừng và báo 3D Artist.

## 3. Chế độ SỬA (trên lớp Meshy)

1. **Giữ** nét cọ Meshy. **Giữ** các chi tiết Meshy đã đặt đúng vị trí, đối chiếu với views.
2. **Chỉ vẽ lại chỗ sai:** chi tiết thừa, bóng bake, AO, lệch tông giữa các hướng, seam, hoa văn lem, TEXTURE NOTE.
3. **Vẽ lại cho sắc** hoa văn, đinh, sọc bị Meshy làm lem, theo concept.
4. **Không sửa quá tay.** Giữ vân, vết mòn, muội đúng mức concept.
5. Mỗi lần sửa đi qua **sửa theo crop** (mục 5).

## 4. Chế độ VẼ MỚI (tô nền + paint view)

| # | Bước | Tool |
|---|---|---|
| 1 | **Tô nền.** Tô từng vùng UV theo mã vật liệu, màu từ `concept_colors.json`. Áp quy ước ánh sáng của profile (ví dụ gradient sáng từ trên xuống) | `base_fill.py` (mới) |
| 2 | **Render paint guide.** Render mesh đã khóa, đã tô nền, từ **8 góc**: chia đều quanh vật, độ cao xen kẽ khoảng ±30° | `render_paint_views.py` (mới) |
| 3 | **Vẽ paint view.** Codex vẽ góc front trước làm chuẩn màu, rồi 7 góc còn lại. Prompt: unlit, không bóng đổ, theo concept albedo; ảnh guide của góc đó; ảnh front đã vẽ | `gen_image_codex.py` (D8) |
| 4 | **Chiếu lên UV.** Chiếu 8 view, trọng số theo mức mặt nhìn thẳng vào camera. Loại vùng bị che ở từng view | `project_concept.py` (bản chép, có sửa) |
| 5 | **Lấp vùng khuất trong không gian 3D.** Lấy màu từ điểm lân cận trên model, ưu tiên điểm cùng hướng normal. Nếu không có điểm phù hợp, giữ màu nền của bước 1 | `project_concept.py` (có sửa) |
| 6 | **Sửa seam trong không gian 3D.** Tìm pixel seam từ mask UV, tô lại bằng trung bình có trọng số của điểm lân cận trên model. Chỉ gọi Codex sửa crop khi script không xử lý được | `seam_fix.py` (mới) |
| 7 | Tự kiểm, rồi gọi review-texture | `tex_measure.py`, reviewer |

- Với asset rất đơn giản, bước 1 cộng nét vẽ ở bước 3 có thể là đủ.
- **Không chiếu ảnh view của Concept Views lên model.** Ảnh view vẽ trên blockout, không phải mesh cuối. Ảnh view chỉ là ảnh tham chiếu.
- Không vẽ thẳng lên atlas UV. Lý do: nét chạy theo mép UV, không theo khối (pilot và kit).

## 5. Sửa theo crop (cả hai chế độ)

1. Cắt crop vùng cần sửa, tối đa 1024 px, có lề.
2. Codex sửa crop (D8).
3. Ghép crop vào atlas, làm mềm mép.
4. **Kiểm:** pixel nằm ngoài vùng sửa không được đổi. Nếu đổi, loại kết quả (`crop_edit.py`, mới).

## 6. Tự kiểm — 4 nhóm (`tex_measure.py`)

`tex_measure.py` viết lại từ script pilot cho tổng quát. Vùng vật liệu đọc từ ID map, ID map lấy từ mã vật liệu của part. Ngưỡng mặc định nằm trong profile.

| Nhóm | Nguyên tắc | Đo |
|---|---|---|
| 1. Quy ước ánh sáng | Ánh sáng trong albedo đúng quy ước của style, đồng nhất trên mọi mặt | Chia mặt theo normal. 4 mặt bên cùng tông (chênh ≤ 3 L*). Mặt trên so với mặt bên đúng `top_vs_side_L`. Vùng bị che không tối hơn quy ước. Không AO, glow, highlight cố định |
| 2. Đúng vật liệu | Mỗi vật liệu giống concept và giống asset đã duyệt cùng bộ | dE theo từng mã vật liệu so với concept (≤ 3) và so với asset pilot cùng mã. Mỗi mã đo riêng |
| 3. Đọc được ở kích thước thật | Ở camera game, vật liệu tách nhau rõ; chi tiết không thành nhiễu | Thu render về cỡ màn hình: chênh L* giữa vật liệu kề nhau, năng lượng nhiễu tần số cao. Nét chi tiết ≥ 4–6 px ở 2048 |
| 4. Liền mạch | Không lộ seam, không texel trống, không lem ở mip | Seam đo trong 3D (p90 ≤ 4). Đếm texel chưa vẽ hoặc đen. Kiểm padding |

**Quy ước ánh sáng trong profile:**

```
style:
  light_convention: unlit_flat | painted_top_light
  top_vs_side_L: 0 | +8
visual_checks:
  - "..."    # review-texture kiểm bằng mắt
```

Quy tắc riêng của dự án (ví dụ New Last Order: mái là ngói xếp lớp theo dốc, tường đọc ra từng viên đá, viền vàng dừng đúng mép khung) nằm trong `visual_checks`, không nằm trong agent.

## 7. Reviewer `zps-3dp-review-texture`

Opus, chỉ đọc, context mới mỗi lần, không có tool gọi agent (D1). Texture Artist gọi reviewer. Nếu Texture Artist không có tool gọi agent, Texture Artist trả `review: pending` và 3D Artist gọi reviewer (D6.2).

**Reviewer nhận:**
- Render có texture, có ánh sáng: 3/4 trước, cận trước, 3/4 sau, camera game.
- Render unlit (chỉ albedo) cùng góc.
- Thumbnail ở kích thước thật.
- Atlas 2048 và crop các vùng đã sửa.
- JSON của `tex_measure.py`.
- Concept albedo, `visual_checks`, TEXTURE NOTE.
- Chế độ SỬA: lớp Meshy gốc đặt cạnh bản đã sửa.

**Tiêu chí:**
1. Quy ước ánh sáng: không bóng bake, AO, glow ngoài quy ước; các mặt bên cùng tông.
2. Đúng vật liệu so với concept và bộ đã duyệt.
3. Đọc được ở thumbnail.
4. Liền mạch: không thấy seam ở camera game; nét theo khối, không theo mép UV.
5. Từng mục `visual_checks`.
6. TEXTURE NOTE đã xử lý hết.
7. Chế độ SỬA: chi tiết Meshy đúng vẫn còn; không sửa quá tay.

**Chẩn đoán trước khi đề xuất sửa** (theo kit). Lỗi đen hoặc sai màu: kiểm color space, alpha, normal trước khi vẽ lại. Lỗi seam: kiểm UV và padding trước khi làm mờ. Nếu không tách được do map hay do UV, ghi cả hai giả thuyết.

**Output:** JSON theo D1. `top_fix` thuộc đúng một loại:

| Loại | Ai sửa | Khi nào |
|---|---|---|
| `repaint: <vùng>, lỗi: <mô tả>` | Texture Artist, sửa theo crop | Lỗi vẽ, sửa được |
| `fix_uv_mesh: <mô tả>` | 3D Artist (version mới, DUYỆT 1 lại) | Lỗi do UV, mesh, normal |
| `meshy_regen: <lý do>` | 3D Artist gọi Meshy lần 2, chỉ khi Texture Artist cũng xác nhận "không sửa được" (D7.2) | `blocker`: hỏng cả style hoặc phần lớn bề mặt |
| `note: <nội dung>` | Ghi vào `texture/notes.md` | `minor`, không chặn |

Duyệt theo ủy quyền (D1.5) chỉ khi không còn `blocker`, `major` hay `unclear`.

## 8. Vòng sửa (D11)

- Tối đa 3 vòng tự sửa theo reviewer trước khi trả 3D Artist.
- Dừng sớm: nếu một vòng không giảm số lỗi `blocker` + `major` so với vòng trước, dừng và trả kết quả kèm lý do.
- Vòng nào tệ hơn thì hoàn tác. Giữ bản tốt nhất, không giữ bản mới nhất.
- Feedback của anh mở một đợt mới, đếm lại từ 0.

## 9. Đầu ra (phần B của handoff)

- `albedo_2048.png`.
- Phần B: chế độ đã làm và lý do; vùng đã sửa; render trên model đã mở (ghi renderer: Blender, không phải engine); kết quả review-texture (tự kiểm hay độc lập, lỗi còn mở) hoặc `review: pending`; yêu cầu gửi 3D Artist (UV, mesh) gom trong một lần; những gì chưa kiểm.
- Chế độ SỬA: nếu lỗi không sửa được, ghi "không sửa được, lý do: …" (điều kiện để gọi Meshy lần 2).
- Ghi chú cài đặt material cho người nhập vào engine: unlit, base color only.

Báo cáo ngắn trả 3D Artist theo mẫu cố định (D6.3).

## 10. Tool

**Chép từ kit v0.10.4 (bản riêng, D2):**
- `project_concept.py` (zps-3d-artist), **có sửa**: 8 view, trọng số theo góc nhìn, loại vùng bị che, lấp vùng khuất trong 3D. Ghi phần sửa trong `SOURCE.md`.
- `render_model.py`, `inspect_model.py`, `palette_report.py` (`.art-production-support/shared/scripts`).

**Mới:** `base_fill.py`, `render_paint_views.py`, `seam_fix.py`, `crop_edit.py`, `tex_measure.py`.

**Dùng chung với Concept Views:** `gen_image_codex.py` (D8).

## 11. Việc cần kiểm khi viết code

Ghi trong `docs/coding-checklist.md`.
