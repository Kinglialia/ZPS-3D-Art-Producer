# Spec — Producer (v1)

Tên kỹ thuật: `zps-3dp-producer`. Tên hiển thị: ZPS-3DP - Producer.
Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D14 và các quyết định trước còn hiệu lực).

**Nền:** skill `producer` anh đã làm (`producer-skill.zip`: `SKILL.md`, `scripts/producer.py`, `references/`, `templates/`). Spec này giữ cơ chế của skill đó và ghi những chỗ thay đổi.

---

## 1. Vai trò

Producer là **skill chạy trong phiên chính**. Producer chỉ điều phối:
- Chạy script `producer.py` (gọi tắt `P`).
- Giao việc cho worker và reviewer bằng file brief do script sinh ra.
- Chạy `P ingest` để script đọc báo cáo và chuyển trạng thái.
- Chuyển câu hỏi của agent cho anh, và chuyển nguyên văn feedback của anh vào file.

Producer **không** mở ảnh, JSON, log hay file dự án (D6). Trạng thái nằm trong file, không nằm trong trí nhớ của Producer.

## 2. Giữ nguyên từ skill nền

| Cơ chế | Mô tả |
|---|---|
| Trạng thái trong file | `production/assets/<id>/status.json` (chỉ script ghi), `ledger.md` (chỉ ghi thêm) |
| Script quyết định thứ tự | `P next` cho biết bước tiếp theo của từng asset |
| Giao việc bằng file | `P brief <id>` sinh brief, in JSON (`role`, `agent`, `model`, `resume`, `brief`, `report`) |
| Báo cáo contract | Dòng `KEY: value` ở đầu file report. Script kiểm định dạng, không đoán |
| `pipeline.toml` | Nơi duy nhất định nghĩa bước, agent, model, gate, output bắt buộc |
| Version theo bước | `<bước>/vN/` có `final/`, `work/`, brief, report |
| Resume | Vòng sửa ≤ `resume_rounds` (2): gửi tiếp cho đúng worker cũ. Sau đó: worker mới, có thể dùng `escalate_model` |
| Ruling | Quyết định Producer tự đưa ra được ghi bằng `P rule "<id>: <quyết định> — <lý do> — <cái giá nếu sai>"` |
| Cảnh báo đổi nguồn | Concept hoặc art direction đổi sau khi asset bắt đầu → cảnh báo ⚠, hỏi anh làm lại hay giữ |
| Trang duyệt local | `P serve` (127.0.0.1:8765): nút Duyệt / Cần sửa / Ghi chú, xem GLB xoay được |
| Hook và lệnh phụ | SessionStart chạy `P next --session`; `dashboard`, `validate`, `cleanup` (dry-run trước), `archive` |

## 3. Pipeline 6 bước (`pipeline.toml`)

| # | `id` | Worker | Reviewer | Gate |
|---|---|---|---|---|
| 1 | `blockout` | `zps-3dp-blockout` | `zps-3dp-review-blockout` | `review_human` |
| 2 | `views_front` | `zps-3dp-concept-views` | `zps-3dp-review-views` (chỉ front) | `review` |
| 3 | `views_rest` | `zps-3dp-concept-views` | `zps-3dp-review-views` (cả bộ) | `review_human` |
| 4 | `model` | `zps-3dp-3d-artist` | `zps-3dp-review-clay` | `review_human` (DUYỆT 1) |
| 5 | `texture` | `zps-3dp-texture-artist` | `zps-3dp-review-texture` | `review` |
| 6 | `assemble` | `zps-3dp-3d-artist` | `zps-3dp-review-texture` (bản cuối trên model) | `review_human` (DUYỆT 2) |

- **Producer sắp xếp reviewer** qua script. Worker không gọi reviewer, không gọi agent khác.
- Gate `review_human` (mới): reviewer PASS → `waiting_human` → anh (hoặc chính sách) duyệt → bước sau. Bỏ `final_human_gate`, vì `assemble` đã có gate này.
- Mỗi bước khai báo danh sách loại `TOP_FIX` được phép (mục 6).

