# Producer — quyết định đã chốt

Mỗi dòng là một quyết định của anh. Ghi ngày và lý do ngắn. Phân tích nền: `docs/review-kit-v0.10.4-vs-process.md`.

## D1 — 4 reviewer riêng (2026-11-08)

- Người làm và người kiểm là hai sub-agent khác nhau.
- Có 4 reviewer: `review-blockout`, `review-views`, `review-clay`, `review-texture`. Mỗi reviewer có rubric riêng trong file agent của nó.
- Model ghi trong frontmatter của agent. Dự kiến: Sonnet cho blockout và views; Opus cho clay và texture. Cần đo lại sau vài công trình đầu.
- Quy tắc chung, chép vào cả 4 file. Có một test kiểm tra 4 file giữ đúng các quy tắc này:
  1. Chỉ đọc. Reviewer không sửa file và không chạy lại script.
  2. Mỗi lần gọi dùng context mới. Reviewer chỉ nhận artifact, số đo và rubric.
  3. Output là JSON: pass / fail / unclear cho từng tiêu chí, kèm đúng một `top_fix`.
  4. Tối đa 3 vòng. Nếu quá 3 vòng, Producer dừng và hỏi anh.
  5. Mặc định anh duyệt mọi điểm duyệt. Reviewer chỉ duyệt thay khi anh báo Producer cho lô đó ("lô này anh không duyệt"). Điều kiện: mọi script pass, mọi tiêu chí pass, không có `unclear`. Kết quả ghi "reviewer duyệt theo ủy quyền của anh, ngày …". Anh hủy được sau. (Sửa 2026-11-08.)
- Script kiểm trước, reviewer kiểm sau. Nếu script fail, maker tự sửa và không gọi reviewer.
- Lý do: self-review đã lọt lỗi trong pilot (render phẳng tự viết che lỗi mặt trùng, alpha, normal). Về token, 4 agent và 1 agent với 4 rubric tốn như nhau. 4 agent tránh truyền nhầm rubric và giữ model riêng cho từng bước.

## D2 — Sub-agent Blockout riêng (2026-11-08, sửa cùng ngày)

- Blockout là một sub-agent riêng. 3D Artist và Concept Views không làm blockout nữa.
- Blockout dựng blockout công trình: `part_graph.json` + `parts_lib.py`, có đánh version. Chi tiết cần đo nhô ra hoặc lõm vào ít nhất 2 cm.
- MAP-LAYOUT **không** thuộc Blockout (xem D3).
- Agent Blockout là người duy nhất sửa file blockout gốc. 3D Artist chép graph sang thư mục làm việc của mình rồi thêm chi tiết. 3D Artist không sửa file gốc.
- Khi blockout đổi version, Producer đánh dấu các view và model dựng từ version cũ là đã cũ.
- Blockout giữ bản chép riêng của các quy tắc và tool lấy từ 3D Artist (kit v0.10.4, commit `905dc93`). Blockout không trỏ sang 3D Artist. Lý do: Blockout cần cố định, còn 3D Artist sẽ thay đổi theo thời gian.
- Concept Views chỉ còn việc ảnh: gen view, đo, sửa.
- Lý do: blockout dùng để đo, còn model cuối cần thêm chi tiết. Hai mục tiêu ngược nhau. Lỗi trong pilot ("Model = blockout", "W×D hiểu nhầm") đều đến từ việc ranh giới giữa các bước không rõ.

## D3 — Phân vai nguồn thông tin cho Blockout (2026-11-08)

