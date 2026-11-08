# Spec — Producer (v2)

Tên kỹ thuật: `zps-3dp-producer`. Tên hiển thị: ZPS-3DP - Producer.
v1 duyệt: 2026-11-08. v2: 2026-11-09 (D21, D22). Quyết định nền: `docs/decisions.md` (D14, D21, D22 và các quyết định trước còn hiệu lực).

**Nền:** skill `producer` anh đã làm (`producer-skill.zip`: `SKILL.md`, `scripts/producer.py`, `references/`, `templates/`). Spec này giữ cơ chế của skill đó và ghi những chỗ thay đổi.

---

## 1. Vai trò

Producer là **skill chạy trong phiên chính**. Producer chỉ điều phối:
- Chạy script `producer.py` (gọi tắt `P`).
- Giao việc cho worker và reviewer bằng file brief do script sinh ra.
- Chạy `P ingest` để script đọc báo cáo và chuyển trạng thái.
- Chuyển câu hỏi của agent cho anh, và chuyển nguyên văn feedback của anh vào file.

Producer **không** mở ảnh, JSON, log hay file dự án (D6). Producer **không** tự ghi trạng thái (D21.5): mọi đánh dấu (version cũ, số lần gọi Meshy, hash) do script tính. Trạng thái nằm trong file, không nằm trong trí nhớ của Producer.

## 2. Giữ nguyên từ skill nền

| Cơ chế | Mô tả |
|---|---|
| Trạng thái trong file | `production/assets/<id>/status.json` (chỉ script ghi), `ledger.md` (chỉ ghi thêm) |
| Script quyết định thứ tự | `P next` cho biết bước tiếp theo của từng asset |
| Giao việc bằng file | `P brief <id>` sinh brief, in JSON (`role`, `agent`, `model`, `resume`, `brief`, `report`) |
| Báo cáo contract | Dòng `KEY: value` ở đầu file report. Script kiểm định dạng, không đoán |
| `pipeline.toml` | Nơi duy nhất định nghĩa bước, agent, model, gate, output bắt buộc, giới hạn chạy song song |
| Version theo bước | `<bước>/vN/` có `final/`, `work/`, brief, report |
| Resume | Vòng sửa ≤ `resume_rounds` (2): gửi tiếp cho đúng worker cũ. Sau đó: worker mới, có thể dùng `escalate_model` |
| Ruling | Quyết định Producer tự đưa ra được ghi bằng `P rule "<id>: <quyết định> — <lý do> — <cái giá nếu sai>"` |
| Cảnh báo đổi nguồn | Concept, thẻ, profile hoặc art direction đổi sau khi asset bắt đầu → cảnh báo ⚠, hỏi anh làm lại hay giữ (mục 11, D21.5) |
| Trang duyệt local | `P serve` (127.0.0.1:8765): nút Duyệt / Cần sửa / Ghi chú, xem GLB xoay được |
| Hook và lệnh phụ | SessionStart chạy `P next --session`; `dashboard`, `validate`, `cleanup` (dry-run trước), `archive` |

## 3. Pipeline 6 bước (`pipeline.toml`, D14.2)

| # | `id` | Worker | Kiểm | Gate |
|---|---|---|---|---|
| 1 | `blockout` | `zps-3dp-blockout` | `zps-3dp-review-blockout` | `review_human` |
| 2 | `views_front` | `zps-3dp-concept-views` | `zps-3dp-review-views` (chỉ front) | `review` |
| 3 | `views_rest` | `zps-3dp-concept-views` | `zps-3dp-review-views` (cả bộ) | `review_human` |
| 4 | `model` | `zps-3dp-3d-artist` | `zps-3dp-review-clay` | `review_human` (DUYỆT 1) |
| 5 | `texture` | `zps-3dp-texture-artist` | `zps-3dp-review-texture` | `review` |
| 6 | `assemble` | Script `assemble.py`, không có agent (D22.11) | Kiểm trong chính script (mục 6.4) | `checks_human` (DUYỆT 2) |

**Ba loại gate:**

| Gate | Sau khi worker xong |
|---|---|
| `review` | Reviewer PASS → bước sau |
| `review_human` | Reviewer PASS → `waiting_human` → duyệt theo chính sách (mục 4) → bước sau |
| `checks_human` (mới, D21.6, D22.11) | Script của bước pass → `waiting_human` → anh duyệt. Script fail → `blocked`, không có vòng sửa; Producer báo anh kèm điểm fail |

- **Producer sắp xếp reviewer** qua script. Worker không gọi reviewer, không gọi agent khác.
- Bỏ `final_human_gate`, vì `assemble` đã có gate người duyệt (D14.3).
- Model của từng bước có agent theo D16: pilot dùng Opus cho mọi bước; sau pilot hạ từng bước theo bảng D16.2.
- `assemble` không có agent (D22.11): mọi việc của bước này là việc xác định. Texture đã được review-texture chấm trên model ở bước `texture`.
- Mỗi bước khai báo loại `TOP_FIX` được phép và kiểu sửa (mục 6).

