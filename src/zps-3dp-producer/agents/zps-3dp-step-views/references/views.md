# Views: prompt, gen lại, README, VIEWS.md

Nguồn: kit `zps-concept-views/references/process.md` (Step 3, Way A) và `.art-production-support/shared/gen-craft.md`; xem `SOURCE.md`.

## 1. Quy ước

Vật quay mặt về −Y. `left` là bên trái của chính vật (camera ở +X). `right` là bên phải của vật (camera ở −X). Giống Blockout.

Mỗi prompt là một file `V/work/prompts/<view>-<k>.md`, chỉ chứa phần vẽ; `gen_image_codex.py` thêm khung cố định. Giữ mọi prompt và mọi ảnh gen trong `V/work/` để gen lại được. Prompt, bản không chọn, log không vào `final/`.

`--size`: lấy từ `V/work/sizes.json`, do `pick_size.py` tính từ kích thước bbox của `guides/views.json`. Mỗi view một cỡ. Cạnh dài phải > 1040 px.

Thay mỗi `[...]` bằng thông tin thật:
- `[MATERIAL LIST]`: từ `guides/views.json` `materials` (mã → màu ID), tên vật liệu lấy từ `<id>.material.md`. Ví dụ `#E6194B red = STONE, cream plastered stone`.
- `[BG]`: `hex` của `bg_color.json`.
- `[PROPS]`: số props theo dòng thành phần đếm của `blockout.md`; không có props thì bỏ dòng.
- `[HIDDEN-SIDE DESCRIPTION]`: mặt đó theo `blockout.md` (phần khuất, "Blockout tự quyết") và `hidden_sides` của thẻ, viết bằng tiếng Anh.

## 2. Prompt front (ảnh 1 = concept albedo, ảnh 2 = `front_guide.png`)

```text
Repaint image 2 (a flat-coloured 3D guide render) as a finished game-asset illustration
in the exact art style, materials, colours and level of detail of the concept art in image 1.
Image 1: take the shapes and paint colours only; ignore its lighting and shadows.

STRICT RULES
- Orthographic FRONT view, camera straight on, no perspective, no tilt.
- Keep EXACTLY the silhouette, proportions and position of every part of image 2.
  Do not add, remove, move, resize or rotate any part.
- Keep the roof edge, fascia, base and plinth at exactly the heights of image 2.
- Each flat colour in image 2 marks one material: [MATERIAL LIST].
  Paint each region with that material as it looks in the concept.
- [PROPS] separate props, each where image 2 shows it.
- Plain, flat, solid background [BG]. No ground, no cast shadow, no vignette,
  no text, no labels, no border.
- Unlit base-color look, even ambient light, the same in every view. No shadow cast on the object,
  no strong directional light, no dark ambient-occlusion corners. The shading of the guide image
  only shows the form: do not copy it as light. Keep material detail (grain, weave, finish) as painted colour variation.
- The whole object fully visible and centred. Do not crop. Do not stretch.
```

## 3. Prompt các view khác (ảnh 1 = concept albedo, ảnh 2 = `front.png` đã duyệt, ảnh 3 = `<view>_guide.png`)

```text
Image 2 is the approved FRONT view of an object. Image 3 is a flat-coloured 3D guide render
of the [BACK / LEFT / RIGHT / TOP] view of the SAME object.
Repaint image 3 so it looks like the same object as image 2, from the [VIEW] side,
in the art style of the concept in image 1.

STRICT RULES
- Orthographic [VIEW] view, camera straight on, no perspective, no tilt.
- Keep EXACTLY the silhouette, proportions and position of every part of image 3.
  Do not add, remove, move, resize or rotate any part.
- Keep the roof edge, fascia, base and plinth at exactly the heights of image 3.
- Each flat colour in image 3 marks one material: [MATERIAL LIST].
  Every material must have the SAME colour, texture and wear as in image 2.
- What this side looks like: [HIDDEN-SIDE DESCRIPTION].
- [PROPS] separate props, each where image 3 shows it.
- Plain, flat, solid background [BG]. No ground, no cast shadow, no vignette,
  no text, no labels, no border.
- Unlit base-color look, even ambient light, the same in every view. No shadow cast on the object,
  no strong directional light, no dark ambient-occlusion corners. The shading of the guide image
  only shows the form: do not copy it as light.
- The whole object fully visible and centred. Do not crop. Do not stretch.
```

Gen lại: giữ prompt cũ, thêm một dòng nêu đúng lỗi, ví dụ "the roof must be #A1901B ochre like image 2, not orange", "the window is on the RIGHT half of the wall, exactly where the orange region of image 3 is".

## 4. Gen lại hay ghi chú (concept-views.md §5)

| Lỗi | Xử lý | Ghi vào |
|---|---|---|
| Sai hình: silhouette, mốc chiều cao, thiếu hoặc dính props | Gen lại | — |
| Sai màu cả mặt, có bóng đổ, có ánh sáng một hướng | Gen lại | — |
| Vật chạm mép ảnh (`border`), số khối rời khác guide (`components`) | Gen lại | — |
| Sai màu một vùng nhỏ (ví dụ đầu dầm thành đá) | Không gen lại | TEXTURE NOTE |
| Vị trí chi tiết lệch nhỏ (ví dụ dải ngang mỏng lệch 3–4%) | Không gen lại | NGOẠI LỆ, kèm con số |
| Motif hai màu, đèn | Reviewer kiểm bằng mắt | — |

Tự gen lại chỉ cho view mà `measure.json` ghi `fail`, một lần mỗi view trong một vòng. Không sửa ảnh bằng tay hay bằng code để pass. Không đổi ngưỡng.

## 5. `report/VIEWS.md`

Review board hiện 3 dòng đầu (bỏ dòng trống). Dòng 1: `# Views <id> v<N> · <bước>`. Dòng 2: điểm `overall_score` của `report.json` và view fail nếu có. Dòng 3: số lần gen mỗi view. Sau đó: bảng điểm từng view (IoU, tỉ lệ, vị trí chi tiết, dE), view gen lại và vì sao, NGOẠI LỆ, TEXTURE NOTE, giả định về phần khuất.

## 6. `README.md` (chỉ `views_rest`)

Dòng đầu cố định, đúng từng chữ:

```text
Thông số, mốc chiều cao, phần khuất, Blockout tự quyết, ghi chú real/texture_only: xem `blockout.md` của blockout đã duyệt. Không chiếu hay bake màu từ ảnh view lên model; màu lấy từ albedo.
```

Sau đó đúng 4 mục, theo thứ tự. Mục không có nội dung ghi "không có". Không chép lại nội dung của `blockout.md`. Mục 3 ghi `right = left lật ngang` khi thẻ có `symmetric.left_right: true` và `VIEWS` có left, right.

```text
## 1. NGOẠI LỆ
back: dải gờ lệch 3% (0,12 m) so với guide
## 2. TEXTURE NOTE
không có
## 3. Lật ảnh
right = left lật ngang
## 4. Trạng thái duyệt
chờ duyệt, 2026-11-09
```

Bộ dựng lại sau khi blockout làm lại: thêm `## Thay đổi so với version trước` sau mục 4 (view nào gen mới, view nào giữ).
