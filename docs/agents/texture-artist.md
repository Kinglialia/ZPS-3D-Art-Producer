# Spec — sub-agent Texture Artist (v1.2)

Tên kỹ thuật: `zps-3dp-step-texture`. Tên hiển thị: 3DP Step · Texture. Reviewer: `zps-3dp-check-texture` (D23.2).
Duyệt: 2026-11-08. v1.1: 2026-11-09 (D21). v1.2: 2026-11-09 (D22). Quyết định nền: `docs/decisions.md` (D1, D6, D7, D8, D10, D11, D21, D22).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-surface, zps-texture-review, zps-3d-artist `project_concept.py`).

---

## 1. Vai trò

Texture Artist làm bước `texture` của pipeline (D14.2), giữa `model` và `assemble`. Script sinh brief từ các `final/` đã duyệt (`blockout` để đọc `sources.json`, `model`, `views_rest`) và file concept trong `_approved/<id>/`. Script chép mục `ISSUES` của report bước `model` đã duyệt vào brief. Không có file handoff. Texture Artist tự chọn chế độ (mục 2.1, D17), gọi Meshy khi cần, làm texture albedo theo `texture_res`, rồi ghi báo cáo contract. Producer giao check-texture và đếm vòng sửa (D14.1). Texture Artist không gọi reviewer, không gọi agent khác. Chỉ đọc file và thư mục brief chỉ định.

**Dùng cho:** công trình, props cứng, cây và đá low-poly (D9). Version sau có dùng chung cho nhóm nhân vật hay không: chưa chốt.

| Làm | Không làm |
|---|---|
| Chế độ SỬA: sửa trên lớp Meshy | Sửa mesh, UV, tách material slot (yêu cầu chỉ đi qua `TOP_FIX: fix_uv_mesh`, mục 7) |
| Chế độ VẼ MỚI: tô nền, vẽ paint view, chiếu lên UV, sửa seam | Đổi thiết kế, thêm motif mới |
| Chọn chế độ (D10), gọi Meshy retexture | Gắn texture vào model và xuất GLB cuối (việc của script `assemble.py`, D22.11) |
| Tự kiểm bằng `tex_measure.py`, ghi báo cáo contract | Gọi reviewer. Tự duyệt. Thu nhỏ texture |

## 2. Đầu vào (brief do script sinh)

- Mesh đã khóa (`<tên>-untextured.glb`) và hash.
- Mục `ISSUES` của report bước `model` đã duyệt (script chép vào brief).
- Chỉ định cách làm của anh hoặc Producer, nếu có (mục 2.1).
- Bảng part → mã vật liệu, ảnh `parts_*`, `spec.json` (từ `final/` của `model`; chỉ đọc).
- `sources.json` (từ `final/` của `blockout`): danh sách mã vật liệu.
- Concept albedo, `concept_colors.json`, `final/` đã duyệt của `views_rest` (views chỉ làm ảnh tham chiếu; TEXTURE NOTE trong README).
- Thẻ asset: `texture_res` (mặc định 2048). Profile: quy ước ánh sáng (`style.light_convention`). Rubric theo loại, mục `texture` (D14.6). Preset và mặc định skill: ngưỡng 4 nhóm (D13).
- Lỗi cần sửa (`TOP_FIX` của reviewer hoặc feedback của anh), nếu đây là vòng sửa.

Script kiểm hash mesh khi sinh brief (D22.12). Texture Artist chỉ kiểm các file brief chỉ định có tồn tại. Số hình học lấy từ `sources.json` (D22.13).

## 2.1 Chọn chế độ: Meshy rồi SỬA, hay VẼ MỚI

**[Sửa theo D30.11]** Script chọn chế độ trước khi giao bước `texture` và ghi dòng `MODE:` vào brief. Ledger ghi chế độ đã chọn và lý do (mỗi lần chế độ hoặc lý do đổi).