## 4. Ai duyệt (D14.4, D21.3)

**Chính sách nằm trong `production/policy.yaml`**, tách khỏi profile. Lý do: đổi người duyệt không ảnh hưởng cách dựng asset, nên không được làm đổi hash profile và bật cảnh báo cho mọi asset đang chạy.

```yaml
# production/policy.yaml — chỉ script ghi
approvals:
  blockout:   human    # human | reviewer
  views_rest: human
  model:      human    # đổi sang reviewer cần --confirm-spend
  # assemble: luôn human, không có khóa
review_board: local    # local | local+remote
delegations: []        # ghi bởi P delegate
```

- Project Setup hỏi anh các giá trị này lúc khởi tạo, ghi file. Gợi ý: pilot để `human` hết.
- Khóa hợp lệ: `blockout`, `views_rest`, `model`. Script từ chối khóa khác. `views_front` và `texture` chỉ do reviewer duyệt. `assemble` luôn do anh duyệt.
- `reviewer`: reviewer PASS (không còn finding `blocker`, `major`, `unclear` đang mở) thì script tự duyệt, ghi ledger "reviewer duyệt theo chính sách dự án".
- **Đổi chính sách:** anh nói trong chat. Producer chạy `P approvals set <bước> <human|reviewer> --by "<nguyên văn>"`. Có hiệu lực ngay, không cần phiên mới, không bật cảnh báo.
- **`model: reviewer` cần `--confirm-spend`** (D21.8). Bước ngay sau `model` gọi Meshy (tốn credit) trên mesh vừa khóa. Không có cờ này, script từ chối và in lý do để Producer hỏi lại anh.
- **Ngoại lệ theo lô:** Producer chạy `P delegate <bước> <id> ...`. Thứ tự ưu tiên: `delegate` > `approvals` > `human`.
- Mọi lần duyệt ghi **ai duyệt** (anh, chính sách, ủy quyền). Anh bấm Cần sửa được bất cứ lúc nào.

## 5. Xem kết quả

Anh nói trong chat. Producer chạy script và chuyển đường dẫn cho anh. Producer không mở file.

| Anh nói | Producer chạy | Anh nhận |
|---|---|---|
| "Tiến độ?" | `P dashboard` | Bảng ngắn: asset, bước, trạng thái, việc anh cần làm |
| "Cho anh xem <asset>" | `P show <id>` | Một file HTML: concept, sheet duyệt, render, GLB, tóm tắt report các bước |
| "Xem <bước> v<N> của <asset>" | `P show <id> --step <bước> --version <N>` | HTML của đúng version đó |
| "Duyệt cả lô" | `P serve` | Trang duyệt local |

- Producer đưa file cho anh bằng tool gửi file của runtime (Claude Code: `SendUserFile`). Nội dung không vào context Producer.
- `P show --bundle`: nhúng ảnh (thu cạnh dài về tối đa 1024 px; crop giữ nguyên) và GLB nhỏ vào một file HTML, để xem trên điện thoại. Khi anh dùng Remote Control, Producer tự thêm `--bundle`.
- Câu hỏi "vì sao …?": trả lời bằng dòng lý do và danh sách finding có id trên trang duyệt. Không gọi thêm agent (D22.17).
- `P show`, `--bundle`, `P serve` và `P ab board` dùng chung một renderer, là file JavaScript của Review Board (D22.15). `P show` là trang board của một asset xuất thành file tĩnh.
- Duyệt bằng nút, khoanh vùng, xem toàn màn hình và zoom: Review Board (`docs/review-board.md`, D19).

## 6. Contract

### 6.1 Reviewer (D14.10, D21.1)

```
VERDICT: PASS | FIX | ESCALATE
RUBRIC: <key>=pass|fail|unclear; ...
COUNTS: blocker=N; major=N; minor=N; unclear=N
TOP_FIX: <loại>: F<n>[, F<m> ...]
FINDINGS:
- F<n> [blocker|major|minor|unclear] <loại> · <ở đâu> — <sai gì> — <sửa thế nào>
PRIOR:
- F<n>: resolved | open | regressed
```

**Finding có id cố định qua các vòng.** Script lưu finding **theo từng version**: `<bước>/vN/findings.json` (id, mức, loại, trạng thái, vòng xuất hiện đầu, vòng gần nhất) (D22.1). Brief vòng sửa lấy danh sách finding của bản được chọn làm gốc (bản tốt nhất), không phải của bản mới nhất. Brief của reviewer có danh sách đó và số id bắt đầu cho finding mới. Reviewer phải ghi `PRIOR` cho **mọi** finding đang mở. Thiếu một dòng → `ingest` báo lỗi contract.

