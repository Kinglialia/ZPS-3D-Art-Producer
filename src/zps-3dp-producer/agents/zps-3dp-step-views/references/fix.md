# Views: vòng sửa và bằng chứng

Đọc file này khi brief có `TOP_FIX` hoặc xin bằng chứng. Ký hiệu `T`, `F`, `V`, `C`, `CC`, `P`, `R`, `RUN`, `PY`, `VIEWS` như file agent.

## Vòng sửa

Brief ghi bản gốc `P` và `TOP_FIX`. Chép `P/final/` vào `F`, trừ `review/`. Đọc trước JSON fail mà brief liệt kê, rồi tới finding.

- `regen`: gen lại mọi view có tên ở đầu `region` của các finding trong `TOP_FIX`, trong một lệnh gen. Prompt dùng `--fix` cho `repair` và `--fix` cho `preserve`. Giữ nguyên view khác.
- Có finding mở đầu bằng `front:`: front mới là chuẩn màu mới. Làm lại bước 6–8 của file agent cho front. Rồi gen lại mọi view của `VIEWS` ở bước 9, kể cả view không có finding.
- Rồi chạy lại từ bước đo của file agent: front một mình (bước 7), cả bộ với `--front` (bước 10), rồi sheet, README, `check_package.py`. Ghi `FIXED:` theo brief.

## Bằng chứng

Vòng xin bằng chứng: chỉ làm crop brief xin. `viewing_condition` ghi `xin ảnh <nhãn> box x0,y0,x1,y1` theo tỉ lệ 0–1: `RUN views_sheet.py crop --image <ảnh của nhãn> --box x0,y0,x1,y1 --frac --out V/review/evidence-<k>/<tên>.png`. Không sửa `final/`.
