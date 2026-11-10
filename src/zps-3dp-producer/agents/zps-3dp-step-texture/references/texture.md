# Texture: chế độ, sửa theo crop, `notes.md`

Nguồn: `docs/agents/texture-artist.md` §2–§9. Ký hiệu `T`, `F`, `V`, `G`, `M`, `VF`, `C`, `R`, `PY`, `BL` như file agent.

## 1. Chọn chế độ

Script chọn chế độ và ghi vào brief một dòng `MODE:` (D30.11). Ledger ghi chế độ và lý do.

- `MODE: Meshy SỬA`: có key Meshy và budget, hoặc mesh này đã có lớp Meshy qua topology. Meshy rồi SỬA, bất kể asset đơn giản hay phức tạp.
- `MODE: VẼ MỚI`: profile không có `paths.env_file`, người dùng chỉ định, hoặc hết lần gọi mà không có lớp Meshy dùng được.
- `texture_complexity.py --mode <meshy|paint>` ghi `scores`, `simple` và `proposed` (= chế độ của dòng `MODE:`) vào `F/texture_spec.json`. `simple` chỉ để tham khảo.
- Ghi vào `F/texture_spec.json`: `"used": "meshy" | "paint"`, `"reason": "<một dòng>"`.
- Đổi nhánh giữa chừng chỉ khi lớp Meshy không dùng được (topology fail, Meshy lần hai vẫn hỏng) và hết lần gọi → VẼ MỚI. Không đặt lại vòng sửa; ghi vào `notes.md`.

## 2. Meshy rồi SỬA

1. `--dry-run` để xem giá, rồi gọi Meshy (lệnh ở file agent). Một lần gọi cho mỗi mesh; brief cho biết số lần còn lại. Wrapper tải `base_color.png` của task (albedo) và kiểm topology với `G` vào `V/work/meshy/call-<k>/topology.json`. `base_color.png` đã ở đúng `R` (wrapper thu nhỏ khi Meshy trả lớn hơn). Thoát 4: topology fail.
2. `PY T/check_meshy.py --final F --locked G --call V/work/meshy/call-<k> --albedo-out V/work/meshy/meshy_albedo.png`. Fail (số tam giác, bộ ba UV hoặc cỡ `base_color` sai): bỏ lớp đó, ghi vào `notes.md`; không còn lần gọi thì VẼ MỚI. Gate cứng: không khai `ACCEPTED_FAIL`. Không lấy ảnh trong `glb.glb` làm albedo, không tự viết script so mesh.
3. Chép `V/work/meshy/meshy_albedo.png` sang `F/review/meshy_albedo.png` (reviewer đặt cạnh bản đã sửa).
4. Script sửa trước (D17): `PY T/tone_fix.py --glb G --model M --albedo V/work/meshy/meshy_albedo.png --profile <profile> --res R --out V/work/tone.png`. Cân tông 4 mặt bên, nâng vùng bị che, làm đều seam.
5. Chỉ chỗ script không sửa được (chi tiết thừa, hoa văn lem, nét cần vẽ lại cho sắc, TEXTURE NOTE) mới sửa theo crop (mục 5).
6. Giữ nét cọ, vân, vết mòn, chi tiết Meshy đã đúng vị trí (đối chiếu `VR/`). Không sửa quá tay.
7. Kết quả cuối: `F/albedo_<R>.png`.

## 3. VẼ MỚI

1. `PY T/base_fill.py --final F --model M --concept-colors VF/concept_colors.json --profile <profile> --res R --out V/work/paint/base_fill.png`.
2. `BL T/render_paint_views.py -- --glb G --albedo V/work/paint/base_fill.png --outdir V/work/paint`. Ra 8 `guide_<k>.png` và `cameras.json`.
3. Codex vẽ `paint_<k>.png` cùng cỡ với `guide_<k>.png`: góc `k=0` (front) trước làm chuẩn màu, rồi 7 góc còn lại. Ảnh 1 `C/concept_albedo.png`, ảnh 2 `guide_<k>.png`, ảnh 3 (từ góc thứ hai) `paint_0.png`. Prompt: unlit, không bóng đổ, giữ đúng hình và vị trí vật liệu của guide, màu theo concept. `--size 1536x1024` (cỡ guide); ảnh trả về cùng tỉ lệ được tool thu về cỡ guide. Asset rất đơn giản: có thể bỏ bước này và dùng `base_fill.png` cho bước 4 (ghi lý do).
4. `PY T/project_views.py --glb G --model M --views V/work/paint --base V/work/paint/base_fill.png --res R --out V/work/paint/projected.png`. Vùng không view nào thấy lấy màu cùng mặt, rồi cùng mã vật liệu và hướng, rồi màu nền. Thoát 1 khi bỏ một `paint_<k>.png` khác tỉ lệ guide: chỉ gen lại các view tool nêu, rồi chạy lại bước này.
5. `PY T/seam_fix.py --glb G --albedo V/work/paint/projected.png --res R --out F/albedo_<R>.png`.
6. Sửa thêm theo crop nếu cần (mục 5).

Không chiếu ảnh của bước views lên model: ảnh view vẽ trên blockout. Ảnh view chỉ để tham chiếu.

## 4. `notes.md`

Review page hiện ba dòng đầu (bỏ dòng trống):

```text
# Texture <id> v<N>
<chế độ đã dùng và lý do, một dòng>
Meshy <n> lần, <credit> credit (<k> lần thử lại do lỗi kỹ thuật); <số vùng sửa theo crop> vùng sửa
```

Rồi các mục: `## Đã sửa` (vùng, finding id, tool), `## Ghi chú material` (unlit, chỉ base color), `## Chưa kiểm` (render bằng Blender Workbench, chưa mở trong engine; so với pilot `not_checked` khi chưa có pilot). Số lần gọi và lần thử lại đọc từ `V/work/meshy/call-<k>/meshy_call.json`.

## 5. Sửa theo crop

1. `PY T/crop_edit.py cut --albedo <albedo> --box x0,y0,x1,y1 --out V/work/crops/<k>`. Vùng cộng lề tối đa 1024 px; lớn hơn thì chia nhỏ.
2. Codex sửa `V/work/crops/<k>/send.png` (crop phóng lên cạnh dài 1536 px; ảnh 1 là send, ảnh 2 là concept), `--size` bằng cỡ `send` trong `crop.json`.
3. `PY T/crop_edit.py paste --albedo <albedo> --crop V/work/crops/<k> --edited <ảnh Codex> --out <albedo mới>`. Ảnh khác cỡ, hoặc pixel ngoài vùng đổi: tool bỏ kết quả; gen lại một lần, rồi ghi `ISSUES`.
4. Đo lại bằng `tex_measure.py` sau mỗi lượt crop.

## 6. Ảnh cho reviewer

`render_texture.py` ghi vào `F/review/`: `lit_<view>.png`, `unlit_<view>.png` (view: `34_front`, `close_front`, `34_back`, `game`), `thumb.png`, `renders.json` (camera của từng ảnh: `assemble.py` render lại GLB đúng các camera này để so pixel), và `F/final_lit_vs_concept.png`. Đừng sửa hay xóa `renders.json`.
