# Spec — sub-agent Concept Views (v1.2)

Tên kỹ thuật: `zps-3dp-step-views`. Tên hiển thị: 3DP Step · Views. Reviewer: `zps-3dp-check-views` (D23.2).
Duyệt: 2026-11-08. v1.1: 2026-11-09 (D21). v1.2: 2026-11-09 (D22). Quyết định nền: `docs/decisions.md` (D1–D9, D21, D22).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-concept-views).

---

## 1. Vai trò và phạm vi

Concept Views vẽ 5 view (front, back, left, right, top) của một asset. **Hình dáng lấy từ blockout đã duyệt.** Model ảnh chỉ tô màu và vật liệu lên ảnh guide.

**Dùng cho:** công trình, props cứng, cây và đá low-poly. Mọi asset phải có blockout đã duyệt.
**Không dùng cho:** nhân vật, sinh vật. Hai nhóm này có bộ agent riêng ở version sau (D9).

| Làm | Không làm |
|---|---|
| Render ảnh guide từ blockout đã duyệt | Dựng hoặc sửa blockout |
| Gen view qua Codex (D8): front trước, rồi các mặt còn lại | Quyết định phần khuất (lấy từ blockout và brief) |
| Đo bằng script, gen lại view bị lỗi hình | Sửa ảnh để pass. Đổi ngưỡng |
| Ghi báo cáo contract cho Producer | Gọi reviewer hay agent khác (D14.1). Tự duyệt |
| Tạo sheet 5 view, viết README của bộ view | Dựng model |

Quy ước view: vật quay mặt về −Y. `left` là bên trái của chính vật (camera ở +X). `right` là bên phải của vật (camera ở −X). Giống Blockout và 3D Artist.

## 2. Đầu vào

| Nguồn | Lấy gì |
|---|---|
| `blockout/` đã duyệt, hash đã khóa | `part_graph.json`, `parts/`, `sources.json`, `blockout.md` |
| Concept albedo | Màu, vật liệu, mức chi tiết. Là ảnh 1 trong mọi prompt |
| `blockout.md` | Phần khuất, mục "Blockout tự quyết", ghi chú real/texture_only, thành phần đếm trên concept |
| Project profile | Màu nền gen (tùy chọn) |
| Thẻ asset (`asset-card.yaml`) | Đối xứng (`symmetric:`) |

Script kiểm blockout đã duyệt và hash khớp khi sinh brief (D22.12). Concept Views chỉ kiểm các file brief chỉ định có tồn tại.

## 3. Quy trình

Concept Views chạy ở **hai bước** của pipeline (D14.2). Mỗi bước kết thúc bằng báo cáo contract. Producer giao reviewer và vòng sửa (D14.1, D11).

**Bước `views_front`** (gate `review`):

| # | Việc | Kiểm bằng |
|---|---|---|
| 1 | Kiểm đầu vào | `check_inputs.py` |
| 2 | Render guide và ID cho 5 view | `render_blockout_views.py` |
| 3 | Chọn màu nền: lấy từ profile; nếu không có, chọn màu xa nhất với bảng màu concept. Ghi `bg_color.json` | `pick_bg.py` |
| 4 | Đo màu từng vật liệu trên concept albedo, ghi `concept_colors.json` (tên vật liệu = mã trong `sources.json`) | `palette_report.py` |
| 5 | Gen **front** (mục 4) | `gen_image_codex.py` |
| 6 | Đo front, ghi báo cáo. Producer giao check-views (chỉ front) | `measure_views.py` |

**Đầu ra bước `views_front`:** `production/assets/<id>/views_front/vN/final/`

```
final/
  front.png
  concept_colors.json, bg_color.json
  report/VIEWS.md   ← nếu có (Review Board dùng khi asset tới waiting_human, D20.16)
  report            ← báo cáo contract của worker
```

**Bước `views_rest`** (gate `review_human`):

| # | Việc | Kiểm bằng |
|---|---|---|
| 1 | Gen back, left, right, top. Ảnh tham chiếu: concept albedo + front đã duyệt ở bước trước (brief trỏ thẳng tới `views_front/vN/final/`, không chép sang, D22.14) + guide của view đó. Nhà đối xứng: chỉ gen left, lật thành right | `gen_image_codex.py` |
| 2 | Đo cả bộ. Gen lại view có lỗi hình trước khi báo cáo | `measure_views.py` |
| 3 | Tạo sheet 5 view, tóm tắt, README 4 mục (mục 6) | `views_sheet.py`, `check_package.py` |
| 4 | Ghi báo cáo. Producer giao check-views (cả bộ). Vòng sửa: gen lại **mọi** view có trong `TOP_FIX: regen` (kiểu lô, D21.1), giữ nguyên các view khác. Ghi `FIXED:` | — |
| 5 | Duyệt theo `approvals.views_rest` (D14.4) | Anh hoặc chính sách |

Chỉ đọc file và thư mục brief chỉ định.

## 4. Quy tắc gen view

