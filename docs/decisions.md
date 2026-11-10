# Producer — quyết định đã chốt

Mỗi dòng là một quyết định của anh. Ghi ngày và lý do ngắn. Phân tích nền: `docs/review-kit-v0.10.4-vs-process.md`.

## D1 — 4 reviewer riêng (2026-11-08)

- Người làm và người kiểm là hai sub-agent khác nhau.
- Có 4 reviewer: `review-blockout`, `review-views`, `review-clay`, `review-texture`. Mỗi reviewer có rubric riêng trong file agent của nó.
- **[Thay bằng D16.5]** ~~Model ghi trong frontmatter của agent.~~ Dự kiến: Sonnet cho blockout và views; Opus cho clay và texture. Cần đo lại sau vài công trình đầu.
- Quy tắc chung, chép vào cả 4 file. Có một test kiểm tra 4 file giữ đúng các quy tắc này:
  1. Chỉ đọc. Reviewer không sửa file và không chạy lại script. **[Sửa theo D27.5: reviewer tự ghi file report của mình, chỉ ở đường dẫn trong brief]**
  2. Mỗi lần gọi dùng context mới. Reviewer chỉ nhận artifact, số đo và rubric.
  3. **[Thay bằng D14.10]** ~~Output là JSON: pass / fail / unclear cho từng tiêu chí, kèm đúng một `top_fix`.~~ Output theo contract `KEY: value`.
  4. Tối đa 3 vòng. Nếu quá 3 vòng, Producer dừng và hỏi anh.
  5. Mặc định anh duyệt mọi điểm duyệt. Reviewer chỉ duyệt thay khi anh báo Producer cho lô đó ("lô này anh không duyệt"). Điều kiện: mọi script pass, mọi tiêu chí pass, không có `unclear`. Kết quả ghi "reviewer duyệt theo ủy quyền của anh, ngày …". Anh hủy được sau. (Sửa 2026-11-08.)
  6. **[Thêm theo D25.B]** Ảnh cùng góc của bản trước ở vòng sửa; `EVIDENCE_OPENED`; cảnh báo xu hướng duyệt dễ; không tự đo; chỉ chấm trong phạm vi bước.
- Script kiểm trước, reviewer kiểm sau. Nếu script fail, maker tự sửa và không gọi reviewer.
- Lý do: self-review đã lọt lỗi trong pilot (render phẳng tự viết che lỗi mặt trùng, alpha, normal). Về token, 4 agent và 1 agent với 4 rubric tốn như nhau. 4 agent tránh truyền nhầm rubric và giữ model riêng cho từng bước.

## D2 — Sub-agent Blockout riêng (2026-11-08, sửa cùng ngày)

- Blockout là một sub-agent riêng. 3D Artist và Concept Views không làm blockout nữa.
- Blockout dựng blockout công trình: `part_graph.json` + `parts_lib.py`, có đánh version. Chi tiết cần đo nhô ra hoặc lõm vào ít nhất 2 cm.
- MAP-LAYOUT **không** thuộc Blockout (xem D3).
- Agent Blockout là người duy nhất sửa file blockout gốc. 3D Artist chép graph sang thư mục làm việc của mình rồi thêm chi tiết. 3D Artist không sửa file gốc.
- **[Thay bằng D21.5]** ~~Khi blockout đổi version, Producer đánh dấu các view và model dựng từ version cũ là đã cũ.~~ Script tự suy ra version cũ từ `inputs` của từng version.
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

1. **Producer là skill chạy trong phiên chính.** Producer chỉ điều phối: giao việc, nhận báo cáo ngắn, ghi sổ trạng thái **[Thay bằng D14 (mở đầu: trạng thái trong file)]** ~~`producer/status.md` (mỗi công trình một dòng)~~ `status.json` / `dashboard.md`. Producer không mở ảnh, JSON hay file dự án. Mọi agent tự làm việc của mình, kể cả bàn giao.
2. **[Thay bằng D14.1]** ~~Agent nào làm thì tự gọi reviewer của mình.~~ Blockout gọi review-blockout, Concept Views gọi review-views, 3D Artist gọi review-clay, Texture Artist gọi review-texture. Sub-agent được gọi sub-agent (Claude Code: tối đa 3 tầng dưới phiên chính; Codex 0.164: đã thử thật 3 tầng). Dự phòng: nếu agent không có tool gọi agent, agent trả `review: pending`, và agent gọi nó tự gọi reviewer. Reviewer không có tool gọi agent.
3. **[Thay bằng D14 (mở đầu: contract báo cáo)]** ~~**Báo cáo ngắn theo mẫu cố định.** Agent trả về Producer: `asset | gate | status | sheet | summary`, vài dòng.~~ Worker ghi `STATUS / OUTPUT / RUBRIC / ISSUES`. Ảnh và chi tiết nằm trong file, không nằm trong báo cáo.
4. **Hai runtime: Claude Code và Codex.** Một nguồn chung, không phụ thuộc runtime. Mỗi runtime có một adapter riêng (gọi agent, chạy Blender, mạng, ảnh, Review Board). Một script build xuất ra hai bản. Bảng khác biệt ghi trong `docs/EDITIONS.md`. Thứ tự làm: bản Claude, chạy thử, rồi bản Codex. Bản Codex: Blender chạy ngoài sandbox; quyền mạng và sandbox cấp ở phiên gốc, vì sub-agent Codex dùng chung quyền của phiên gốc.
5. **Tên.** **[Sửa theo D23.2: agent đặt theo bước, `zps-3dp-step-<bước>`, `zps-3dp-check-<bước>`]** ~~Tên kỹ thuật `zps-3dp-<vai>` (ví dụ `zps-3dp-3d-artist`). Tên hiển thị `ZPS-3DP - <Vai>`.~~ Tiền tố này tránh trùng với skill `zps-3d-artist`, `zps-concept-views` của kit đang cài.

## D7 — Spec 3D Artist v1 (2026-11-08)

Spec đã duyệt: `docs/agents/3d-artist.md`.

1. **[Thay bằng D14.2]** ~~Vai trò. 3D Artist là chủ asset từ lúc dựng tới lúc bàn giao. 3D Artist tự gọi review-clay, Meshy và Texture Artist.~~
2. **Meshy.** **[Sửa theo D20.14: lần hai cần anh duyệt; chỉ Texture Artist gọi]** Chỉ retexture, giữ UV, không remesh. Gọi một lần. Gọi lần hai chỉ khi review-texture đánh `blocker` và Texture Artist xác nhận không sửa được. Lần hai vẫn hỏng thì Texture Artist vẽ mới. Dùng Texture Artist ngay từ đầu nếu Producer yêu cầu hoặc không có key Meshy.
3. **Gộp mesh.** Join và quét lỗi. Không weld, không boolean. Khóa mesh bằng hash sau DUYỆT 1. Giả định: `repair.py` của pilot chỉ dùng cho nhánh B (Meshy remesh).
4. **UV và texture.** Làm theo `texture_res` của thẻ asset, mặc định 2048 (sửa theo D13). Đổi độ phân giải cho asset cụ thể là việc của agent khác.
5. **Cách dựng.** Part graph. Không nhắc okf_context của Gen3D trong các skill của mình.
6. **Phạm vi v1.** Chỉ self-model. Không gen mesh bằng AI. Không làm nhân vật, sinh vật. Cây và đá low-poly có làm (sửa theo D9).
7. **Tam giác nhỏ.** Chỉ cảnh báo. LOD làm sau.
8. **Detail pass hai lớp.** Lớp 1: quy tắc chung theo silhouette và pixel (3 px, 16 px). Lớp 2: ví dụ của dự án trong profile, có sau pilot. Thêm: mặt phẳng tối thiểu, phóng to độ sâu, test thumbnail, tris/m² so với pilot, trần tris theo hạng, bevel tùy chọn.
9. **Review.** Render có ánh sáng, wireframe, thumbnail, lineup, `clay_lit_concept` (DUYỆT 1). Gói hoàn thành có `final_lit_vs_concept.png`, đặt cạnh concept có bóng.
10. **[Thay bằng D14.8]** ~~**Bàn giao.** 3D Artist tự chép vào `3D/0X-<tên>/` sau DUYỆT 2.~~

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

- `texture_complexity.py` đo 5 chỉ số. Asset **đơn giản** (vật liệu ≤ 2; cụm màu ≤ 6; không hoa văn, chữ, biển; không phải hero) thì **[Thay bằng D14.2]** ~~3D Artist gọi thẳng Texture Artist~~ Texture Artist vẽ mới. Asset phức tạp thì Meshy trước (D7.2). **[Sửa theo D30.11: có key Meshy và budget thì Meshy SỬA là chế độ mặc định, không xét độ phức tạp. VẼ MỚI chỉ khi không có key hoặc anh chỉ định. Ledger ghi chế độ đã chọn và lý do.]**
- Ngưỡng nằm trong profile. Ca giáp ranh do 3D Artist quyết và ghi lý do. Anh hoặc Producer được ghi đè.
- Ghi kết quả từng asset vào sổ dự án để xem lại ngưỡng. **[Sửa theo D21.5: script ghi `texture-log.jsonl` khi duyệt bước texture; agent không ghi ra ngoài thư mục version]**
- Đã ghi vào `docs/agents/texture-artist.md` (mục 2.1).

