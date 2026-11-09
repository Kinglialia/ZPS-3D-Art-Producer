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
  pids/<tài nguyên>/<id>.pid    # worker ghi PID tiến trình Blender; gen_image_codex.py ghi <id>-<pid>.pid mỗi lần chạy; P next đếm PID còn sống
  rubrics/<type>.md             # rubric chung theo loại; dòng đầu status: draft|approved
  ledger.md                     # append-only: sự kiện + RULING
  .lock                         # mỗi lệnh ghi và mỗi nút trên review page giữ flock file này
  schedule.md                   # `- YYYY-MM-DD · milestone`
  dashboard.md                  # tự sinh
  assets/<id>/
    status.json                 # chỉ script ghi
    brief.md · rubric.md · feedback.md
    <step>/vN/
      brief-worker.md · report-worker.md · brief-review.md · report-review.md · findings.json
      final/ · work/ · review/evidence-<k>/
  archive/<id>/
```

## Các trường status.json đáng chú ý

- `concept_dir`: thư mục `_approved/<id>/`.
- `inputs[<step>]["vN"]`: đầu vào khi sinh brief vN: `{<bước trước đã duyệt>: {"v", "hash"}, "concept", "card", "profile", "art_direction"}`. `profile` là `PROFILE_HASH` của brief; `ingest` so report với giá trị này.
- `approved`, `approved_hash`, `rejected`: version đã duyệt, sha256 của `final/` lúc duyệt, các version khác của bước. `redo` xóa cả ba từ bước đó trở đi. `final/` đã duyệt bị sửa → `brief` và `ingest` bước sau báo lỗi.
- `locked[<bước>]`: sha256 của file `lock` của bước (`model`: `final/<id>-untextured.glb`) lúc duyệt; khóa mesh (D20.7). Mở lại bước đó (`redo`, `fix_uv_mesh`) thì xóa cùng `approved`.
- `stale["<step> vN"] = "<bước trước> vM"`: vN dựng từ bản vM không còn là bản duyệt (so theo hash). Script tính lại khi sinh brief, khi duyệt, khi `redo`; trang duyệt hiện "dựng từ … — cũ".
- `sources`: hash concept (theo nội dung, trừ thẻ), thẻ, profile lúc giao việc đầu tiên. Khác hiện tại → cảnh báo "concept/thẻ/profile đổi sau khi bắt đầu".
- `started`, `ad_ack`: so với ngày trong `## Thay đổi` của README art direction → cảnh báo "art direction đổi". `ack` đặt lại `sources` và `ad_ack`.
- `fix_round`, `fix_base`, `round_versions`: vòng sửa của đợt feedback, bản gốc (bản tốt nhất), các version đã chấm trong đợt.
- `evidence`, `evidence_used`: vòng bằng chứng đang chạy (`version`, `k`, `hash` của `final/`) và số lần đã xin trong đợt.
- `offer`, `label`: version đưa người dùng duyệt và nhãn ("chưa đạt" khi chưa qua).
- `decisions["<step> vN"]`: quyết định Duyệt / Cần sửa đã nhận; quyết định sau cho cùng version bị bỏ qua, trừ Cần sửa cho bản đã duyệt. Script xóa khóa này mỗi lần đưa vN cho người dùng duyệt, nên một lần đưa nhận một quyết định.
- `worker_agent_id`: subagent worker để resume vòng sửa. Mở lại một bước khác bước đang chạy thì xóa, vì worker cũ có context của bước khác.
- `reopened[<loại>]`: số lần reviewer mở lại bước trước bằng loại `TOP_FIX` đó (`regen_front`, `fix_uv_mesh`) trong đợt feedback. Cùng loại lần thứ hai → `waiting_human`; loại khác không tính. `redo` của người dùng xóa hết.
- `prior[<bước>]`: bản đã duyệt của bước sau khi một bước trước nó làm lại. Brief lần dựng đầu của bước đó trỏ tới bản này để giữ phần không đổi. Duyệt bước đó thì xóa.

## Art direction trong brief

Script đọc các dòng `- \`file.md\` — ... — steps: a, b` trong phần trước `## Thay đổi` của README. Worker bước X nhận tài liệu có tag X. Reviewer bước X nhận tài liệu có tag X hoặc `review`. Không có README: brief ghi "chưa có art direction".

## State machine (mỗi asset, tại bước `stage`)

| State | Nghĩa | Lệnh đưa ra khỏi state |
|---|---|---|
| draft | rubric loại chưa duyệt | `ready` → todo |
| todo | bước chưa bắt đầu | `brief` → running (tạo vN mới) |
| running | worker đang làm | `ingest` → review / waiting_human / blocked / bước sau |
| review | worker xong, chờ giao reviewer | `brief` → reviewing |
| reviewing | reviewer đang chấm | `ingest`: PASS → bước sau · FIX → fix · `regen_front` → fix của `views_front` · `fix_uv_mesh` → fix của `model` · ESCALATE → waiting_human |
| fix | cần vòng sửa | `brief` → running (vN+1, resume hoặc model escalate) |
| evidence | reviewer cần thêm ảnh (`need_evidence`) | `brief` → evidence_running (không tạo version) |
| evidence_running | worker đang render bằng chứng | `ingest` → review · `final/` đổi → blocked |
| waiting_human | chờ người dùng | `feedback --action approve` → bước sau hoặc done · `redo` → fix |
| blocked | thiếu context, thiếu output, worker kẹt | `retry` → running |
| done_enabled | xong mọi bước đang bật; bước sau `enabled = false` | `redo` → fix · `retry` → todo của bước sau, khi bước đó đã bật |
| done | xong | `archive` |