- Khi anh `redo` (đợt feedback mới): finding còn mở của bản gốc được chép sang đợt mới, cộng finding của anh. Bộ đếm vòng đặt lại (D11.4).
- Mỗi key chấm `unclear` trong `RUBRIC` phải có ít nhất một finding mức `unclear` (D22.6).
- **Tin nhắn trả về cho Producer** chỉ gồm hai dòng `VERDICT` và `COUNTS` (D22.6). `RUBRIC`, `FINDINGS`, `PRIOR` nằm trong file report.

**Chọn VERDICT** (theo thứ tự, dừng ở dòng đầu tiên khớp):

| # | Điều kiện | VERDICT | TOP_FIX |
|---|---|---|---|
| 1 | Lựa chọn thẩm mỹ anh phải quyết, hoặc rubric mâu thuẫn brief | ESCALATE | — |
| 2 | Còn finding `blocker` hoặc `major` đang mở | FIX | Loại có finding nặng nhất. Hai loại cùng mức: `structure` trước `param`, `fix_uv_mesh` trước `repaint`, vì sửa cấu trúc có thể làm finding kia mất hiệu lực. Finding `unclear` để vòng sau chấm lại |
| 3 | Chỉ còn finding `unclear` | FIX | `need_evidence` |
| 4 | Không còn `blocker`, `major`, `unclear` | PASS | — |

**Loại `TOP_FIX` theo bước** (khai báo trong `pipeline.toml`; script từ chối loại khác):

| Bước | Loại | Kiểu sửa |
|---|---|---|
| `blockout`, `model` | `structure` | **Đơn**: đúng một finding mỗi vòng. Thay đổi cấu trúc cần tách riêng để biết cái nào gây lỗi mới |
| | `param` | **Lô**: mọi finding `param` đang mở |
| `views_front`, `views_rest` | `regen` | **Lô**: mọi view có finding `regen`. Mỗi view độc lập |
| `views_rest` | `regen_front` | Front sai so với bộ (D22.4). Script chạy `redo --step views_front`; các bước sau tự chạy lại |
| | `note_exception`, `note_texture` | Chỉ ghi chú, không gây FIX |
| `texture` | `repaint` | **Lô**: mọi vùng có finding `repaint`. Mỗi vùng độc lập |
| | `fix_uv_mesh` | Script chạy `redo --step model`. DUYỆT 1 lại |
| | `meshy_regen` | Script đặt `waiting_human` (mục 6.3) |
| | `note` | Chỉ ghi chú, không gây FIX |
| Mọi bước có reviewer | `need_evidence` | Vòng xin bằng chứng (mục 7) |

Script kiểm `TOP_FIX` liệt kê đúng: kiểu đơn có đúng một id; kiểu lô có đủ mọi finding đang mở cùng loại.

### 6.2 Worker

Giữ như skill nền: `STATUS / OUTPUT / RUBRIC / ISSUES`. Thêm:
- `PROFILE_HASH: <hash>`: **chép từ brief**. Script tính hash khi sinh brief (mục 10); `ingest` so với hash trong brief. Lệch → báo lỗi, không chuyển trạng thái.
- `FIXED: F<n>, ...` (vòng sửa): finding worker cho là đã sửa. Chỉ để đối chiếu; reviewer quyết.
- Texture Artist: `UNFIXABLE: yes|no`.

Worker không khai số lần gọi Meshy. Script đọc `budget.json` (mục 6.3).

**Kiểm đầu vào** (D22.12): chỉ script kiểm hash đầu vào, khi sinh brief và khi ingest (mục 11). `check_inputs.py` của agent chỉ kiểm file có tồn tại.

**Brief bước `texture`:** script sinh brief từ các `final/` đã duyệt (`blockout` để đọc `sources.json`, `model`, `views_rest`) và file concept trong `_approved/<id>/`. Script chép mục `ISSUES` của report bước `model` đã duyệt vào brief. Không có file handoff.

### 6.3 Meshy (D20.14, D21.2)

1. **Budget gắn với hash mesh**, không gắn với asset. `production/assets/<id>/texture/budget.json`:
   ```json
   {"entries": [{"mesh_hash": "...", "allowed": 1, "used": 0, "credits": 0, "approved_by": "default"}]}
   ```