- Có key Meshy và budget → **Meshy SỬA**, không xét độ phức tạp. Đây là chế độ mặc định.
- Hết lần gọi mà mesh này đã có lớp Meshy qua topology (D30.3) → Meshy SỬA trên lớp đó.
- Profile không có `paths.env_file`, anh chỉ định, hoặc hết lần gọi mà không có lớp Meshy dùng được → **VẼ MỚI**. Anh chỉ định bằng `P texture-mode <id> paint` trước bước texture, hoặc `meshy <id> paint` khi trả lời câu hỏi Meshy của script.
- `P texture-mode <id> meshy` buộc Meshy; hết budget mà không có lớp dùng được thì asset `blocked`. `auto` trả về quy tắc mặc định (`docs/producer.md` §6.3).
- Có `env_file` mà thiếu key: script chặn trước khi giao bước (`docs/producer.md` §6.3).

Năm chỉ số dưới đây vẫn được đo và ghi, chỉ để tham khảo và để đo lại sau 3–5 asset. `proposed` trong `texture_spec.json` là chế độ của dòng `MODE:`.

`texture_complexity.py` đo 5 chỉ số:

| # | Chỉ số | Nguồn |
|---|---|---|
| 1 | Số mã vật liệu | `sources.json` (`final/` của `blockout`) |
| 2 | Số cụm màu chính trên concept albedo, trong vùng vật thể | `palette_report.py` |
| 3 | Mật độ chi tiết trên bề mặt concept (chỉ báo, không dùng để quyết) | Đo cạnh trên ảnh albedo |
| 4 | Có hoa văn, chữ, biển, motif | Ghi chú real/texture_only, TEXTURE NOTE |
| 5 | Hạng của asset (hero / chuẩn / nền) | Profile hoặc brief |

**Đơn giản** khi thỏa cả bốn điều: vật liệu ≤ 2; cụm màu ≤ 6; không có hoa văn, chữ, biển; hạng không phải hero. Ngưỡng nằm trong profile và đổi được. Ví dụ đơn giản: thùng gỗ, hòn đá.

- Script ghi đề xuất và điểm số vào `texture_spec.json` (trong `texture/vN/final/`). Texture Artist không ghi vào `spec.json` của 3D Artist (D20.11).
- Texture Artist ghi điểm số, chế độ đề xuất và chế độ đã dùng vào `texture_spec.json`. Texture Artist **không** ghi ra ngoài thư mục version (D21.5). Muốn xem lại ngưỡng sau vài chục asset (D10): `P texture-stats` tổng hợp từ ledger và các `texture_spec.json` lúc cần, không duy trì file sổ riêng (D22.17).

## 2.2 Gọi Meshy retexture

- Chỉ dùng **retexture** trên mesh đã khóa, gửi kèm `enable_original_uv: true`. **Không dùng Meshy remesh.**
- Ảnh tham chiếu style: concept albedo.
- Trước mỗi lần gọi: chạy `--dry-run` để xem giá.
- **Gọi qua `meshy_call.py`** (D24.2), không gọi thẳng `gen_api.py`. Wrapper lấy key từ `.env` của project (D24.3), quản budget theo hash mesh trong file `texture/budget-<mesh_hash>.json` đúng định dạng của kit, và xử lý lỗi (`docs/producer.md` §6.3). Texture Artist không đọc `.env`, không truyền key. Giới hạn `meshy = 1` trong `[limits]` bảo đảm không gọi song song.
- Sau khi Meshy trả file (D30.3): albedo là `texture_urls[0].base_color` của task, không phải ảnh trong GLB. Meshy chuẩn hóa GLB (scale ×2, dời tâm z), nên `meshy_call.py` chỉ so topology với mesh đã khóa: số tam giác, và tập bộ ba UV của tam giác (dung sai 1e-4). Wrapper xin `texture_resolution` nhỏ nhất (`2k`, `4k`, `8k`) ≥ `texture_res`. `base_color` lớn hơn thì thu về `texture_res` (bộ lọc vùng); nhỏ hơn thì fail. Lệch một điều: loại lớp đó. Đây là gate cứng, không khai `ACCEPTED_FAIL`.
- **Gọi một lần cho mỗi mesh** (D20.14, D21.2). Texture Artist là agent duy nhất gọi Meshy.
- **Mesh đổi** (sau `fix_uv_mesh` hoặc anh làm lại `model`): texture Meshy cũ làm trên UV cũ, không dùng được. Script hỏi anh gọi lại Meshy hay VẼ MỚI trước khi giao bước `texture`. Brief ghi chỉ định đó.
- **Lỗi kỹ thuật:** kit trừ budget trước khi gọi. Lỗi trước khi task được tạo: wrapper hoàn budget và thử lại. Lỗi sau khi task đã tạo (hết thời gian chờ, lỗi tải file): wrapper chờ tiếp đúng `task_id` đó, **không tạo task mới**. Tối đa 3 lần (như D8.3). Sau 3 lần: `STATUS: BLOCKED` kèm lỗi, Producer hỏi anh (D24.2, sửa D20.14).
- Lỗi sửa được (bóng bake, chi tiết thừa, lệch tông, seam, hoa văn lem): chế độ SỬA trên lớp Meshy, qua các vòng review thường.
- **Không sửa được:** check-texture trả `TOP_FIX: meshy_regen`, hoặc Texture Artist ghi `UNFIXABLE: yes` kèm lý do. Script đặt `waiting_human`. Anh duyệt lần gọi thứ hai. Chỉ khi brief tiếp theo ghi "được gọi Meshy thêm một lần", Texture Artist mới gọi lại. Script không tự cho.
- Nếu lần hai vẫn không dùng được: chế độ VẼ MỚI.
- Không tự khai số lần gọi trong báo cáo (D21.2, thay `MESHY_CALLS` của D20.14). Script tính từ file budget: số lần = `used_credits / giá`.
- Ghi số lần gọi, số lần thử lại do lỗi kỹ thuật và credit đã dùng vào `texture/notes.md`.