## 4. Ai duyệt

**Chính sách trong profile** (Project Setup hỏi anh lúc khởi tạo):

```yaml
approvals:
  blockout:   human    # human | reviewer
  views_rest: human
  model:      human
  assemble:   human    # luôn human, không đổi được
```

- Khóa của `approvals` là id của bước có gate người duyệt: `blockout`, `views_rest`, `model`, `assemble`. Script từ chối khóa khác.
- `views_front` luôn chỉ do reviewer duyệt.

- `reviewer`: reviewer PASS (không còn `major`, `unclear`) thì script tự duyệt, ghi ledger "reviewer duyệt theo chính sách dự án".
- Gợi ý lúc khởi tạo: pilot để `human` hết. Sau pilot anh đổi khi đã chạy ổn.
- **Đổi chính sách:** anh nói trong chat. Producer chạy `P approvals set <bước> <human|reviewer> --by "<nguyên văn>"`. Script kiểm giá trị, từ chối đổi `assemble`, ghi profile và ledger. Có hiệu lực ngay, không cần phiên mới.
- **Ngoại lệ theo lô:** anh nói trong chat. Producer chạy `P delegate <bước> <id> ...`. Thứ tự ưu tiên: `delegate` > `approvals` > `human`.
- Mọi lần duyệt ghi **ai duyệt** (anh, chính sách, ủy quyền). Anh bấm Cần sửa được bất cứ lúc nào.

## 5. Xem kết quả

Anh nói trong chat. Producer chạy script và chuyển đường dẫn cho anh. Producer không mở file.

| Anh nói | Producer chạy | Anh nhận |
|---|---|---|
| "Tiến độ?" | `P dashboard` | Bảng ngắn: asset, bước, trạng thái, việc anh cần làm |
| "Cho anh xem <asset>" | `P show <id>` (mới) | Một file HTML: concept, sheet duyệt, render, GLB, tóm tắt report các bước |
| "Xem <bước> v<N> của <asset>" | `P show <id> --step <bước> --version <N>` | HTML của đúng version đó |
| "Duyệt cả lô" | `P serve` | Trang duyệt local |
| "Vì sao …?" | Gọi agent của bước đó trả lời | Câu trả lời ngắn |

- Producer đưa file cho anh bằng tool gửi file (`SendUserFile`). Nội dung không vào context Producer.
- `P show --bundle`: nhúng ảnh (thu cạnh dài về tối đa 1024 px; crop giữ nguyên) và GLB nhỏ vào một file HTML, để xem trên điện thoại. Khi anh dùng Remote Control, Producer tự thêm `--bundle`.
- Duyệt bằng nút, khoanh vùng, xem toàn màn hình và zoom: Review Board (`docs/review-board.md`, D19). Trên điện thoại: bật `review_board: local+remote`.

## 6. Contract của reviewer

```
VERDICT: PASS | FIX | ESCALATE
RUBRIC: <key>=pass|fail|unclear; ...
COUNTS: blocker=N; major=N; minor=N
TOP_FIX: <loại>: <chi tiết>
FINDINGS:
- [blocker|major|minor] <ở đâu> — <sai gì> — <sửa thế nào>
```

| Điều kiện | VERDICT |
|---|---|
| Không `blocker`, `major`, `unclear` | PASS |
| Có `blocker` hoặc `major` sửa được | FIX |
| Lựa chọn thẩm mỹ anh phải quyết, hoặc rubric mâu thuẫn brief | ESCALATE |
| Có `unclear` | FIX, `TOP_FIX: need_evidence: <ảnh cần thêm>` |

**Loại `TOP_FIX` theo bước** (khai báo trong `pipeline.toml`; script từ chối loại khác):