## D11 — Vòng sửa: 3 vòng, dừng sớm, hoàn tác, reset theo feedback (2026-11-08)

Áp dụng cho mọi agent có vòng review (Blockout, Concept Views, 3D Artist, Texture Artist). D11 thay cho các dòng "tối đa 3 vòng" ở từng spec.

1. **Tối đa 3 vòng** agent tự sửa theo reviewer, trước khi gửi anh.
2. **Dừng sớm.** **[Thay bằng D21.1]** ~~Nếu một vòng không giảm số lỗi `blocker` + `major` so với vòng trước, agent dừng và báo, không chạy tiếp.~~ Tiến bộ đo theo finding có id.
3. **Hoàn tác.** Vòng nào tệ hơn thì quay về bản trước. Gửi anh bản tốt nhất, không phải bản mới nhất. **[Sửa theo D27.1: hai bản hòa số `blocker` + `major` đang mở thì chọn bản giải quyết được nhiều hơn]**
4. **Feedback của anh mở một đợt mới**, đếm lại từ 0. Không giới hạn số đợt. Đợt mới bắt đầu từ bản tốt nhất đã gửi anh.
5. **Feedback của anh ưu tiên hơn rubric.** Nếu feedback làm lệch một ràng buộc (ví dụ bbox so với MAP-LAYOUT), agent làm theo anh, ghi rõ chỗ lệch, và báo Producer phần bị ảnh hưởng.
6. **Ghi lịch sử** từng đợt (số đợt, feedback nguyên văn, số vòng) vào file trạng thái của công trình.
7. Lý do: Self-Refine, GIER, Nexus cho thấy phần lớn cải thiện nằm ở vòng 1–3; Code-as-Room thấy 10 vòng tệ hơn 5; Huang et al. (ICLR 2024) cho thấy vòng sửa chỉ có ích khi có phản hồi bên ngoài (script, reviewer độc lập). Thiết kế của mình có phản hồi bên ngoài.

## D12 — Spec Texture Artist v1 (2026-11-08)

Spec đã duyệt: `docs/agents/texture-artist.md`.

1. Hai chế độ: SỬA trên lớp Meshy (giữ chi tiết đúng, chỉ vẽ lại chỗ sai) và VẼ MỚI.
2. VẼ MỚI = tô nền bằng script theo mã vật liệu + 8 paint view qua Codex + chiếu lên UV + lấp vùng khuất và sửa seam trong không gian 3D (theo MVPaint). Không vẽ thẳng lên atlas.
3. Mọi lần sửa đi qua crop ≤ 1024 px. Pixel ngoài vùng sửa không được đổi.
4. Tự kiểm theo 4 nhóm chung: quy ước ánh sáng, đúng vật liệu, đọc được ở kích thước thật, liền mạch. **[Thay bằng D14.6]** ~~Quy tắc riêng của dự án nằm trong `visual_checks` của profile.~~ Quy tắc riêng nằm trong rubric theo loại.
5. **[Mở rộng bởi D20.5: thêm `need_evidence`]** review-texture (Opus) có 4 loại `top_fix`: `repaint`, `fix_uv_mesh`, `meshy_regen`, `note`.

## D13 — Project Profile, thẻ asset, Project Setup (2026-11-08)

Spec: `docs/project-profile.md`.

1. **Bốn lớp thông số**, lớp sau ghi đè lớp trước: mặc định skill → preset theo loại game → profile dự án → thẻ asset.
2. **Profile dự án ngắn**, không có trường gắn với một loại asset. Thước tỉ lệ, quy tắc phần khuất, `visual_checks` là danh sách mở. Số kỹ thuật nằm trong preset.
3. **Thẻ asset** nằm trong brief của từng concept: hạng, `texture_res`, trần tris riêng, thước riêng, đối xứng, ghi chú real/texture_only. Hạng chỉ quyết định trần tris.
4. **Texture:** làm theo thẻ asset. Nếu thẻ không ghi, mặc định 2048. Đổi cho asset cụ thể là việc của agent khác.
5. **Skill Project Setup** (`zps-3dp-project-setup`) chạy trong phiên chính, vì phải hỏi anh. Skill tạo profile, ghi cập nhật sau pilot khi anh duyệt, và có `check_profile.py`. Agent không tự sửa profile.
6. **Flow:** anh gọi Producer → Producer kiểm profile → nếu thiếu, làm cùng anh qua Project Setup → ghi file và kiểm → **Producer nhắc anh gõ lệnh xóa context và mở phiên mới** (Claude Code: `/clear`; Codex: `/new`) → phiên mới chỉ đọc profile và sổ trạng thái.
7. Producer cũng nhắc mở phiên mới sau khi cập nhật profile, và khi context đã dài sau một lô.
8. **Sub-agent hỏi anh** chỉ qua một đường: sub-agent dừng và ghi câu hỏi vào báo cáo ngắn; Producer chuyển câu hỏi cho anh; anh trả lời; Producer gọi lại sub-agent kèm câu trả lời.

## D14 — Dùng skill `producer` của anh làm nền (2026-11-08)

Spec: `docs/producer.md`. Nền: `producer-skill.zip` (SKILL.md, producer.py, references, templates). Giữ cơ chế của skill nền: trạng thái trong file, script quyết định thứ tự, brief bằng file, contract báo cáo, `pipeline.toml`, version theo bước, resume, ruling, trang duyệt local, hook.

1. **Producer sắp xếp reviewer** qua script (thay D6.2). Worker không gọi reviewer, không gọi agent khác. Resume worker cũ ở vòng 1–2, worker mới từ vòng 3. Bỏ dự phòng `review: pending`. Lý do: script đếm vòng chắc chắn, không phụ thuộc giới hạn tầng, reviewer độc lập hơn. Token gần bằng; chậm hơn khoảng 20–60 giây mỗi vòng.
2. **Pipeline 6 bước** (thay D7.1): `blockout` → `views_front` → `views_rest` → `model` → `texture` → `assemble`. 3D Artist làm `model` ~~và `assemble`~~ **[Sửa theo D22.11: `assemble` do script làm]**. Texture Artist làm `texture`, gồm chọn Meshy hay vẽ mới (D10) và gọi Meshy.
3. **Gate `review_human`**: reviewer PASS rồi chờ duyệt. Dùng cho `blockout`, `views_rest`, `model`, ~~`assemble`~~ **[Sửa theo D21.6: `assemble` dùng gate `checks_human`]**. `views_front`, `texture` dùng `review`. Bỏ `final_human_gate`.
4. **Chính sách duyệt `approvals`** ~~trong profile~~ **[Sửa theo D21.3: trong `production/policy.yaml`]** (Project Setup hỏi lúc khởi tạo): mỗi điểm duyệt là `human` hoặc `reviewer`. `assemble` luôn `human`. Đổi bằng lời trong chat → Producer chạy `P approvals set`. Ngoại lệ theo lô: `P delegate`. Thứ tự: `delegate` > `approvals` > `human`. Thay một phần D1.5.
5. **Xem kết quả:** anh nói trong chat → Producer chạy `P dashboard`, `P show <id>` (HTML), `P show --bundle` (nhúng ảnh, xem trên điện thoại), `P serve`. Producer gửi file bằng tool gửi file, không mở file.
6. **Thông số và rubric:** số mà script dùng nằm trong YAML (D13); tài liệu style nằm trong `art-direction/` (AD giữ); tiêu chí chung của bước nằm trong agent reviewer; tiêu chí riêng theo loại nằm trong `production/rubrics/<loại>.md` (anh duyệt). `visual_checks` chuyển khỏi profile vào rubric theo loại. Loại asset lấy từ `type` trong thẻ.
7. **GUIDELINE.md mở rộng:** mẫu `asset-card.yaml`, danh sách file bắt buộc, cách làm lúc chốt, việc của AD. `check_card.py` đi kèm. `P intake` kiểm thẻ, file bắt buộc, profile; sai thì không đăng ký.
8. **Ba khu thư mục:** `_approved/<id>/` (đầu vào, anh ghi), `production/assets/<id>/` (làm việc, script và agent ghi), `deliver/<id>/` (kết quả đã duyệt, **[Thay bằng D20.2]** ~~script chép sau mỗi lần duyệt~~ script chép khi duyệt `assemble`). Bỏ `View Concept/` riêng; bỏ `3D/`, thay bằng `deliver/`.
9. **Dọn version:** **[Thay bằng D22.2]** ~~duyệt một bước thì các version khác chuyển sang `_rejected/`.~~ Đánh dấu `rejected` trong status, không di chuyển thư mục. Xóa chỉ qua `P cleanup` khi asset đã xong, dry-run trước, anh đồng ý. Agent chỉ đọc đường dẫn trong brief.
10. **Contract reviewer:** `VERDICT`, `RUBRIC` (có `unclear`), `COUNTS` (blocker/major/minor), `TOP_FIX` (loại theo bước), `FINDINGS`. **[Mở rộng bởi D21.1: finding có id, `PRIOR`, `TOP_FIX` kiểu đơn/lô]** D11 (dừng sớm, bản tốt nhất) làm bằng script. `fix_uv_mesh` → redo `model`. **[Thay bằng D20.14]** ~~`meshy_regen` thêm một lần khi Texture Artist báo `UNFIXABLE: yes`.~~