## 3. Chế độ SỬA (trên lớp Meshy)

1. **Giữ** nét cọ Meshy. **Giữ** các chi tiết Meshy đã đặt đúng vị trí, đối chiếu với views.
2. **Chỉ vẽ lại chỗ sai:** chi tiết thừa, bóng bake, AO, lệch tông giữa các hướng, seam, hoa văn lem, TEXTURE NOTE.
3. **Vẽ lại cho sắc** hoa văn, đinh, sọc bị Meshy làm lem, theo concept.
4. **Không sửa quá tay.** Giữ vân, vết mòn, muội đúng mức concept.
5. **Script sửa trước (D17).** Chạy `tone_fix.py` trước khi gọi Codex: cân tông các mặt bên theo hướng normal, nâng vùng bị che về mức quy ước (ví dụ dưới diềm), làm mịn seam theo số đo của `tex_measure.py`. Đo lại sau khi chạy.
6. Chỉ những lỗi script không sửa được (chi tiết thừa, hoa văn lem, vẽ lại cho sắc, TEXTURE NOTE) mới đi qua **sửa theo crop** bằng Codex (mục 5).

## 4. Chế độ VẼ MỚI (tô nền + paint view)

| # | Bước | Tool |
|---|---|---|
| 1 | **Tô nền.** Tô từng vùng UV theo mã vật liệu, màu từ `concept_colors.json`. Áp quy ước ánh sáng của profile (ví dụ gradient sáng từ trên xuống) | `base_fill.py` (mới) |
| 2 | **Render paint guide.** Render mesh đã khóa, đã tô nền, từ **8 góc**: chia đều quanh vật, độ cao xen kẽ khoảng ±30° | `render_paint_views.py` (mới) |
| 3 | **Vẽ paint view.** Codex vẽ góc front trước làm chuẩn màu, rồi 7 góc còn lại. Prompt: unlit, không bóng đổ, theo concept albedo; ảnh guide của góc đó; ảnh front đã vẽ | `gen_image_codex.py` (D8) |
| 4 | **Chiếu lên UV.** Chiếu 8 view, trọng số theo mức mặt nhìn thẳng vào camera. Loại vùng bị che ở từng view | `project_concept.py` (bản chép, có sửa) |
| 5 | **Lấp vùng khuất trong không gian 3D.** Lấy màu từ điểm lân cận trên model, ưu tiên điểm cùng hướng normal. Nếu không có điểm phù hợp, giữ màu nền của bước 1 | `project_concept.py` (có sửa) |
| 6 | **Sửa seam trong không gian 3D.** Tìm pixel seam từ mask UV, tô lại bằng trung bình có trọng số của điểm lân cận trên model. Chỉ gọi Codex sửa crop khi script không xử lý được | `seam_fix.py` (mới) |
| 7 | Tự kiểm, ghi báo cáo. Producer giao check-texture (D14.1) | `tex_measure.py`, reviewer |

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
| 1. Quy ước ánh sáng | Ánh sáng trong albedo đúng quy ước của style, đồng nhất trên mọi mặt. Mặt trong khe rãnh và hốc lõm không tính vào `light.shaded_share` (D27.9, dưới bảng) | Chia mặt theo normal. 4 mặt bên cùng tông (chênh ≤ 3 L*). Mặt trên so với mặt bên đúng `top_vs_side_L`. Vùng bị che không tối hơn quy ước. Không AO, glow, highlight cố định |
| 2. Đúng vật liệu | Mỗi vật liệu giống concept và giống asset đã duyệt cùng bộ | dE theo từng mã vật liệu so với concept (≤ 3) và so với asset pilot cùng mã. Mỗi mã đo riêng. Chưa có `pilot_asset` (D21.7): phần so với pilot ghi `not_checked` |
| 3. Đọc được ở kích thước thật | Ở camera game, vật liệu tách nhau rõ; chi tiết không thành nhiễu | Thu render về cỡ màn hình: chênh L* giữa vật liệu kề nhau, năng lượng nhiễu tần số cao. Nét chi tiết ≥ 4–6 px ở 2048 |
| 4. Liền mạch | Không lộ seam, không texel trống, không lem ở mip | Seam đo trong 3D (p90 ≤ 4). Đếm texel chưa vẽ hoặc đen. Kiểm padding |

