# Contracts: state, thư mục, format

## Cấu trúc thư mục

```
<thư mục concept>/              # của người dùng, Concept Artist, AD
  GUIDELINE.md                  # quy ước gửi cho agent ngoài pipeline
  _approved/<building-id>/      # người dùng chép concept đã duyệt; script chỉ đọc
  art-direction/README.md       # AD sở hữu; cửa vào, có tag steps: và mục ## Thay đổi

production/                     # trong project Claude Code; chỉ script và subagent ghi
  pipeline.toml                 # workflow, đường dẫn, chuẩn preview, [limits]
  PROJECT-PROFILE.yaml          # Project Setup viết; brief từ chối khi sai
  policy.yaml                   # ai duyệt; chỉ P approvals / P delegate ghi
  preflight.json                # P preflight ghi; P next, P brief đọc
  hash-cache.json               # tree_hash nhớ theo thư mục: {<thư mục>|<skip>: {sig (đường dẫn, mtime_ns, cỡ của từng file), hash}}; script ghi, xóa được, mất thì tính lại
  pids/<tài nguyên>/<id>.pid    # run_tool.py (Blender) và gen_image_codex.py (Codex) ghi <id>-<pid>.pid mỗi lần chạy và xóa khi xong; P next đếm PID còn sống
  rubrics/<type>.md             # rubric chung theo loại; dòng đầu status: draft|approved
  ledger.md                     # append-only: `- <giờ> · <runtime> · <sự kiện>` + RULING
  session.json                  # P next --session ghi JSON hook SessionStart nhận qua stdin: {session_id, source, transcript_path, at, transcripts[]} (D30.10)
  .lock                         # mỗi lệnh ghi và mỗi nút trên review page giữ flock file này
  schedule.md                   # `- YYYY-MM-DD · milestone`
  dashboard.md                  # tự sinh
  show/<id>[-<step>-vN][-bundle].html  # P show: trang board tĩnh
  board/                        # trang claude.ai: remote.json (url, lần đẩy, dòng đã kéo), push/<push>/, inbox/
  assets/<id>/
    status.json                 # chỉ script ghi
    brief.md · rubric.md · feedback.md
    feedback/<step>-vN-<k>/     # một lần gửi có khoanh: regions.json, ảnh đã khoanh <tên ảnh>.png
    custom_parts.py             # D32: hàm `custom` riêng của asset (Python thuần, chỉ math), worker blockout/model viết (dòng CUSTOM_PARTS: của brief); D29 giữ (D32.3)
    purge-manifest.json         # D29: đã xóa gì: {asset, at, source (approve|purge), by, assemble, freed_bytes, zip, deleted[] (đường dẫn trong assets/<id>/), deleted_other[] (đường dẫn trong production/: show, board/push, pids), thumbnails[]}
    <step>/vN/
      brief-worker.md · worker-out.md · brief-review.md · review-out.md · findings.json
      review/sheet.png, sheet-<n>.png, sheet.json, summary.json  # D31.1, D38.5, D38.6: mỗi trang sheet tối đa 8 ô, trang 2 trở đi là sheet-2.png, ...; sheet.json: nhãn ô → {src, page, box}; ô crop 1:1 nằm trong sheet-crops/; summary.json: số của từng part và của bước, ghi khi dựng brief reviewer; sheet-<b|c>.png cho phương án param
      final/ · work/ · review/evidence-<k>/
      work/custom_mesh/<part>.json  # D32.2: lưới của hàm trong custom_parts.py, custom_mesh.py ghi; Blender dựng từ đây
  archive/<id>/
```

## Các trường status.json đáng chú ý

