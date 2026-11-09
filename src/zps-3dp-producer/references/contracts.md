# Contracts: state, thư mục, format

## Cấu trúc thư mục

```
<thư mục concept>/              # của người dùng, Concept Artist, AD
  GUIDELINE.md                  # quy ước gửi cho agent ngoài pipeline
  _approved/<building-id>/      # người dùng chép concept đã duyệt; script chỉ đọc
  art-direction/README.md       # AD sở hữu; cửa vào, có tag steps: và mục ## Thay đổi

production/                     # trong project Claude Code; chỉ script và subagent ghi
  pipeline.toml                 # workflow, đường dẫn, chuẩn preview
  rubrics/<type>.md             # rubric chung theo loại; dòng đầu status: draft|approved
  ledger.md                     # append-only: sự kiện + RULING
  schedule.md                   # `- YYYY-MM-DD · milestone`
  dashboard.md · review.html    # tự sinh
  assets/<id>/
    status.json                 # chỉ script ghi
    brief.md · rubric.md · feedback.md
    <step>/vN/
      brief-worker.md · report-worker.md · brief-review.md · report-review.md
      final/ · work/ · handoff.md
  archive/<id>/
```

## Các trường status.json đáng chú ý

- `concept_dir`, `concept_mtime`: thư mục concept và thời điểm sửa mới nhất lúc intake. File mới hơn → cảnh báo "concept đổi".
- `started`, `ad_ack`: so với ngày trong `## Thay đổi` của README art direction → cảnh báo "art direction đổi".
- `ack` cập nhật cả hai mốc.

## Art direction trong brief

Script đọc các dòng `- \`file.md\` — ... — steps: a, b` trong phần trước `## Thay đổi` của README. Worker bước X nhận tài liệu có tag X. Reviewer bước X nhận tài liệu có tag X hoặc `review`. Không có README: brief ghi "chưa có art direction".

## State machine (mỗi asset, tại bước `stage`)

| State | Nghĩa | Lệnh đưa ra khỏi state |
|---|---|---|
| draft | rubric loại chưa duyệt | `ready` → todo |
| todo | bước chưa bắt đầu | `brief` → running (tạo vN mới) |
| running | worker đang làm | `ingest` → review / waiting_human / blocked / bước sau |
| review | worker xong, chờ giao reviewer | `brief` → reviewing |
| reviewing | reviewer đang chấm | `ingest`: PASS → bước sau · FIX → fix · ESCALATE → waiting_human |
| fix | cần vòng sửa | `brief` → running (vN+1, resume hoặc model escalate) |
| waiting_human | chờ người dùng | `feedback --action approve` → bước sau hoặc done · `redo` → fix |
| blocked | thiếu context, thiếu output, worker kẹt | `retry` → running |
| done | xong | `archive` |

FIX lần thứ `max_fix_rounds + 1` chuyển sang waiting_human. `redo` của người dùng đặt lại bộ đếm vòng sửa và huỷ duyệt của bước đó cùng các bước sau.

## Contract báo cáo

Worker: bốn dòng đầu của `report-worker.md`, cũng là toàn bộ tin nhắn trả về.
```
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
OUTPUT: <thư mục final/>
RUBRIC: <key>=pass|fail; ...
ISSUES: <tối đa 2 vấn đề hoặc none>
```

Reviewer: mở đầu `report-review.md`; tin nhắn trả về chỉ gồm hai dòng đầu.
```
VERDICT: PASS | FIX | ESCALATE
RUBRIC: <key>=pass|fail; ...
FINDINGS:
- [critical|minor] <ở đâu> — <sai gì> — <sửa thế nào>
```

Script đọc các dòng `KEY: value` trong 40 dòng đầu. Thiếu hoặc sai giá trị thì `ingest` báo lỗi, không đoán.

## Nguồn tham khảo của thiết kế

- obra/superpowers, skill `subagent-driven-development`: ledger sống sót qua compact, brief và report bằng file, contract trạng thái của worker, giới hạn vòng sửa rồi đổi subagent với model mạnh hơn, ghi lại mọi ruling.
- Anthropic, "How we built our multi-agent research system": mỗi subagent cần mục tiêu, format output, hướng dẫn dùng tool, ranh giới nhiệm vụ.