## D15 — Model sinh ảnh và khi Codex hỏng (2026-11-08)

1. `gen_image_codex.py` luôn gọi `codex exec -m gpt-6-astra`, ghi model rõ trong lệnh, không dựa vào config mặc định của máy. Tên model và mức reasoning nằm trong preset: `image_gen: {codex_model: gpt-6-astra, reasoning: medium}`. Ảnh tham chiếu gửi bằng cờ `-i`.
2. Khi Codex hỏng (3 lần lỗi kỹ thuật, D8.3): agent báo `STATUS: BLOCKED` kèm lỗi, Producer **hỏi anh**. Không có phương án tự động: không vẽ bằng code, không tự dùng Gen3D hay API khác. Anh chọn cách xử lý; Producer ghi lựa chọn vào ledger rồi `P retry`.

## D16 — Chọn model cho worker và reviewer (2026-11-08)

1. **Pilot: Opus cho mọi bước**, cả worker lẫn reviewer. Thay tạm D1 (reviewer blockout và views dùng Sonnet) trong lúc pilot. Lý do: pilot là lúc chỉnh rubric và profile; giữ model tốt nhất để lỗi còn lại là lỗi của spec, không phải của model.
2. **Sau pilot: hạ từng bước**, đo rồi mới giữ. Ứng viên hạ:

   | Bước | Ứng viên sau pilot |
   |---|---|
   | Concept Views (2 bước), Texture | Sonnet, `escalate_model` = Opus |
   | `assemble` | Sonnet hoặc Haiku |
   | review-blockout, review-views | Sonnet (theo D1) |
   | Blockout, `model`, review-clay, review-texture | Giữ Opus |

3. **Đo gì để quyết:** số vòng sửa mỗi bước, tỉ lệ anh duyệt ngay lần đầu, số lần reviewer chấm lệch so với quyết định của anh. Bước nào sau khi hạ không kém đi thì giữ model mới.
4. Tính theo **chi phí cho mỗi asset hoàn thành**, không theo từng lần gọi. Ước lượng (chưa đo): bảng hạ ở mục 2 rẻ hơn dùng Opus hết khoảng 20–40%; nếu model rẻ thêm một vòng sửa mỗi bước thì phần tiết kiệm có thể mất hết.
5. Model nằm trong `pipeline.toml` (`model`, `escalate_model`, `reviewer_model`). Trong file agent dùng tên chung `opus`, `sonnet`, `haiku`. Bản Codex: adapter ghi model riêng (D15).

## D17 — Texture Artist: Claude điều phối, Codex chỉ vẽ; script sửa trước (2026-11-08)

1. **Cách A.** Texture Artist là sub-agent Claude. Texture Artist chạy mọi script (D10, Meshy, `base_fill`, chiếu UV, sửa seam, `tex_measure`). Codex (`gpt-6-astra`) chỉ vẽ paint view và sửa crop. Lý do: phần lớn bước `texture` là script; nếu Codex hỏng thì chỉ phần vẽ bị dừng.
2. **`tone_fix.py` chạy trước Codex** ở chế độ SỬA: cân tông theo hướng mặt, nâng vùng bị che, làm mịn seam, theo số đo của `tex_measure.py`. Chỉ lỗi script không sửa được mới gọi Codex. Lý do: rẻ hơn, ổn định hơn, giảm số lần gọi Codex.

## D18 — Gọi sinh ảnh Codex bằng mẫu prompt cố định (2026-11-08)

1. Không làm skill sinh ảnh riêng bên Codex. Không gọi sub-agent texture bên Codex.
2. `gen_image_codex.py` chạy `codex exec -m gpt-6-astra -C <thư mục làm việc của bước> -s workspace-write -i <ảnh tham chiếu> …`. Prompt có hai phần: **khung cố định** (dùng tool sinh ảnh; lưu ảnh vào `<đường dẫn>`; ghi `result.json` gồm đường dẫn, kích thước, lỗi; không làm việc khác) và **nội dung vẽ** do Concept Views hoặc Texture Artist viết.
3. Script đọc `result.json`, kiểm file ảnh tồn tại và đúng kích thước. Sai thì tính một lần lỗi kỹ thuật (D8.3).
4. Dự phòng: nếu Astra không lưu đúng đường dẫn, script lấy ảnh mới nhất của phiên đó trong `~/.codex/generated_images/` rồi chép sang. Kém chắc hơn, chỉ để dự phòng.
5. Lý do: chất lượng ảnh như nhau (cùng Astra, cùng tool ảnh); hướng dẫn nằm một chỗ trong repo, có test; không phải cài thêm gì bên Codex.

## D19 — Review Board (2026-11-08)

Spec: `docs/review-board.md`.

1. **Hai trang, cùng một bộ tính năng:** trang local `P serve` (luôn có) và trang claude.ai (tùy chọn, `review_board: local+remote` trong ~~profile~~ **[Sửa theo D21.3: `policy.yaml`]**). Bản Codex chỉ có trang local.
2. **Xem:** chạm để mở toàn màn hình (lớp phủ CSS), ‹ › hoặc vuốt để chuyển ảnh, hai ngón để zoom, chạm hai lần để zoom nhanh. Ảnh tải lên là ảnh gốc. Model 3D xoay và zoom được.
3. **Khoanh vùng v1 trên ảnh:** chế độ Xem và chế độ Khoanh; vòng tròn, chữ nhật, nét tự do; mỗi vùng có số và ghi chú; lưu theo tọa độ ảnh gốc. Lưu ảnh đã khoanh và JSON vào thư mục feedback của asset. Brief vòng sửa và reviewer nhận danh sách vùng. **v2:** ghim trên model 3D.
4. **GLB trên claude.ai:** nhúng base64 trong file JSON, tải lên làm asset (đã thử trên điện thoại: chạy). GLB tối đa khoảng 15 MB. Dự phòng: video quay 360°.
5. **Đồng bộ:** `P board prepare` chuẩn bị file; Producer tải lên và ghi dữ liệu bằng tool, theo đường dẫn, không mở file. Kéo về: Producer đọc dòng đổi trạng thái, tải ảnh khoanh về, chạy `P feedback`.
6. Phần xem và khoanh vùng là một file JavaScript dùng chung cho hai trang.

## D20 — Sửa mâu thuẫn sau review spec (2026-11-08)