- `concept_dir`: thư mục `_approved/<id>/`.
- `inputs[<step>]["vN"]`: đầu vào khi sinh brief vN: `{<bước trước đã duyệt>: {"v", "hash"}, "concept", "card", "profile", "art_direction"}`. `profile` là `PROFILE_HASH` của brief; `ingest` so report với giá trị này. `gen_image_codex.py` thêm `image_model_requested` và `image_model_actual` (chuỗi, nhiều giá trị nối bằng ", "; không biết model thực tế → "không có số", D28.1). Hai khóa này là chuỗi, không phải dict, vì mọi dict trong `inputs` là bản của bước trước.
- `approved`, `approved_hash`, `rejected`: version đã duyệt, sha256 của `final/` lúc duyệt, các version khác của bước. `redo` xóa cả ba từ bước đó trở đi. `final/` đã duyệt bị sửa → `brief` và `ingest` bước sau báo lỗi.
- `locked[<bước>]`: sha256 của file `lock` của bước (`model`: `final/<id>-untextured.glb`) lúc duyệt; khóa mesh (D20.7). Mở lại bước đó (`redo`, `fix_uv_mesh`) thì xóa cùng `approved`.
- `stale["<step> vN"] = "<bước trước> vM"`: vN dựng từ bản vM không còn là bản duyệt (so theo hash). Script tính lại khi sinh brief, khi duyệt, khi `redo`; trang duyệt hiện "dựng từ … — cũ".
- `sources`: hash concept (theo nội dung, trừ thẻ), thẻ, profile lúc giao việc đầu tiên. Khác hiện tại → cảnh báo "concept/thẻ/profile đổi sau khi bắt đầu".
- `started`, `ad_ack`: so với ngày trong `## Thay đổi` của README art direction → cảnh báo "art direction đổi". `ack` đặt lại `sources` và `ad_ack`.
- `fix_round`, `fix_base`, `round_versions`: vòng sửa của đợt feedback, bản gốc (bản tốt nhất), các version đã chấm trong đợt.
- `evidence`, `evidence_used`: vòng bằng chứng đang chạy (`version`, `k`, `hash` của `final/`; `served: true` khi script tự lấy ảnh; `agent_id`: reviewer đã xin ảnh đó) và số lần đã xin trong đợt.
- `evidence_served` (D31.1): số lần script tự lấy ảnh có trên đĩa cho `need_evidence` trong đợt, không giao worker, không tính vào `evidence_used`. Tối đa `[review] served_evidence` của `pipeline.toml`; quá thì sang vòng worker như cũ. Reviewer xin bằng `viewing_condition: xin ảnh <nhãn ô>[ box x0,y0,x1,y1]` (tỉ lệ 0–1); nhãn ô, ở bất kỳ trang nào, lấy từ `vN/review/sheet.json` của `review_sheet.py` (`src`: file của ô; ô `…_crop` là file crop 1:1). Có `agent_id` thì lần giao reviewer kế resume đúng reviewer đó với brief ngắn `vN/review/evidence-<k>/brief-review.md` (ảnh, id cho `PRIOR`, id finding kế), rồi xóa `agent_id`. Reviewer chỉ được resume trong một lượt chấm của một version. Không có `agent_id`, giao lại vì kẹt, version mới: reviewer mới, brief đủ.
- `offer`, `label`: version đưa người dùng duyệt và nhãn ("chưa đạt" khi chưa qua).
- `offer_key`, `offers`: khóa của lần đưa duyệt đang chờ (`<step>-vN-<số lần đưa>`) và bộ đếm. Trang gửi khóa nó đã hiện; khóa khác khóa hiện tại thì script bỏ qua quyết định (và ghi chú có khoanh).
- `decisions["<step> vN"]`: quyết định Duyệt / Cần sửa đã nhận, kèm `offer`; quyết định sau cho cùng version bị bỏ qua, trừ Cần sửa cho bản đã duyệt khi lệnh không nêu khóa. Quyết định nêu đúng khóa đã có quyết định luôn bị bỏ qua, dù tới từ trang local hay remote. Script xóa khóa này mỗi lần đưa vN cho người dùng duyệt, nên một lần đưa nhận một quyết định.
- `pending_redo[<bước>]`: danh sách Cần sửa gửi lúc asset `running`, `reviewing` hoặc `evidence_running`: `{text, at, offer, marks[], folder}`. Lần `ingest` kế áp dụng mọi mục thành finding `H<n>` trên version vừa ingest rồi đưa asset vào vòng sửa; reviewer PASS ở lần ingest đó không duyệt bước. Bước sau bước đang chạy bị từ chối như cũ.
- `worker_agent_id`: subagent worker để resume vòng sửa. Mở lại một bước khác bước đang chạy thì xóa, vì worker cũ có context của bước khác.
- `reopened[<loại>]`: số lần reviewer mở lại bước trước bằng loại `TOP_FIX` đó (`fix_uv_mesh`) trong đợt feedback. Cùng loại lần thứ hai → `waiting_human`; loại khác không tính. `redo` của người dùng xóa hết.
- `prior[<bước>]`: bản đã duyệt của bước sau khi một bước trước nó làm lại. Brief lần dựng đầu của bước đó trỏ tới bản này để giữ phần không đổi. Duyệt bước đó thì xóa.
- `ask`: câu hỏi Meshy đang chờ người dùng (`kind` = `meshy_regen` | `mesh_changed`, `budget` = tên file budget, `next` = `fix` | `todo`, `base`, `new_round`). Duyệt = gọi thêm một lần (`max_credits` + giá); `P meshy <id> paint` = VẼ MỚI. Trả lời xong thì xóa.
- `paint_for`: 12 ký tự đầu hash mesh mà người dùng chọn VẼ MỚI; brief `texture` của mesh đó ghi `MODE: VẼ MỚI`.
- `meshy_price`: giá một lần retexture, đọc từ `gen_api.py texture --dry-run` khi sinh brief.
- `texture_choice`: chế độ người dùng chọn bằng `P texture-mode` (D30.11): `{mode: auto|meshy|paint, by, at}`. Không có = `auto`: chế độ `texture_default` của `policy.yaml` (`meshy | paint`, D34.2; thiếu khóa = giá trị của template). `gate()` của bước texture đọc trường này.
- `texture_mode`: chế độ texture script chọn lần cuối (D30.11): `{mode, reason, mesh}`, `mode` là `Meshy SỬA` hoặc `VẼ MỚI`, `mesh` là 12 ký tự đầu hash mesh. Ledger ghi một dòng khi giá trị này đổi.
- `purged`: `{at, manifest, freed_bytes, zip}` sau khi xóa file trung gian (D29). Có trường này thì `redo` bị từ chối.
- `keep_files`: giờ `P keep` trước DUYỆT 2; lần duyệt đó không xóa, rồi script bỏ trường. `purge_hold`: `ab` khi `production-<runtime>/` chưa có kết quả so A/B; `P next` nhắc tới khi có kết quả. `policy.yaml`: `purge` (`on_approve` | `off`), `purge_zip` (thư mục).
- `blocked_from`: state (`todo`, `fix`) trước khi brief chặn asset; `retry` trả về đúng state đó.
- `direct_rounds`, `direct_names`: số vòng trả thẳng đã dùng và bộ tên check fail của vòng trước. Đặt lại khi một version không còn check fail, khi sang bước khác, khi `redo`.
- `dispatch_out`: dòng JSON của lần giao agent đang chạy. `brief` gọi lại khi agent còn chạy thì in lại đúng dòng này, không làm việc khác.
- `retry_why`: lý do `blocked` của lần dựng ngay trước ("thiếu output: X" hoặc ghi chú). `retry` resume worker cũ với một mục ngắn trong brief. Xóa ở lần `ingest` kế.
- `dispatches`: mỗi lần giao subagent `{step, v, role, model, at}`; `model` là model thật của runtime (`runtime.json` `models`), `null` = model của phiên; `at` tính tới giây. `brief` gọi lại khi subagent chưa trả về thì không thêm lần giao. `ingest` đóng lần giao cùng bước, version và vai trò: `ingested` (giờ ingest), `tokens` (`--tokens N`), `duration_ms` (`--duration-ms M`), `after` (state sau ingest); không có số thì `null`, ledger ghi "không có số". `P stats` tính khoảng chờ Producer từ `ingested` của lần trước tới `at` của lần sau, khi `after` là `todo`, `review`, `fix` hoặc `evidence`. Lần giao reviewer có thêm `scope` (`full` | `fix`, D31.2), để `P stats` tách vòng đầu, vòng sửa, vòng chấm cuối (D31.4), và `evidence` (k) khi nó chấm tiếp một vòng bằng chứng. Không có `scope` (lần giao cũ): reviewer đầu tiên của bước là vòng đầu, các lần sau là vòng sửa. Thời gian bước: `at` của worker đầu tiên tới `approved_at`, chỉ khi bước đang được duyệt. Chờ anh: `offer_log` từ `at` tới `decided`.
- `session.json`: `source` là của lần mở phiên gần nhất (`startup`, `resume`, `clear`, `compact`). `transcripts` gom mọi transcript của phiên chính, không trùng. `P stats` cộng `usage` của từng message một lần (theo `message.id`): `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. Bỏ dòng `isSidechain` và dòng hỏng. Token Producer của bước là các message có `timestamp` trong khoảng thời gian bước. Hai asset chạy cùng lúc thì khoảng chồng nhau, nên một message được tính cho cả hai.
- `offer_log`: mỗi lần đưa người dùng duyệt hoặc hỏi `{key, step, v, why, verdict, at}`; quyết định Duyệt / Cần sửa / VẼ MỚI của người dùng thêm `decision`, `decided`. Ghi chú không phải quyết định. `P compare` đọc trường này.
- `approved_at[<bước>]`: lúc bước được duyệt.
- `dispatches[].usage`: ghi lúc `ingest` từ transcript của subagent: `{input, output, cache_read, cache_creation, duration_ms}`. `tokens` là tổng bốn số đầu. Không đọc được transcript thì `usage: null`. Không có khóa `usage` là lần giao từ bản cũ. Số đã lưu thì không đọc lại; `P stats` chỉ đọc lại transcript cho lần giao còn thiếu `tokens` hoặc `duration_ms`.
- `producer_usage[<bước>]`: ghi lúc bước được duyệt, cùng khoảng thời gian `P stats` dùng: `{tokens, from, to}`. Không có số thì là chuỗi lý do. Bước script không có lần giao: khoảng của nó bắt đầu lúc bước trước được duyệt.
- `deliver/<id>/RUN-REPORT.md`: bảng thời gian và token thật của từng bước, `P report <id>` ghi. Chỉ ghi khi asset `done`: tự động ngay sau khi chép gói, và khi chạy `P report <id>` lại. Mỗi dòng một bước đã chạy (kể cả bước script), dòng cuối là tổng. `Version` là số version đã dựng; `Vòng sửa` là số version trừ một; `Lần giao` là mọi lần giao subagent của bước, kể cả lần xin evidence và lần giao lại vì kẹt; `Kẹt` là số mục của `stalls`; `Model` là model của worker / reviewer. `Credit Meshy` là `used_credits` của `texture/budget-*.json`. `Gọi Codex` là số lần `gen_image_codex.py` bắt đầu một lệnh `codex exec` ở mọi version của bước (dòng `start` trong `vN/heartbeat.log`): gen lại một file là thêm một lần, một lần gọi `--batch` cho nhiều ảnh là một lần. Version không có `heartbeat.log` ghi "không có số". Số không có thì ghi "không có số" và lý do một lần dưới bảng. Dấu `*` ở token Producer: hai asset chạy cùng lúc, token tính chung. `P report` không có id in một dòng mỗi asset và tổng lô; tổng lô đọc transcript của Producer để tính mỗi message một lần, và không có transcript thì ghi "không có số" khi các asset chồng thời gian.

## Runtime và A/B

`runtime.json` trong thư mục skill (build ghi): `runtime`, `suffix`, `models`, `agent_file`. `PRODUCER_RUNTIME` ghi đè; cây `src/` là `src`. `PRODUCER_ROOT=production-<runtime>` chỉ nhận lệnh ghi của runtime đó; gói cuối vào `deliver-<runtime>/`.

`ab/` ở gốc project (chung hai runtime):
- `mapping.json`: `{"assets": {<id>: {"A": <runtime>, "B": <runtime>}}}`, nhãn ngẫu nhiên, gán một lần cho asset có ở cả hai thư mục.
- `preferences.jsonl`: mỗi lần bấm "Bản nào tốt hơn" `{asset, choice: A|B|tie, text, by, at}`; dòng cuối của asset là lựa chọn.
- `judge/<id>/concept/`, `judge/<id>/o<k>/{X,Y}/`: bản chép ảnh gói cuối; lần 1 X = A, lần 2 X = B. `brief.md`, `judge-out.md` (`WINNER: <tiêu chí>=X|Y|tie; …`, `EVIDENCE_OPENED`), `result.json` (theo nhãn A/B). Hai lần lệch nhau thì tiêu chí đó hòa.
- `compare.md`: bản cuối của `P compare`.

## Budget Meshy

`assets/<id>/texture/budget-<sha256 mesh[:12]>.json`, định dạng kit `{"max_credits": N, "used_credits": U}`. Chỉ script Producer và `gen_api.py` (qua `meshy_call.py`) ghi. Brief `texture` đầu tiên của một hash mở file với `max_credits` = giá một lần; nếu hash khác đã tiêu credit thì `max_credits: 0` và hỏi người dùng (mesh đổi). Số lần còn gọi = `(max − used) / giá`, in ở dòng `MESHY_CALLS` của brief.

## Art direction trong brief

Script đọc các dòng `- \`file.md\` — ... — steps: a, b` trong phần trước `## Thay đổi` của README. Worker bước X nhận tài liệu có tag X. Reviewer bước X nhận tài liệu có tag X hoặc `review`. Không có README: brief ghi "chưa có art direction".

