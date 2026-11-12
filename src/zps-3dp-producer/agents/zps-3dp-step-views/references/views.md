# Views: prompt, gen lại, README, VIEWS.md

Nguồn: kit `zps-concept-views/references/process.md` (Step 3, Way A) và `.art-production-support/shared/gen-craft.md`; xem `SOURCE.md`.

## 1. Quy ước

Vật quay mặt về −Y. `left` là bên trái của chính vật (camera ở +X). `right` là bên phải của vật (camera ở −X). Giống Blockout.

Mỗi prompt là một file `V/work/prompts/<view>-<k>.md`, chỉ chứa phần vẽ; `gen_image_codex.py` thêm khung cố định. Giữ mọi prompt và mọi ảnh gen trong `V/work/` để gen lại được. Prompt, bản không chọn, log không vào `final/`.

`--size`: lấy từ `V/work/sizes.json`, do `pick_size.py` tính từ kích thước bbox của `guides/views.json`. Mỗi view một cỡ. Cạnh dài phải > 1040 px.

## 2. Prompt

Không viết prompt bằng tay. `RUN make_prompt.py` điền mẫu của kit từ `guides/views.json`, `bg_color.json`, `<id>.material.md`, dòng thành phần của `blockout.md` và `V/work/sizes.json`. Lời nhắc cố định nằm trong `tools/make_prompt.py`: giữ hình và mốc cao của guide, nền phẳng, ánh sáng đều, không bóng đổ.

- `--hidden "<mô tả>"`: chỉ cho back, left, right, top. Viết bằng tiếng Anh một câu: mặt đó trông thế nào, theo `blockout.md` (phần "Blockout tự quyết") và `hidden_sides` của thẻ. Không ghi cho front.
- `--fix "<dòng>"`: chỉ khi gen lại. Một dòng nêu đúng một lỗi. Có thể lặp. Ví dụ "the top edge must be #A1901B ochre like image 2, not orange", "the handle is on the RIGHT half of the lid, exactly where the orange region of image 3 is".
- Tên file prompt và ảnh gen: `<view>-<k>`, với k = 1 cho lần gen đầu và 2 cho lần gen lại. `measure.py --pick-best` tìm ảnh `<view>-1.png`.

## 3. Gen lại hay ghi chú (concept-views.md §5)

| Lỗi | Xử lý | Ghi vào |
|---|---|---|
| Sai hình: silhouette, mốc chiều cao, thiếu hoặc dính props | Gen lại | — |
| Sai màu cả mặt, có bóng đổ, có ánh sáng một hướng | Gen lại | — |
| Vật chạm mép ảnh (`border`), số khối rời khác guide (`components`) | Gen lại | — |
| Sai màu một vùng nhỏ (ví dụ đầu tay nắm thành màu thân) | Không gen lại | TEXTURE NOTE |
| Vị trí chi tiết lệch nhỏ (ví dụ dải ngang mỏng lệch 3–4%) | Không gen lại | NGOẠI LỆ, kèm con số |
| Motif hai màu, đèn | Reviewer kiểm bằng mắt | — |

Tự gen lại chỉ cho view mà `measure.json` ghi `fail`, một lần mỗi view trong một vòng. Sau lần gen lại, `measure.py --pick-best` giữ ảnh có điểm đo tốt hơn (ít check fail hơn, rồi IoU cao hơn; bằng nhau thì giữ ảnh gen lại). Không sửa ảnh bằng tay hay bằng code để pass. Không đổi ngưỡng.

## 4. `report/VIEWS.md`

Review board hiện 3 dòng đầu (bỏ dòng trống). Dòng 1: `# Views <id> v<N> · <bước>`. Dòng 2: điểm `overall_score` của `report.json` và view fail nếu có. Dòng 3: số lần gen mỗi view. Sau đó: bảng điểm từng view (IoU, tỉ lệ, vị trí chi tiết, dE), view gen lại và vì sao, NGOẠI LỆ, TEXTURE NOTE, giả định về phần khuất.

## 5. `README.md` (chỉ `views_rest`)

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
