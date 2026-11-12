# Texture: chế độ, sửa theo crop, `notes.md`

Nguồn: `docs/agents/texture-artist.md` §2–§9. Ký hiệu `T`, `F`, `V`, `G`, `M`, `VS`, `C`, `R`, `RES`, `RUN`, `PY` như file agent.

## 1. Chọn chế độ

Script chọn chế độ và ghi vào brief một dòng `MODE:`. Ledger ghi chế độ và lý do.

- `MODE: Meshy SỬA`: có key Meshy và budget, hoặc mesh này đã có lớp Meshy qua topology. Meshy rồi SỬA, bất kể asset đơn giản hay phức tạp.
- `MODE: VẼ MỚI`: profile không có `paths.env_file`, người dùng chỉ định, `policy.yaml` có `texture_default: paint`, hoặc hết lần gọi mà không có lớp Meshy dùng được.
- `texture_complexity.py --mode <meshy|paint>` ghi `scores`, `simple` và `proposed` (= chế độ của dòng `MODE:`) vào `F/texture_spec.json`. `simple` chỉ để tham khảo. Với `--glb G`, tool đo một lần cho mỗi mesh: version sau của cùng mesh lấy lại điểm.
- Ghi vào `F/texture_spec.json`: `"used": "meshy" | "paint"`, `"reason": "<một dòng>"`.
- Đổi nhánh giữa chừng chỉ khi lớp Meshy không dùng được (topology fail, Meshy lần hai vẫn hỏng) và hết lần gọi → VẼ MỚI. Không đặt lại vòng sửa; ghi vào `notes.md`.

## 2. Meshy rồi SỬA

1. Gọi Meshy (lệnh ở file agent, không chạy `--dry-run`: brief đã ghi giá ở `MESHY_CALLS`). Một lần gọi cho mỗi mesh; brief cho biết số lần còn lại. Một lần chạy chờ tối đa khoảng 28 phút (1700 s). Wrapper tải `base_color.png` của task (albedo) và kiểm topology với `G` vào `V/work/meshy/call-<k>/topology.json`. `base_color.png` đã ở đúng `RES` (wrapper thu nhỏ khi Meshy trả lớn hơn). Thoát 4: topology fail.
2. `RUN check_meshy.py --final F --locked G --call V/work/meshy/call-<k> --albedo-out V/work/meshy/meshy_albedo.png`. Fail (số tam giác, bộ ba UV hoặc cỡ `base_color` sai): bỏ lớp đó, ghi vào `notes.md`; không còn lần gọi thì VẼ MỚI. Gate cứng: không khai `ACCEPTED_FAIL`. Không lấy ảnh trong `glb.glb` làm albedo, không tự viết script so mesh.
3. Chép `V/work/meshy/meshy_albedo.png` sang `F/review/meshy_albedo.png` (reviewer đặt cạnh bản đã sửa).
4. Script sửa trước: `RUN tone_fix.py --glb G --model M --albedo V/work/meshy/meshy_albedo.png --profile <profile> --res RES --concept-colors CC --out V/work/tone.png`. Cân tông 4 mặt bên, nâng vùng bị che (trừ rãnh), dời a*b* của từng mã về màu concept, làm đều seam trong từng mã.
5. Chỉ chỗ script không sửa được (chi tiết thừa, hoa văn lem, nét cần vẽ lại cho sắc, TEXTURE NOTE) mới sửa theo crop (mục 5).
6. Giữ nét cọ, vân, vết mòn, chi tiết Meshy đã đúng vị trí (đối chiếu `VS/`). Không sửa quá tay.
7. Kết quả cuối: `F/albedo_<RES>.png`. Rồi đo (`tex_measure.py`), sau đó mới render (file agent, bước 5 và 6).

## 3. VẼ MỚI