1. **MAP-LAYOUT:** thêm `<id>.layout.md` vào `_approved/<id>/`. Profile có `has_map: true|false`. `true`: intake bắt buộc có file này. `false`: Blockout lấy W×D×H từ thẻ asset.
2. **`deliver/<id>/`** chỉ chứa `assemble/vN/final/` đã duyệt. Các bước giữa nằm lại trong `production/`.
3. **Brief Texture Artist:** script sinh từ các `final/` đã duyệt (`blockout`, `model`, `views_rest`; xem D20.10) và file concept, chép mục `ISSUES` của report `model`. Bỏ file handoff. Sửa UV, mesh chỉ qua `TOP_FIX: fix_uv_mesh`.
4. **[Thay bằng D21.6]** ~~**`repaint` ở `assemble`:** script chạy `redo --step texture`, rồi `assemble` tự chạy lại. Bộ đếm vòng `texture` giữ nguyên.~~ `assemble` không có reviewer; anh bấm Cần sửa và chọn bước.
5. **Ba trạng thái kết thúc:** hết vòng 3 vẫn FIX → về bản tốt nhất, `waiting_human`; `ESCALATE` → `waiting_human` ngay; `need_evidence` → vòng ngắn không tính, lần thứ hai → `waiting_human`.
6. **[Thay bằng D20.14]** ~~**Meshy lần hai:** reviewer trả `meshy_regen` → Texture Artist thử sửa một vòng → chỉ khi `UNFIXABLE: yes` mới gọi lại, tối đa một lần.~~
7. **Khóa mesh:** script ghi hash `<tên>-untextured.glb` vào `status.json` khi duyệt `model`. Bỏ A10. Thêm danh sách `model/vN/final/`.
8. **Khóa `approvals`** là id bước có gate người duyệt (`blockout`, `views_rest`, `model`, ~~`assemble`~~). **[Sửa theo D21.3: `assemble` luôn human, không có khóa]** Script từ chối khóa khác. `views_front` chỉ reviewer duyệt.
9. **`size_m` trong thẻ asset:** thẻ có `size_m: {w, d, h}` (mét). Trường này bắt buộc khi profile có `has_map: false`. `check_card.py` kiểm trường này lúc intake. Project Setup hỏi anh `has_map`.
10. **Đầu vào brief `texture`:** brief trỏ tới `final/` đã duyệt của `blockout` (để đọc `sources.json`), `model` và `views_rest`. `model/vN/final/` có thêm `spec.json` và ảnh `parts_*`.
11. **`spec.json` có một chủ:** 3D Artist ghi `spec.json` trong `model/vN/final/` (A7, dùng lại ở C4). Texture Artist không ghi vào `spec.json`. Texture Artist ghi `texture_spec.json` trong `texture/vN/final/`.
12. **Nguồn tỉ lệ khi `has_map: false`:** W×D×H lấy từ `size_m` của thẻ. `character_h` lấy từ `scale_refs` của profile. `door_h` lấy từ `scale_overrides` của thẻ. Nếu thẻ không có cửa, Blockout đo cửa trên concept, lấy `character_h` làm thước, và ghi giá trị cùng cách đo vào `sources.json`. Khi đó `files.layout` trỏ tới `asset-card.yaml`. Bbox so với `size_m`.
13. **Chủ `texture/notes.md`:** Texture Artist ghi file này trong `texture/vN/final/`. Ở `assemble`, ~~3D Artist~~ **[Sửa theo D22.11: script `assemble.py`]** chỉ chép file vào gói cuối và ghép README.
14. **Gọi Meshy** (thay D20.6):
    - Mỗi asset gọi Meshy một lần. Chỉ Texture Artist gọi Meshy.
    - **[Sửa theo D24.2: kit trừ budget trước khi gọi; lỗi sau khi task đã tạo thì chờ tiếp `task_id`, không gọi lại]** ~~Lỗi kỹ thuật (hết thời gian chờ, lỗi mạng, lỗi API không trừ credit) không tính là một lần gọi. Texture Artist thử lại, tối đa 3 lần, như D8.3.~~ Sau 3 lần lỗi: `STATUS: BLOCKED`, Producer hỏi anh.
    - Texture chưa đạt: Texture Artist sửa qua các vòng review thường.
    - Không sửa được (reviewer trả `TOP_FIX: meshy_regen`, hoặc report của Texture Artist có `UNFIXABLE: yes`): script đặt `waiting_human`. Anh duyệt lần gọi thứ hai. Chỉ khi đó brief tiếp theo mới cho gọi Meshy thêm một lần. Script không tự cho.
    - **[Thay bằng D21.2]** ~~Script đếm số lần gọi Meshy từ report của Texture Artist (`MESHY_CALLS: <n>`). Nếu số này vượt số lần được phép, script báo lệch.~~ `gen_api.py` ghi `budget.json` theo hash mesh; script đọc file đó.
15. **Bộ đếm `need_evidence`** (lần thứ hai → `waiting_human`, D20.5) đặt lại theo từng đợt feedback của anh, giống bộ đếm 3 vòng (D11.4).
16. **Tóm tắt trên Review Board** cho bước không có gate người duyệt nhưng có thể tới `waiting_human`: `views_front` dùng `VIEWS.md` (như `views_rest`); `texture` dùng `texture/notes.md`. Board hiện thêm lý do asset được gửi anh. Lý do lấy từ report reviewer, hoặc từ report worker khi `BLOCKED` hay `UNFIXABLE`.
17. **Anh duyệt bằng hình, chữ ngắn:** Review Board đặt hình trên cùng. Tóm tắt tối đa 3 dòng (3 dòng đầu của file tóm tắt), lý do chuyển lên anh một dòng. Phần còn lại ẩn, bấm mới mở.

Đã sửa thêm 15 lỗi nhỏ trong các spec (tên file, tham chiếu mục, nút duyệt, `PROFILE_HASH`, `note`, đánh dấu mục đã thay).

## D21 — Sửa sau review spec lần 2, và chạy hai runtime để so sánh (2026-11-09, duyệt cùng D22)

Nguồn: review spec ngày 2026-11-08/09 (mục 1–14), phản biện của anh về Review Board và Codex.

1. **Finding có id, sửa theo lô, tiến bộ theo finding** (thay D11.2, mở rộng D14.10). Finding mang id `F<n>` cố định qua các vòng, script giữ `<bước>/findings.json`. Reviewer ghi `PRIOR: resolved | open | regressed` cho mọi finding đang mở. `TOP_FIX` liệt kê finding cần sửa: kiểu **đơn** cho `structure` (một finding mỗi vòng), kiểu **lô** cho `param`, `regen`, `repaint` (mọi finding cùng loại). Một vòng có tiến bộ khi ít nhất một finding `blocker`/`major` cũ được giải quyết và số `regressed` ít hơn số `resolved`; từ vòng 2, vòng không tiến bộ → `waiting_human`. Lý do: một finding mỗi vòng × 3 vòng không qua được output có hơn 3 lỗi nặng; reviewer có context mới mỗi lần nên tổng số đếm nhiễu.
2. **Budget Meshy gắn với hash mesh** (thay phần `MESHY_CALLS` của D20.14). ~~`gen_api.py` đọc và ghi `budget.json`, từ chối gọi khi hết lượt~~ **[Sửa theo D24.2: một file budget theo định dạng kit cho mỗi hash mesh; không sửa `gen_api.py`]**; worker không tự khai. Mesh đổi (sau `fix_uv_mesh` hoặc làm lại `model`) → script hỏi anh gọi lại Meshy hay VẼ MỚI. Lý do: sửa mesh làm texture Meshy cũ mất hiệu lực mà đã hết lượt gọi.
3. **`approvals`, `review_board` nằm trong `production/policy.yaml`** (sửa D14.4, D19.1, D20.8). `assemble` luôn human, không có khóa. Hash profile bỏ `paths` và khóa bắt đầu bằng `_`. Lý do: đổi người duyệt không được bật cảnh báo "profile đổi" cho mọi asset đang chạy.
4. **`need_evidence`** chỉ dùng khi không còn finding `blocker`/`major` đang mở. Ảnh ghi vào `vN/review/evidence-<k>/`, không tạo version mới. Lý do: thứ tự khi có cả lỗi nặng và `unclear` chưa rõ; version rỗng làm nhiễu "bản tốt nhất".
5. **Script làm việc trạng thái** (thay phần "Producer đánh dấu" của D2, sửa D10): `inputs` mỗi version và suy ra version cũ; `PROFILE_HASH` sinh trong brief, so khi ingest; ~~`texture-log.jsonl` ghi khi duyệt bước texture~~ **[Thay bằng D22.17: `P texture-stats` tổng hợp khi cần]**; `check_profile.py` chạy khi intake và sinh brief, agent không chạy lại. Agent không ghi ra ngoài thư mục version.
6. **`assemble` không có reviewer** (sửa D14.3, thay D20.4). Gate mới `checks_human`: ~~`check_assemble.py` pass → anh duyệt (DUYỆT 2)~~ **[Sửa theo D22.11: script `assemble.py` pass → anh duyệt; fail → `blocked`]**. Anh bấm Cần sửa thì chọn bước `texture` hoặc `model`; feedback mở đợt mới theo D11.4. ~~Model của `assemble` vẫn theo D16.~~ **[D22.11: không còn agent]** Lý do: texture đã được chấm trên model ở bước `texture`; `assemble` toàn việc xác định.
7. **Pilot trước, lô sau.** `pilot_asset: null` → `intake --all` từ chối, chỉ đăng ký từng asset khi không có asset khác đang chạy. Các phép so với pilot ghi `not_checked`.
8. **`approvals set model reviewer` cần `--confirm-spend`**, vì bước sau tiêu credit Meshy.
9. **`[limits]`** trong `pipeline.toml` (`blender`, `codex_image`, `meshy`) và `uses` theo bước; `P next` chờ slot. Mỗi runtime có `[limits]` riêng.
10. **So A/B Claude Code với Codex** (mở rộng D6.4, giữ thứ tự làm của D6.4). Một lõi chung, hai adapter. Thư mục làm việc và kết quả riêng cho mỗi runtime (`production-claude/`, `production-codex/`). Chạy lệch giờ. Chỉ 2–3 asset pilot, vì credit Meshy nhân đôi. Duyệt mù trên trang so cặp `P ab board`; `P compare` tổng hợp số vòng sửa, tỉ lệ duyệt ngay lần đầu, số lần chuyển lên anh, thời gian, chi phí, tỉ lệ pass script, số lần reviewer chấm lệch so với anh. Kết luận gộp runtime và model đi kèm.
11. **Một phiên bản `model-viewer`** (3.5.0) cho cả trang local và trang claude.ai.

## D22 — Sửa sau review spec lần 3: lỗ hổng, chỗ thừa, thứ tự code (2026-11-09)

Nguồn: review lần 3, ba câu trả lời của anh (agent chỉ chạy qua Producer; bộ view chỉ pipeline đọc; README gói cuối do script ghép).

