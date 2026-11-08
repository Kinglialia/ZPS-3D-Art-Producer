# Việc phải kiểm khi viết code

Mỗi dòng là một điều chưa xác nhận bằng chạy thật. Khi viết code, kiểm từng dòng và ghi kết quả vào cột "Kết quả". Không đánh dấu xong nếu chưa chạy.

| # | Agent | Việc cần kiểm | Nguồn | Kết quả |
|---|---|---|---|---|
| 1 | Blockout | `graph.py` của kit bỏ qua field lạ (`role`, `tag`), không báo lỗi | blockout.md §10 | |
| 2 | Blockout | `gates.py` đọc khóa config `contact_dist_m`, `contact_samples`, `inset_depth_tolerance`. `config.yaml` dùng đúng tên này | blockout.md §10 | |
| 3 | Blockout | `bootstrap.py` tìm thư viện ở `agents/zps-3dp-blockout/tools/.deps/blender-py<ver>`. Chạy `setup_deps.sh` trước các script chạy trong Blender | blockout.md §10 | |
| 4 | Blockout | `assembly.py` chạy được bằng Python thường (không Blender) khi graph chỉ có primitive. Dùng blockout mẫu để thử | blockout.md §9 | |
| 5 | Blockout | Mask từ `concept_mask.py` được `raster.concept_mask` của kit đọc đúng là mask (trắng trên nền đen, viền đen) | blockout.md §8 | |
| 6 | 3D Artist | `bake.py` của kit ở chế độ `rebake` có tách riêng phần unwrap UV được không, hay phải viết script unwrap mới | 3d-artist.md §13 | |
| 7 | 3D Artist | Join không weld: `mesh_check` của kit có thể báo đỉnh trùng ở cạnh đã tách. Đặt ngưỡng đúng trong spec | 3d-artist.md §13 | |
| 8 | 3D Artist | `gen_api.py texture` (Meshy) cần mạng. Bản Codex xin phép mạng ở phiên gốc | 3d-artist.md §13, D6.4 | |
| 9 | Concept Views, Texture Artist | `codex exec` nhận ảnh tham chiếu đầu vào, và trả đường dẫn ảnh đầu ra ổn định. Có tốn lượt Codex | D8 | |
| 10 | Concept Views | `measure_views.py` sau khi sửa tách nền theo màu khóa toàn ảnh: khe giữa cột không còn bị tính là vật thể | review-kit G1 | |
| 13 | Concept Views | `diff_guides.py` phát hiện đúng view nào đổi guide khi blockout lên version (thử: đổi một cửa sổ mặt sau) | concept-views.md §9 | |
| 14 | Concept Views | `pick_bg.py` chọn màu nền không trùng màu vật liệu nào của concept (thử với bộ đá kem + gỗ tối) | concept-views.md §3 | |
| 15 | Blockout | Part `custom` dựng được cây và đá low-poly; gate của kit chạy đúng với khối nhiều mặt | D9.1 | |
| 11 | Codex | Sub-agent Codex vẫn gọi được sub-agent 3 tầng ở bản Codex đang dùng. Nếu không, dùng dự phòng `review: pending` | D6.2 | Đã thử với Codex 0.164 ngày 2026-11-08: 3 tầng chạy được |
| 12 | Review Board | Sub-agent tải ảnh và ghi dữ liệu lên trang duyệt; anh bấm Duyệt thì agent đọc được | decisions "Chưa chốt" | Đã thử ngày 2026-11-08: chạy được. Lỗi hiển thị "Đã lưu" đã sửa ở trang thử, chưa xem lại |
