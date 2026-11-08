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
3. **Field tùy chọn `tag` (`base` | `roof`).** `check_base` và `check_support` chỉ chạy trên part có tag. Không có tag thì trả `not_checked`. Part `mirror_of` phải tự ghi `material`, `role`, `tag`. **Blockout không làm nhân vật, sinh vật.** (Sửa theo D9: bản đầu ghi thêm "cây, đá" là sai.)
4. **`check_fix.py` chạy sau khi sửa.** Script so graph cũ với graph mới. Nếu `fixed_params` đổi hoặc bbox lệch quá ±2%, Blockout chạy `apply_edit.py --revert`.
5. **Gộp render thành `render_review.py`.** Một lần mở Blender cho ảnh camera game, lineup và crop chân nhà. Các ảnh `clay_*`, `normal_*`, `overlay_*`, `parts_*` vẫn dùng `render_views.py` của kit.

## D6 — Producer, điều phối, runtime và tên (2026-11-08)

1. **Producer là skill chạy trong phiên chính.** Producer chỉ điều phối: giao việc, nhận báo cáo ngắn, ghi sổ trạng thái `producer/status.md` (mỗi công trình một dòng). Producer không mở ảnh, JSON hay file dự án. Mọi agent tự làm việc của mình, kể cả bàn giao.
2. **Agent nào làm thì tự gọi reviewer của mình.** Blockout gọi review-blockout, Concept Views gọi review-views, 3D Artist gọi review-clay, Texture Artist gọi review-texture. Sub-agent được gọi sub-agent (Claude Code: tối đa 3 tầng dưới phiên chính; Codex 0.164: đã thử thật 3 tầng). Dự phòng: nếu agent không có tool gọi agent, agent trả `review: pending`, và agent gọi nó tự gọi reviewer. Reviewer không có tool gọi agent.
3. **Báo cáo ngắn theo mẫu cố định.** Agent trả về Producer: `asset | gate | status | sheet | summary`, vài dòng. Ảnh và chi tiết nằm trong file, không nằm trong báo cáo.
4. **Hai runtime: Claude Code và Codex.** Một nguồn chung, không phụ thuộc runtime. Mỗi runtime có một adapter riêng (gọi agent, chạy Blender, mạng, ảnh, Review Board). Một script build xuất ra hai bản. Bảng khác biệt ghi trong `docs/EDITIONS.md`. Thứ tự làm: bản Claude, chạy thử, rồi bản Codex. Bản Codex: Blender chạy ngoài sandbox; quyền mạng và sandbox cấp ở phiên gốc, vì sub-agent Codex dùng chung quyền của phiên gốc.
5. **Tên.** Tên kỹ thuật `zps-3dp-<vai>` (ví dụ `zps-3dp-3d-artist`). Tên hiển thị `ZPS-3DP - <Vai>`. Tiền tố này tránh trùng với skill `zps-3d-artist`, `zps-concept-views` của kit đang cài.

## D7 — Spec 3D Artist v1 (2026-11-08)

Spec đã duyệt: `docs/agents/3d-artist.md`.

1. **Vai trò.** 3D Artist là chủ asset từ lúc dựng tới lúc bàn giao. 3D Artist tự gọi review-clay, Meshy và Texture Artist.
2. **Meshy.** Chỉ retexture, giữ UV, không remesh. Gọi một lần. Gọi lần hai chỉ khi review-texture đánh `blocker` và Texture Artist xác nhận không sửa được. Lần hai vẫn hỏng thì Texture Artist vẽ mới. Dùng Texture Artist ngay từ đầu nếu Producer yêu cầu hoặc không có key Meshy.
3. **Gộp mesh.** Join và quét lỗi. Không weld, không boolean. Khóa mesh bằng hash sau DUYỆT 1. Giả định: `repair.py` của pilot chỉ dùng cho nhánh B (Meshy remesh).
4. **UV và texture.** Luôn làm và giao ở 2048. Số liệu nằm trong project profile. Thu nhỏ texture là việc của agent khác.
5. **Cách dựng.** Part graph. Không nhắc okf_context của Gen3D trong các skill của mình.
6. **Phạm vi v1.** Chỉ self-model. Không gen mesh bằng AI. Không làm nhân vật, sinh vật. Cây và đá low-poly có làm (sửa theo D9).
7. **Tam giác nhỏ.** Chỉ cảnh báo. LOD làm sau.
8. **Detail pass hai lớp.** Lớp 1: quy tắc chung theo silhouette và pixel (3 px, 16 px). Lớp 2: ví dụ của dự án trong profile, có sau pilot. Thêm: mặt phẳng tối thiểu, phóng to độ sâu, test thumbnail, tris/m² so với pilot, trần tris theo hạng, bevel tùy chọn.
9. **Review.** Render có ánh sáng, wireframe, thumbnail, lineup, `clay_lit_concept` (DUYỆT 1). Gói hoàn thành có `final_lit_vs_concept.png`, đặt cạnh concept có bóng.
10. **Bàn giao.** 3D Artist tự chép vào `3D/0X-<tên>/` sau DUYỆT 2.