## State machine (mỗi asset, tại bước `stage`)

| State | Nghĩa | Lệnh đưa ra khỏi state |
|---|---|---|
| draft | rubric loại chưa duyệt | `ready` → todo |
| todo | bước chưa bắt đầu | `brief` → running (tạo vN mới) |
| running | worker đang làm | `ingest` → review / waiting_human / blocked / bước sau · có JSON `fail`/`error` trong `final/review/{gates,checks}/` hoặc `final/review/{join,unwrap}.json` (tool model ghi hai file này ngoài `checks/`) mà không có `ACCEPTED_FAIL` hợp lệ → fix (không giao reviewer, D31.3); hết `max_direct_rounds`, hoặc bộ tên fail y hệt vòng trả thẳng trước → waiting_human |
| review | worker xong, chờ giao reviewer | `brief` → reviewing; `ingest` của worker tự giao (in dòng JSON của `brief`) |
| reviewing | reviewer đang chấm | `ingest`: PASS ở `REVIEW_SCOPE: full`, hoặc ở `fix` mà `RUBRIC` không có `not_checked` → bước sau · PASS ở `fix` có `not_checked` → review (reviewer `full` trên cùng version, không gọi worker) · `need_evidence` có ảnh trên đĩa → review (script lấy ảnh) · FIX → fix · `fix_uv_mesh` → fix của `model` · ESCALATE → waiting_human |
| fix | cần vòng sửa | `brief` → running (vN+1, resume hoặc model escalate); `ingest` của reviewer tự giao, trừ khi tài nguyên của bước hết slot |
| evidence | reviewer cần thêm ảnh (`need_evidence`) | `brief` → evidence_running (không tạo version) |
| evidence_running | worker đang render bằng chứng | `ingest` → review · `final/` đổi → blocked |
| waiting_human | chờ người dùng | `feedback --action approve` → bước sau hoặc done; có `ask` thì → fix/todo với thêm một lần gọi Meshy · `meshy <id> paint` → fix/todo · `redo` → fix |
| blocked | thiếu context, thiếu output, worker kẹt; `texture` thiếu key; `assemble.py` fail | `retry` → running · về `blocked_from` · bước script → todo (version mới) |
| done_enabled | xong mọi bước đang bật; bước sau `enabled = false` | `redo` → fix · `retry` → todo của bước sau, khi bước đó đã bật |
| done | xong | `archive` |

