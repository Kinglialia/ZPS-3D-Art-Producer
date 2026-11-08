# Việc phải kiểm khi viết code

Mỗi dòng là một điều chưa xác nhận bằng chạy thật. Khi viết code, kiểm từng dòng và ghi kết quả vào cột "Kết quả". Không đánh dấu xong nếu chưa chạy.

| # | Agent | Việc cần kiểm | Nguồn | Kết quả |
|---|---|---|---|---|
| 1 | Blockout | `graph.py` của kit bỏ qua field lạ (`role`, `tag`), không báo lỗi | blockout.md §10 | |
| 2 | Blockout | `gates.py` đọc khóa config `contact_dist_m`, `contact_samples`, `inset_depth_tolerance`. `config.yaml` dùng đúng tên này | blockout.md §10 | |
| 3 | Blockout | `bootstrap.py` tìm thư viện ở `agents/zps-3dp-blockout/tools/.deps/blender-py<ver>`. Chạy `setup_deps.sh` trước các script chạy trong Blender | blockout.md §10 | |
| 4 | Blockout | `assembly.py` chạy được bằng Python thường (không Blender) khi graph chỉ có primitive. Dùng blockout mẫu để thử | blockout.md §9 | |
| 5 | Blockout | Mask từ `concept_mask.py` được `raster.concept_mask` của kit đọc đúng là mask (trắng trên nền đen, viền đen) | blockout.md §8 | |
| 6 | 3D Artist | `bake.py` của kit ở chế độ `rebake` có tách riêng phần unwrap UV được không, hay phải viết script unwrap mới | 3d-artist.md §12 | |
| 7 | 3D Artist | Join không weld: `mesh_check` của kit có thể báo đỉnh trùng ở cạnh đã tách. Đặt ngưỡng đúng trong spec | 3d-artist.md §12 | |
| 8 | Texture Artist | `gen_api.py texture` (Meshy) cần mạng. Bản Codex xin phép mạng ở phiên gốc | texture-artist.md §10, D6.4 | |
| 9 | Concept Views, Texture Artist | `codex exec -m gpt-6-astra -s workspace-write -i …` với khung prompt cố định: Astra lưu ảnh đúng đường dẫn và ghi `result.json`; nếu không, dự phòng lấy từ `~/.codex/generated_images/`. Có tốn lượt Codex | D8, D18 | Cờ `-i` và `-m` có trong `codex exec --help` (2026-11-08) |
| 10 | Concept Views | `measure_views.py` sau khi sửa tách nền theo màu khóa toàn ảnh: khe giữa cột không còn bị tính là vật thể | review-kit G1 | |
| 11 | Codex | Sub-agent Codex gọi được sub-agent 3 tầng (D14.1 không còn cần, ghi lại để tham khảo) | D6.2 (đã thay bằng D14.1) | Đã thử với Codex 0.164 ngày 2026-11-08: 3 tầng chạy được |
| 12 | Review Board | Producer tải ảnh và ghi dữ liệu lên trang claude.ai; anh bấm Duyệt thì agent đọc được; GLB nhúng base64 trong JSON hiện được trên điện thoại | D19 | Đã thử 2026-11-08: chạy được cả ba. glTF JSON có `data:` thì lỗi |
| 13 | Concept Views | `diff_guides.py` phát hiện đúng view nào đổi guide khi blockout lên version (thử: đổi một cửa sổ mặt sau) | concept-views.md §9 | |
| 14 | Concept Views | `pick_bg.py` chọn màu nền không trùng màu vật liệu nào của concept (thử với bộ đá kem + gỗ tối) | concept-views.md §3 | |
| 15 | Blockout | Part `custom` dựng được cây và đá low-poly; gate của kit chạy đúng với khối nhiều mặt | D9.1 | |
| 16 | Texture Artist | `texture_complexity.py` xếp đúng: thùng gỗ và hòn đá là "đơn giản", một công trình pilot là "phức tạp" | texture-artist.md §2.1 | |
| 17 | Texture Artist | `project_concept.py` sau khi sửa: nhận 8 view, trọng số theo góc nhìn, loại vùng bị che, lấp vùng khuất trong 3D theo normal | texture-artist.md §4 | |
| 18 | Texture Artist | `crop_edit.py`: ảnh Codex trả về có cùng kích thước với crop gửi đi; pixel ngoài vùng sửa không đổi sau khi ghép | texture-artist.md §5 | |
| 19 | Texture Artist | `tex_measure.py` đọc vùng vật liệu từ ID map (không gắn nhãn cứng); chạy được trên một asset khác Warehouse | texture-artist.md §6 | |
| 20 | Mọi agent | Quy tắc dừng sớm và hoàn tác (D11) chạy đúng: đếm lỗi `blocker` + `major` từ report reviewer (contract) qua các vòng | D11 | |
| 21 | Project Setup | `check_profile.py` báo đúng khi thiếu trường bắt buộc, sai kiểu, hoặc preset không tồn tại; thiếu `has_map` cũng là thiếu trường bắt buộc; agent dừng khi profile không hợp lệ | project-profile.md §5 | |
| 22 | Mọi agent | Đọc thông số đúng thứ tự mặc định → preset → profile → thẻ asset; ghi hash profile vào báo cáo | project-profile.md §1, §3 | |
| 23 | Producer | Resume worker cũ trên Codex qua `collaboration.send_message` / `followup_task`: worker còn context, không đọc lại file | D14.1, producer.md §14 | |
| 24 | Producer | Gate `review_human`: reviewer PASS → `waiting_human`; `approvals: reviewer` tự duyệt khi không còn `major`/`unclear`; `assemble` không đổi được | producer.md §3–4 | |
| 25 | Producer | Contract reviewer mới (`COUNTS`, `TOP_FIX` theo bước) được `ingest` đọc đúng; loại `TOP_FIX` sai bước bị từ chối | producer.md §6 | |
| 26 | Producer | Dừng sớm và bản tốt nhất: brief vòng sửa trỏ tới bản tốt nhất, không phải bản mới nhất | producer.md §7 | |
| 27 | Producer | Duyệt một bước: chuyển version khác sang `_rejected/`. Chỉ khi duyệt `assemble` mới chép `final/` sang `deliver/<id>/`; duyệt bước khác không chép gì sang `deliver/`; làm lại sau DUYỆT 2 đánh dấu README | producer.md §8, D20.2 | |
| 28 | Producer | `P show --bundle`: một file HTML mở được trên điện thoại, ảnh thu về ≤ 1024 px, dung lượng hợp lý | producer.md §5 | |
| 29 | Producer | `P intake` từ chối asset thiếu file bắt buộc hoặc `asset-card.yaml` sai (`check_card.py`); `type` lấy từ thẻ | producer.md §9 | |
| 30 | Producer | `fix_uv_mesh` chạy `redo --step model`; `meshy_regen` hoặc `UNFIXABLE: yes` đặt `waiting_human` (xem dòng 41) | producer.md §6, D20.14 | |
| 31 | Texture Artist | `tone_fix.py` giảm chênh tông 4 hướng và bóng dưới diềm về trong ngưỡng của `tex_measure.py`, không làm phẳng vân hay vết mòn | D17, texture-artist.md §3 | |
| 32 | Review Board | Lớp phủ toàn màn hình, zoom hai ngón, chạm hai lần, vuốt chuyển ảnh chạy trên iPhone trong Artifact và trên trang local | review-board.md §3 | |
| 33 | Review Board | Khoanh vùng: chế độ Xem/Khoanh không lẫn thao tác; tọa độ theo ảnh gốc đúng sau khi zoom; ảnh khoanh và JSON lưu đúng thư mục | review-board.md §4 | |
| 34 | Review Board | `P board prepare` + đẩy lên + kéo về: Producer không mở ảnh; `P feedback` nhận đường dẫn ảnh khoanh; brief vòng sau có danh sách vùng | review-board.md §6 | |
| 35 | Producer | `has_map: true` mà thiếu `<id>.layout.md` → intake từ chối; `has_map: false` mà thẻ thiếu `size_m` hoặc `size_m` sai dạng `{w, d, h}` → `check_card.py` báo lỗi, intake từ chối; `has_map: false` và có `size_m` → intake nhận, Blockout lấy W×D×H từ `size_m` | producer.md §9, D20.1, D20.9 | |
| 36 | Producer | Brief bước `texture` có mục `ISSUES` chép đúng từ report `model` đã duyệt; trỏ tới `final/` đã duyệt của `blockout`, `model`, `views_rest`; không có file handoff | producer.md §6, D20.3, D20.10 | |
| 37 | Producer | `TOP_FIX: repaint` ở `assemble` chạy `redo --step texture`; bộ đếm vòng `texture` không đặt lại; `assemble` tự chạy lại khi `texture` duyệt lại | producer.md §6, D20.4 | |
| 38 | Producer | Hết vòng 3 vẫn FIX: script quay về bản tốt nhất và đặt `waiting_human`; trang duyệt hiện bản đó và finding còn mở | producer.md §7, D20.5 | |
| 39 | Producer | `VERDICT: ESCALATE` đặt `waiting_human` ngay, không chạy thêm vòng; trang duyệt hiện lý do | producer.md §7, D20.5 | |
| 40 | Producer | Vòng `need_evidence` không tính vào 3 vòng; cùng bước xin `need_evidence` lần thứ hai → `waiting_human`; bộ đếm này đặt lại khi anh gửi feedback (`redo`) | producer.md §7, D20.5, D20.15 | |
| 41 | Producer | `TOP_FIX: meshy_regen` hoặc `UNFIXABLE: yes` → script đặt `waiting_human`, không tự cho gọi Meshy lần hai; chỉ sau khi anh duyệt, brief tiếp theo mới ghi "được gọi Meshy thêm một lần" | producer.md §6, D20.14 | |
| 42 | Producer | Duyệt `model`: script ghi hash `<tên>-untextured.glb` vào `status.json`; `assemble` báo `BLOCKED` khi hash lệch | 3d-artist.md §3, D20.7 | |
| 43 | Producer | `approvals` có khóa lạ (ví dụ `views`, `views_front`) → script từ chối; `P approvals set` cũng từ chối | producer.md §4, D20.8 | |
| 44 | Producer | Report worker thiếu `PROFILE_HASH` → `ingest` báo lỗi định dạng; hash khớp profile đang dùng | producer.md §6 | |
| 45 | Producer | Report Texture Artist thiếu `MESHY_CALLS` → `ingest` báo lỗi định dạng; `MESHY_CALLS` vượt số lần được phép → script báo lệch | producer.md §6, D20.14 | |
| 46 | Texture Artist | Lỗi kỹ thuật khi gọi Meshy (hết thời gian chờ, lỗi mạng, lỗi API không trừ credit) không tăng `MESHY_CALLS`; thử lại tối đa 3 lần, rồi `STATUS: BLOCKED` | texture-artist.md §2.2, D20.14 | |
| 47 | Blockout | `has_map: false`: `sources.json` lấy W×D×H từ `size_m`, `character_h` từ `scale_refs`, `door_h` từ `scale_overrides` hoặc đo trên concept (có ghi cách đo); `files.layout` trỏ tới `asset-card.yaml`; `check_layout.py` so bbox với `size_m` | blockout.md §2, §5, D20.12 | |
| 48 | Review Board | `views_front` và `texture` ở `waiting_human` hiện đúng tóm tắt (`VIEWS.md`, `texture/notes.md`) và lý do gửi anh (từ report reviewer, hoặc report worker khi `BLOCKED` / `UNFIXABLE`) | review-board.md §2, D20.16 | |