2. Chỉ Texture Artist gọi Meshy, và chỉ qua `gen_api.py`. Wrapper này đọc budget, từ chối khi `used >= allowed`, và ghi `used`, `credits` sau mỗi lần gọi có trừ credit. Script đọc file này; worker không tự khai.
3. Lỗi kỹ thuật (hết thời gian chờ, lỗi mạng, lỗi API không trừ credit) không tính là một lần gọi. Thử lại tối đa 3 lần (như D8.3). Sau 3 lần lỗi: `STATUS: BLOCKED`, Producer hỏi anh.
4. Texture chưa đạt: Texture Artist sửa qua các vòng review thường.
5. **Không sửa được** (`TOP_FIX: meshy_regen` hoặc `UNFIXABLE: yes`): script đặt `waiting_human`. Anh duyệt → script tăng `allowed` của mesh hiện tại thêm 1 và ghi `approved_by`. Brief sau ghi số lần còn được gọi.
6. **Mesh đổi** (sau `fix_uv_mesh` hoặc anh làm lại `model`): hash mới có entry mới với `allowed: 0`. Texture cũ làm trên UV cũ, không dùng được. Script đặt `waiting_human` với câu hỏi: "Mesh đổi, texture Meshy cũ mất hiệu lực. Gọi lại Meshy (tốn credit) hay VẼ MỚI?". Anh chọn Meshy → `allowed: 1`; chọn VẼ MỚI → brief ghi chỉ định chế độ.

### 6.4 Bước `assemble` bằng script (D22.11)

`assemble.py` chạy khi bước `texture` được duyệt. Không có agent, không có reviewer.

1. Kiểm hash mesh khớp hash đã khóa khi duyệt `model`.
2. Gắn `albedo_<texture_res>.png` vào mesh đã khóa. Xuất GLB cuối: 1 mesh, 1 node, 1 material, unlit, base color only. Lưu `.blend`.
3. Chạy QA của kit trên GLB cuối: `mesh_check`, `uv_check`, `export_check`, `screen_tris_check`.
4. **Kiểm GLB hiển thị đúng:** render một bộ nhỏ (3/4 trước, camera game) từ chính file GLB đã xuất, so pixel với render cùng góc của bước `texture`. Lệch quá ngưỡng → fail. Lý do: bắt lỗi phát sinh khi xuất (color space, alpha, unlit) mà render trong Blender không thấy.
5. Ghép gói cuối: `model/`, `texture/` (chép `albedo` và `notes.md` từ `final/` của bước `texture`), `review/` (sheet DUYỆT 1, render và `final_lit_vs_concept.png` của bước `texture`, ảnh so ở điểm 4, report reviewer).
6. Ghép `README.md` từ report các bước: dòng đầu là trạng thái và ngày; cách làm (chế độ texture, số lần gọi Meshy từ `budget.json`); ngoại lệ (NGOẠI LỆ, TEXTURE NOTE, mục "Blockout tự quyết"); việc còn mở (finding `minor` chưa đóng); những gì chưa kiểm (engine, camera chưa chốt, % tam giác nhỏ).
7. Pass → `waiting_human` (DUYỆT 2). Fail ở bất kỳ điểm nào → `blocked`, Producer báo anh kèm điểm fail.

Mỗi điểm fail ghi vào `assemble/vN/report-script.md` theo dạng finding để trang duyệt hiện được.

## 7. Vòng sửa (D11, D21.1, D21.4, bằng script)

1. **Trần:** tối đa `max_fix_rounds` = 3 vòng mỗi bước, tính trong một đợt feedback. Feedback `redo` của anh mở đợt mới, đặt lại bộ đếm (D11.4).
2. **Mỗi vòng:** worker sửa đúng các finding liệt kê trong `TOP_FIX`, bắt đầu từ bản brief chỉ định (bản tốt nhất).
3. **Tiến bộ** đo trên finding có id, không đo trên tổng số đếm. Một vòng có tiến bộ khi: có ít nhất một finding `blocker` hoặc `major` cũ chuyển `resolved`, và số finding chuyển `regressed` ít hơn số `resolved`. Finding mới phát hiện không tính là thụt lùi, vì reviewer có context mới mỗi lần nên có thể thấy thêm lỗi cũ chưa ai nêu.
4. **Dừng sớm:** từ vòng 2, nếu vòng không có tiến bộ → `waiting_human`, ghi "không tiến bộ ở vòng N" kèm danh sách finding còn mở.
5. **Bản tốt nhất** (D11.3): version có ít finding `blocker` + `major` đang mở nhất (bằng nhau thì version cũ hơn). Brief vòng sửa trỏ tới bản tốt nhất. Khi gửi anh hoặc khi dừng, gửi bản tốt nhất.
6. **Vòng xin bằng chứng (`need_evidence`):**
   - Chỉ dùng khi không còn `blocker`, `major` đang mở (mục 6.1, bảng VERDICT).
   - Worker của cùng bước chỉ render các ảnh reviewer xin, ghi vào `<bước>/vN/review/evidence-<k>/`. **Không tạo version mới.** Reviewer chấm lại chính `vN` với ảnh thêm.
   - Worker không được sửa `final/` (D22.5). Script so hash `final/` trước và sau vòng; lệch → báo lỗi, bỏ kết quả vòng đó.
   - Resume worker cũ nếu còn; vòng này không tính vào `resume_rounds`.
   - Không tính vào 3 vòng. Cùng bước xin lần thứ hai trong một đợt feedback → `waiting_human` (D20.15).