status.json của v0.7.1 còn bước `views_front` hoặc `views_rest`: mọi lệnh trên asset đó dừng với một dòng; `P next`, `P validate` nêu `migrate <id>` (`references/setup.md`, mục Nâng cấp từ v0.7.1).
Brief `texture` ở todo/fix có thể đổi state trước khi tạo version: thiếu key → blocked; mesh đổi → waiting_human với `ask`.
`waive <id> F<n>` (D30.1) chạy ở mọi state và không tự đổi state, trừ khi finding đó là finding chặn cuối cùng của bản `fix_base` (fix), bản đang đưa duyệt (waiting_human) hoặc bản xin bằng chứng (evidence): khi đó → review, `rereview` = version đó (reviewer `full` trên chính version đó, base là findings của chính nó, không có `COMPARE`). Ở reviewing: ghi `waive_pending`, áp dụng khi ingest report đó; FIX mà không còn finding chặn sau khi áp dụng → như PASS, và ở vòng `fix` vẫn có thêm reviewer `full`, vì reviewer chưa chấm PASS. Mọi lần chuyển state in dòng JSON giao việc tiếp theo (D30.5).
FIX lần thứ `max_fix_rounds + 1` chuyển sang waiting_human. Vòng trả thẳng của D31.3 không tính vào `max_fix_rounds`: nó có trần riêng `[review] max_direct_rounds` (mặc định 2), và bộ tên check fail y hệt vòng trả thẳng trước chuyển sang waiting_human ngay. Một version không còn check fail đặt lại hai bộ đếm đó. `redo` của người dùng đặt lại bộ đếm vòng sửa và huỷ duyệt của bước đó cùng các bước sau.

