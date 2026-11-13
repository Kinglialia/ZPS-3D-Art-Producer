VERDICT: PASS
RUBRIC: mass=pass; detail=pass; shading=pass; planes=pass; thumbnail=pass; density=pass; blockout_match=pass; shadow_read=pass
TOP_FIX: none
EVIDENCE_OPENED: lit_34_back, lit_34_front, lit_front, lit_game, clay_lit_concept, clay_34, clay_front, parts_34, wire_34, wire_34_crop, thumb, uv_checker, overlay_34, overlay_front, summary.json, findings.json, custom_parts.py, model.md, part_graph.json, blockout.md, detail.json, worker-out.md, concept_shadow.png, asset-card.yaml, rubric.md, feedback.md
FINDINGS: none
PRIOR:
- F2: open | evidence: lit_34_front, custom_parts.py | acceptance: lit_34_front: mép trên và mép trước rail_top có dải bo giống đỉnh trụ.

## Ghi chú chấm (REVIEW_SCOPE: full, v1)

- Chưa có art direction. Chấm theo brief, rubric `## model`, thẻ asset và concept_shadow.png.
- Mục "Hiện hành" trong feedback.md trống. Không có H<n>.
- F1 đã waive: không mở lại, không ghi PRIOR.

### mass = pass
- clay_front và clay_34 khớp concept_shadow.png. Hai trụ sau cao, thanh vòm trên, ba thanh tựa đứng, thanh ngang dưới, ba ván ngồi nhô qua khung, apron trước, bốn chân thẳng.
- Không có khối ổ bánh mì. Mép ván ngồi thẳng hàng với mép ngoài trụ và chân, như concept.
- Ghi chú, không phải finding: đầu apron_back (part 9) lộ thành một khối nhỏ cạnh post_BL dưới ván ngồi trên parts_34, clay_34 và lit_34_front. Vị trí này do blockout.md mục 6 quyết ("apron sau dài 0.46 m ... chạm mặt trước hai trụ"). Bước model không đổi `attach`. Đây là đầu vào đã duyệt, không chấm lại. Camera game (lit_game) không thấy chi tiết này.

### detail = pass
- Bảng detail pass trong model.md khớp concept: bevel toon 9 mm trên chân, trụ, apron, rail_low, thanh tựa và ván ngồi. Ván ngồi có rãnh ghép bằng bevel.
- Ghi chú real/texture_only chép đúng từ thẻ. Vân và mắt gỗ để texture.
- custom_parts.py: `arched_rail` dựng dải parabol. Kích thước đi qua tham số (`span_x`, `rail_t`, `rail_top_h`, `arch_rise`, `arch_seg`). Không có số đếm viết thẳng. Số đếm đi qua tag (legs 4, back_slats 3, seat_planks 3, back_rails 2, seat_aprons 4).
- rail_top không bo cạnh: F2 (preference) vẫn open. Không chặn PASS.

### shading = pass
- lit_34_back, lit_34_front, clay_34, clay_front: không có vệt đen, không z-fighting, không lỗ, không mặt ngược.
- Bóng chéo trên thanh tựa ở lit_front, lit_game và clay_lit_concept do đèn render chiếu từ dưới. Lỗi này thuộc F1 (đã waive), không do mesh.

### planes = pass
- wire_34 và wire_34_crop: mặt ván ngồi và apron chỉ có đường chéo chia tam giác. Không có cạnh thừa.
- Mặt trước rail_top có nhiều tam giác. Mặt này là dải vòm phẳng 26 đỉnh, nên 24 tam giác là số tối thiểu. Đây không phải cạnh thừa.

### thumbnail = pass
- thumb: đọc rõ trụ, vòm tựa, ba thanh tựa, ba ván ngồi và bốn chân.

### density = pass
- not_checked: chưa có pilot (`detail.vs_pilot` = not_checked trong detail.json). 509 tris / trần 3000, 302.47 tris/m².

### blockout_match = pass
- Script điền từ JSON. Chép nguyên.

### shadow_read = pass (giới hạn)
- Chỉ chấm phần không phụ thuộc hướng đèn trên clay_lit_concept. Ván ngồi nhô qua khung như concept. Hốc giữa ba thanh tựa và khoảng hở dưới ván ngồi giống concept.
- Bóng đổ chính không chấm được vì đèn render chiếu từ dưới. Lỗi này thuộc F1, người dùng đã waive. Kết quả pass không dựa trên bằng chứng về bóng đổ chính.

### uv_checker
- Ô lưới đều trên mọi mặt lớn, không méo rõ. `uv.stretch_share` = 0.0.