7. **Chuyển lên anh** (`waiting_human`): hết vòng 3 vẫn FIX (gửi bản tốt nhất kèm finding còn mở); dừng sớm; `ESCALATE`; `need_evidence` lần hai; Meshy (mục 6.3 điểm 5 và 6); `assemble.py` pass (DUYỆT 2). `assemble.py` fail → `blocked`.
8. **Cần sửa ở bước `assemble`** (D21.6, thay D20.4): không có agent và reviewer, nên khi anh bấm Cần sửa, trang duyệt hỏi sửa ở bước nào: `texture` (vẽ lại) hoặc `model` (mesh, UV). Script chạy `redo --step <bước>`; các bước sau tự chạy lại.

## 8. Thư mục

```
<thư mục concept>/_approved/<id>/      KHU 1 — ĐẦU VÀO. Anh chép vào. Pipeline chỉ đọc
  concept_albedo.png, concept_shadow.png, asset-card.yaml, <id>.material.md,
  <id>.layout.md                       chỉ khi profile có `has_map: true`

production/                            KHU 2 — LÀM VIỆC. Chỉ script và agent ghi
  PROJECT-PROFILE.yaml, policy.yaml, pipeline.toml, ledger.md, dashboard.md
  rubrics/<loại>.md
  assets/<id>/
    status.json, brief.md, rubric.md, feedback.md, feedback/
    <bước>/vN/{final, work, review, findings.json, brief-*.md, report-*.md}
    texture/budget.json

deliver/<id>/                          KHU 3 — KẾT QUẢ CUỐI ĐÃ DUYỆT
  nội dung `assemble/vN/final/` đã duyệt: README.md, model/, texture/, review/
```

- **Chép khi duyệt** (D20.2): chỉ khi `assemble` được duyệt (DUYỆT 2), script chép `assemble/vN/final/` sang `deliver/<id>/`. Các bước giữa nằm lại trong `production/`.
- **Làm lại sau DUYỆT 2:** README trong `deliver/<id>/` ghi "đang làm lại". Bản cũ giữ cho tới khi có bản duyệt mới.
- **Version bị loại** (D22.2, thay D14.9): khi một bước được duyệt, script đánh dấu các version khác của bước đó là `rejected` trong `status.json`. **Không di chuyển thư mục**, vì brief cũ, `inputs`, ảnh khoanh, evidence và `ab/mapping.json` đều trỏ tới đường dẫn version.
- **Xóa:** chỉ qua `P cleanup`, chỉ khi asset đã xong, chạy dry-run trước, xóa thật khi anh đồng ý. Xóa `work/` của các version `rejected`; giữ preview và report. Sau đó `P archive`.
- **Agent chỉ đọc và ghi đường dẫn trong brief.** Mọi file agent có dòng: "Chỉ đọc file và thư mục brief chỉ định. Chỉ ghi trong thư mục version brief giao. Không quét thư mục asset."
- Bỏ thư mục `View Concept/` riêng. Brief bước sau trỏ thẳng tới `final/` đã duyệt của bước trước.

## 9. Nhận việc (intake)

- Giữ cách của skill nền: chỉ đăng ký khi anh bảo; `P intake` liệt kê theo nhóm; `--all`, `--priority`.
- **Kiểm:** `asset-card.yaml` hợp lệ (`check_card.py`: trường bắt buộc, giá trị hợp lệ, `type` có rubric); đủ file bắt buộc (albedo, có bóng, thẻ, material handoff); profile hợp lệ (`check_profile.py`).
- **Concept brief = `asset-card.yaml`** (D22.3). Phần khuất (`hidden_sides`), đối xứng (`symmetric`), ghi chú real/texture_only (`real_texture_only_notes`) nằm trong thẻ. Không có file brief riêng. Khi spec agent nói "concept brief", nghĩa là thẻ này.
- **MAP-LAYOUT:** nếu profile có `has_map: true`, intake bắt buộc có `<id>.layout.md`. Nếu `has_map: false`, thẻ bắt buộc có `size_m: {w, d, h}` (mét); `check_card.py` kiểm trường này. Blockout lấy W×D×H từ `size_m` (D20.9).
- Thiếu hoặc sai → không đăng ký. Producer báo anh theo nhóm lỗi.
- Loại asset lấy từ `type` trong thẻ (`building`, `prop`, `tree`, `rock`). Loại `character`, `creature`: báo v1 chưa hỗ trợ (D9).
- **Pilot trước, lô sau** (D21.7): khi profile có `pilot_asset: null`, `intake --all` từ chối; chỉ đăng ký từng asset gọi đích danh, và chỉ khi không có asset nào khác đang chạy. Các phép so với pilot (tris/m², dE vật liệu) ghi `not_checked`, không fail.

