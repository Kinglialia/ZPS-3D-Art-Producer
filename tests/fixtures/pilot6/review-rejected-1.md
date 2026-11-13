VERDICT: ESCALATE
RUBRIC: mass=pass; detail=pass; shading=pass; planes=pass; thumbnail=pass; density=pass; blockout_match=pass; shadow_read=unclear
TOP_FIX: none
PRIOR: F1=open; F2=open
EVIDENCE_OPENED: lit_34_back, lit_34_front, lit_front, lit_game, clay_lit_concept, evidence-1/clay_lit_concept.png, clay_34, clay_front, parts_34, wire_34, wire_34_crop, thumb, uv_checker, overlay_34, overlay_front, custom_parts.py, summary.json, concept_albedo.png, concept_shadow.png, asset-card.yaml, rubric.md, brief.md, feedback.md, worker-out.md, model.md, blockout.md, detail.json, qa_mesh_check.json, renders.json, normal.json
FINDINGS: none

## Cần quyết định (lý do ESCALATE)
- Không còn finding mesh nào mở ở mức blocker, major hay minor. Bảy key pass. Chỉ `shadow_read` không chấm được.
- Ảnh trong evidence-1 là đúng clay_lit_concept cũ, phóng cỡ gốc. Đèn render vẫn sai, nên xin lại ảnh cũng không giải quyết được. Một vòng `need_evidence` nữa sẽ giao lại cùng file.
- ESCALATE là lựa chọn gần nhất: rubric đòi một lần đọc bóng, nhưng đường xin bằng chứng của brief không cho được ảnh đúng. Lỗi nằm ở tool render, không ở model. Worker và reviewer đều không được sửa tool.
- Phương án 1: sửa dấu `scene.display.light_direction` trong `render_review.py` `light()`. Render lại clay_lit_concept và các ô lit_* trên cùng GLB, rồi chấm lại chỉ `shadow_read` (vòng `fix`).
- Phương án 2: duyệt v1 và ghi `shadow_read` là không chấm được do lỗi tool.

## PRIOR
- F1 (unclear, đèn render): open. evidence-1/clay_lit_concept.png vẫn có bóng đổ bắt đầu ở trụ trái ngang mặt ngồi rồi leo chéo lên phải qua thanh tựa. Mép trên của bóng chạy ngang qua thanh tựa phải và trụ phải. Đó là bóng của mép trước và mép bên mặt ngồi bị hắt lên. apron_front không có dải bóng dưới mép ván ngồi. Vậy nắng đến từ dưới, không phải từ trái cao 45° như thẻ ghi. Không part nào gây ra bóng này (confidence high). Phần đọc được: ván ngồi chìa qua chân và trụ như concept, cung vòm rail_top và khe giữa thanh tựa đúng. Bóng đổ chính thì không đối chiếu được.
- F2 (preference, rail_top không bo cạnh): open. Version không đổi. Không chặn PASS.

## Ghi chú
- Chưa có art direction.
- REVIEW_SCOPE full. VIEWS: none: mặt khuất chấm theo `hidden_sides` của thẻ và `blockout.md`. lit_34_back khớp: apron sau nằm dưới mép ván, mặt sau thanh tựa trơn, không có giằng thấp.
- mass: clay_front và clay_34 khớp concept_albedo.png. Có hai trụ liền chân sau, rail_top vòm cả mép trên lẫn mép dưới, 3 thanh tựa và rail_low. Có 3 ván nhô nhẹ qua khung, apron trước và 4 chân. Không khối nào giống ổ bánh mì.
- detail: bảng detail pass trong model.md khớp concept. Ghi chú real/texture_only chép đúng từ thẻ. Cạnh trên rail_low vuông có lý do hình học.
- shading: clay_34 và clay_front sạch. Bóng chéo trên lit_front, lit_game và clay_lit_concept là bóng đổ của đèn đặt sai (F1), không do pháp tuyến. Thể tích âm của 4 apron trong qa_mesh_check.json đến từ các mặt đã xóa khi join, không do mặt bị lật.
- planes: trên wire_34 và wire_34_crop, mỗi mặt trên ván có một đường chéo. Dải bevel không có vạch thừa.
- thumbnail: thumb đọc rõ tựa vòm, 3 thanh tựa, 3 ván và 4 chân.
- density: pass. not_checked: chưa có pilot (509 tris, 302.47 tris/m², trần 3000).
- blockout_match: chép từ script (detail.json, qa_mesh_check.json).
- uv_checker: ô lưới đều cỡ, không ô méo. `uv.stretch_share` = 0.0.
- overlay_*: phần đỏ trong các khe là mask concept bị lấp kín, không phải hình học thiếu.