| Bước | Loại |
|---|---|
| `blockout`, `model` | `structure`, `param`, `need_evidence` |
| `views_front`, `views_rest` | `regen`, `need_evidence`. `note_exception`, `note_texture` chỉ ghi chú, không gây FIX |
| `texture` | `repaint`, `fix_uv_mesh`, `meshy_regen` (→ `waiting_human`), `need_evidence`. `note` chỉ ghi chú, không gây FIX |
| `assemble` | `repaint`, `fix_uv_mesh`, `need_evidence`. `note` chỉ ghi chú, không gây FIX |

- `fix_uv_mesh`: script chạy `redo --step model`. DUYỆT 1 lại.
- `repaint` ở bước `assemble`: script chạy `redo --step texture`. Khi `texture` được duyệt lại, `assemble` tự chạy lại. Bộ đếm vòng của `texture` giữ nguyên, không đặt lại. Trần 3 vòng vẫn áp dụng.
- **Gọi Meshy** (D20.14):
  1. Mỗi asset gọi Meshy một lần. Chỉ Texture Artist gọi Meshy.
  2. Lỗi kỹ thuật (hết thời gian chờ, lỗi mạng, lỗi API không trừ credit) không tính là một lần gọi. Texture Artist thử lại, tối đa 3 lần (như D8.3). Sau 3 lần lỗi: `STATUS: BLOCKED`, Producer hỏi anh.
  3. Texture chưa đạt: Texture Artist sửa qua các vòng review thường.
  4. Không sửa được (reviewer trả `TOP_FIX: meshy_regen`, hoặc report có `UNFIXABLE: yes`): script đặt `waiting_human`. Anh duyệt lần gọi thứ hai. Chỉ khi đó brief tiếp theo mới ghi "được gọi Meshy thêm một lần". Script không tự cho.
  5. Script đọc `MESHY_CALLS` trong report. Nếu số lần gọi vượt số lần được phép, script báo lệch.

**Contract của worker** giữ như skill nền: `STATUS / OUTPUT / RUBRIC / ISSUES`. Thêm `PROFILE_HASH: <hash>`: hash của profile đã dùng (`docs/project-profile.md` §3). Texture Artist có thêm `UNFIXABLE: yes|no` và `MESHY_CALLS: <n>` (số lần gọi Meshy có trừ credit, cộng dồn cho asset).

**Brief bước `texture`:** script sinh brief từ các `final/` đã duyệt (`blockout` để đọc `sources.json`, `model`, `views_rest`) và file concept trong `_approved/<id>/`. Script chép mục `ISSUES` của report bước `model` đã duyệt vào brief. Không có file handoff.

## 7. Vòng sửa (D11, bằng script)

1. Tối đa `max_fix_rounds` = 3.
2. **Dừng sớm:** nếu `blocker + major` không giảm so với vòng trước → `waiting_human`, ghi "không tiến bộ ở vòng N".
3. **Bản tốt nhất:** script ghi version có `blocker + major` thấp nhất (bằng nhau thì version cũ hơn). Brief vòng sửa trỏ tới bản tốt nhất. Khi gửi anh hoặc khi dừng, gửi bản tốt nhất.
4. Feedback của anh (`redo`) đặt lại bộ đếm (skill nền đã có).
5. **Các trạng thái chuyển lên anh:**
   - **Hết vòng 3 mà vẫn FIX:** script quay về bản tốt nhất (D11) và đặt `waiting_human`. Trang duyệt hiện bản đó và các finding còn mở. Anh chọn Duyệt, Cần sửa (bộ đếm đặt lại theo đợt feedback) hoặc Ghi chú.
   - **`VERDICT: ESCALATE`:** script đặt `waiting_human` ngay, không chạy thêm vòng. Trang duyệt hiện lý do của reviewer.
   - **`TOP_FIX: need_evidence`:** script giao worker của cùng bước một vòng ngắn. Vòng này chỉ render các ảnh reviewer xin. Vòng này không tính vào 3 vòng. Nếu cùng bước xin `need_evidence` lần thứ hai, script đặt `waiting_human`. Bộ đếm này đặt lại theo từng đợt feedback của anh, giống bộ đếm 3 vòng (D20.15).
   - **Xin gọi Meshy lần hai** (`meshy_regen` hoặc `UNFIXABLE: yes`): script đặt `waiting_human`. Chỉ khi anh duyệt, brief sau mới cho gọi thêm một lần (D20.14, mục 6).