1. `RUN base_fill.py --final F --model M --concept-colors CC --profile <profile> --res RES --out V/work/paint/base_fill.png`.
2. `RUN bl render_paint_views.py --glb G --albedo V/work/paint/base_fill.png --outdir V/work/paint`. Ra 8 `guide_<k>.png` và `cameras.json`.
3. `RUN make_paint_prompts.py --views V/work/paint --concept C --concept-colors CC --view-set VS --out V/work/prompts`, thêm `--batch` khi `GEN_ARGS` có `--batch`. Không viết prompt bằng tay. Tool ghi `V/work/prompts/paint_<k>.md` và in `--size` của guide.
4. Gen cả 8 view trong một lệnh (`PY "<GEN_IMAGE>"` như file agent): `--image C/concept_albedo.png --size <size>` trước `--prompt` đầu tiên, rồi với mỗi `k`: `--prompt V/work/prompts/paint_<k>.md --image V/work/paint/guide_<k>.png --out V/work/paint/paint_<k>.png`. Tool chạy các view song song. Khi `GEN_ARGS` có `--batch`: mọi ảnh vào một lần gọi, nên đặt `--image` của guide theo đúng thứ tự các `--prompt`. Ảnh trả về cùng tỉ lệ được tool thu về cỡ guide. Tool kiểm từng file và chỉ gen lại file hỏng.
5. `RUN project_views.py --glb G --model M --views V/work/paint --base V/work/paint/base_fill.png --res RES --out V/work/paint/projected.png`. Mỗi mặt lấy một view. Vùng không view nào thấy lấy màu cùng mặt, rồi cùng mã vật liệu và hướng, rồi màu nền. Thoát 1 khi một `paint_<k>.png` thiếu, khác tỉ lệ guide hoặc lệch khỏi guide: log nêu `gen lại paint_<k>.png`. Viết lại prompt các view đó (`--k <k>`, `--fix "<lỗi trong log>"`), gen lại trong một lệnh, rồi chạy lại bước này.
6. `RUN seam_fix.py --glb G --model M --albedo V/work/paint/projected.png --res RES --out F/albedo_<RES>.png`.
7. Sửa thêm theo crop nếu cần (mục 5).

Asset rất đơn giản: có thể bỏ bước 3–5 và chạy bước 6 với `--albedo V/work/paint/base_fill.png` (ghi lý do).

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

1. `RUN crop_edit.py cut --albedo <albedo> --box x0,y0,x1,y1 --out V/work/crops/<k>`. Vùng cộng lề tối đa 1024 px; lớn hơn thì chia nhỏ. Tool đệm crop bằng atlas xung quanh cho đủ tỉ lệ 3:2 hoặc 2:3.
2. Codex sửa `V/work/crops/<k>/send.png` (1536x1024 hoặc 1024x1536; ảnh 1 là send, ảnh 2 là concept), `--size` bằng cỡ `send` trong `crop.json`. Prompt: chỉ sửa trong vùng, giữ nguyên mọi pixel xung quanh, không dời ảnh.
3. `RUN crop_edit.py paste --albedo <albedo> --crop V/work/crops/<k> --edited <ảnh Codex> --glb G --out <albedo mới>`. Ảnh khác tỉ lệ, vùng quanh chỗ sửa bị dời hay đổi, hoặc pixel ngoài vùng đổi: tool bỏ kết quả; gen lại một lần, rồi ghi `ISSUES`. Tool làm lại gutter quanh vùng dán.
4. Đo lại bằng `tex_measure.py` sau mỗi lượt crop. Render lại (`render_texture.py`) chỉ sau lượt đo pass cuối.

## 6. Ảnh cho reviewer

`render_texture.py` chạy sau `tex_measure.py` và ghi vào `F/review/`: `lit_<view>.png`, `unlit_<view>.png` (view: `34_front`, `close_front`, `34_back`, `game`), `thumb.png`, `renders.json` (camera của từng ảnh và sha256 của albedo đã render: `assemble.py` render lại GLB đúng các camera này để so pixel), và `F/final_lit_vs_concept.png`. Đừng sửa hay xóa `renders.json`.