**Mặt khe rãnh trong `light.shaded_share`** (D27.9, code `852e217`):
- Concept vẽ nét mực trong khe rãnh và hốc lõm. Nét đó không phải bóng bake, nên `tex_measure.py` bỏ các mặt này khỏi phép đo.
- Cách nhận ra mặt khe: phép thử che tia (`tex.occluded`). Mỗi mặt bắn 25 tia nửa cầu từ 4 điểm trên mặt. Tỉ lệ tia chạm mesh trong `alpha_min_px / px_per_m` mét (đọc từ `spec.json` của `model`) lấy trung vị trên 4 điểm.
- Mặt có tỉ lệ ≥ `groove_occluded` (mặc định 0,55) là mặt khe. Một tường phẳng hoặc mái chìa chỉ che tối đa 0,48, nên mặt cạnh đai hay dưới nắp vẫn được đo.
- `light.shaded_share` bỏ texel của mặt khe khỏi cả số texel lẫn trung bình mặt bên. JSON ghi `groove_share` cho từng mã vật liệu. `side_spread_L` và `top_vs_side_L` không đổi.
- Một texel chỉ tính là bóng khi chính nó tối và vùng lọc thông thấp quanh nó cũng tối.
- Không lọc nét mực theo màu. Profile không có cờ `style.line_art`.
- Run 4: nét mực trong khe bị tính là bóng (TIMBER 0,055, IRON 0,037 so với ngưỡng 0,02), check fail ở mọi lần.

**Quy ước ánh sáng trong profile:**

```
style:
  light_convention: unlit_flat | painted_top_light
  top_vs_side_L: 0 | +8
```

Quy tắc riêng của dự án (ví dụ New Last Order: mái là ngói xếp lớp theo dốc, tường đọc ra từng viên đá, viền vàng dừng đúng mép khung) nằm trong **rubric theo loại**, mục `texture` (`production/rubrics/<loại>.md`, D14.6), không nằm trong agent.

## 7. Reviewer `zps-3dp-check-texture`

Opus, chỉ đọc, trừ file report của mình (D27.5); context mới mỗi lần, không có tool gọi agent (D1). Producer giao reviewer ở bước `texture` (D14.1). Bước `assemble` không có agent và reviewer; script `assemble.py` kiểm và anh duyệt (D22.11).

**Reviewer nhận:**
- Render có texture, có ánh sáng: 3/4 trước, cận trước, 3/4 sau, camera game.
- Render unlit (chỉ albedo) cùng góc.
- Thumbnail ở kích thước thật.
- Atlas `<texture_res>` và crop các vùng đã sửa.
- JSON của `tex_measure.py`.
- Concept albedo, mục `texture` của rubric theo loại, TEXTURE NOTE.
- Chế độ SỬA: lớp Meshy gốc đặt cạnh bản đã sửa.

