VERDICT: ESCALATE
RUBRIC: mass=pass; detail=pass; shading=pass; planes=pass; thumbnail=pass; density=pass; blockout_match=pass; shadow_read=unclear
TOP_FIX: none
PRIOR: F1=open; F2=open
EVIDENCE_OPENED: lit_34_back, lit_34_front, lit_front, lit_game, clay_lit_concept, evidence-1/clay_lit_concept.png, clay_34, clay_front, parts_34, wire_34, wire_34_crop, thumb, uv_checker, overlay_34, overlay_front, custom_parts.py, summary.json, concept_albedo.png, concept_shadow.png, asset-card.yaml, rubric.md, brief.md, feedback.md, worker-out.md, model.md, blockout.md, detail.json, qa_mesh_check.json, renders.json, normal.json
FINDINGS: none
  Ghi chú (không phải finding):
  Lý do ESCALATE: không còn finding mesh nào mở ở mức blocker, major hay minor. Bảy key pass; chỉ shadow_read không chấm được.
  Ảnh evidence-1/clay_lit_concept.png là đúng clay_lit_concept cũ, phóng cỡ gốc. Đèn render vẫn sai, nên một vòng need_evidence nữa sẽ giao lại cùng file.
  Lỗi nằm ở tool render, không ở model. Worker và reviewer đều không được sửa tool. Rubric đòi một lần đọc bóng mà đường xin bằng chứng của brief không cho được.
  Phương án 1: sửa dấu scene.display.light_direction trong render_review.py light(). Render lại clay_lit_concept và các ô lit_* trên cùng GLB, rồi chấm lại chỉ shadow_read (vòng fix).
  Phương án 2: duyệt v1 và ghi shadow_read là không chấm được do lỗi tool.
  PRIOR id 1 (unclear, đèn render) còn open. Trên evidence-1/clay_lit_concept.png, bóng đổ bắt đầu ở trụ trái ngang mặt ngồi và leo chéo lên phải qua thanh tựa.
  Mép trên của bóng chạy ngang qua thanh tựa phải và trụ phải: đó là bóng của mép mặt ngồi bị hắt lên. apron_front không có dải bóng dưới mép ván ngồi.
  Vậy nắng đến từ dưới, không phải từ trái cao 45° như thẻ ghi. Không part nào gây ra bóng này (confidence high).
  Phần đọc được: ván ngồi chìa qua chân và trụ như concept; cung vòm rail_top và khe giữa thanh tựa đúng. Bóng đổ chính không đối chiếu được.
  PRIOR id 2 (preference, rail_top không bo cạnh) còn open; version không đổi; không chặn PASS.
  Chưa có art direction.
  VIEWS none: mặt khuất chấm theo hidden_sides của thẻ và blockout.md. lit_34_back khớp: apron sau dưới mép ván, mặt sau thanh tựa trơn, không giằng thấp.
  mass: clay_front và clay_34 khớp concept_albedo.png (hai trụ liền chân sau, rail_top vòm, 3 thanh tựa, rail_low, 3 ván nhô nhẹ, apron trước, 4 chân).
  detail: bảng detail pass trong model.md khớp concept; ghi chú real/texture_only chép đúng từ thẻ.
  shading: clay_34 và clay_front sạch. Bóng chéo trên lit_* là bóng đổ của đèn đặt sai, không do pháp tuyến.
  planes: wire_34 và wire_34_crop không có vạch thừa; mỗi mặt trên ván một đường chéo.
  thumbnail: thumb đọc rõ tựa vòm, 3 thanh tựa, 3 ván và 4 chân.
  density: pass. not_checked: chưa có pilot (509 tris, 302.47 tris/m², trần 3000).
  blockout_match: chép từ script (detail.json, qa_mesh_check.json).
  uv_checker: ô lưới đều cỡ, không ô méo; uv.stretch_share = 0.0.