## Contract báo cáo

Agent tự ghi report vào đường dẫn `report` của brief; tin nhắn trả về chỉ gồm các dòng brief yêu cầu. Lệnh ghi bị chặn thì agent trả cả report giữa dòng `--- report ---` và dòng `--- end ---`; Producer ghi nguyên văn tin nhắn vào file và chạy `ingest --fallback` (`ab judge --fallback`). Script ghi sự kiện `report_fallback` (vai trò, bước) vào ledger và `fallback: true` vào lần giao. `ingest` và `ab judge` chỉ đọc phần giữa hai dòng đó khi có.

Script đọc dòng `KEY: value` đầu tiên của mỗi khóa trong cả file. Script đọc theo nội dung, không theo hình thức:
- Khóa không phân biệt hoa thường, được in đậm hoặc đặt trong backtick (`**VERDICT:** PASS`).
- Giá trị liệt kê (`VERDICT`, `RUBRIC`, `COMPARE`, `PICK`, trạng thái `PRIOR`) lấy từ chữ đầu, không phân biệt hoa thường. Ghi chú trong ngoặc sau giá trị bị bỏ (`roof=pass (ok)`).
- Dòng thụt lề nối vào giá trị ngay trên nó. Một trường của finding xuống hàng vẫn là một trường.
- `FINDINGS` và `PRIOR` là khối: các dòng `- ` và dòng thụt lề ngay sau, tới khóa kế tiếp. Dòng không thụt lề kết thúc khối. Nếu sau nó còn mục `- F<n>` thì mục đó sẽ mất, nên đó là lỗi và `ingest` nêu đúng dòng.