## 8. Thư mục

```
<thư mục concept>/_approved/<id>/      KHU 1 — ĐẦU VÀO. Anh chép vào. Pipeline chỉ đọc
  concept_albedo.png, concept_shadow.png, asset-card.yaml, <id>.material.md,
  <id>.layout.md                       chỉ khi profile có `has_map: true`

production/                            KHU 2 — LÀM VIỆC. Chỉ script và agent ghi
  PROJECT-PROFILE.yaml, pipeline.toml, ledger.md, dashboard.md
  rubrics/<loại>.md
  assets/<id>/
    status.json, brief.md, rubric.md, feedback.md, feedback/
    <bước>/vN/{final, work, brief-*.md, report-*.md}
    <bước>/_rejected/vN/

deliver/<id>/                          KHU 3 — KẾT QUẢ CUỐI ĐÃ DUYỆT
  nội dung `assemble/vN/final/` đã duyệt: README.md, model/, texture/, review/
```

- **Chép khi duyệt:** chỉ khi `assemble` được duyệt (DUYỆT 2), script chép `assemble/vN/final/` sang `deliver/<id>/`. Các bước giữa nằm lại trong `production/`.
- **Làm lại sau DUYỆT 2:** README trong `deliver/<id>/` ghi "đang làm lại". Bản cũ giữ cho tới khi có bản duyệt mới.
- **Dọn version:** khi một bước được duyệt, script chuyển các version khác của bước đó sang `<bước>/_rejected/`.
- **Xóa:** chỉ qua `P cleanup`, chỉ khi asset đã xong, chạy dry-run trước, xóa thật khi anh đồng ý. Xóa `work/` của `_rejected/`; giữ preview và report. Sau đó `P archive`.
- **Agent chỉ đọc đường dẫn trong brief.** Mọi file agent có dòng: "Chỉ đọc file và thư mục brief chỉ định. Không quét thư mục asset."
- Bỏ thư mục `View Concept/` riêng. Brief bước sau trỏ thẳng tới `final/` đã duyệt của bước trước.

## 9. Nhận việc (intake)

- Giữ cách của skill nền: chỉ đăng ký khi anh bảo; `P intake` liệt kê theo nhóm; `--all`, `--priority`.
- **Thêm kiểm:** `asset-card.yaml` hợp lệ (`check_card.py`: trường bắt buộc, giá trị hợp lệ, `type` có rubric); đủ file bắt buộc (albedo, có bóng, thẻ, material handoff); profile hợp lệ (`check_profile.py`).
- **MAP-LAYOUT:** nếu profile có `has_map: true`, intake bắt buộc có `<id>.layout.md`. Nếu `has_map: false`, thẻ bắt buộc có `size_m: {w, d, h}` (mét); `check_card.py` kiểm trường này. Blockout lấy W×D×H từ `size_m` (D20.9).
- Thiếu hoặc sai → không đăng ký. Producer báo anh theo nhóm lỗi.
- Loại asset lấy từ `type` trong thẻ (`building`, `prop`, `tree`, `rock`), không dùng một `type` cố định. Loại `character`, `creature`: báo v1 chưa hỗ trợ (D9).

## 10. Thông số và rubric

| Loại thông tin | Nằm ở |
|---|---|
| Số và quy ước script dùng | Preset → profile → thẻ asset (D13) |
| Tài liệu style | `art-direction/` (AD giữ, tag `steps:`), như skill nền |
| Tiêu chí chấm chung của bước | Trong file agent reviewer |
| Tiêu chí chấm riêng theo loại asset | `production/rubrics/<loại>.md`, chia mục theo bước. Anh duyệt một lần (`status: approved`) |