1. **Vật liệu.** Concept Artist giao file Material Handoff kèm concept. Blockout gắn nhãn `material` của mỗi part bằng đúng mã trong file đó (`STONE`, `TIMBER`…). Thiếu mã thì Blockout báo Producer, không đoán.
2. **MapLayout là skill riêng.** Skill này thảo luận cùng anh để cân đối các chỉ số, rồi chốt `MAP-LAYOUT.md`. Blockout chỉ đọc file này, không ghi. Nếu kích thước có vấn đề, Blockout báo Producer để MapLayout và anh sửa.
3. **Hợp đồng với 3D Artist.** Một trang liệt kê các mục bắt buộc trong `part_graph.json`. Một script test chạy mỗi khi sửa 3D Artist: 3D Artist phải đọc và dựng được một blockout mẫu nhỏ tự tạo trong repo. Không dùng Warehouse làm mẫu, vì Warehouse chỉ là bài test quy trình.
4. **real / texture_only.** Ghi chú real/texture_only trong concept của từng công trình là bắt buộc. Phần còn lại 3D Artist quyết ở detail pass. Blockout chỉ đánh dấu part là "khối chính" hay "mốc đo", và chép nguyên ghi chú của concept vào `blockout.md`.
5. **Tỉ lệ và phần khuất.** Concept Artist thiết kế phần khuất và ghi vào brief. Tỉ lệ lấy từ MapLayout (dự án có map) hoặc từ brief (asset lẻ). Nếu mô tả có thông tin, Blockout dựng theo. Nếu mô tả không có, Blockout tự quyết theo quy tắc mặc định của dự án, và ghi từng chỗ vào mục "Blockout tự quyết" trong `blockout.md`.
- Các số liệu của New Last Order (cửa 1,8 m, 3.000 tris…) là ví dụ của dự án, không phải mặc định của skill.

## D4 — Spec Blockout v1 (2026-11-08)

- Spec đã duyệt nằm ở `docs/agents/blockout.md`.
- Spec giữ test hợp đồng. Test chỉ chạy khi sửa skill 3D Artist, không chạy cho từng blockout.
- Spec có thêm 5 điểm từ nghiên cứu: bảng thành phần, lọc `top_fix`, mức độ lỗi, render camera game, khóa tỉ lệ chính trước. Không thêm lưới kích thước.

## D5 — Sửa spec Blockout thành v1.1 (2026-11-08)

Các điểm này lộ ra khi đọc code kit, trước khi viết code. Nguyên tắc: đơn giản, dễ bảo trì, không làm quá.

1. **`sources.json`.** MAP-LAYOUT và Material Handoff có một file cho mỗi công trình. Blockout đọc nguyên các file này, rồi chép giá trị cần kiểm vào `sources.json`, kèm dòng trích và hash của file nguồn. Script chỉ đọc JSON.
2. **Bỏ `inventory.json` và `check_inventory.py`.** Blockout ghi một dòng "thành phần đếm trên concept" vào `blockout.md`. Reviewer so dòng đó với concept. Lý do: script chỉ so graph với danh sách do chính Blockout viết, nên không bắt được lỗi đếm sai từ concept. Việc đếm props trên ảnh gen thuộc review-views.
3. **Field tùy chọn `tag` (`base` | `roof`).** `check_base` và `check_support` chỉ chạy trên part có tag. Không có tag thì trả `not_checked`. Part `mirror_of` phải tự ghi `material`, `role`, `tag`. **Blockout không làm nhân vật, sinh vật, cây, đá.**
4. **`check_fix.py` chạy sau khi sửa.** Script so graph cũ với graph mới. Nếu `fixed_params` đổi hoặc bbox lệch quá ±2%, Blockout chạy `apply_edit.py --revert`.
5. **Gộp render thành `render_review.py`.** Một lần mở Blender cho ảnh camera game, lineup và crop chân nhà. Các ảnh `clay_*`, `normal_*`, `overlay_*`, `parts_*` vẫn dùng `render_views.py` của kit.

## Chưa chốt
- Skill MapLayout (mới) và việc sửa Concept Artist (Material Handoff, ghi chú real/texture_only, phần khuất).

- 3D Artist: 5 điểm (gộp mesh C1, project profile texture/UV C4, part graph hay archkit C6, bỏ path gen mesh trong v1, tam giác nhỏ là cảnh báo) và runtime (chỉ Claude Code, hay cả Codex).
- Màu nền gen view (C3).
- Thư mục `upstream/`: giữ bản chép, dùng submodule, hay chỉ trỏ đường dẫn.