Sai nội dung thì `ingest` in một dòng `LỖI: <report> sai contract: <lỗi>; <lỗi>`, không đổi state, và đổi tên report thành `<tên>.rejected-<k>.md` (k tăng dần). Đường dẫn report trống để agent viết lại; `P wait` và kiểm kẹt không tính file bị từ chối là report xong.

Worker (`worker-out.md`). Tin nhắn trả về chỉ dòng `STATUS`.
```
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
OUTPUT: <thư mục final/>
RUBRIC: <key>=pass|fail; ...
ISSUES: <tối đa 2 vấn đề hoặc none>
PROFILE_HASH: <chép từ brief>        bắt buộc; khác giá trị trong brief → ingest báo lỗi
FIXED: F<n>, ...                     vòng sửa; chỉ để reviewer đối chiếu
RESOLVED_NOTES: <bước> vN F<k>, ...  ghi chú còn mở của bước trước mà worker đã làm (brief liệt kê), hoặc none
ACCEPTED_FAIL: <file JSON> — <lý do có số>; ...   check fail không sửa được (D31.3), hoặc none
```

`ACCEPTED_FAIL`: một dòng, các mục cách nhau bằng `; `; lý do không chứa `;`. Giữa file và lý do là `—`, `–` hoặc `-` có khoảng trắng hai bên. `<file JSON>` là đường dẫn trong `final/review/{gates,checks}/`, hoặc `final/review/join.json`, `unwrap.json`. `ingest` từ chối mục cho JSON không có trong `acceptable` của bước (`pipeline.toml`), mọi gate cứng (`HARD_GATES` trong code: `inputs.json`, `package.json` là hash; `schema.json`; `qa_export_check.json`; `meshy.json` là topology Meshy; `load_cfg` từ chối `acceptable` có gate cứng), lý do không có số, và mục chưa ghi vào mục `NGOẠI LỆ` của `final/README.md` của chính version đó (mọi bước; `assemble.py` chép các mục này vào Ngoại lệ của README gói cuối). Mục bị từ chối → vẫn là vòng sửa; ledger ghi `ACCEPTED_FAIL từ chối`. Ledger đếm mỗi mục hợp lệ theo bước và theo check (`accepted_fail` trong status.json). Vòng trả thẳng: `fix_base` giữ nguyên (findings của reviewer), `direct` = version check fail (brief sửa từ bản đó); review đầu tiên sau các vòng trả thẳng không có base nên không bị dừng vì "không tiến bộ".

Texture Artist thêm `UNFIXABLE: yes|no`; `yes` → waiting_human với `ask` (`meshy_regen`), hoặc blocked khi bước này không có Meshy.

Script (`report-script.md`, bước có `script` trong `pipeline.toml`, ví dụ `assemble`): `STATUS`, `OUTPUT`, `ISSUES`, `PROFILE_HASH` như worker (`PROFILE_HASH` là tham số cuối của lệnh), rồi `EVIDENCE_OPENED` và `FINDINGS` mỗi điểm fail một finding. `ingest` ghi các finding đó vào `findings.json` của version để trang duyệt hiện. `DONE` → waiting_human; `BLOCKED` → blocked.

Reviewer (`review-out.md`). Tin nhắn trả về chỉ dòng `VERDICT`. Script tự tính `COUNTS` và id của loại `TOP_FIX` kiểu lô; reviewer không ghi hai thứ này.
```
VERDICT: PASS | FIX | ESCALATE
RUBRIC: <key>=pass|fail|unclear|not_checked; ...   not_checked chỉ khi brief ghi REVIEW_SCOPE: fix
TOP_FIX: <loại>[: F<n>[, F<m>]]      chỉ khi FIX; structure ghi id, loại lô chỉ ghi loại
EVIDENCE_OPENED: <nhãn ảnh, file đã mở>
COMPARE: F<n>=better|same|worse; ... vòng sửa: mọi id trong TOP_FIX của bản gốc
PICK: a|b|c                          chỉ khi TOP_FIX của bản gốc là param
RESOLVED_CONFIRMED: <bước> vN F<k>, ... mục RESOLVED_NOTES của worker có bằng chứng trên ảnh, hoặc none
FINDINGS:                            chỉ finding mới, id từ next_id của bản gốc
- F<n> [blocker|major|minor|preference|unclear] <loại>
  region: … | viewing_condition: … | evidence: …
  consequence: … | confidence: high|medium|low
  repair: … | preserve: … | acceptance: …
PRIOR:                               đúng mọi finding đang mở của bản gốc
- F<n>: open|resolved|regressed|superseded | evidence: <nhãn>
```