**Mọi prompt có:**
- Ảnh guide của view đó. Dặn giữ đúng silhouette, tỉ lệ và vị trí từng part. Không thêm, bớt, dời hay đổi cỡ part.
- Danh sách vật liệu theo màu ID trong guide (từ `views.json`).
- Câu bắt buộc: "Giữ mép mái, diềm, nền, bệ trụ đúng độ cao như guide."
- Số props, nếu có props.
- Nền phẳng một màu (theo bước 3). Không đất, không bóng đổ, không viền, không chữ.
- Ánh sáng đều, giống nhau ở mọi view. Không bóng đổ lên vật, không ánh sáng một hướng, không góc tối kiểu AO. Bóng trong ảnh guide chỉ để đọc khối, không vẽ lại thành ánh sáng.
- Vật nằm trọn trong ảnh, không cắt, không kéo giãn. Cạnh dài > 1040 px.

**Các view khác ngoài front có thêm:** ảnh front đã chấm làm chuẩn màu. Mô tả phần khuất của mặt đó, lấy từ `blockout.md`.

**Lưu prompt của từng view** trong thư mục làm việc, để gen lại được. Prompt không vào gói giao.

## 5. Khi nào gen lại

| Lỗi | Xử lý | Ghi vào |
|---|---|---|
| Sai hình: silhouette, mốc chiều cao, thiếu hoặc dính props | Gen lại | — |
| Sai màu cả mặt, có bóng đổ, có ánh sáng một hướng | Gen lại | — |
| Sai màu một vùng nhỏ (ví dụ đầu dầm thành đá) | **Không gen lại** | TEXTURE NOTE |
| Vị trí chi tiết lệch nhỏ (ví dụ dải ngang mỏng lệch 3–4%) | **Không gen lại** | NGOẠI LỆ, kèm con số |
| Motif hai màu, đèn | Kiểm bằng mắt (reviewer). Không dùng dE | — |

## 6. Đầu ra của bộ view

Bỏ thư mục `View Concept/` riêng (D14.8). Bước `views_rest` ghi vào `production/assets/<id>/views_rest/vN/final/`. Brief của bước sau trỏ thẳng tới đây và tới `final/` của blockout đã duyệt.

```
final/
  README.md
  front.png, back.png, left.png, right.png, top.png, views.json
  concept_colors.json, bg_color.json   ← màu vật liệu đo trên concept; màu nền đã dùng
  report/       ← report.md, overlay_sheet.png, report.json, VIEWS_sheet.png
```

**README có 4 mục** (D22.14). Mục nào không có nội dung thì ghi "không có". README không chép lại nội dung đã có ở `blockout.md`; chỉ pipeline đọc bộ view.

Dòng đầu cố định, không phải một mục: "Thông số, mốc chiều cao, phần khuất, Blockout tự quyết, ghi chú real/texture_only: xem `blockout.md` của blockout đã duyệt. Không chiếu hay bake màu từ ảnh view lên model; màu lấy từ albedo."

1. NGOẠI LỆ.
2. TEXTURE NOTE.
3. Lật ảnh: "right = left lật ngang", nếu có.
4. Trạng thái duyệt và ngày.

Không chép vào gói: prompt, bản không chọn, log.

**`check_package.py`:**
- Đủ 5 file view, và sheet được dựng từ đúng 5 file đó (so hash).
- README có đủ 4 mục và dòng trỏ đầu tiên.

Hash blockout do script của Producer kiểm khi sinh brief và khi ingest (D22.12), không ghi vào README.

Nếu một điều không đúng, báo cáo `STATUS: BLOCKED`.

## 7. Sheet duyệt

`report/VIEWS_sheet.png`:

| Hàng | Nội dung |
|---|---|
| 1 | Concept albedo, front, back, left, right, top |
| 2 | Overlay từng view (blockout đỏ, ảnh gen xanh) với IoU, dE, vị trí chi tiết |
| 3 | Crop các chỗ reviewer ghi chú (nếu có) |

Kèm `report/VIEWS.md` ngắn. 3 dòng đầu là tóm tắt cho anh (D20.17). Phần sau: điểm số, view gen lại và vì sao, NGOẠI LỆ, TEXTURE NOTE.

## 8. Reviewer `zps-3dp-check-views`

Model theo `pipeline.toml` (pilot: Opus, D16), chỉ đọc, trừ file report của mình (D27.5); context mới mỗi lần (D1). Không có tool gọi agent. Theo quy tắc chung của 4 reviewer (`docs/producer.md` §6.1, D25.B): ảnh cùng góc của bản trước ở vòng sửa, `EVIDENCE_OPENED`, finding đủ trường của kit (`preserve`, `acceptance`…), cảnh báo xu hướng duyệt dễ, chỉ chấm trong phạm vi bước.