## D8 — Sinh ảnh dùng Codex (2026-11-08)

1. Bộ Producer bản Claude vẫn có Concept Views và Texture Artist. Bước sinh ảnh và sửa ảnh của hai agent này gọi **tool ảnh của Codex qua `codex exec`**. Bản Codex dùng tool ảnh có sẵn của Codex.
2. Lý do: Claude không tự sinh ảnh. Codex có tính năng `image_generation`. Claude giữ việc điều phối, đo và review.
3. **Khi Codex CLI lỗi:** nếu gọi 3 lần liên tiếp mà không ra ảnh, agent dừng và báo Producer, kèm thông báo lỗi. Ví dụ lỗi: chưa cài, chưa đăng nhập, hết hạn mức, hết thời gian chờ, không có file ảnh. Producer xin anh duyệt. Chỉ khi anh duyệt mới dùng tool ảnh phía Claude (ví dụ `generate_image` của Gen3D, có tính credit).
4. 3 lần thử này chỉ tính **lỗi kỹ thuật**. Ảnh ra nhưng chất lượng chưa đạt thì đi theo vòng review của từng agent, không tính vào 3 lần này.
5. Adapter của bản Claude ghi cách gọi `codex exec`, chỗ lấy ảnh đầu ra, và cách chép ảnh vào thư mục công trình.

## D9 — Phạm vi v1 và một Producer (2026-11-08)

1. **v1 làm:** công trình, props cứng, cây và đá low-poly. Cả bốn loại đi cùng một luồng: Blockout (part graph, part `custom` cho cây, đá) → Concept Views → 3D Artist (self-model) → Texture Artist. Nếu dáng quá phức tạp so với primitive (cây nhiều cành nhỏ, đá tả thực), agent báo Producer, không cố dựng.
2. **v1 không làm:** nhân vật, sinh vật. Hai nhóm này có luồng khác ở mọi bước. Version sau làm bộ agent riêng `zps-3dp-char-*`.
3. **Một Producer duy nhất.** Producer nhìn loại asset rồi giao cho đúng bộ agent. Bộ nhân vật dùng lại Producer, Review Board, mẫu báo cáo ngắn, D1 và D8.
4. Sửa lỗi phạm vi: D5.3 và D7.6 bản đầu ghi loại trừ "cây, đá". Anh chỉ chọn loại trừ nhân vật. Đã sửa hai mục đó.
5. Spec Concept Views v1 đã duyệt: `docs/agents/concept-views.md`.

## D10 — Asset texture đơn giản không qua Meshy (2026-11-08)

- `texture_complexity.py` đo 5 chỉ số. Asset **đơn giản** (vật liệu ≤ 2; cụm màu ≤ 6; không hoa văn, chữ, biển; không phải hero) thì 3D Artist gọi thẳng Texture Artist vẽ mới. Asset phức tạp thì Meshy trước (D7.2).
- Ngưỡng nằm trong profile. Ca giáp ranh do 3D Artist quyết và ghi lý do. Anh hoặc Producer được ghi đè.
- Ghi kết quả từng asset vào sổ dự án để xem lại ngưỡng.
- Đã ghi vào `docs/agents/3d-artist.md` (B1, mục 8.1).

