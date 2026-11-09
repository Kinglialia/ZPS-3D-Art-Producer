# Việc phải kiểm khi viết code

Mỗi dòng là một điều chưa xác nhận bằng chạy thật. Khi viết code, kiểm từng dòng và ghi kết quả vào cột "Kết quả". Không đánh dấu xong nếu chưa chạy.

| # | Agent | Việc cần kiểm | Nguồn | Kết quả |
|---|---|---|---|---|
| 1 | Blockout | `graph.py` của kit bỏ qua field lạ (`role`, `tag`), không báo lỗi | blockout.md §10 | |
| 2 | Blockout | `gates.py` đọc khóa config `contact_dist_m`, `contact_samples`, `inset_depth_tolerance`. `config.yaml` dùng đúng tên này | blockout.md §10 | |
| 3 | Blockout | `bootstrap.py` tìm thư viện ở `agents/zps-3dp-step-blockout/tools/.deps/blender-py<ver>`. Chạy `setup_deps.sh` trước các script chạy trong Blender | blockout.md §10 | |
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
| 20 | Mọi agent | **[Sửa theo D21.1]** Tiến bộ đo theo finding có id: reviewer ghi `PRIOR` cho mọi finding đang mở; vòng không giải quyết được finding `blocker`/`major` cũ nào → `waiting_human` từ vòng 2; bản tốt nhất (D11.3) | D11, D21.1 | |
| 21 | Project Setup | `check_profile.py` báo đúng khi thiếu trường bắt buộc, sai kiểu, hoặc preset không tồn tại; thiếu `has_map` cũng là thiếu trường bắt buộc; có `approvals` hay `review_board` trong profile là lỗi (D21.3); script không sinh brief khi profile không hợp lệ (D21.5) | project-profile.md §5 | |
| 22 | Mọi agent | Đọc thông số đúng thứ tự mặc định → preset → profile → thẻ asset; **[Sửa theo D21.3, D21.5]** chép `PROFILE_HASH` từ brief vào báo cáo, không tự tính | project-profile.md §1, §3 | |
| 23 | Producer | Resume worker cũ trên Codex qua `collaboration.send_message` / `followup_task`: worker còn context, không đọc lại file | D14.1, producer.md §16 | |
| 24 | Producer | Gate `review_human`: reviewer PASS → `waiting_human`; `approvals: reviewer` tự duyệt khi không còn `major`/`unclear`; **[Sửa theo D21.6]** `assemble` dùng gate `checks_human` | producer.md §3–4 | |
| 25 | Producer | Contract reviewer mới (`COUNTS`, `TOP_FIX` theo bước) được `ingest` đọc đúng; loại `TOP_FIX` sai bước bị từ chối | producer.md §6 | |
| 26 | Producer | Dừng sớm và bản tốt nhất: brief vòng sửa trỏ tới bản tốt nhất, không phải bản mới nhất | producer.md §7 | |
| 27 | Producer | **[Sửa theo D22.2]** Duyệt một bước: các version khác được đánh dấu `rejected` trong status, thư mục giữ nguyên. Chỉ khi duyệt `assemble` mới chép `final/` sang `deliver/<id>/`; duyệt bước khác không chép gì sang `deliver/`; làm lại sau DUYỆT 2 đánh dấu README | producer.md §8, D20.2, D22.2 | |
| 28 | Producer | `P show --bundle`: một file HTML mở được trên điện thoại, ảnh thu về ≤ 1024 px, dung lượng hợp lý | producer.md §5 | |
| 29 | Producer | `P intake` từ chối asset thiếu file bắt buộc hoặc `asset-card.yaml` sai (`check_card.py`); `type` lấy từ thẻ | producer.md §9 | |
| 30 | Producer | `fix_uv_mesh` chạy `redo --step model`; `meshy_regen` hoặc `UNFIXABLE: yes` đặt `waiting_human` (xem dòng 41) | producer.md §6, D20.14 | |
| 31 | Texture Artist | `tone_fix.py` giảm chênh tông 4 hướng và bóng dưới diềm về trong ngưỡng của `tex_measure.py`, không làm phẳng vân hay vết mòn | D17, texture-artist.md §3 | |
| 32 | Review Board | Lớp phủ toàn màn hình, zoom hai ngón, chạm hai lần, vuốt chuyển ảnh chạy trên iPhone trong Artifact và trên trang local | review-board.md §3 | |
| 33 | Review Board | Khoanh vùng: chế độ Xem/Khoanh không lẫn thao tác; tọa độ theo ảnh gốc đúng sau khi zoom; ảnh khoanh và JSON lưu đúng thư mục | review-board.md §4 | |
| 34 | Review Board | `P board prepare` + đẩy lên + kéo về: Producer không mở ảnh; `P feedback` nhận đường dẫn ảnh khoanh; brief vòng sau có danh sách vùng | review-board.md §6 | |
| 35 | Producer | `has_map: true` mà thiếu `<id>.layout.md` → intake từ chối; `has_map: false` mà thẻ thiếu `size_m` hoặc `size_m` sai dạng `{w, d, h}` → `check_card.py` báo lỗi, intake từ chối; `has_map: false` và có `size_m` → intake nhận, Blockout lấy W×D×H từ `size_m` | producer.md §9, D20.1, D20.9 | |
| 36 | Producer | Brief bước `texture` có mục `ISSUES` chép đúng từ report `model` đã duyệt; trỏ tới `final/` đã duyệt của `blockout`, `model`, `views_rest`; không có file handoff | producer.md §6, D20.3, D20.10 | |
| 37 | Producer | **[Thay bằng D21.6]** ~~`TOP_FIX: repaint` ở `assemble` chạy `redo --step texture`~~ Cần sửa ở `assemble`: trang duyệt hỏi bước (`texture` / `model`); script chạy `redo --step <bước>`; bộ đếm đặt lại theo D11.4 | producer.md §7, D21.6 | |
| 38 | Producer | Hết vòng 3 vẫn FIX: script quay về bản tốt nhất và đặt `waiting_human`; trang duyệt hiện bản đó và finding còn mở | producer.md §7, D20.5 | |
| 39 | Producer | `VERDICT: ESCALATE` đặt `waiting_human` ngay, không chạy thêm vòng; trang duyệt hiện lý do | producer.md §7, D20.5 | |
| 40 | Producer | Vòng `need_evidence` không tính vào 3 vòng; cùng bước xin `need_evidence` lần thứ hai → `waiting_human`; bộ đếm này đặt lại khi anh gửi feedback (`redo`) | producer.md §7, D20.5, D20.15 | |
| 41 | Producer | `TOP_FIX: meshy_regen` hoặc `UNFIXABLE: yes` → script đặt `waiting_human`, không tự cho gọi Meshy lần hai; chỉ sau khi anh duyệt, script tăng `allowed` trong `budget.json` và brief tiếp theo ghi số lần còn được gọi | producer.md §6.3, D20.14, D21.2 | |
| 42 | Producer | Duyệt `model`: script ghi hash `<tên>-untextured.glb` vào `status.json`; **[Sửa theo D22.11]** `assemble.py` fail và đặt `blocked` khi hash lệch | 3d-artist.md §3, D20.7, D22.11 | |
| 43 | Producer | `approvals` trong `policy.yaml` có khóa lạ (ví dụ `views`, `views_front`, `assemble`) → script từ chối; `P approvals set` cũng từ chối | producer.md §4, D20.8, D21.3 | |
| 44 | Producer | Report worker thiếu `PROFILE_HASH` → `ingest` báo lỗi định dạng; hash phải khớp hash script ghi trong brief | producer.md §6.2, D21.5 | |
| 45 | Producer | **[Thay bằng D21.2]** ~~Report Texture Artist thiếu `MESHY_CALLS`…~~ `gen_api.py` từ chối gọi khi `used >= allowed` của hash mesh hiện tại; script đọc `budget.json`, không đọc số worker khai | producer.md §6.3, D21.2 | |
| 46 | Texture Artist | Lỗi kỹ thuật khi gọi Meshy (hết thời gian chờ, lỗi mạng, lỗi API không trừ credit) không tăng `used` trong `budget.json`; thử lại tối đa 3 lần, rồi `STATUS: BLOCKED` | texture-artist.md §2.2, D20.14, D21.2 | |
| 47 | Blockout | `has_map: false`: `sources.json` lấy W×D×H từ `size_m`, `character_h` từ `scale_refs`, `door_h` từ `scale_overrides` hoặc đo trên concept (có ghi cách đo); `files.layout` trỏ tới `asset-card.yaml`; `check_layout.py` so bbox với `size_m` | blockout.md §2, §5, D20.12 | |
| 48 | Review Board | `views_front` và `texture` ở `waiting_human` hiện đúng tóm tắt (`VIEWS.md`, `texture/notes.md`) và lý do gửi anh (từ report reviewer, hoặc report worker khi `BLOCKED` / `UNFIXABLE`) | review-board.md §2, D20.16 | |
| 49 | Producer | Reviewer ghi đủ `PRIOR` cho mọi finding đang mở. Thử trên một asset thật, đo tỉ lệ thiếu dòng; nếu cao, đưa danh sách finding vào brief dưới dạng mẫu điền sẵn | producer.md §6.1, D21.1 | |
| 50 | Producer | `TOP_FIX` kiểu đơn có đúng một id; kiểu lô có đủ mọi finding đang mở cùng loại; sai thì `ingest` báo lỗi | producer.md §6.1, D21.1 | |
| 51 | Blockout | Sửa theo lô loại `param`: `check_fix.py` chạy sau từng finding, không chỉ một lần cuối vòng | blockout.md §3, D21.1 | |
| 52 | Producer | Mesh đổi sau khi đã gọi Meshy: hash mới có entry `allowed: 0`; script đặt `waiting_human` với câu hỏi gọi lại Meshy hay VẼ MỚI | producer.md §6.3, D21.2 | |
| 53 | Producer | Hash profile: chuẩn hóa YAML (sắp xếp khóa, bỏ `paths` và khóa `_`); đổi `_source` hay `paths` không đổi hash; `approvals set` không bật cảnh báo | producer.md §10, D21.3 | |
| 54 | Producer | `need_evidence` ghi vào `vN/review/evidence-<k>/`, không tạo version; reviewer chấm lại chính `vN`; không được dùng khi còn `blocker`/`major` | producer.md §7, D21.4 | |
| 55 | Producer | `inputs` mỗi version; blockout lên version thì view và model dựng từ bản cũ hiện nhãn "cũ" trên trang duyệt mà Producer không làm gì | producer.md §11, D21.5 | |
| 56 | Producer | **[Thay bằng D22.17]** `P texture-stats` tổng hợp đúng từ ledger và các `texture_spec.json`; không có file `texture-log.jsonl` | producer.md §17, D22.17 | |
| 57 | Producer | **[Thay bằng D22.11]** `assemble.py`: 1 mesh / 1 node / 1 material, unlit, độ phân giải texture, hash mesh, đủ file gói, README ghép đúng từ report; fail → `blocked`, không có vòng sửa | producer.md §6.4, D22.11 | |
| 58 | Producer | `pilot_asset: null`: `intake --all` từ chối; so với pilot ghi `not_checked` ở check-clay và `tex_measure.py`, không lỗi | producer.md §9, D21.7 | |
| 59 | Producer | `approvals set model reviewer` không có `--confirm-spend` → từ chối | producer.md §4, D21.8 | |
| 60 | Producer | `[limits]`: đếm slot theo tiến trình đang chạy thật, không theo trạng thái `running` (asset `running` có thể đang chờ reviewer, không giữ Blender) | producer.md §12, D21.9 | |
| 61 | Producer | Claude Code: lời gọi subagent nhận `model` theo từng lần giao, để `pipeline.toml` quyết model | producer.md §16, D16.5 | |
| 62 | Producer | A/B: `P ab board` không lộ tên runtime ở đâu trên trang, kể cả đường dẫn ảnh và tên file tải về; `P compare --reveal` chỉ chạy khi đã duyệt hết lô | review-board.md §8, D21.10 | |
| 63 | Producer | A/B: mỗi runtime có báo được token đã dùng theo model không; nếu không, `P compare` ghi "không có số" thay vì 0 | producer.md §16, D21.10 | |
| 64 | Review Board | Trang local chạy đủ tính năng với `model-viewer@3.5.0` (trước dùng 4.0.0) | review-board.md §5, D21.11 | |
| 65 | Producer | Finding lưu theo version: vòng sửa quay về bản tốt nhất thì brief và reviewer nhận đúng danh sách finding của bản đó; khi `redo`, finding còn mở được chép sang đợt mới | producer.md §6.1, D22.1 | |
| 66 | Producer | Vòng evidence: hash `final/` không đổi, đổi thì bỏ kết quả; không tính vào `resume_rounds` | producer.md §7, D22.5 | |
| 67 | Producer | Mỗi key `unclear` trong `RUBRIC` có finding tương ứng, thiếu thì `ingest` báo lỗi; tin nhắn reviewer trả về chỉ có `VERDICT` và `COUNTS` | producer.md §6.1, D22.6 | |
| 68 | Producer | `TOP_FIX: regen_front` ở `views_rest` chạy `redo --step views_front`; `views_rest` chạy lại sau khi front được duyệt lại | producer.md §6.1, concept-views.md §8, D22.4 | |
| 69 | Concept Views | README bộ view có đủ 4 mục và dòng trỏ; không có bước chép front; reviewer lần 2 không có finding nào về front trừ `regen_front` | concept-views.md §3, §6, §8, D22.14 | |
| 70 | Review Board | Bấm Duyệt hai lần (local rồi remote) cho cùng (asset, bước, version): lần sau bị bỏ qua và có thông báo; phiên mới kéo dữ liệu remote trước `P next` | review-board.md §2, §6, D22.8 | |
| 71 | Mọi agent | `check_inputs.py` của agent chỉ kiểm file tồn tại; hash lệch do script bắt khi sinh brief hoặc ingest (thử: sửa một byte của `part_graph.json` đã duyệt) | producer.md §11, D22.12 | |
| 72 | 3D Artist, Texture Artist | Số hình học chỉ đọc từ `sources.json`; đổi `size_m` trong thẻ sau khi blockout đã duyệt không làm đổi số mà 3D Artist dùng, mà bật cảnh báo đổi thẻ | producer.md §10, D22.13 | |
| 73 | Producer | Claude Code: resume đúng subagent cũ bằng SendMessage với agent id lấy từ kết quả lần giao trước | producer.md §16 | |
| 74 | Codex | `codex exec` gọi lồng từ bên trong một phiên Codex chạy được và lấy được ảnh; nếu không, bản Codex dùng tool ảnh có sẵn | producer.md §16, D18 | |
| 75 | Texture Artist | Meshy retexture với `enable_original_uv: true` giữ nguyên UV và số tam giác trên một mesh thật | texture-artist.md §2.2, D21.2 | |
| 76 | — | Đọc code kit v0.10.4: tool của kit có tự kiểm hash hay không. Nếu có, xem lại D22.12 | D22.12 | |
| 77 | Producer | `assemble.py` so pixel GLB với render bước `texture`: chọn ngưỡng; thử với một GLB cố ý sai color space để chắc script bắt được | producer.md §6.4, D22.11 | |
| 78 | Mọi reviewer | Test D1 kiểm 4 file reviewer có đủ quy tắc chung theo contract mới: finding có id, `PRIOR`, `TOP_FIX` kiểu đơn/lô, chỉ trả 2 dòng | D1, D22.7 | |
| 79 | Producer | Adapter quy đổi `opus`/`sonnet`/`haiku` sang model thật; ledger ghi model thật mỗi lần giao | producer.md §16, D22.9 | |
| 80 | Producer | A/B: mỗi runtime so tris/m² và dE với pilot trong `deliver` của chính nó | producer.md §16, D22.10 | |
| 81 | Mọi agent | Gọi "ZPS - 3D Artist", "ZPS Texture Artist" trong một phiên có cài cả kit và bộ Producer: Claude chọn skill của kit, không chọn `zps-3dp-step-*`. Thử cả khi không nói tên, chỉ mô tả việc ("dựng model cho concept này") | producer.md §3, D23.2 | |
| 82 | Project Setup | Frontmatter `disable-model-invocation: true` có trên bản Claude Code đang dùng; skill không tự kích hoạt; gọi `/zps-3dp-project-setup` vẫn chạy. Bản Codex: tìm cơ chế tương đương | project-profile.md §5, D23.3 | |