`ingest` kiểm:
- Finding đủ 8 trường của kit `issue-fields.json` (`region` … `acceptance`). Một trường không được chứa ` | <tên trường>:`.
- `evidence` của finding mới và của `PRIOR … resolved` chứa ít nhất một nhãn trong `EVIDENCE_OPENED` (so chuỗi con, không phân biệt hoa thường, nhãn có hoặc không có đuôi file).
- `PRIOR` có đúng các id đang mở (`open`, `regressed`) của bản gốc. Id mới không trùng id cũ.
- `REVIEW_SCOPE` (D31.2) nằm trong brief reviewer và trong `scope` của lần giao; report không chép lại. `full`: lần review đầu, và bản worker báo `DONE` với mọi finding `blocker`, `major`, `unclear` đang mở đều có trong `FIXED` (`minor`, `preference` còn mở không tính). `fix`: các vòng còn lại.
- `not_checked` trong `RUBRIC`: nhận ở vòng `fix`, từ chối ở vòng `full`.
- `RUBRIC` có mọi key của mục `## <bước>` trong `rubric.md` của asset. Thiếu key là lỗi contract, nêu tên key. Key script đã điền từ JSON thì được bỏ.
- `COMPARE` đủ id trong `TOP_FIX` của bản gốc; `resolved` cần `better`; `worse` cần `regressed`. Id ngoài `TOP_FIX`: bỏ qua và ghi cảnh báo vào ledger, không báo lỗi (D30.4).
- `RESOLVED_NOTES`, `RESOLVED_CONFIRMED`: mỗi mục dạng `<bước> vN F<k>`. `RESOLVED_CONFIRMED` chỉ gồm mục có trong `RESOLVED_NOTES` của report worker cùng version (D27.8).
- `COUNTS`: script tính từ finding đang mở sau khi áp `PRIOR`. Report còn ghi `COUNTS` mà lệch hoặc thiếu mức thì ledger ghi cảnh báo, không từ chối.
- Số key `unclear` trong `RUBRIC` ≤ số finding `unclear` đang mở.
- VERDICT: `PASS` khi không còn `blocker`, `major`, `unclear` đang mở (`preference`, `minor` không chặn). `FIX` khi còn. `PASS` ở vòng `fix` cho bước qua khi `RUBRIC` không có `not_checked`; có thì script giao reviewer `full` trên cùng version.
- `TOP_FIX`: loại nằm trong `top_fix` của bước (trừ loại `note*`) hoặc `need_evidence`; là loại của finding nặng nhất, cùng mức thì `structure`, `fix_uv_mesh` trước. `structure`: reviewer ghi id; đúng một id, hoặc nhiều id khi không có hai finding chung một part. Part là phần `region` trước `:`, tên part trong `part_graph.json`, nhiều part cách nhau bằng dấu phẩy (`roof: …`, `trunk, branch_2: …`), không phân biệt hoa thường. Chung part, thiếu part, id lặp: `ingest` từ chối và nêu lý do. Loại lô: script lấy đủ mọi finding `blocker|major|minor` đang mở của loại đó; reviewer ghi id lệch thì ledger cảnh báo và script dùng id của mình. `need_evidence`: đủ mọi finding `unclear` đang mở, chỉ khi không còn `blocker`, `major`.

Bản gốc của vN là `status.json` → `fix_base` (brief worker vòng sửa ghi). Brief reviewer điền sẵn `PRIOR`, `COMPARE` với `?` để reviewer thay.

## findings.json (mỗi version, chỉ script ghi)