## D11 — Vòng sửa: 3 vòng, dừng sớm, hoàn tác, reset theo feedback (2026-11-08)

Áp dụng cho mọi agent có vòng review (Blockout, Concept Views, 3D Artist, Texture Artist). D11 thay cho các dòng "tối đa 3 vòng" ở từng spec.

1. **Tối đa 3 vòng** agent tự sửa theo reviewer, trước khi gửi anh.
2. **Dừng sớm.** Nếu một vòng không giảm số lỗi `blocker` + `major` so với vòng trước, agent dừng và báo, không chạy tiếp.
3. **Hoàn tác.** Vòng nào tệ hơn thì quay về bản trước. Gửi anh bản tốt nhất, không phải bản mới nhất.
4. **Feedback của anh mở một đợt mới**, đếm lại từ 0. Không giới hạn số đợt. Đợt mới bắt đầu từ bản tốt nhất đã gửi anh.
5. **Feedback của anh ưu tiên hơn rubric.** Nếu feedback làm lệch một ràng buộc (ví dụ bbox so với MAP-LAYOUT), agent làm theo anh, ghi rõ chỗ lệch, và báo Producer phần bị ảnh hưởng.
6. **Ghi lịch sử** từng đợt (số đợt, feedback nguyên văn, số vòng) vào file trạng thái của công trình.
7. Lý do: Self-Refine, GIER, Nexus cho thấy phần lớn cải thiện nằm ở vòng 1–3; Code-as-Room thấy 10 vòng tệ hơn 5; Huang et al. (ICLR 2024) cho thấy vòng sửa chỉ có ích khi có phản hồi bên ngoài (script, reviewer độc lập). Thiết kế của mình có phản hồi bên ngoài.

## D12 — Spec Texture Artist v1 (2026-11-08)

Spec đã duyệt: `docs/agents/texture-artist.md`.

1. Hai chế độ: SỬA trên lớp Meshy (giữ chi tiết đúng, chỉ vẽ lại chỗ sai) và VẼ MỚI.
2. VẼ MỚI = tô nền bằng script theo mã vật liệu + 8 paint view qua Codex + chiếu lên UV + lấp vùng khuất và sửa seam trong không gian 3D (theo MVPaint). Không vẽ thẳng lên atlas.
3. Mọi lần sửa đi qua crop ≤ 1024 px. Pixel ngoài vùng sửa không được đổi.
4. Tự kiểm theo 4 nhóm chung: quy ước ánh sáng, đúng vật liệu, đọc được ở kích thước thật, liền mạch. Quy tắc riêng của dự án nằm trong `visual_checks` của profile.
5. review-texture (Opus) có 4 loại `top_fix`: `repaint`, `fix_uv_mesh`, `meshy_regen`, `note`.

## Chưa chốt
- Skill MapLayout (mới) và việc sửa Concept Artist (Material Handoff, ghi chú real/texture_only, phần khuất).
- **Review Board.** Trang duyệt trên claude.ai (cách A) đã thử: phiên chính và sub-agent đều tải được ảnh, ghi và đọc được dữ liệu; nút Duyệt của anh lưu được. Còn bàn: chốt cách A hay B, tính năng khoanh vùng trên ảnh, cách làm khi chạy bằng Codex. Trang thử: https://claude.ai/artifact/FizgnSc5J7wp1aHBv3uuxs
- Spec cho Producer. Spec riêng cho 4 reviewer (rubric đã nằm trong spec của từng agent; cần gom thành file agent khi viết code).
- Texture Artist có dùng chung cho nhóm nhân vật ở version sau không.

- 3D Artist: 5 điểm (gộp mesh C1, project profile texture/UV C4, part graph hay archkit C6, bỏ path gen mesh trong v1, tam giác nhỏ là cảnh báo) và runtime (chỉ Claude Code, hay cả Codex).
- Màu nền gen view (C3).
- Thư mục `upstream/`: giữ bản chép, dùng submodule, hay chỉ trỏ đường dẫn.