**Tiêu chí:**
1. Quy ước ánh sáng: không bóng bake, AO, glow ngoài quy ước; các mặt bên cùng tông.
2. Đúng vật liệu so với concept và bộ đã duyệt.
3. Đọc được ở thumbnail.
4. Liền mạch: không thấy seam ở camera game; nét theo khối, không theo mép UV.
5. Từng mục `texture` của rubric theo loại.
6. TEXTURE NOTE đã xử lý hết.
7. Chế độ SỬA: chi tiết Meshy đúng vẫn còn; không sửa quá tay.
7b. **Texture khớp hình học** (D26.1, tiêu chí texture–geometry coherence của GPTEval3D): ranh giới vật liệu trên texture trùng với cạnh và khối của mesh (đá dừng ở mép tường, viền khung nằm đúng trên khung); không có chi tiết vẽ giả khối mà mesh không có ở chỗ đó, trừ khi là `texture_only` đã ghi.
8. **Kiểm kê phần tử và lỗi ảnh AI** (D25.F, theo `art-quality.md` và `gen-craft.md` của kit), trên lớp Meshy và trên paint view: mọi motif, chữ, biển, vết bẩn, nguồn sáng vẽ trên texture phải truy được về concept hoặc TEXTURE NOTE; soát bảng lỗi ảnh AI (thừa chi tiết, chữ giả, ánh sáng vẽ sai hướng, nhiễu giả chi tiết, lệch style, scale vân khác nhau trên cùng vật liệu). Không truy được → finding `repaint`.

Theo quy tắc chung của 4 reviewer (`docs/producer.md` §6.1, D25.B): ảnh cùng góc của bản trước ở vòng sửa, `EVIDENCE_OPENED`, finding đủ trường của kit (`preserve`, `acceptance`…), cảnh báo xu hướng duyệt dễ, chỉ chấm trong phạm vi bước.

**Chẩn đoán trước khi đề xuất sửa** (theo kit). Lỗi đen hoặc sai màu: kiểm color space, alpha, normal trước khi vẽ lại. Lỗi seam: kiểm UV và padding trước khi làm mờ. Nếu không tách được do map hay do UV, ghi cả hai giả thuyết.

**Output:** contract reviewer (D14.10, D21.1, `docs/producer.md` §6.1), finding có id, `PRIOR` cho mọi finding đang mở. `TOP_FIX` thuộc đúng một loại:

| Loại | Ai sửa | Khi nào |
|---|---|---|
| `repaint: F<n>, F<m> …` | Texture Artist, sửa theo crop. Kiểu lô (D21.1): mọi finding `repaint` đang mở; mỗi finding ghi rõ vùng và lỗi | Lỗi vẽ, sửa được |
| `fix_uv_mesh: <mô tả>` | Script chạy `redo --step model` (D14.10). DUYỆT 1 lại | Lỗi do UV, mesh, normal |
| `meshy_regen: <lý do>` | Script đặt `waiting_human`. Anh duyệt lần gọi Meshy thứ hai; script tăng `max_credits` của file budget hiện tại thêm một lần gọi, brief tiếp theo ghi số lần còn được gọi (mục 2.2, D20.14, D21.2) | `blocker`: hỏng cả style hoặc phần lớn bề mặt, không sửa được |
| `need_evidence: <ảnh cần thêm>` | Texture Artist, vòng ngắn chỉ render ảnh xin thêm vào `vN/review/evidence-<k>/`, không tạo version mới (D21.4). Không tính vào 3 vòng (`docs/producer.md` §7) | Chỉ còn tiêu chí `unclear`, không còn `blocker`, `major` |
| `note: <nội dung>` | Ghi vào `texture/notes.md` | `minor`, không chặn |

Bước `texture` có gate `review`: reviewer PASS (không còn finding `blocker`, `major`, `unclear` đang mở) thì sang `assemble`.

## 8. Vòng sửa (D11)