```
{"version": N, "base": M|null, "top_fix": {"kind": k, "ids": [..]}|null, "pick": "a"|null, "next_id": K,
 "findings": {"F1": {"priority", "kind", "status", "first_v", "last_v", "region", …, "acceptance"}}}
```
`resolved_notes` (chỉ khi có): ghi chú của bước trước mà reviewer xác nhận (`RESOLVED_CONFIRMED`), cộng các mục của bản gốc. `assemble.py` bỏ các mục này khỏi "Việc còn mở" của README khi version đó được duyệt. Mỗi file giữ mọi finding từ bản gốc (kể cả đã đóng) cộng finding mới. `first_v`, `last_v`: version finding xuất hiện đầu và được chấm gần nhất. Đang mở: `open`, `regressed`. Đã đóng: `resolved`, `superseded`, `waived`. Finding `waived` (D30.1) có thêm `waived: {by: user|producer, why, at}`; không tính vào `COUNTS`, không cần dòng `PRIOR`, brief sau bỏ qua, reviewer không mở lại.

Finding mới ở bước có `regions` (`pipeline.toml`) mở đầu `region` bằng một tên trong đó; loại mở lại bước trước (`fix_uv_mesh`) thì không. Loại `note*` chỉ ở mức `minor`. Ở bước `views`, front sai là finding `regen` có `region` `front: …`, sửa trong cùng bước: worker gen lại front, rồi gen lại mọi view khác, vì front là chuẩn màu.

`TOP_FIX: fix_uv_mesh: F<n>[, F<m>]` ở `texture` (§6.1): script chép mọi id sang `findings.json` của bản `model` đã duyệt với id mới của bản đó, loại `structure`, và đặt `top_fix` của bản đó là các id mới. Rồi `model` vào vòng sửa từ bản đó, như `redo`. Mở lại `model` xóa khóa mesh; duyệt lại thì khóa mesh mới.

`redo` ghi lời người dùng thành finding `H<k>` (`major`, loại đầu tiên trong `top_fix` của bước) vào `findings.json` của version bị trả về, tạo file nếu chưa có. Reviewer vòng sau ghi `PRIOR` cho `H<k>` như mọi finding.

## Vùng khoanh (review-board.md §4)

Trang gửi `regions`: `[{n, image, shape, coords, note}]`. `n` = 1, 2, 3…; `image` = tên ảnh trên thẻ (vd `review/game_cam.png`, `concept/concept_albedo.png`), không phải đường dẫn; `shape` = `circle` | `rect` | `free`; `coords` theo ảnh gốc, tỉ lệ 0–1: `circle`, `rect` là khung `[x0, y0, x1, y1]`, `free` là `[[x, y], …]` (2–500 điểm); `note` tối đa 500 ký tự; tối đa 50 vùng. Script vẽ vùng lên ảnh gốc, lưu `feedback/<step>-vN-<k>/` (`<step> vN` = thẻ người dùng thấy) với `regions.json` (thêm `id` = `H<n>`, null khi vùng chưa thành finding). Mỗi vùng thành `H<n>` (`major`) ở version nhận quyết định (Duyệt kèm vùng: `minor`, loại `note*` đầu tiên của bước, bước không có thì `note`, để brief bước sau liệt kê), có thêm `mark: {png, n}`; brief worker và reviewer vòng sau liệt kê `<png>: 1 (H2) <note>; …`. Asset không chờ người dùng (và không phải `redo`): chỉ lưu thư mục, không thành finding. Duyệt ở bước không có reviewer (`assemble`) đóng các `H` đang mở của version đó.

## Trang claude.ai (`P board`)

Dữ liệu (ArtifactData), mỗi lần đẩy chỉ tạo dòng mới: `offers/<push>~<id>` (payload thẻ, ảnh là đường dẫn tải lên, `glb_json`), `pushes/<push>` (`at`, `project`, `open`: id → dòng `offers`), `files/<push>` (`{đường dẫn: id asset}`, Producer ghi từ kết quả tải lên). Trang ghi `feedback/<id tự sinh>`: `{aid, key, action, text, step, regions, at}`. `P board pull` đọc `<out_dir>/feedback/*.json` (có hoặc không có khóa `data`), áp mỗi dòng một lần theo `at` qua đúng hàm của `P feedback`, nhớ id đã kéo trong `board/remote.json`. Dòng chỉ được đánh dấu đã kéo khi `act()` áp dụng hoặc bỏ qua vì cũ, hoặc khi dòng sai dạng; dòng bị `act()` từ chối ở lại, in một dòng tên dòng và lỗi, và được thử lại ở lần kéo sau.

## Nguồn tham khảo của thiết kế

- obra/superpowers, skill `subagent-driven-development`: ledger sống sót qua compact, brief và report bằng file, contract trạng thái của worker, giới hạn vòng sửa rồi đổi subagent với model mạnh hơn, ghi lại mọi ruling.
- Anthropic, "How we built our multi-agent research system": mỗi subagent cần mục tiêu, format output, hướng dẫn dùng tool, ranh giới nhiệm vụ.