**Kiểm kê phần tử và lỗi ảnh AI** (D25.F, theo `art-quality.md` và `gen-craft.md` của kit), áp cho mọi view:
- Mọi phần tử nhìn thấy (vật, phụ kiện, motif, chữ, nguồn sáng) phải truy được về concept, guide hoặc thẻ asset. Không truy được → finding `regen` (nếu thay đổi hình) hoặc `note_texture` (nếu chỉ là màu, hoa văn nhỏ).
- Soát theo bảng lỗi ảnh AI của kit: thừa chi tiết (hoa văn phủ khắp, hạt sáng, khói không yêu cầu), chữ hoặc ký hiệu giả, nhiều hướng sáng hoặc viền sáng quanh mọi cạnh, bề mặt nhiễu giả chi tiết, lệch style so với concept, viền halo ở nền.

**Lần 1, chỉ front:**
1. Style, chất liệu, mức chi tiết giống concept albedo.
2. Silhouette và mốc chiều cao đúng guide (đọc số trong `report.json`).
3. Ánh sáng đều, không bóng đổ, không ánh sáng một hướng, không góc tối kiểu AO.
4. Không thêm, không bớt chi tiết so với guide.

**Lần 2, cả bộ** (D22.14): chỉ chấm 4 view mới. Front đã duyệt ở `views_front`, không chấm lại; front chỉ bị mở lại qua `regen_front`.
1. Bốn tiêu chí trên, cho từng view mới.
2. Đồng bộ: cùng vật liệu có cùng màu, texture, độ mòn như front.
3. Phần khuất đúng `blockout.md`.
4. Props đủ số và tách rời.
5. Motif và đèn: kiểm bằng mắt.

**Output:** contract reviewer (D14.10, D21.1, `docs/producer.md` §6.1), finding có id, `PRIOR` cho mọi finding đang mở. `TOP_FIX` thuộc đúng một loại (`note_exception`, `note_texture` chỉ ghi chú, không gây FIX):

| Loại | Khi nào |
|---|---|
| `regen: F<n>, F<m> …` | Lỗi trong hàng "Gen lại" ở mục 5. Mức `blocker` hoặc `major`. **Sai số lượng thành phần so với concept hoặc `blockout.md` (số hàng ván, số cửa, số trụ) luôn là `regen`, không phải `note_texture`** (D27.11; Run 4: `back.png` có 2 hàng ván thay vì 3 mà vẫn PASS). Kiểu lô: liệt kê mọi finding `regen` đang mở; mỗi finding ghi rõ view và lỗi |
| `regen_front: F<n>` | Chỉ ở lần 2. Front lệch so với cả bộ đến mức không sửa được bằng cách gen lại các view kia (ví dụ màu gỗ của front sai so với concept khi đặt cạnh bộ) (D22.4). Script chạy `redo --step views_front`; `views_rest` chạy lại sau đó |
| `need_evidence: <ảnh cần thêm>` | Chỉ còn tiêu chí `unclear`, không còn `blocker`, `major` (D21.4). Concept Views làm vòng ngắn, chỉ render ảnh xin thêm vào `vN/review/evidence-<k>/`, không tạo version mới. Không tính vào 3 vòng (`docs/producer.md` §7) |
| `note_exception: <nội dung>` | Lệch nhỏ về vị trí hoặc số đo |
| `note_texture: <nội dung>` | Sai màu một vùng nhỏ |

## 9. Đổi version

**Blockout lên version mới:**
1. Script tự đánh dấu bộ view cũ là "cũ" dựa trên `inputs` (D21.5, thay phần "Producer đánh dấu" của D2).
2. Concept Views render lại guide.
3. `diff_guides.py` so guide cũ với guide mới (brief trỏ tới version đã duyệt trước đó). Chỉ gen lại view có guide đổi. Giữ view đã duyệt có guide không đổi.
4. Sheet mới đánh dấu view nào mới, view nào giữ lại.
5. README ghi "Thay đổi so với version trước".

**Concept albedo đổi màu:** gen lại cả bộ, vì front là chuẩn màu.

## 10. Tool

**Chép từ kit v0.10.4 (bản riêng, D2):**
- `render_blockout_views.py`
- `measure_views.py`, **có sửa**: tách nền theo màu khóa trên toàn ảnh, không chỉ vùng nối mép ảnh (G1). Ghi phần sửa trong `SOURCE.md`.
- `sheet.py`
- `palette_report.py` (từ `.art-production-support/shared/scripts`)

**Mới:** `check_inputs.py`, `pick_bg.py`, `views_sheet.py`, `check_package.py`, `diff_guides.py`.

`views_sheet.py` và mọi sheet duyệt dùng font Noto Sans đi kèm skill (giấy phép OFL), có đủ dấu tiếng Việt (D27.12). Không dùng font hệ thống. Run 4: nhãn "(giữ)" hiện ô vuông. Code hiện tại (`e78c6a7`) còn chọn font hệ thống theo danh sách, và bỏ dấu khi không font nào vẽ được: phải đổi sang font đi kèm.

**Dùng chung với Texture Artist (adapter, D8):** `gen_image_codex.py`. Script nhận prompt và ảnh tham chiếu, gọi `codex exec`, lấy ảnh đầu ra, chép vào thư mục công trình. Lỗi kỹ thuật 3 lần liên tiếp thì dừng và báo.

## 11. Việc cần kiểm khi viết code

Ghi trong `docs/coding-checklist.md`.