1. **Finding lưu theo version** (`<bước>/vN/findings.json`). Vòng sửa lấy danh sách của bản gốc (bản tốt nhất). Khi anh `redo`, finding còn mở được chép sang đợt mới, cộng finding của anh. Lý do: một file chung cho cả bước sai khi vòng sửa quay về bản cũ.
2. **Không di chuyển version bị loại** (thay D14.9). Đánh dấu `rejected` trong status; **[Thay bằng D29]** ~~`cleanup` xóa `work/` của chúng khi asset xong~~. Lý do: brief, `inputs`, ảnh khoanh, evidence, `ab/mapping.json` đều trỏ tới đường dẫn version. Bớt code.
3. **Concept brief = `asset-card.yaml`.** Không có file brief riêng. Sửa `out-of-scope-changes.md` theo `_approved/<id>/` và `<id>.layout.md`; quy ước tỉ lệ chung nằm trong `scale_refs` của profile.
4. **`regen_front`** ở `views_rest`: front sai so với bộ → `redo --step views_front`. Lý do: trước đây không có đường quay lại.
5. **Vòng evidence không được sửa `final/`.** Script so hash trước và sau. Vòng này không tính vào `resume_rounds`.
6. **Contract reviewer:** mỗi key `unclear` phải có finding; tin nhắn trả về Producer chỉ gồm `VERDICT` và `COUNTS`. **[Thêm ngoại lệ theo D27.5: lệnh ghi file report bị chặn thì agent trả cả report giữa dòng `--- report ---` và dòng `--- end ---`]**
7. **Test D1** (quy tắc chung của 4 reviewer) cập nhật theo contract mới: finding có id, `PRIOR`, `TOP_FIX` kiểu đơn và lô.
8. **Quyết định không ghi trùng** theo bộ (asset, bước, version), dù bấm ở trang local hay remote. Phiên mới với `local+remote`: Producer kéo dữ liệu remote về trước `P next`.
9. **Spec agent viết trung lập với runtime.** Adapter ghi cách quy đổi `opus`, `sonnet`, `haiku` sang model thật; ledger ghi model thật đã dùng.
10. **A/B: mỗi runtime so với pilot trong `deliver` của chính nó.**
11. **`assemble` bằng script `assemble.py`, không có agent** (sửa D14.2, D20.13, D21.6). Gắn texture, xuất GLB, QA của kit, render một bộ nhỏ từ GLB và so pixel với render của bước `texture`, ghép gói cuối và README từ report các bước. Pass → DUYỆT 2; fail → `blocked`. Bộ render có texture và `final_lit_vs_concept.png` chuyển sang bước `texture`. Lý do: không việc nào cần phán đoán; bớt một subagent mỗi asset; so pixel GLB giữ được việc bắt lỗi khi xuất.
12. **Chỉ script kiểm hash đầu vào**, khi sinh brief và khi ingest. `check_inputs.py` của agent chỉ kiểm file tồn tại. Lý do: agent chỉ chạy qua Producer (anh xác nhận); skill độc lập sau này sẽ viết riêng. Code agent tách lớp tool (`tools/`) khỏi lớp contract để skill độc lập dùng lại tool.
13. **`sources.json` là nguồn duy nhất cho số hình học** sau khi blockout được duyệt. Profile, preset, thẻ chỉ dùng cho thông số không phải hình học.
14. **Concept Views bớt chép và bớt chấm lại:** README bộ view còn 4 mục (NGOẠI LỆ, TEXTURE NOTE, lật ảnh, trạng thái) và một dòng trỏ sang `blockout.md`; bỏ bước chép front sang `views_rest`; review lần 2 chỉ chấm 4 view mới và độ đồng bộ, không chấm lại front.
15. **Một renderer** (file JS của Review Board) cho `P serve`, trang remote, `P show`, `--bundle`, `P ab board`.
16. **Rubric theo loại chỉ chứa tiêu chí pass/fail kèm tham chiếu tài liệu AD.** Mô tả style chỉ nằm trong `art-direction/`.
17. **Bỏ `P explain` và `texture-log.jsonl`** (đề xuất kèm D21). Câu "vì sao" trả lời bằng lý do và finding trên trang duyệt; thống kê texture dùng `P texture-stats` lúc cần.
18. **Thứ tự code theo lát dọc 6 giai đoạn** (`docs/producer.md` §18). GĐ 1 kiểm phần rủi ro nhất: reviewer ghi đủ `PRIOR`, vòng sửa theo finding hội tụ.

## D23 — Duyệt 3 đề xuất còn mở và đổi tên agent (2026-11-09)

1. **Duyệt 3 đề xuất kèm D21, D22:** vùng anh khoanh trên Review Board thành finding `H<n>` (review-board §4); nút "Bản nào tốt hơn" trên trang so cặp A/B (review-board §8); hash concept theo nội dung file (producer §11).
2. **Agent đặt tên theo bước pipeline** (sửa D6.5). Lý do: tên theo vai trò trùng với skill của kit (`zps-concept-views`, `zps-3d-artist`, `zps-texture-artist`), anh gọi "ZPS - 3D Artist" thì Claude có thể chọn nhầm. Tên mới:

   | Cũ | Mới | Tên hiển thị |
   |---|---|---|
   | `zps-3dp-blockout` | `zps-3dp-step-blockout` | 3DP Step · Blockout |
   | `zps-3dp-concept-views` | `zps-3dp-step-views` | 3DP Step · Views |
   | `zps-3dp-3d-artist` | `zps-3dp-step-model` | 3DP Step · Model |
   | `zps-3dp-texture-artist` | `zps-3dp-step-texture` | 3DP Step · Texture |
   | `zps-3dp-review-blockout`, `-views`, `-clay`, `-texture` | `zps-3dp-check-blockout`, `-views`, `-clay`, `-texture` | 3DP Check · … |

   `zps-3dp-producer` và `zps-3dp-project-setup` giữ tên. Description của mọi agent bước và kiểm mở đầu bằng câu cố định "Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. Không dùng khi người dùng gọi trực tiếp." Các quyết định cũ (D1–D22) giữ tên cũ để đúng lịch sử; spec và checklist dùng tên mới.
3. **Skill Project Setup chỉ gọi tường minh** (`disable-model-invocation: true`), vì không bao giờ cần tự kích hoạt. Cần kiểm trường này trên bản Claude Code đang dùng (coding-checklist dòng 82).

## D24 — Sửa sau khi đọc code kit v0.10.4 (`905dc93`), và key Meshy của project (2026-11-09)

Nguồn: đọc `src/zps-3d-artist/tools`, `src/zps-concept-views/scripts`, `build.py`, `editions/` của kit. Đọc code, chưa chạy.

1. **Primitive của blockout đúng tập kit nhận:** `box | wedge | cylinder | custom` (spec cũ ghi "prism", kit không có). `rotation_deg` chỉ 0, 90, 180, 270. Mái dốc dùng `wedge` hoặc `custom`. `check_schema.py` kiểm.
2. **Gọi Meshy qua wrapper `meshy_call.py`, không sửa `gen_api.py`** (sửa D20.14, D21.2). Kit trừ budget *trước* khi gọi, vì lời gọi trả phí mà thất bại vẫn có thể đã tốn credit. Lỗi trước khi task được tạo → wrapper hoàn budget, thử lại. Lỗi sau khi task đã tạo (hết thời gian chờ) → chờ tiếp đúng `task_id`, không tạo task mới, vì gọi lại là trả tiền thêm một lần. Budget theo hash mesh = một file `budget-<mesh_hash>.json` đúng định dạng kit (`max_credits`, `used_credits`).
3. **Key Meshy lấy từ `.env` trong thư mục project** (anh yêu cầu). Profile có `paths.env_file` (mặc định `.env`; nằm trong `paths` nên không làm đổi hash profile). Wrapper đặt `ZPS_ART_ENV_FILE` cho tiến trình con và xóa `MESHY_API_KEY` khỏi môi trường con, để key của project luôn được dùng. Agent không đọc `.env`; brief không chứa key. `P init` thêm `.env` vào `.gitignore`. Có `env_file` mà thiếu key → `blocked` trước bước `texture`.
4. **Tận dụng tool của kit:** `assemble.py` dùng `finalize.py` làm cổng (kết quả QA gắn với sha256 của GLB, thiếu `mesh_check` hoặc có fail thì từ chối) và `export_check` với `expect_unlit`. Unwrap dùng `xatlas_unwrap()` trong `bake.py`, gọi từ script mỏng `unwrap.py` chạy trong Blender.
5. **Cấu trúc hai bản chép từ kit** (cụ thể hóa D6.4): `build.py`, `editions/{claude,codex}/edition.json`, `adapter.md`, `tests/`. Bản Codex thêm hậu tố `-codex` vào tên (như `skill_suffix` của kit). Description ≤ 300 ký tự (Codex rút gọn dài hơn), câu chặn gọi nhầm của D23.2 đứng đầu.
6. **Không đặt `mesh.max_duplicate_verts`**: `mesh_check` của kit chỉ báo đỉnh trùng ở mức info, nên join không weld không fail.
7. Hash nội bộ của kit (`code_hash` trong `gates.py`, `render_views.py`; sha256 trong `finalize.py`) là kiểm tươi trong một bước, không trùng với kiểm đầu vào giữa các bước của script Producer. D22.12 giữ nguyên.

