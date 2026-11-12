# Vòng sửa

Đọc file này khi brief có `TOP_FIX`, hoặc khi brief xin bằng chứng. Ở lần dựng đầu, đừng đọc.

Brief ghi bản gốc và `TOP_FIX`. Mỗi finding có id `<Fid>` (ví dụ `F3`). `F` vẫn là `V/final/`.

## Mở đầu

1. Chép `part_graph.json`, `sources.json` và `blockout.md` của bản gốc vào `F`. Không chép `parts_lib.py`: lần dựng ghi lại file đó.
2. Đọc trước các file JSON gate và check **fail** của bản gốc (`<bản gốc>/final/review/**`). Rồi mới tới finding.

## `structure`

Đúng một finding.

1. Chép `part_graph.json` và file `CUSTOM_PARTS:` (nếu có) hiện tại vào `V/work/edits/<Fid>/`.
2. Sửa theo `repair`, giữ `preserve`. Part gọi hàm của file `CUSTOM_PARTS:`: chạy `RUN custom_mesh.py --work F`.
3. `RUN gate_all.py --work F --check-args "check_inputs=..."` (đối số như ở lần dựng đầu).
4. `RUN check_fix.py --work F --old <bản gốc>/final/part_graph.json --finding <Fid>`.
5. Fail: chép lại từ `V/work/edits/<Fid>/`, dựng lại, ghi lý do vào báo cáo. Không sửa `fixed_params`.

## `param`

Mọi finding trong `TOP_FIX`.

1. Áp giá trị của mọi finding vào `F/part_graph.json`. Đó là phương án `a`.
2. `RUN gate_all.py --work F ...` một lần. Rồi `RUN check_fix.py --work F --old <bản gốc>/final/part_graph.json --finding <Fid>` một lần cho mỗi id.
3. Dựng thêm 1–2 phương án (`b`, `c`): `RUN make_variant.py --from F --out V/variants/<b|c> --set <param>=<giá trị> [--set ...] --old <bản gốc>/final/part_graph.json --finding <Fid> [--finding ...] --check-args "check_inputs=..."`. Một lệnh chép graph, đổi giá trị, dựng, gate, chạy mọi `check_*` và `check_fix` cho thư mục đó. Graph gọi hàm của file `CUSTOM_PARTS:`: tool chỉ chép rồi thoát 1, nên `RUN` in `error` và đường dẫn log. Mở log, đọc dòng `next:` và chạy đúng các lệnh trong dòng đó.
4. Render từng phương án một lần: `RUN bl render_critic.py --work V/variants/<b|c> --mode critic --outdir V/variants/<b|c>/review/renders [--spec V/work/spec.json]` và `RUN bl render_review.py --work V/variants/<b|c>`.
5. Reviewer chọn phương án nào thì thư mục đó thành `final/`, nên mỗi phương án giữ JSON của chính nó. Ghi giá trị của từng phương án vào `blockout.md`.

## Sau khi sửa

- Chạy lại bước 5 đến 7 của quy trình (overlay, render, `blockout_md.py`) cho `F`.
- Ghi `FIXED:` theo brief.
- Mục "Thay đổi so với version trước" của `blockout.md`: part nào, param nào đổi, vì sao.

## Vòng xin bằng chứng

Chỉ render ảnh brief xin vào `V/review/evidence-<k>/`. Không sửa `final/`.
