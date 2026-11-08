# Spec — sub-agent Concept Views (v1)

Tên kỹ thuật: `zps-3dp-concept-views`. Tên hiển thị: ZPS-3DP - Concept Views. Reviewer: `zps-3dp-review-views`.
Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D1–D9).
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
| Đo bằng script, gen lại view bị lỗi hình, tối đa 3 vòng mỗi view | Sửa ảnh để pass. Đổi ngưỡng |
| Gọi review-views (2 lần) | Tự duyệt |
| Tạo sheet 5 view, đóng gói `View Concept/0X-<tên>/` | Dựng model |

Quy ước view: vật quay mặt về −Y. `left` là bên trái của chính vật (camera ở +X). `right` là bên phải của vật (camera ở −X). Giống Blockout và 3D Artist.

## 2. Đầu vào

| Nguồn | Lấy gì |
|---|---|
| `blockout/` đã duyệt, hash đã khóa | `part_graph.json`, `parts/`, `sources.json`, `blockout.md` |
| Concept albedo | Màu, vật liệu, mức chi tiết. Là ảnh 1 trong mọi prompt |
| `blockout.md` | Phần khuất, mục "Blockout tự quyết", ghi chú real/texture_only, thành phần đếm trên concept |
| Project profile | Màu nền gen (tùy chọn), đối xứng |

Nếu blockout chưa duyệt hoặc hash không khớp, Concept Views dừng và báo Producer.

## 3. Quy trình

| # | Bước | Kiểm bằng |
|---|---|---|
| 1 | Kiểm đầu vào | `check_inputs.py` |
| 2 | Render guide và ID cho 5 view | `render_blockout_views.py` |
| 3 | Chọn màu nền: lấy từ profile; nếu không có, chọn màu xa nhất với bảng màu concept | `pick_bg.py` |
| 4 | Đo màu từng vật liệu trên concept albedo, ghi `concept_colors.json` (tên vật liệu = mã trong `sources.json`) | `palette_report.py` |
| 5 | Gen **front** (mục 4) | `gen_image_codex.py` |
| 6 | Đo front. Gọi **review-views lần 1** (chỉ front). Nếu `regen`, gen lại front | `measure_views.py`, reviewer |
| 7 | Gen back, left, right, top. Ảnh tham chiếu: concept albedo + front đã chấm + guide của view đó. Nhà đối xứng: chỉ gen left, lật thành right | `gen_image_codex.py` |
| 8 | Đo cả bộ. Gen lại view có lỗi hình. Tối đa 3 vòng mỗi view | `measure_views.py` |
| 9 | Gọi **review-views lần 2** (cả bộ). Xử lý `top_fix` theo loại (mục 5) | Reviewer |
| 10 | Tạo sheet 5 view và tóm tắt | `views_sheet.py` |
| 11 | Gửi **DUYỆT VIEWS**. Anh duyệt trên sheet 5 view, hoặc reviewer duyệt theo ủy quyền (D1.5) | Anh |
| 12 | Đóng gói `View Concept/0X-<tên>/` và viết README (mục 6) | `check_package.py` |

Nếu một view vẫn lỗi sau 3 vòng, Concept Views dừng gen view đó và ghi lên sheet, để anh quyết.

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

## 6. Gói View Concept

```
View Concept/0X-<tên>/
  README.md
  concept/      ← albedo (nguồn màu), có bóng (chỉ để đọc khối)
  views/        ← front, back, left, right, top đã duyệt + views.json
  blockout/     ← bản chép blockout đã khóa (Blockout publish vào đây)
  report/       ← report.md, overlay_sheet.png, report.json, VIEWS_sheet.png, JSON reviewer
```

**README có 9 mục.** Mục nào không có nội dung thì ghi "không có".

1. Thứ tự nguồn: hình học = blockout; màu và vật liệu = concept albedo; vị trí chi tiết = views; kích thước = `sources.json`. Nếu ảnh mâu thuẫn ghi chú: làm theo ảnh mới hơn và ghi lại mâu thuẫn.
2. Thông số và mốc chiều cao. Lấy từ blockout, không đo lại.
3. Phần khuất, chép từ `blockout.md`, gồm mục "Blockout tự quyết".
4. Ghi chú real/texture_only, chép từ concept.
5. NGOẠI LỆ.
6. TEXTURE NOTE.
7. Cảnh báo cố định: "Không chiếu hay bake màu từ ảnh view lên model. Màu lấy từ albedo."
8. Lật ảnh: "right = left lật ngang", nếu có.
9. Trạng thái duyệt và ngày.

Không chép vào gói: prompt, bản không chọn, log.

**`check_package.py`:**
- Hash của 5 file view khớp bản đã duyệt trên sheet.
- `blockout/part_graph.json` khớp hash blockout đã khóa.
- README có đủ 9 mục.

Nếu một điều không đúng, không giao gói.

## 7. Sheet duyệt

`report/VIEWS_sheet.png`:

| Hàng | Nội dung |
|---|---|
| 1 | Concept albedo, front, back, left, right, top |
| 2 | Overlay từng view (blockout đỏ, ảnh gen xanh) với IoU, dE, vị trí chi tiết |
| 3 | Crop các chỗ reviewer ghi chú (nếu có) |

Kèm `report/VIEWS.md` khoảng 10 dòng: điểm số, view gen lại và vì sao, NGOẠI LỆ, TEXTURE NOTE.

## 8. Reviewer `zps-3dp-review-views`

Sonnet, chỉ đọc, context mới mỗi lần (D1). Không có tool gọi agent.

**Lần 1, chỉ front:**
1. Style, chất liệu, mức chi tiết giống concept albedo.
2. Silhouette và mốc chiều cao đúng guide (đọc số trong `report.json`).
3. Ánh sáng đều, không bóng đổ, không ánh sáng một hướng, không góc tối kiểu AO.
4. Không thêm, không bớt chi tiết so với guide.

**Lần 2, cả bộ:**
1. Bốn tiêu chí trên, cho từng view.
2. Đồng bộ: cùng vật liệu có cùng màu, texture, độ mòn như front.
3. Phần khuất đúng `blockout.md`.
4. Props đủ số và tách rời.
5. Motif và đèn: kiểm bằng mắt.

**Output:** JSON theo D1. `top_fix` thuộc đúng một loại:

| Loại | Khi nào |
|---|---|
| `regen: <view>, lỗi: <mô tả>` | Lỗi trong hàng "Gen lại" ở mục 5. Mức `blocker` hoặc `major` |
| `note_exception: <nội dung>` | Lệch nhỏ về vị trí hoặc số đo |
| `note_texture: <nội dung>` | Sai màu một vùng nhỏ |

## 9. Đổi version

**Blockout lên version mới:**
1. Producer đánh dấu bộ view cũ là "cũ" (D2).
2. Concept Views render lại guide.
3. `diff_guides.py` so guide cũ với guide mới. Chỉ gen lại view có guide đổi. Giữ view đã duyệt có guide không đổi.
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

**Dùng chung với Texture Artist (adapter, D8):** `gen_image_codex.py`. Script nhận prompt và ảnh tham chiếu, gọi `codex exec`, lấy ảnh đầu ra, chép vào thư mục công trình. Lỗi kỹ thuật 3 lần liên tiếp thì dừng và báo.

## 11. Việc cần kiểm khi viết code

Ghi trong `docs/coding-checklist.md`.