## D25 — Mang các điểm hay của kit vào spec (2026-11-09)

Nguồn: `art-operation.md`, `art-quality.md`, `issue-fields.json`, `review.md`, `3d-critic.md`, skill Art Learning, `evals/triggers.json`, `preflight.py`, `estimate.py`, `installer/codex_rules.py`, `gen-craft.md` của kit `905dc93`.

- **A. Finding dùng bộ trường của kit và AD** (mở rộng D21.1): `region`, `viewing_condition`, `evidence`, `consequence`, `confidence`, `repair`, `preserve`, `acceptance`. `resolved` chỉ khi chứng minh được `acceptance`. Thêm trạng thái `superseded` (yêu cầu đổi) và mức `preference` (khẩu vị, không chặn PASS). Lý do: `PRIOR` khách quan hơn, ít thụt lùi hơn, và finding của reviewer, của anh, của AD cùng một format.
- **B. Quy tắc chung của reviewer theo `3d-critic.md`** (bổ sung D1): ảnh cùng góc của bản trước ở vòng sửa; `EVIDENCE_OPENED`; câu cảnh báo xu hướng duyệt dễ; không tự đo; chỉ chấm trong phạm vi bước. Test D1 kiểm.
- **C. `P preflight`** mỗi phiên, gọi `preflight.py` của kit, thêm codex CLI, key Meshy, Blender. Tính năng tắt thì không giao bước cần nó.
- **D. Blender trong bản Codex chạy ngoài sandbox bằng allow-list** (cụ thể hóa D6.4), theo `codex_rules.py` của kit. Lý do: trên macOS Blender crash trong sandbox.
- **E. Eval kích hoạt** cho mọi skill và agent, có câu âm trùng kit. Build chạy. Thay việc kiểm tay ở checklist dòng 81.
- **F. Kiểm kê phần tử và bảng lỗi ảnh AI** cho check-views và check-texture.
- **G. Thứ tự ưu tiên khi nguồn mâu thuẫn:** feedback của anh, brief > art direction > spec, profile, thẻ, `sources.json` > tài liệu agent, reference kit > mặc định. Gặp mâu thuẫn thì ghi cả hai nguồn và lựa chọn.
- **H. Đổi nhánh không đặt lại bộ đếm; bản gửi anh khi chưa qua mang nhãn "chưa đạt".**
- **I. Ước lượng thời gian, credit và báo giá Meshy cả lô** lúc `intake`, dùng `estimate.py` của kit; ghi log mỗi asset.
- **J. Nguyên tắc Art Learning cho `P compare` và D16.3:** đếm theo asset; ghi cả lần thử bị loại; im lặng không phải duyệt.

## D26 — Mang ý từ paper và repo ngoài vào (2026-11-09)

Nguồn: GPTEval3D (CVPR 2024, 3DTopia/GPTEval3D), BlenderAlchemy (ECCV 2024), Procedura (arXiv 2608.26238, SpatiaOS/Procedura), 3DCodeBench (arXiv 2606.01057), skill chính thức meshy-dev/meshy-3d-agent. Đã xem và không lấy: Blender MCP/ViSculpt (điều khiển Blender đang mở, không hợp chạy nền), LL3M (reviewer khác họ model, không làm được trong một runtime), Planner–Actor–Critic (trùng thiết kế hiện tại).

1. **So theo cặp** (GPTEval3D). Reviewer vòng sửa ghi `COMPARE` (tốt hơn / như cũ / xấu hơn) so với bản gốc cho từng finding trong `TOP_FIX` vòng trước; `PRIOR` phải nhất quán với `COMPARE`. `P compare` so cặp A/B hỏi hai lần đổi thứ tự, tính Elo trên lô pilot, đặt cạnh lựa chọn của anh. check-texture thêm tiêu chí texture khớp hình học.
2. **Phương án cho lỗi `param`** (BlenderAlchemy). Worker dựng 2–3 giá trị, render cùng góc; reviewer chọn bằng `PICK`; vẫn tính một vòng. Không áp cho `structure` và bước gen ảnh.
3. **Kiểm liên thông part graph** (Procedura): mọi part nối về gốc qua chuỗi `attach`; `check_schema.py` kiểm.
4. **Brief vòng sửa kèm file JSON gate/check fail** (3DCodeBench: phản hồi thực thi xác định là yếu tố chính giúp vòng sửa hội tụ). **[Mở rộng theo D31.3: check fail trả thẳng về worker, không gọi reviewer]**
5. **Meshy:** giá mặc định retexture 10 credit; so payload của `gen_api.py` với `reference.md` của skill Meshy chính thức trước lần gọi thật đầu tiên. Skill chính thức cũng chỉ đọc key từ `.env` ở thư mục làm việc, khớp D24.3.

## D27 — Sửa sau Run 4 (wooden-chest, 6 bước, 2h51m, ~3,4M token) và các mục còn chờ (2026-11-09, chốt 2026-11-10)

Nguồn: `RUN4-REPORT.md`; câu hỏi của anh về việc ai gọi reviewer; guideline Concept Artist (`GUIDELINE-concept-artist.md`).