## 10. Thông số và rubric

| Loại thông tin | Nằm ở |
|---|---|
| Số và quy ước script dùng | Mặc định skill → preset → profile → thẻ asset (D13) |
| Ai duyệt, trang duyệt | `production/policy.yaml` (mục 4) |
| Tài liệu style | `art-direction/` (AD giữ, tag `steps:`), như skill nền. **Chỉ** ở đây (D22.16) |
| Tiêu chí chấm chung của bước | Trong file agent reviewer |
| Tiêu chí chấm riêng theo loại asset | `production/rubrics/<loại>.md`, chia mục theo bước. Anh duyệt một lần (`status: approved`). Chỉ chứa tiêu chí pass/fail kèm tham chiếu tới tài liệu AD (ví dụ "mái đúng `roofs.md` §2"), không mô tả style (D22.16) |
| Số hình học sau khi blockout được duyệt | `sources.json` của blockout là nguồn duy nhất cho các bước sau (D22.13). Profile và thẻ chỉ còn dùng cho thông số không phải hình học (`texture_res`, ngưỡng pixel, `detail_examples`) |

- Số không viết hai lần. Tài liệu art direction có thể nhắc số, nhưng số thật nằm trong YAML. Nếu lệch, YAML thắng.
- **Hash profile** (D21.3) tính trên nội dung đã chuẩn hóa của `PROJECT-PROFILE.yaml`, **bỏ** `paths` và mọi khóa bắt đầu bằng `_` (ví dụ `_source`). Sửa ghi chú nguồn hay đường dẫn không làm đổi hash.
- `check_profile.py` do script chạy một lần khi `intake` và khi sinh brief. Agent không chạy lại.

## 11. Theo dõi đầu vào và version cũ (D21.5, bằng script, thay phần "Producer đánh dấu" của D2)

Mỗi version ghi trong `status.json` các đầu vào đã dùng. Script là tầng duy nhất kiểm các hash này, khi sinh brief và khi ingest (D22.12):

```json
"inputs": {"blockout": "<hash final đã duyệt>", "views_rest": "<hash>", "model": "<hash mesh>",
           "card": "<hash asset-card.yaml>", "concept": "<hash các file _approved/<id>/>",
           "profile": "<hash profile>", "art_direction": "<ngày thay đổi gần nhất>"}
```

- **Version cũ:** một version là "cũ" khi đầu vào của nó khác bản đã duyệt hiện tại của bước trước. Script tự suy ra; Producer không đánh dấu tay. Trang duyệt hiện nhãn "dựng từ blockout v1 — cũ".
- **Cảnh báo ⚠:** concept, thẻ, profile hoặc art direction đổi sau khi asset bắt đầu. Hỏi anh làm lại hay giữ, rồi `P ack <id>`.
- **Dùng lại:** worker bước sau đọc `inputs` của version trước (qua brief) để biết phần nào giữ được, ví dụ `diff_guides.py` của Concept Views.
- Concept dùng hash nội dung file, không dùng thời gian sửa: chép lại cùng file không bật cảnh báo (đề xuất, chờ duyệt).

## 12. Giới hạn chạy song song (D21.9)

```toml
# pipeline.toml
[limits]
blender = 2        # số tiến trình Blender cùng lúc (blockout, model, texture render, assemble.py)
codex_image = 2    # số lệnh gen ảnh qua gen_image_codex.py cùng lúc
meshy = 1          # số lần gọi Meshy cùng lúc
```

- Mỗi bước khai báo tài nguyên dùng (`uses = ["blender", "codex_image"]`). `P next` chỉ đề xuất giao việc khi còn chỗ; asset chờ hiện "chờ slot <tài nguyên>".
- Mỗi runtime có `[limits]` riêng (mục 16). Hai runtime không chạy cùng lúc trên một máy.

## 13. GUIDELINE.md (D14.7)

`P init` sinh `GUIDELINE.md` cho dự án (skill nền). Anh gửi cho Concept Artist, View Artist, AD. Thêm:
1. Mẫu `asset-card.yaml` và hướng dẫn từng trường (bắt buộc / bỏ trống thì hiểu thế nào).
2. Danh sách file bắt buộc trong `_approved/<id>/`, đúng tên file. Tên file trong `_approved/` giờ là quy ước bắt buộc, thay cho "tên tự do" của skill nền.
3. Cách làm lúc chốt: Concept Artist soạn thẻ từ những gì đã thảo luận, hỏi anh một lần các trường còn trống kèm gợi ý, viết material handoff, chạy `check_card.py`, rồi báo anh. Anh chép thư mục đã đủ vào `_approved/`.
4. AD: viết tài liệu style có tag `steps:`. Không ghi số kỹ thuật; muốn đổi số thì đề xuất với anh.

`check_card.py` đi kèm GUIDELINE, để Concept Artist tự kiểm.

