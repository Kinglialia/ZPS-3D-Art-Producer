# Texture: vòng sửa

Chỉ đọc file này khi brief có dòng `Bản gốc:`. Ký hiệu `T`, `F`, `V`, `G`, `M`, `R`, `RUN`, `PY` như file agent. `<bản gốc>` là thư mục ở dòng `Bản gốc:` của brief.

`F` đã có bản chép của `<bản gốc>/final/`, cả `review/` (`id_map.*`, `meshy_albedo.png`, `checks/meshy.json` là bằng chứng của lớp đang sửa), trừ file bước 5–6 ghi lại. Không chép tay. Đọc trước JSON fail mà brief liệt kê, rồi tới finding. Sửa theo đúng thứ tự brief nêu:

- JSON fail (vòng trả thẳng): sửa như bước 5 của file agent, bằng script trước, rồi theo crop.
- `H<n>` (feedback của người dùng): mỗi yêu cầu một crop (`R/texture.md` mục 5), theo nguyên văn trong `acceptance`.
- `repaint`: mọi finding trong `TOP_FIX`, mỗi finding một crop (`R/texture.md` mục 5); giữ `preserve`.
- `meshy_regen`: brief có `MESHY_CALLS` ≥ 1 thì gọi Meshy một lần và làm lại chế độ SỬA trên lớp mới; brief có `MODE: VẼ MỚI` hoặc không còn lần gọi thì VẼ MỚI.
- Mesh và UV không sửa ở đây: lỗi do UV, mesh, normal chỉ đi qua reviewer (`fix_uv_mesh`).
- Rồi chạy lại bước 5–7 của file agent. Ghi `FIXED:` theo brief và mục "Đã sửa" của `notes.md`.