FIX lần thứ `max_fix_rounds + 1` chuyển sang waiting_human. `redo` của người dùng đặt lại bộ đếm vòng sửa và huỷ duyệt của bước đó cùng các bước sau.

## Contract báo cáo

Script đọc dòng `KEY: value` đầu tiên của mỗi khóa trong cả file. `FINDINGS` và `PRIOR` là khối: các dòng `- ` và dòng thụt lề ngay sau, tới khóa kế tiếp hoặc dòng không thụt lề. Sai thì `ingest` in một dòng `LỖI: <report> sai contract: <lỗi>; <lỗi>`, không đổi state.

Worker (`report-worker.md`). Tin nhắn trả về chỉ dòng `STATUS`.
```
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
OUTPUT: <thư mục final/>
RUBRIC: <key>=pass|fail; ...
ISSUES: <tối đa 2 vấn đề hoặc none>
PROFILE_HASH: <chép từ brief>        bắt buộc; khác giá trị trong brief → ingest báo lỗi
FIXED: F<n>, ...                     vòng sửa; chỉ để reviewer đối chiếu
```

Reviewer (`report-review.md`). Tin nhắn trả về chỉ dòng `VERDICT` và `COUNTS`.
```
VERDICT: PASS | FIX | ESCALATE
RUBRIC: <key>=pass|fail|unclear; ...
COUNTS: blocker=N; major=N; minor=N; preference=N; unclear=N
TOP_FIX: <loại>: F<n>[, F<m>]        chỉ khi FIX
EVIDENCE_OPENED: <nhãn ảnh, file đã mở>
COMPARE: F<n>=better|same|worse; ... vòng sửa: mọi id trong TOP_FIX của bản gốc
PICK: a|b|c                          chỉ khi TOP_FIX của bản gốc là param
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
- `COMPARE` đủ id; `resolved` cần `better`; `worse` cần `regressed`.
- `COUNTS` bằng số finding đang mở sau khi áp `PRIOR`.
- Số key `unclear` trong `RUBRIC` ≤ số finding `unclear` đang mở.
- VERDICT: `PASS` khi không còn `blocker`, `major`, `unclear` đang mở (`preference`, `minor` không chặn). `FIX` khi còn.
- `TOP_FIX`: loại nằm trong `top_fix` của bước (trừ loại `note*`) hoặc `need_evidence`; là loại của finding nặng nhất, cùng mức thì `structure`, `fix_uv_mesh` trước. `structure` đúng một id. Loại khác: đủ mọi finding `blocker|major|minor` đang mở của loại đó. `need_evidence`: đủ mọi finding `unclear` đang mở, chỉ khi không còn `blocker`, `major`.

Bản gốc của vN là `status.json` → `fix_base` (brief worker vòng sửa ghi). Brief reviewer điền sẵn `PRIOR`, `COMPARE` với `?` để reviewer thay.

## findings.json (mỗi version, chỉ script ghi)

```
{"version": N, "base": M|null, "top_fix": {"kind": k, "ids": [..]}|null, "pick": "a"|null, "next_id": K,
 "findings": {"F1": {"priority", "kind", "status", "first_v", "last_v", "region", …, "acceptance"}}}
```
Mỗi file giữ mọi finding từ bản gốc (kể cả đã đóng) cộng finding mới. `first_v`, `last_v`: version finding xuất hiện đầu và được chấm gần nhất. Đang mở: `open`, `regressed`. Đã đóng: `resolved`, `superseded`.

`TOP_FIX: regen_front: F<n>` ở `views_rest` (D22.4): script chép F<n> sang `findings.json` của bản `views_front` đã duyệt với id mới của bản đó, loại `regen`, và đặt `top_fix` của bản đó là id mới. Rồi `views_front` vào vòng sửa từ bản đó, như `redo`. Front duyệt lại thì `views_rest` dựng lại từ đầu. Finding mới ở bước có `regions` (`pipeline.toml`) mở đầu `region` bằng một tên trong đó; loại `regen_front` thì không. Loại `note*` chỉ ở mức `minor`.

`TOP_FIX: fix_uv_mesh: F<n>[, F<m>]` ở `texture` (§6.1): như `regen_front`, nhưng chép mọi id sang bản `model` đã duyệt, loại `structure`. Mở lại `model` xóa khóa mesh; duyệt lại thì khóa mesh mới.

`redo` ghi lời người dùng thành finding `H<k>` (`major`, loại đầu tiên trong `top_fix` của bước) vào `findings.json` của version bị trả về, tạo file nếu chưa có. Reviewer vòng sau ghi `PRIOR` cho `H<k>` như mọi finding.

## Nguồn tham khảo của thiết kế

- obra/superpowers, skill `subagent-driven-development`: ledger sống sót qua compact, brief và report bằng file, contract trạng thái của worker, giới hạn vòng sửa rồi đổi subagent với model mạnh hơn, ghi lại mọi ruling.
- Anthropic, "How we built our multi-agent research system": mỗi subagent cần mục tiêu, format output, hướng dẫn dùng tool, ranh giới nhiệm vụ.
