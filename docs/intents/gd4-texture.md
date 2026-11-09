# Intent: GĐ 4, Texture và Assemble (`texture`, `assemble`, DUYỆT 2)

## Problem

GĐ 3 dừng ở `done_enabled` sau DUYỆT 1. `docs/producer.md` §18 hàng GĐ 4 cần bước `texture` (budget Meshy theo hash mesh), bước `assemble` bằng script, DUYỆT 2 và gói `deliver/<id>/`. Chưa có wrapper Meshy, agent texture, reviewer texture hay `assemble.py`.

## Outcome

- `pipeline.toml` bật cả 6 bước. Luồng chạy được: blockout → views → model → texture → assemble → `waiting_human` → duyệt → `done`, `deliver/<id>/` có gói.
- `scripts/meshy_call.py`: chạy `gen_api.py` của kit (chép nguyên) với `.env` của project, không có `MESHY_API_KEY` trong môi trường con; budget theo hash mesh; lỗi trước khi có task thì hoàn budget và thử lại, sau khi có task thì chờ tiếp đúng `task_id`; 3 lần thì dừng.
- Brief `texture` kiểm key, mở budget, hỏi người dùng khi mesh đổi. `meshy_regen` và `UNFIXABLE: yes` chờ người dùng; duyệt thì thêm một lần gọi.
- `scripts/assemble.py`: kiểm hash mesh, gắn albedo, xuất GLB unlit, QA và `finalize.py` của kit, so pixel với render bước texture, ghép gói và README. Pass → DUYỆT 2; fail → `blocked`.
- Agent `zps-3dp-step-texture` (12 tool), reviewer `zps-3dp-check-texture`. `P texture-stats`, ước lượng lô ở `intake`, `estimate.py log` khi DUYỆT 2.

## Surfaces

- Người dùng: trả lời câu hỏi Meshy (duyệt = gọi thêm, `meshy <id> paint` = VẼ MỚI); DUYỆT 2 trên review board, Cần sửa chọn `texture` hoặc `model`.
- Producer: chỉ chạy lệnh `P`; bước `assemble` là một lệnh Bash mà `P brief` in ra.
- Subagent texture: đọc brief, gọi Meshy chỉ qua `meshy_call.py`, Codex qua `gen_image_codex.py`.
- Meshy, Codex: dịch vụ trả phí. Test không gọi thật.

## Constraints

- File chép từ kit giữ nguyên byte, ghi sha256 trong `SOURCE.md`.
- Không agent nào đọc `.env`; brief không chứa key hay đường dẫn `.env`.
- Brief reviewer chỉ nêu đầu vào reviewer dùng (`review_inputs`, `review_concept`).
- Blender không để lại `.blend1`.
- Mỗi lệnh `P` in một dòng ngắn. File agent ngắn, chi tiết trong `references/`.

## Out of scope

Review board đầy đủ (GĐ 5: hỏi Meshy hay VẼ MỚI bằng nút); bản Codex, A/B (GĐ 6); chạy Meshy, Codex thật.

## Decisions

Của người dùng (qua task):
- Bật `texture`, `assemble`; chạy hết pipeline tới `done`.
- Test không gọi Meshy hay Codex thật; fake HTTP cho Meshy, `codex` giả.
- Test Blender chạy `assemble.py` thật, có một ca sai color space phải fail.

Của em:
- Bước script: `pipeline.toml` có khóa `script`. `P brief` in `{"role": "script", "command", "report"}`; script ghi `report-script.md` theo contract worker cộng `FINDINGS` cho từng điểm fail; `ingest` ghi các finding đó vào `findings.json` để board hiện. `retry` của bước script tạo version mới, để bản fail giữ report.
- Câu hỏi Meshy nằm trong `status.json` `ask`. Duyệt (CLI hoặc board) = gọi thêm một lần; `P meshy <id> paint` = VẼ MỚI. Lý do: board GĐ 4 chỉ có Duyệt / Cần sửa / Ghi chú, và VẼ MỚI không phải một đợt feedback mới (D25.H: không đặt lại bộ đếm).
- Chỉ hỏi "mesh đổi" khi một budget của hash khác đã tiêu credit. Budget cũ chưa dùng thì mesh mới được một lần gọi luôn.
- `meshy_regen` là kiểu lô, xếp sau `fix_uv_mesh`, trước `repaint`. Duyệt xong là vòng sửa mới từ đúng bản reviewer chấm.
- Không có `paths.env_file`: VẼ MỚI, không mở budget. Preflight không chặn bước `texture` vì thiếu Meshy.
- `outputs` nhận `{res}` = `texture_res` của thẻ (mặc định 2048).
- So pixel: render unlit Workbench, view transform Standard, camera ghi trong `renders.json` của bước texture. Ngưỡng: lệch trung bình ≤ 6/255 trên vùng vật thể, silhouette lệch ≤ 2 %. Ca đúng đo 0,0; albedo ghi ở giá trị linear đo 65.
- QA của kit chạy trên bản chép cùng byte của GLB trong `work/`, vì glTF validator ghi file cạnh GLB đầu vào. `finalize.py` nhận vì sha256 bằng nhau.
- Kit file của script Producer nằm ở `scripts/kit/` theo đúng cấu trúc `zps-3d-artist/`, để đường dẫn tương đối trong file kit đúng.
- Tool texture đọc vùng vật liệu từ ID map: mặt của mesh khóa khớp tâm tam giác part của model (`parts/`, `join.json`).
- `project_views.py` rút từ `project_concept.py` của kit: camera của paint view thay khung bbox, z-buffer numpy thay tia BVH.
- Paint guide 1536 × 1024 và crop gửi Codex phóng lên cạnh dài 1536 px, vì `gen_image_codex.py` đòi cạnh dài > 1040 px.

## Open questions

- Meshy thật: payload retexture, giá 10 credit, giữ UV và số tam giác (checklist 75, 102).
- Reviewer texture thật bắt được phần tử thừa và ranh giới lệch 10 cm (checklist 93, 103).
- Ngưỡng `tex_measure.py` và chất lượng `tone_fix.py`, `project_views.py` trên concept thật.
