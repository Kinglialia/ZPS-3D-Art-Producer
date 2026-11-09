# Intent: GĐ 3, Model (`model`, DUYỆT 1)

## Problem

GĐ 2 dừng ở `done_enabled` sau khi bộ view được duyệt. `docs/producer.md` §18 hàng GĐ 3 cần bước `model`, reviewer `check-clay`, khóa mesh khi duyệt, đường `fix_uv_mesh` từ `texture` về `model`, và các trường brief bước `texture` cần (`ISSUES`, `final/` đã duyệt). GĐ 2 còn để lại một chỗ nối sai: bộ đếm `reopened` dùng chung, nên một `regen_front` trước đó làm `fix_uv_mesh` đầu tiên đi thẳng tới người dùng.

## Outcome

- `pipeline.toml` bật `model` (gate `review_human`). `texture`, `assemble` vẫn tắt.
- Luồng chạy được: `views_rest` duyệt → `model` → vòng sửa → `waiting_human` → duyệt → khóa mesh → `done_enabled`.
- Duyệt `model` ghi sha256 của `final/<id>-untextured.glb` vào `status.json` `locked.model`. Mở lại `model` xóa khóa đó.
- `TOP_FIX: fix_uv_mesh` ở `texture` mở lại bản `model` đã duyệt, chép mọi id được liệt kê. `reopened` đếm theo từng loại `TOP_FIX`.
- Brief worker chép dòng `ISSUES` của report worker bản đã duyệt của bước khai trong `issues` (texture: `model`).
- Agent `zps-3dp-step-model` với tool trong `agents/zps-3dp-step-model/tools/`, reviewer `zps-3dp-check-clay`.
- Test e2e chạy CLI thật từ duyệt `views_rest` qua vòng sửa `structure`, `param` (có `PICK`) tới duyệt, rồi bật `texture` cho hai vòng `fix_uv_mesh`. Test Blender chạy unwrap thật và các check trên một mesh nhỏ.

## Surfaces

- Người dùng: duyệt DUYỆT 1 trên review board bằng `review/model_sheet.png` và GLB `<id>-untextured.glb`.
- Producer: chỉ chạy lệnh `P`, mỗi lệnh in một dòng.
- Subagent model: đọc brief, chạy tool, mở Blender qua dòng `BLENDER:` và dòng PID của brief.
- Kit v0.10.4: file chép nguyên, sha256 trong `SOURCE.md`.

## Constraints

- File chép từ kit giữ nguyên byte. Phần sửa nằm trong tool của mình.
- Brief chỉ nêu file cần đọc: `final/` đã duyệt của `blockout`, `views_front`, `views_rest` (D22.14: không chép), ba file concept, profile và preset. Số hình học chỉ lấy từ `sources.json` (D22.13).
- Acceptance của reviewer là điều thấy được trên ảnh cùng góc hoặc số của script, không là % chuẩn hóa theo bbox.
- Mỗi lệnh `P` in một dòng ngắn. File agent ngắn, chi tiết nằm trong `references/`.
- Không gọi dịch vụ trả phí.

## Out of scope

Agent `texture`, `assemble.py`, budget Meshy theo hash mesh, câu hỏi "mesh đổi" (GĐ 4); `finalize.py`, `report.py` của kit; review board đầy đủ (GĐ 5); bản Codex và A/B (GĐ 6).

## Decisions

Của người dùng (qua task):
- Bật `model`; `texture`, `assemble` tắt.
- Sửa chỗ nối `reopened` của GĐ 2; thêm `board.HERO` cho `model`.
- Rubric mẫu có mục `## model` với key của file check-clay.

Của em:
- `pipeline.toml` thêm ba khóa bước: `lock` (file khóa sha256 khi duyệt), `issues` (bước đầu vào chép `ISSUES`), `pilot` (brief ghi `PILOT:`). `outputs` và `lock` nhận `{id}`.
- `locked` là một dict theo bước, cùng vòng đời với `approved`: `reopen` xóa nó từ bước mở lại trở đi.
- `reopened` là dict theo loại `TOP_FIX`. Status cũ có số nguyên (GĐ 2): đọc là `regen_front`.
- `fix_uv_mesh` là kiểu lô: chép mọi id sang bản `model` đã duyệt với loại `structure`. Lý do: một lần mở lại tốn một DUYỆT 1; hai lỗi UV không nên tốn hai lần.
- Không có dòng `ISSUES` khi report ghi `none`.
- `PILOT:` trỏ tới `deliver/<pilot_asset>/` của chính runtime (`state.DELIVER`, cùng hằng số `approve` dùng khi chép gói cuối).
- Tool mới ngoài danh sách spec: `make_spec.py` (spec kit từ `sources.json`, preset, profile, thẻ), `join_mesh.py` (gộp mesh), `lib/glbread.py`, `lib/cli.py`.
- `check_detail.py` so tris của part build model với part build blockout, không so GLB cuối với `assembled.glb`. Lý do: union của blockout tam giác hóa lại mọi chỗ chạm, còn bước gộp mesh xóa mặt bị che, nên cả hai số đều không đo được phần detail pass thêm.
- `join_mesh.py` tự lấy mẫu tia ở gần mọi góc và trung điểm cạnh. `optbpy.visibility` của kit chỉ lấy tâm và ba điểm quanh tâm, nên xóa mặt trên của nền khi phần giữa nằm dưới tường.
- `unwrap.py` thu UV vào trong một khoảng bằng padding, vì xatlas để đảo cách mép atlas khoảng 0,5 px.
- Bộ render dùng Workbench: clay có bóng theo `sun`, không phải Eevee hay Cycles. Lý do: nhanh, chạy nền, cùng kết quả mỗi vòng.
- `screen_tris_check` cần OpenCV trong Blender: `setup_deps.sh` của model cài `opencv-python-headless`.

## Open questions

- Reviewer check-clay thật ghi đủ `PRIOR` và chấm được z-fighting trên ảnh: cần một lần chạy trên concept thật.
- Ngưỡng 20° tách cạnh và mật độ tia 64 hướng mới thử trên hut tổng hợp.
- Bóng Workbench có đủ để đọc "độ chìa mái, độ sâu hốc" như concept có bóng không: cần ảnh thật.