- `visual_checks` bỏ khỏi profile, chuyển vào rubric theo loại.
- Số không viết hai lần. Tài liệu art direction có thể nhắc số, nhưng số thật nằm trong YAML. Nếu lệch, YAML thắng.
- Cảnh báo ⚠ khi profile đổi (theo hash), giống cảnh báo art direction đổi.

## 11. GUIDELINE.md

`P init` sinh `GUIDELINE.md` cho dự án (skill nền). Anh gửi cho Concept Artist, View Artist, AD. Thêm:
1. Mẫu `asset-card.yaml` và hướng dẫn từng trường (bắt buộc / bỏ trống thì hiểu thế nào).
2. Danh sách file bắt buộc trong `_approved/<id>/`.
3. Cách làm lúc chốt: Concept Artist soạn thẻ từ những gì đã thảo luận, hỏi anh một lần các trường còn trống kèm gợi ý, viết material handoff, chạy `check_card.py`, rồi báo anh.
4. AD: viết tài liệu style có tag `steps:`. Không ghi số kỹ thuật; muốn đổi số thì đề xuất với anh.

`check_card.py` đi kèm GUIDELINE, để Concept Artist tự kiểm.

## 12. Khởi tạo và phiên mới (D13)

1. Anh gọi Producer. Producer chạy `check_profile.py`.
2. Thiếu profile → nạp skill Project Setup, làm cùng anh (gồm cả câu hỏi `approvals`).
3. Xong → **Producer nhắc anh gõ lệnh xóa context và mở phiên mới** (Claude Code: `/clear`; Codex: `/new`).
4. Producer cũng nhắc mở phiên mới sau khi cập nhật nội dung profile, và khi context đã dài sau một lô.

## 13. Hỏi anh

Sub-agent không chat với anh. Đường duy nhất: worker trả `STATUS: NEEDS_CONTEXT` hoặc `BLOCKED` kèm câu hỏi → asset `blocked` → Producer hỏi anh (hoặc tự bổ sung nếu đã có thông tin, theo skill nền) → ghi vào mục "Làm rõ" của brief → `P retry`.

## 14. Runtime

- Bản Claude: skill nền như hiện tại.
- Bản Codex: adapter riêng (D6.4). Gọi agent qua `collaboration.spawn_agent`, resume qua `collaboration.send_message` (cần thử). Đường dẫn và hook khác. Blender ngoài sandbox, quyền mạng cấp ở phiên gốc.

## 15. Thay đổi script cần làm (tóm tắt)

| Thay đổi | Hàm | Ước lượng |
|---|---|---|
| Gate `review_human`, bỏ `final_human_gate` | `cmd_ingest`, `advance` | ~10 dòng |
| `approvals` trong profile, `P approvals set`, `P delegate` | mới + `cmd_ingest` | ~40 dòng |
| Contract reviewer: `COUNTS`, `TOP_FIX` theo bước, `UNFIXABLE` | `cmd_ingest`, `parse_contract` | ~40 dòng |
| Dừng sớm, bản tốt nhất | `cmd_ingest`, `worker_brief` | ~30 dòng |
| `fix_uv_mesh` → redo model; `meshy_regen` / `UNFIXABLE` → `waiting_human`; đếm `MESHY_CALLS` | `cmd_ingest` | ~20 dòng |
| Chép sang `deliver/` (chỉ khi duyệt `assemble`), chuyển `_rejected/` | `approve_step` | ~30 dòng |
| `P show`, `--bundle` | mới | ~120 dòng |
| `P board prepare` (Review Board, `docs/review-board.md` §6) | mới | — |
| Intake: `check_card`, file bắt buộc, `type` từ thẻ, `check_profile` | `scan_approved`, `cmd_intake`, `create_asset` | ~60 dòng |
| Đọc preset/profile/thẻ, hash profile, cảnh báo profile đổi | mới + `warnings_for` | ~50 dòng |
| Tên `zps-3dp-producer`, đường dẫn | `SKILL.md`, `setup.md` | — |