1. **Bản tốt nhất khi hòa** (sửa D11.3): ít `blocker` + `major` đang mở nhất. Hòa thì chọn version giải quyết được nhiều `blocker` + `major` hơn. Vẫn hòa thì chọn version cũ hơn. Code: `bf10d36`. **[Sửa theo D30.2: thêm một bậc hòa, và bậc cuối chọn version mới hơn]**
2. **`P ingest` in luôn lệnh giao việc tiếp theo.** Producer giao trong cùng lượt. **[Mở rộng theo D30.5: mọi lần chuyển state]**
3. **Giữ Producer gọi reviewer, không để worker tự gọi.** Lý do: reviewer độc lập (worker không chọn được ảnh và cách đặt vấn đề); vòng sửa nằm trong script (trần vòng, finding, bản tốt nhất, chuyển lên anh); giữ D1 và D21.5. Phần chậm hơn ước lượng dưới 5% thời gian bước. Ledger ghi thời gian và token theo vai trò (worker, reviewer, script, khoảng chờ Producer). `P stats` in bảng. Producer truyền token và thời lượng của subagent vào `P ingest` qua tham số mới. Runtime không báo số thì ledger ghi "không có số", không ghi 0. Nếu chờ Producer > 15% thời gian bước thì xem lại.
4. **Mục "Hiện hành" của `feedback.md`:** mỗi lần anh `redo`, script thêm dòng redo vào "Hiện hành" (văn bản nhiều dòng nối thành một dòng). Khi bước đó được duyệt, script xóa các dòng redo của bước khỏi "Hiện hành". Ghi chú chỉ vào Log. Reviewer không báo "Hiện hành trống". Code: `dfba2eb`, `c7a904e`.
5. **Agent tự ghi file report.** Reviewer và worker ghi report vào đúng đường dẫn trong brief. Lệnh ghi bị chặn thì agent trả cả report giữa dòng `--- report ---` và dòng `--- end ---`, và Producer lưu file. Đây là đường dự phòng, phải hiếm. Script ghi mỗi lần dự phòng vào ledger: sự kiện `report_fallback`, kèm vai trò và bước. Settings thêm rule allow cho lệnh ghi dưới `production/`, để bớt lần bị chặn. D22.6 giữ nguyên: tin nhắn trả về chỉ gồm `VERDICT` và `COUNTS`; ngoại lệ duy nhất là đường dự phòng. File agent của 4 reviewer ghi hai quy tắc contract: finding loại `note` luôn `minor`; trích dẫn trong `PRIOR` dùng đúng nguyên văn nhãn ở `EVIDENCE_OPENED`. Code `170aadc` bắt reviewer luôn trả report bằng chữ: phải đổi theo mục này. Hai quy tắc contract và cách đọc phần giữa hai dòng đánh dấu (`170aadc`, `39c8ebf`) giữ lại. **[Sửa: nguyên nhân gốc]** Quyền ghi không phải nguyên nhân gốc. Harness Claude Code chặn lệnh Write của subagent khi tên file khớp `^(report|summary|findings|analysis).*\.md$`, không phân biệt hoa thường. Lỗi in ra là "Subagents should return findings as text" (https://github.com/anthropics/claude-code/issues/44657). Tên cũ `report-worker.md`, `report-review.md` và `report.md` của A/B khớp mẫu này, nên mọi lần ghi của worker và reviewer bị chặn. Tên mới `worker-out.md`, `review-out.md`, `judge-out.md` không khớp mẫu, nên sửa được lỗi. Mọi file brief giao cho subagent ghi không được có tên khớp mẫu này. Đường dự phòng bằng tin nhắn và sự kiện `report_fallback` giữ lại cho lần bị chặn hiếm. Lệnh ghi bị chặn thì agent không ghi vòng qua Bash (`cat`, heredoc, `tee`, python): agent dùng đường dự phòng.
6. **Thẻ asset và ảnh concept** (guideline Concept Artist): thêm trường `view` (`front | 34 | game_camera`); `hidden_sides` bắt buộc đủ 4 mặt, chưa biết ghi "chưa biết"; hai ảnh concept trùng khung, nền phẳng một màu, cạnh dài ≥ 1024 px. `check_card.py` kiểm.
7. **`assemble.py` chỉ chạy từ gốc project.** Thư mục đang đứng không có `production/assets/<id>/status.json` thì script thoát mã 2 và không ghi gì. Code: `9711540`. **[Mở rộng theo D30.12: mọi tool ghi file]**
8. **"Việc còn mở" của README** chỉ lấy finding còn mở của version được duyệt. Worker bước sau ghi `RESOLVED_NOTES: <mục>` khi đã làm một ghi chú của bước trước. Reviewer của bước đó xác nhận các mục này trong report. README chỉ bỏ mục đã được reviewer xác nhận. Code hiện tại (`1620c40`) mới làm một trường hợp: bỏ finding `note_texture` khi review texture đã duyệt có `texture_note=pass`.
9. **Đo bóng bỏ mặt khe rãnh.** `light.shaded_share` bỏ các mặt nằm trong khe rãnh và hốc lõm. `tex_measure.py` nhận ra các mặt này bằng phép thử che tia. Không lọc nét mực theo màu. Không có cờ `style.line_art`. Code: `852e217`.
10. **Bevel chỉ đọc từ trường riêng:** `bevel` (thẻ), `style.bevel` (profile). Giá trị: `none | toon`. Số đo chỉ nằm trong preset (`toon`: bán kính 9 mm, 2 segment). Tool không suy ra bevel từ ghi chú chữ. `check_card.py` chỉ cảnh báo khi một ghi chú có "bo cạnh" mà trường `bevel` trống. Code hiện tại (`e2ff049`, `a83f9b1`) còn bật bevel theo bảng cụm từ: phải đổi sang chỉ đọc trường.
11. **Hai lỗi review lọt qua:** sai số lượng thành phần so với concept luôn là `regen`; `preserve` phải nêu tên chi tiết cạnh vùng sửa.
12. **Font có dấu tiếng Việt** (Noto Sans, giấy phép OFL) đi kèm skill cho mọi sheet. Code hiện tại (`e78c6a7`) còn chọn font hệ thống: phải đổi sang font đi kèm.
13. **Part `custom` chỉ gọi hàm đã duyệt** (cả hai bản). Skill Producer kèm `custom_lib.py`, chứa `arch_cap` và các hàm `custom` đã dùng ở các lần chạy thật. Một wrapper quanh `check_schema.py` chỉ nhận `fn` có trong `custom_lib.py` và từ chối mọi hàm khác. Không sửa `check_schema.py`. Agent không được thêm hàm vào thư viện. Hàm mới cần anh duyệt rồi mới commit. Hàm đã duyệt thêm: `arch_cap_pointed` (vòm trong nhọn, anh duyệt 2026-11-10, Run 5 model F1). Bản Claude và bản Codex giống nhau, để so A/B. Sau này thư viện chuyển vào kit. Lý do: part `custom` chạy Python do agent viết. Trên Codex, lệnh Blender của `self_build/assembly.py`, `param_fit.py`, `apply_edit.py` vẫn chờ duyệt từng lần, cho tới khi wrapper chạy bên trong lệnh mà rule cho phép (`30e7de2`, `docs/EDITIONS.md`).

## D28 — Model ảnh: ghi vào ledger trước, cấu hình sau (2026-11-10)

Lý do: model ảnh đổi theo thời gian (Images 2.6 ra 4/11/2026). Đổi model không được phải sửa code.

1. **Ledger ghi model ảnh** (v0.7.0). `gen_image_codex.py` ghi model đã yêu cầu và model thực tế đã dùng vào ledger. Mỗi version ghi model ảnh vào `inputs`. Không biết model thực tế thì ghi "không có số".
2. **Để sau:** chọn model ảnh bằng cấu hình (`[image.aliases]`, `[image.<bước>]` trong `pipeline.toml`). Cần kiểm trước: `codex exec` có cho chọn model ảnh không.

## D29 — Dọn dung lượng khi DUYỆT 2 (2026-11-10, thay phần `cleanup` của D22.2)

Lý do: agent sinh rất nhiều file trung gian. Sau khi anh duyệt kết quả cuối, không còn lý do giữ.

1. **Trước DUYỆT 2: giữ hết**, để anh so các bản khi duyệt.
2. **Chỉ DUYỆT 2 do anh duyệt (`by: user`) mới mở lệnh xóa.** Producer tự duyệt (test run) thì không xóa. Finding do Producer waive (D30.1) không mở lệnh xóa.
3. **DUYỆT 2 in danh sách xóa và tổng dung lượng sẽ giải phóng.** Không xóa trong cùng phiên đã duyệt.
4. **Xóa ở đầu phiên sau, chỉ khi `source = startup`.** Hook SessionStart gọi `P next --session`; script đọc `source` trong JSON mà hook nhận qua stdin. `resume` và `compact` không xóa. Lý do: hai giá trị này tiếp tục phiên cũ, không phải phiên mới.
5. **`P keep <id>`** hủy lệnh xóa trước lúc đó. **`P purge <id>`** xóa ngay khi anh muốn.
6. **Sau khi xóa chỉ còn:**
   - `deliver/<id>/` (GLB, albedo, `.blend`, ảnh review, README).
   - Hồ sơ text: `status.json`, ledger, findings, report, feedback.
   - File nguồn dạng text của từng bước: `part_graph.json`, `sources.json`, `spec.json`, `texture_spec.json` (vài KB, để sửa lại không phải làm từ đầu).
7. **Mọi thứ khác xóa thật**, không chuyển vào Thùng rác: version bị loại, version được duyệt của bước giữa, phương án `param` không chọn, ảnh evidence, ảnh gen không dùng, `work/`, `.blend` trung gian, file tải Meshy.
8. **Script ghi manifest** những gì đã xóa và dung lượng. Đường dẫn trong ledger và trang duyệt không gãy: giữ report, findings, ảnh thu nhỏ.
9. **`--zip`** nén phần sắp xóa ra chỗ khác, khi anh muốn giữ.
10. **`P disk`** in dung lượng theo asset, bước, loại file. `P next` cảnh báo khi `production/` vượt `disk_warn_gb` của `policy.yaml`.
11. Áp cho cả hai thư mục khi chạy A/B.
12. Thay `P cleanup` của D22.2 (chỉ xóa `work/` của version bị loại, phải gọi tay).

## D30 — Sửa sau Run 5 (wooden-chest) (2026-11-10)

Nguồn: Run 5, `NEXT-VERSION-BACKLOG.md` mục 4d, `docs/intents/v0.7.0-plan.md`.

1. **`P waive <id> F<n> "lý do"`.** Anh chấp nhận một finding là ngoại lệ ở mọi state, kể cả đang FIX. Finding chuyển `waived`. Brief sau bỏ qua finding đó. Reviewer không mở lại finding đó. Ledger ghi ai waive và lý do. Mặc định `by: user`. `--by producer` chỉ chạy khi `policy.yaml` có `test_mode: true`; không có cờ thì script từ chối, state không đổi. Sheet DUYỆT 2 có mục riêng "Producer đã waive"; finding anh waive vào mục Ngoại lệ. Waive finding chặn cuối của bản đang sửa, đang đưa duyệt hoặc đang xin bằng chứng → reviewer `full` chấm lại chính bản đó, không gọi worker, không tính vào `max_fix_rounds`. Waive khi reviewer đang chấm: áp dụng ở lần `ingest` tới. Anh bật `test_mode` bằng `P approvals set test_mode true --by "<nguyên văn>"` hoặc sửa `policy.yaml` (`P rule` chỉ ghi ruling, không ghi `policy.yaml`). Lý do (Run 5): F2 model mất 4 version vì không có đường này; `feedback --action approve` chỉ chạy khi `waiting_human`.
2. **Quy tắc hòa của bản tốt nhất** (sửa D27.1). Theo thứ tự: ít `blocker` + `major` đang mở nhất → giải quyết nhiều `blocker` + `major` hơn → giải quyết nhiều finding hơn ở mọi mức và không có `regressed` → version mới hơn. Lý do (Run 5): brief model v3 chọn v1, dù v2 = v1 + F3 đã sửa.
3. **Meshy: albedo lấy từ `texture_urls[].base_color`.** API retexture không có tham số tắt chuẩn hóa GLB (scale ×2, dời tâm z). GLB Meshy chỉ dùng để so topology với mesh đã khóa. So số tam giác. So tập hợp bộ ba UV của tam giác: mỗi bộ ba sắp xếp, cả tập sắp xếp, so có dung sai. Không so theo thứ tự tam giác. Không phụ thuộc scale và vị trí. Kích thước ảnh `base_color` phải bằng `texture_res`. Lệch một điều trên thì fail. Bỏ khớp bbox và ngưỡng 1e-5. Worker không tự viết script cho việc này. Test dùng GLB Meshy thật của Run 5.
4. **`ingest` bỏ qua `COMPARE` cho id ngoài `TOP_FIX`** và ghi cảnh báo vào ledger, không báo lỗi. Producer không bao giờ sửa report của reviewer hay worker. Report sai contract thì giao lại cho chính agent đó.
5. **Mọi lần chuyển state in JSON giao việc tiếp theo** (mở rộng D27.2): gồm `feedback --action approve|redo`, `waive`, `retry`.
6. **`counts` trong thẻ asset.** Trường tùy chọn, chỉ có 6 khóa: `body_board_rows`, `lid_board_rows`, `doors`, `windows`, `pillars`, `steps`. Mỗi khóa ánh xạ tới một param có tên trong `fixed_params` của part graph (ví dụ `body_board_rows` ↔ `planks`). Lý do: số hàng ván là tham số hàm, không phải số part. Bảng ánh xạ nằm trong config theo loại asset, không viết cứng trong code. Gate blockout và model so hai số; sai thì fail. Khóa chưa có ánh xạ thì `check_card` cảnh báo, không fail. Lý do: lỗi đếm đã lọt hai lần (Run 4 view, Run 5 blockout).
7. **Installer gộp `settings.snippet.json`** vào settings của project: allow rule (Blender, `meshy_call`, `codex exec`, ghi `production/`) và hook SessionStart chạy `P next`. Không ghi đè rule có sẵn. In diff trước khi ghi. Chạy hai lần không nhân đôi. `P preflight` báo khi chưa có.
8. **Lời giao việc chỉ gồm file role và brief.** Lời giao việc không bao giờ gợi ý ghi file bằng shell (heredoc, `cat >`, `tee`, python). Worker ghi `worker-out.md` bằng Write. Mẫu brief đã đúng; lỗi Run 5 nằm ở lời giao việc.
9. **Hàm `custom` được duyệt vào repo ngay**, kèm test. Không để mỗi run giữ một bản thư viện riêng. `arch_cap_pointed` đã vào `custom_lib.py` (`26549c6`).
10. **Token của Producer trong `P stats`.** Hook SessionStart ghi đường dẫn transcript vào `production/session.json`. Script đọc `usage` trong transcript JSONL của phiên chính, bỏ dòng `isSidechain`. Parse chịu lỗi: không đọc được thì ghi "không có số". Bản Codex ghi "chưa hỗ trợ".
11. **Meshy SỬA là chế độ texture mặc định** (sửa D10). Có key Meshy và budget → Meshy SỬA. Không có key, hoặc anh chỉ định → VẼ MỚI. Giữ budget gate. Ledger ghi chế độ đã chọn và lý do. Lý do (Run 5): Meshy SỬA 15m32s, 2 version, 10 credit; VẼ MỚI ở Run 4: 38m25s, 4 version. Mới có 1 mẫu; đo lại sau 3–5 asset.
12. **Mọi tool ghi file từ chối chạy ngoài project root** (mở rộng D27.7). Một helper `require_root()` dùng chung. Thư mục đang đứng sai thì tool thoát mã lỗi và không tạo file nào. Lý do (Run 5): một check của bước texture ghi `production/` vào gốc repo vì chạy từ sai cwd.
13. **`.env` chỉ trỏ đường dẫn.** Guideline và `setup.md` chỉ nêu đường dẫn `.env`. Không bao giờ đính kèm file `.env` vào chat. Lý do (Run 5): file `.env` đính kèm làm lộ mọi key trong đó.
14. **Version lên 0.7.0**, để bản cài V6 khác tên với v0.6.0.
15. **Cách làm v0.7.0:** worktree `./.worktrees/feat-v0.7.0`, chạy toàn bộ test, merge fast-forward vào `main`.

## D31 — Giảm chi phí review (2026-11-10)

Lý do: Run 5 reviewer tốn 1,33M token, worker 1,04M.

1. **R1 — Sheet review.** `review_sheet.py` ghép các góc của bước thành một ảnh PNG, cạnh dài khoảng 2048 px, có nhãn tên ảnh. Brief reviewer chỉ đưa sheet và concept. Reviewer cần ảnh lẻ thì xin qua `need_evidence` (crop hoặc ảnh gốc). Áp cho `blockout`, `model`, `texture`. Bước views dùng `views_sheet.py` sẵn có.
2. **R2 — Phạm vi chấm theo loại vòng.** Brief reviewer có `REVIEW_SCOPE: full | fix`.
   - `full`: lần review đầu, và bản mà worker báo `DONE` với mọi finding đang mở đều có trong `FIXED` (bản sắp PASS).
   - `fix`: các vòng còn lại. Reviewer chỉ chấm id trong `TOP_FIX` (kèm `COMPARE`), các vùng `preserve`, và một lượt nhìn nhanh toàn sheet để bắt lỗi mới. Mục rubric không chấm ghi `not_checked`.
   - **Chỉ PASS khi lần review gần nhất là `full`.** Vòng `fix` hết lỗi mở, hoặc anh vừa waive finding cuối → script giao thêm một reviewer `full` trên chính version đó, không gọi worker.
3. **R3 — Check fail trả thẳng về worker.** Worker xong mà có JSON `fail` hoặc `error` trong `final/review/{gates,checks}/` → vòng sửa của worker luôn, không gọi reviewer. Brief vòng đó kèm danh sách JSON fail. Vòng trả thẳng tính vào `max_fix_rounds`. Hết vòng → `waiting_human`.
   - Lối ra: worker ghi `ACCEPTED_FAIL: <file> — <lý do có số>` trong `worker-out.md` và mục NGOẠI LỆ của README. Asset sang reviewer; reviewer chấm lý do đó.
   - Chỉ check có `acceptable: true` trong config mới được khai `ACCEPTED_FAIL`.
   - Gate cứng không bao giờ được khai: hash, schema, `export_check`, topology Meshy (D30.3). Khai cho gate cứng → script từ chối, vẫn là vòng sửa.
   - Ledger đếm mỗi lần khai, theo bước và theo check.
4. **R4 — `P stats` tách theo loại vòng.** Thời gian và token reviewer tách thành: vòng đầu, vòng sửa, vòng chấm cuối (`full`).
5. **Để sau pilot:** hạ check-views, check-blockout xuống Sonnet khi ledger cho thấy reviewer chấm khớp với anh (D16.3).
6. **Để sau V6:** bỏ reviewer ở bước có gate người duyệt ngay sau, nếu V6 xác nhận `views: none` dùng được cho phần lớn asset.
7. **Không làm:** resume cùng một reviewer qua nhiều vòng. Lý do: reviewer bị neo vào nhận xét cũ, mất tính độc lập.

## D32 — Trường `views` trong thẻ asset (2026-11-10, thay ý "bỏ view top")

Một trường duy nhất: `views: none | back | full | full_top`. Không thêm `views_top`. Trường này khác trường `view` của D27.6 (góc của ảnh concept).

1. **`none`:** không có bước views. Mặt khuất lấy từ `hidden_sides` và blockout. TEXTURE NOTE và NGOẠI LỆ lấy từ `real_texture_only_notes` của thẻ và file material. Brief model và brief texture chạy được khi không có bộ view. check-clay bỏ tiêu chí so với view.
2. **`back`:** chỉ gen back. Bước `views_front` vẫn chạy, vì front là tham chiếu màu.
3. **`full`:** back và left; right lật từ left khi đối xứng. Không có top.
4. **`full_top`:** `full` cộng top. Chỉ dùng khi mái có thiết kế riêng, không suy ra được từ concept.
5. **Lý do bỏ top:** không bước nào sau views cần ảnh top. Hình mái do blockout quyết. Màu mái thấy trên concept 3/4. VẼ MỚI tự gen paint view. Meshy không dùng top.
6. Giá trị lạ → `check_card` fail. V6 chọn giá trị mặc định.

## Chưa chốt
- Skill MapLayout (mới) và việc sửa Concept Artist (Material Handoff, `asset-card.yaml`, ghi chú real/texture_only, phần khuất). Ngoài scope, xem `out-of-scope-changes.md`.
- Gom rubric của 4 reviewer thành file agent khi viết code (rubric đã nằm trong spec từng agent).
- Texture Artist có dùng chung cho nhóm nhân vật ở version sau không.
- **Cần chạy thử mới biết** (ghi trong `coding-checklist.md`): reviewer ghi đủ `PRIOR`; Claude Code nhận model và resume theo từng lần giao; `codex exec` lồng trong phiên Codex; Meshy giữ UV và số tam giác; runtime báo token theo model.
- Đã đọc code kit v0.10.4 (D24). Các dòng checklist trả lời bằng đọc code vẫn phải chạy thật mới đánh dấu xong.

## Đã đóng (ghi lại cho rõ)

- 3D Artist 5 điểm và runtime: đã chốt ở D7, D6.4.
- Màu nền gen view (C3): `style.view_bg` trong profile; không ghi thì `pick_bg.py` chọn (concept-views.md §3).
- Thư mục `upstream/`: giữ bản chép để đọc, không đưa vào git (`.gitignore`); tạo lại từ remote `assets-kit`, commit `905dc93`.