## 14. Khởi tạo và phiên mới (D13)

1. Anh gọi Producer. Producer chạy `check_profile.py`.
2. Thiếu profile → nạp skill Project Setup, làm cùng anh (gồm cả `policy.yaml`).
3. Xong → **Producer nhắc anh gõ lệnh xóa context và mở phiên mới**, đúng câu lệnh của runtime (Claude Code: `/clear`; Codex: `/new`).
4. Producer cũng nhắc mở phiên mới sau khi cập nhật nội dung profile, và khi context đã dài sau một lô.
5. **Phiên mới khi `review_board: local+remote`** (D22.8): Producer kéo dữ liệu từ trang remote về trước khi chạy `P next`, để không bỏ sót quyết định anh đã bấm trên điện thoại.

**Quyết định không ghi trùng** (D22.8): mỗi bộ (asset, bước, version) chỉ nhận một quyết định Duyệt hoặc Cần sửa. Quyết định đến sau, từ trang local hay remote, bị bỏ qua và script báo lại. Ghi chú thì nhận nhiều lần.

## 15. Hỏi anh (D13.8)

Sub-agent không chat với anh. Đường duy nhất: worker trả `STATUS: NEEDS_CONTEXT` hoặc `BLOCKED` kèm câu hỏi → asset `blocked` → Producer hỏi anh (hoặc tự bổ sung nếu đã có thông tin, theo skill nền) → ghi vào mục "Làm rõ" của brief → `P retry`.

## 16. Runtime và so sánh A/B (D6.4, D21.10)

Bộ skill chạy trên **cả Claude Code và Codex**, để so bên nào cho kết quả tốt hơn.

**Một lõi, hai adapter** (D6.4: một nguồn chung, script build xuất hai bản, bảng khác biệt ở `docs/EDITIONS.md`):

| Phần | Dùng chung | Theo runtime |
|---|---|---|
| `producer.py`, contract, schema, script kiểm, tool của agent | ✓ | |
| Prompt của từng agent (`agents/*.md`) | ✓ | |
| Cách gọi agent, resume, hook, tool gửi file, đường dẫn | | `adapters/claude.md`, `adapters/codex.md` |

- Spec agent viết trung lập với runtime: "sub-agent của runtime", không "sub-agent Claude" (D22.9).
- Adapter ghi cách quy đổi tên chung `opus`, `sonnet`, `haiku` sang model thật của runtime. Ledger ghi model thật đã dùng ở mỗi lần giao (D22.9).
- Claude Code: subagent qua Task; resume qua SendMessage; hook SessionStart; gửi file qua `SendUserFile`; Review Board `local+remote` dùng được (đã thử 2026-11-08).
- Codex: gọi agent qua `collaboration.spawn_agent`, resume qua `collaboration.send_message` (cần thử, `docs/coding-checklist.md`). Blender ngoài sandbox, quyền mạng cấp ở phiên gốc. Review Board chỉ `local`.
- Sửa prompt agent chỉ sửa một chỗ. Adapter không được chứa quy tắc nghiệp vụ.
- Thứ tự làm giữ như D6.4: bản Claude, chạy thử, rồi bản Codex. Chạy A/B khi cả hai bản đã qua một asset trọn vẹn.

**Chạy A/B:**

| Quy tắc | Chi tiết |
|---|---|
| Đầu vào chung | Cùng `_approved/`, cùng profile, cùng rubric, cùng art direction |
| Đầu ra riêng | `PRODUCER_ROOT=production-claude` / `production-codex`; `deliver-claude/`, `deliver-codex/`. Mỗi bên có `status.json`, `policy.yaml`, `[limits]` riêng |
| Chạy lệch giờ | Xong lô của bên này mới chạy bên kia, để thời gian đo được không lẫn tranh chấp tài nguyên |
| Phạm vi | 2–3 asset pilot. Chọn bên thắng, rồi chạy cả lô bằng bên đó. Lý do: credit Meshy nhân đôi |
| Duyệt mù | `P ab board` mở trang so cặp (review-board §8): mỗi asset hai bản đặt cạnh nhau, nhãn A/B gán ngẫu nhiên theo asset, lưu ở `ab/mapping.json`. Anh duyệt từng bản như thường; script ghi về đúng thư mục của runtime đó |
| Mở nhãn | `P compare --reveal`, chỉ sau khi anh đã duyệt hết các asset trong lô so sánh |
| Pilot | Mỗi runtime so với pilot nằm trong `deliver` của chính nó (D22.10) |

**`P compare`** tổng hợp từ ledger của hai bên (script ghi `runtime` vào mọi dòng ledger):
- Số vòng sửa mỗi bước; tỉ lệ anh duyệt ngay lần đầu ở DUYỆT 1 và DUYỆT 2.
- Số lần `waiting_human` theo lý do.
- Thời gian thực mỗi bước và cả asset.
- Chi phí: token theo model (nếu runtime báo được), credit Meshy.
- Số lần reviewer chấm lệch so với quyết định của anh (cùng chỉ số với D16.3).
- Bên nào anh chọn ở nút "Bản nào tốt hơn" (đề xuất, chờ duyệt).
- Tỉ lệ pass lần đầu của script kiểm mỗi bước.