Script của Producer làm (D11, D14.10, D21.1, `docs/producer.md` §7): tối đa 3 vòng; tiến bộ đo theo finding có id; dừng sớm khi một vòng không giải quyết được finding `blocker` hay `major` cũ nào; giữ bản tốt nhất; feedback của anh đặt lại bộ đếm. Ở mỗi vòng sửa, Texture Artist sửa đúng các finding liệt kê trong `TOP_FIX`, bắt đầu từ bản brief chỉ định (bản tốt nhất), và ghi `FIXED:`.

## 9. Đầu ra

Ghi vào `production/assets/<id>/texture/vN/final/`:

- `albedo_<texture_res>.png`.
- **Bộ render có texture** (D22.11; trước đây 3D Artist render ở `assemble`): có texture, có ánh sáng, alpha bật: 3/4 trước, cận trước, 3/4 sau, camera game; cùng góc bản unlit; thumbnail ở kích thước thật. Bộ này dùng cho check-texture và cho sheet DUYỆT 2. `assemble.py` render lại 3/4 trước và camera game từ GLB để so pixel với bộ này.
- **`final_lit_vs_concept.png`** (D22.11): model có texture, cùng góc và hướng nắng với concept có bóng (hướng nắng lấy từ `spec.json` của bước `model`), đặt cạnh concept đó.
- `texture_spec.json`: đề xuất, điểm số và lý do chọn chế độ (mục 2.1).
- `notes.md` (trong gói cuối là `texture/notes.md`): phương pháp, số lần gọi Meshy, số lần thử lại do lỗi kỹ thuật, credit, đã sửa gì. Texture Artist là chủ file này; ở `assemble`, script `assemble.py` chỉ chép (D20.13, D22.11).
- Báo cáo ghi: chế độ đã làm và lý do; số lần gọi Meshy; vùng đã sửa; render trên model đã mở (ghi renderer: Blender, không phải engine); những gì chưa kiểm.
- Yêu cầu sửa UV hoặc mesh chỉ đi qua `TOP_FIX: fix_uv_mesh` (mục 7). Texture Artist không gửi yêu cầu riêng cho 3D Artist.
- Chế độ SỬA: nếu lỗi không sửa được, báo cáo có dòng `UNFIXABLE: yes` và lý do. Script đặt `waiting_human`; anh quyết có gọi Meshy lần 2 không (D20.14).
- Ghi chú cài đặt material cho người nhập vào engine: unlit, base color only.

Báo cáo contract của worker (`STATUS / OUTPUT / RUBRIC / ISSUES / PROFILE_HASH`, thêm `UNFIXABLE: yes|no`, và `FIXED:` ở vòng sửa) theo `docs/producer.md` §6.2. Không có `MESHY_CALLS` (D21.2).

- Texture Artist tự ghi file report vào đường dẫn trong brief (D27.5, `docs/producer.md` §6.5).
- Đã làm một ghi chú của bước trước (TEXTURE NOTE, `note_texture`, mục `ISSUES` của `model`): ghi `RESOLVED_NOTES: <mục>` (D27.8). check-texture xác nhận từng mục trong report.

## 10. Tool

**Chép từ kit v0.10.4 (bản riêng, D2):**
- `project_concept.py` (zps-3d-artist), **có sửa**: 8 view, trọng số theo góc nhìn, loại vùng bị che, lấp vùng khuất trong 3D. Ghi phần sửa trong `SOURCE.md`.
- `render_model.py`, `inspect_model.py`, `palette_report.py` (`.art-production-support/shared/scripts`).

- `gen/gen_api.py` (zps-3d-artist), chỉ lệnh `texture` cho Meshy retexture, **chép nguyên, không sửa** (D24.2, thay D21.2). Mọi lần gọi đi qua `meshy_call.py` của Producer.

**Mới:** `base_fill.py`, `render_paint_views.py`, `seam_fix.py`, `crop_edit.py`, `tex_measure.py`, `texture_complexity.py`, `tone_fix.py`.

**Phân việc (D17):** Texture Artist là sub-agent của runtime (D22.9), chạy mọi script ở trên. Codex (`gpt-6-astra`, D15) chỉ vẽ paint view và sửa crop, qua `gen_image_codex.py`.

**Dùng chung với Concept Views:** `gen_image_codex.py` (D8).

## 11. Việc cần kiểm khi viết code

Ghi trong `docs/coding-checklist.md`.
