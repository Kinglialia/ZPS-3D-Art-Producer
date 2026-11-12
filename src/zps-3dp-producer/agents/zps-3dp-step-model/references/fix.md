# Vòng sửa

Đọc file này khi brief có `TOP_FIX`, dòng "Bản đã duyệt trước", hoặc xin bằng chứng, và khi một check fail mà bạn không sửa được. Ở lần dựng đầu, đừng đọc trước.

Các lệnh `RUN` và `F`, `B`, `C`, `V` có nghĩa như trong file agent. "Gate" là lệnh `RUN gate_all.py` ở bước 3 của quy trình.

## Mở đầu

Brief ghi bản gốc `P` và `TOP_FIX`. Mỗi finding có id `<Fid>` (ví dụ `F3`).

1. Chép `P/final/` vào `F`, trừ `review/`.
2. Đọc trước các file JSON fail mà brief liệt kê. Rồi mới tới finding.

## `structure`

Đúng một finding.

1. Chép `part_graph.json`, `parts_lib.py` và file `CUSTOM_PARTS:` (nếu có) hiện tại vào `V/work/edits/<Fid>/`.
2. Sửa theo `repair`, giữ `preserve`. Part gọi hàm của file `CUSTOM_PARTS:`: chạy `RUN BT/custom_mesh.py --work F`.
3. Gate. Sửa đến khi in `pass`.
4. Hỏng và không sửa được: chép lại từ `V/work/edits/<Fid>/` và ghi lý do vào báo cáo.

Ngoại lệ: finding có `evidence` mở đầu bằng `texture v` đến từ bước texture (`fix_uv_mesh`). Khi đó sửa cùng lúc mọi id `TOP_FIX` liệt kê. Mỗi id một lần sửa như trên, theo `repair` cho mesh hoặc UV.

## `param`

Mọi finding trong `TOP_FIX`.

1. Áp giá trị của mọi finding vào `F/part_graph.json`. Đó là phương án `a`.
2. Dựng thêm 1–2 phương án: chép `F` sang `V/variants/<b|c>/`, đổi giá trị trong graph của thư mục đó.
3. Chạy bước 3 đến 7 của quy trình với thư mục đó thay cho `F`: gate, `build_model.py`, gate sau khi gộp, `qa_all.py`, `render_all.py`.
4. Reviewer chọn thư mục nào thì thư mục đó thành `final/`. Mỗi phương án giữ JSON của chính nó.
5. Ghi giá trị của từng phương án vào `model.md`.

Trong `V/variants/<b|c>/`, `RUN` không thấy JSON fail. Đọc `overall` của từng JSON.

## Sau khi sửa

- Chạy lại bước 4 đến 8 của quy trình cho `F`.
- Ghi `FIXED:` theo brief.
- Mục "Thay đổi so với version trước" của `model.md`: part nào, param nào đổi, vì sao.

## Bản đã duyệt trước

Brief có dòng "Bản đã duyệt trước của bước này" (`P`) khi blockout vừa làm lại. Dựng từ part graph mới của `B`. Part còn đúng tên và param như blockout cũ: dựng lại chi tiết theo bảng detail pass của `P/model.md`.

## `ACCEPTED_FAIL`

Check fail mà bạn không sửa được và có trong danh sách `ACCEPTED_FAIL` của brief: ghi `ACCEPTED_FAIL: <file JSON> — <lý do có số>` trong report. Ghi cùng dòng đó vào mục `## NGOẠI LỆ` của `final/README.md` (tạo mục nếu chưa có). Gate cứng ở file agent không bao giờ được khai.

## Vòng xin bằng chứng

Chỉ render ảnh brief xin vào `V/review/evidence-<k>/`. Không sửa `final/`.