Kết quả so sánh gộp runtime và model đi kèm (Claude dùng Opus/Sonnet, Codex dùng model của nó). Kết luận là "bộ nào tốt hơn cho việc này", không tách riêng runtime hay model.

## 17. Thay đổi script cần làm (tóm tắt)

| Thay đổi | Hàm | Ước lượng |
|---|---|---|
| Gate `review_human`, `checks_human`; bỏ `final_human_gate` | `cmd_ingest`, `advance` | ~25 dòng |
| `assemble.py` (mục 6.4) | mới | ~150 dòng (phần lớn gọi tool của kit) |
| `policy.yaml`, `P approvals set` (+ `--confirm-spend`), `P delegate` | mới + `cmd_ingest` | ~50 dòng |
| Contract reviewer: `COUNTS`, `TOP_FIX` theo bước và kiểu sửa, `PRIOR`; `findings.json` theo version; chép finding khi `redo` | `cmd_ingest`, `parse_contract`, `review_brief` | ~90 dòng |
| Tiến bộ theo finding, dừng sớm, bản tốt nhất | `cmd_ingest`, `worker_brief` | ~40 dòng |
| `need_evidence` trong `vN/review/evidence-<k>/`, không tạo version, so hash `final/` | `cmd_brief`, `cmd_ingest` | ~30 dòng |
| `fix_uv_mesh` → redo model; Meshy budget theo hash mesh; câu hỏi khi mesh đổi | `cmd_ingest`, mới | ~50 dòng |
| `PROFILE_HASH` sinh trong brief, so khi ingest; hash bỏ `paths` và khóa `_` | mới | ~30 dòng |
| `inputs` mỗi version, suy ra version cũ, cảnh báo theo hash | mới + `warnings_for` | ~60 dòng |
| `[limits]` và `uses`; `next` chờ slot | `cmd_next` | ~30 dòng |
| Chép sang `deliver/` (chỉ khi duyệt `assemble`), đánh dấu `rejected` | `approve_step` | ~20 dòng |
| `P texture-stats`: tổng hợp từ ledger và `texture_spec.json` khi cần | mới | ~30 dòng |
| Quyết định không ghi trùng | `human_action` | ~15 dòng |
| Pilot trước lô sau | `cmd_intake` | ~15 dòng |
| `P show`, `--bundle` (dùng renderer của Review Board) | mới | ~60 dòng |
| `P board prepare` (Review Board §6) | mới | — |
| `P ab board`, `P compare`, cột `runtime` trong ledger | mới | ~150 dòng |
| Intake: `check_card`, file bắt buộc, `type` từ thẻ, `check_profile` | `scan_approved`, `cmd_intake`, `create_asset` | ~60 dòng |
| Tên `zps-3dp-producer`, adapter, đường dẫn | `SKILL.md`, `setup.md`, `adapters/` | — |

## 18. Thứ tự code (D22.18)

Code theo lát dọc. Mỗi giai đoạn chạy được trên asset pilot rồi mới sang giai đoạn sau.

| GĐ | Nội dung | Kiểm chứng chính |
|---|---|---|
| 0 | Sửa tài liệu: concept brief = thẻ asset, `out-of-scope-changes.md`, mẫu rubric chỉ có tiêu chí và tham chiếu AD | — |
| 1 | Lõi `producer.py` (state, finding theo version, vòng sửa, policy, limits, kiểm hash) + `blockout` + `review-blockout` + trang duyệt local tối thiểu | Reviewer ghi đủ `PRIOR`; vòng sửa theo finding hội tụ; model và resume theo từng lần giao trên Claude Code |
| 2 | `views_front`, `views_rest`, `gen_image_codex.py`, `regen_front` | Ảnh view đúng guide; front không bị chấm lại |
| 3 | `model`, `review-clay`, khóa mesh | Detail pass, UV, DUYỆT 1 |
| 4 | `texture` (budget Meshy theo hash mesh), `assemble.py` | Meshy giữ UV; GLB hiển thị khớp render của bước `texture` |
| 5 | Review Board đầy đủ: khoanh vùng, trang remote, `P show`, quyết định không ghi trùng | Trên điện thoại và trang local |
| 6 | Bản Codex, adapter, A/B | `codex exec` lồng trong Codex; báo cáo token |

Lý do: phần rủi ro nhất của thiết kế (reviewer ghi `PRIOR`, vòng sửa theo finding) được kiểm ở GĐ 1. Nếu sai, các giai đoạn sau sửa theo trước khi viết.
