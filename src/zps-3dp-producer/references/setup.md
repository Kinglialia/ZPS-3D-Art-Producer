# Cài đặt và tuỳ chỉnh

Cần Python 3.11+ (`python3 --version`). Script cần PyYAML, nên chạy trong venv của skill. Việc riêng của runtime (cách gọi agent, hook, quyền, sandbox, lệnh mở phiên mới) nằm trong `references/runtime.md`.

## Cài bộ skill (một lần cho mỗi project, chạy lại khi nâng cấp)

1. Trong repo bộ skill: `python3 build.py`. Lệnh tạo `dist/zps-3dp-claude-v<ver>/` và `dist/zps-3dp-codex-v<ver>/`, và dừng khi một kiểm tĩnh sai.
2. `python3 dist/zps-3dp-<runtime>-v<ver>/install.py --project <thư mục project>`. Lệnh chép hai skill (`zps-3dp-producer`, `zps-3dp-project-setup`) vào thư mục skill của runtime. Bản Claude Code chép thêm file agent vào thư mục agent của project. Thư mục `agents/` trong skill giữ `tools/` và `references/` của từng agent; file agent đọc chúng qua dòng `TOOLS:` của brief, nên bản chép phẳng vẫn đúng đường dẫn. Cài lại thì skill cũ được thay, các thư mục `.deps/` được giữ.
3. Chạy một lần: `bash .claude/skills/zps-3dp-producer/scripts/setup_deps.sh` (tạo `scripts/.deps/venv` với pyyaml, pytest, Pillow, numpy). Rồi `bash .../agents/<agent>/tools/setup_deps.sh` cho bốn agent bước (`zps-3dp-step-blockout`, `-views`, `-model`, `-texture`). Từ đây `P` là python của venv chạy `producer.py`.
4. Làm các việc của runtime trong `references/runtime.md`: hook mở phiên và quyền (Claude Code); rules Blender ngoài sandbox và tin hook của project một lần (Codex).
5. Thêm vào file hướng dẫn luôn được nạp của project (Claude Code: `CLAUDE.md`; Codex: `AGENTS.md`), để skill được dùng kể cả khi người dùng chỉ nói "tiếp tục":
   ```markdown
   Project này dùng skill zps-3dp-producer để điều phối art. Mọi việc về asset, concept trong _approved, feedback, tiến độ: dùng skill zps-3dp-producer, bắt đầu từ output của `producer.py next`.
   ```
6. Mở phiên mới để runtime nạp skill và agent.

Đổi prompt agent hoặc script: sửa `src/` trong repo bộ skill, build và cài lại. Không sửa bản đã cài.

## Lệnh môi trường và chính sách duyệt

- `P preflight`: kiểm Blender (`BLENDER`, rồi Blender.app, rồi PATH), codex CLI (đã test với codex-cli 0.164.0; lệnh gen là `codex exec -s workspace-write --skip-git-repo-check`; ghi phiên bản codex-cli; `codex exec --help` thiếu flag nào skill dùng thì báo một dòng và tắt `codex_image`), `MESHY_API_KEY` trong `paths.env_file` của profile (mặc định `.env`; script không in key), và `preflight.py` của kit khi có (mặc định skill `zps-3d-artist` cạnh skill này; nơi khác: biến môi trường `PRODUCER_KIT=<đường dẫn preflight.py>`). Ghi `production/preflight.json`. Chạy một lần mỗi phiên.
- `P approvals set <bước> <human|reviewer> --by "<nguyên văn>"`: ghi `production/policy.yaml`. `model reviewer` cần `--confirm-spend`. `P approvals set review_board <local|local+remote> --by "<nguyên văn>"`: đổi trang duyệt.
- `P delegate <bước> <id> ... --by "<nguyên văn>"`: reviewer duyệt bước đó cho các asset này. Thứ tự: `delegate` > `approvals` > `human`.
- `[limits]` trong `pipeline.toml`: số tiến trình cùng lúc. `run_tool.py` ghi `production/pids/blender/<id>-<pid>.pid` cho mỗi lệnh Blender và xóa file khi lệnh xong; `gen_image_codex.py` tự ghi `production/pids/codex_image/<id>-<pid>.pid` cho mỗi lần chạy, và `<id>-<pid>-<k>.pid` cho mỗi luồng gen thêm. `P next` chỉ đếm PID còn sống, mỗi asset một lần.
- `run_tool.py`: một lệnh cho mọi tool của worker. Brief có dòng `RUN:` ghi mọi thứ cố định của lần giao (`--blender`, `--agent`, `--version-dir`); worker thêm `[bl] <tool> <đối số>` phía sau. Tên tool tính từ thư mục `TOOLS:`. `bl` chạy tool trong Blender (`-b --python-exit-code 1 --python <tool> -- <đối số>`); không có `bl` thì tool chạy bằng python của `.deps/venv` trong thư mục `TOOLS:`. Tool phải là file `.py` trong `scripts/` hoặc `agents/*/tools/` của skill; đường dẫn khác, kể cả qua `..` hay symlink, bị từ chối với mã thoát 2. Log vào `vN/work/logs/<tool>.log`; lệnh in đúng một dòng `<tool> <pass|fail|error> [đường dẫn]`. Mã thoát 1 khi tool thoát khác 0 hoặc khi JSON kết quả tool vừa ghi có `overall` là `fail` hay `error`. Thiếu `.deps/` thì nó chạy `setup_deps.sh` của thư mục `TOOLS:` với `BLENDER` là Blender của brief. `install.py` gộp allow rule của `run_tool.py` và `assemble.py`; `P preflight` báo khi thiếu.
- `[codex] timeout_s` trong `pipeline.toml`: giây chờ mỗi lần gọi `codex exec` (mặc định 900, tối thiểu 300). Brief đưa số này vào `GEN_ARGS`. Sau mỗi lần gọi, `gen_image_codex.py` kiểm từng file (có file, header PNG, đọc được, cạnh dài > 1040 px) và chỉ gen lại file hỏng hoặc thiếu.
- `--approve-for-me` của Codex tự duyệt mọi yêu cầu quyền: không bao giờ có trong lệnh mặc định hay `GEN_ARGS`. Chỉ khi một lần gọi bị chặn thật, người dùng chạy lại lệnh gen với `--approve-for-me "<lý do>"`; `<tên>.json` và ledger ghi lý do.
- `codex_batch = true` ở `[[steps]]` texture: `GEN_ARGS` có `--batch`, các paint view dùng chung tham chiếu gen trong một lần gọi. Mặc định `false`. Chỉ bật ở bước texture.
- `PRODUCER_ROOT`: thư mục làm việc (mặc định `production`; bản Codex trong project có cả bản Claude tự dùng `production-codex`); gói cuối vào thư mục `deliver` cùng hậu tố (`production-codex` → `deliver-codex`). Dùng khi so A/B hai runtime.

## Project mới

```
.claude/skills/zps-3dp-producer/scripts/.deps/venv/bin/python .claude/skills/zps-3dp-producer/scripts/producer.py init --project "New Last Order" --concepts "~/MyWorks/Concepts/New Last Order"
```

Lệnh này tạo (không ghi đè file đã có):
- `production/`: pipeline.toml đã điền đường dẫn, policy.yaml (mọi bước `human`), `rubrics/` (default, building), ledger.md, schedule.md.
- Trong thư mục concept: `_approved/` và `GUIDELINE.md` đã điền tên project, đường dẫn và lệnh `check_card.py`.
- `.env` trong `.gitignore` của project, để key Meshy không bị commit.

Key Meshy nằm trong `.env` của project, dòng `MESHY_API_KEY=...`. Đường dẫn ghi ở `paths.env_file` của profile (mặc định `.env`). Chỉ nêu đường dẫn file khi nói với Producer. Không đính kèm file `.env` vào chat: nội dung file vào context và lộ mọi key trong đó. Script tự đọc file; brief không chứa key hay đường dẫn `.env`.

Lệnh này không tạo `production/PROJECT-PROFILE.yaml`. Skill `zps-3dp-project-setup` tạo file này cùng người dùng, theo mẫu `templates/PROJECT-PROFILE.yaml`. Chưa có profile hợp lệ thì `P intake` từ chối. Kiểm profile bằng `scripts/check_profile.py production/PROJECT-PROFILE.yaml` (cùng python của venv). Profile nêu `preset` thì file `presets/<preset>.yaml` trong bộ skill phải có.

Sau đó:
1. Gửi `GUIDELINE.md` cho Concept Artist, View Concept Artist và AD khi làm việc với họ. Gửi file, không dán nội dung, để luôn chỉ có một bản. Sửa guideline thì tăng số phiên bản ở dòng đầu.
2. AD tạo `art-direction/README.md` theo format trong guideline. Chưa có cũng chạy được; brief sẽ ghi "chưa có art direction".
3. Duyệt `production/rubrics/building.md`, đổi dòng đầu thành `<!-- status: approved -->`.

Muốn đổi guideline cho mọi project sau này: sửa `templates/GUIDELINE.md` trong `src/`, build và cài lại. Project đã tạo giữ bản riêng của nó.

## Sửa pipeline

Mọi thay đổi workflow nằm ở `production/pipeline.toml`:
- **Thêm bước:** thêm khối `[[steps]]` đúng vị trí. Agent mới: thêm file agent vào `src/zps-3dp-producer/agents/` của repo bộ skill, thêm câu mẫu vào `evals/triggers.json`, build và cài lại, mở phiên mới. Id của bước cũng là tag `steps:` mà AD dùng trong README art direction.
- **Đổi model:** sửa `model` (worker) và `reviewer_model` (reviewer) của bước. Bước không ghi `reviewer_model` thì dùng `[review] reviewer_model`. `escalate_model` dùng khi vòng sửa vượt `resume_rounds`. Tên chung `opus`, `sonnet`, `haiku`; runtime đổi sang model thật (`references/runtime.md`, mục Model).
- **Đổi output bắt buộc:** sửa `outputs`. Thiếu file thì asset bị blocked.
- **Đổi chuẩn preview:** sửa `[preview].spec`. Brief đưa nguyên văn cho worker.
- **Lệnh ngoài:** `external_command` của bước (biến `{request}`, `{vdir}`, `{log}`); brief ghi lệnh cho worker chạy và chờ lệnh xong.
- **Ai duyệt bước:** `gate = "review"` (reviewer duyệt), `"review_human"` (reviewer chấm, người duyệt theo `policy.yaml`), `"checks_human"` (script kiểm, người dùng duyệt).

Script đọc lại pipeline mỗi lệnh, nên asset đang chạy theo pipeline mới ngay. Đổi `id` của bước mà asset đang đứng ở đó thì `validate` báo lỗi: sửa `stage` trong status.json của asset đó.

## Nâng cấp từ v0.7.1

v0.8.0 gộp hai bước `views_front`, `views_rest` thành một bước `views`. Project tạo bằng v0.7.1 cần ba việc:
1. `production/pipeline.toml`: thay hai khối `[[steps]]` cũ bằng khối `views` của `templates/pipeline.toml`. Đổi hai id cũ thành `views` trong `inputs`, `review_inputs` của `model` và `texture`. Chưa sửa thì mọi lệnh dừng với một dòng nêu việc này.
   Chép thêm từ template các khóa mới vào khối `blockout`, `model`, `texture`. Bắt buộc: `fix_copy_exclude` của `texture` và các JSON kết quả mới trong `outputs`; thiếu thì mọi lệnh dừng với một dòng nêu bước và khóa. Nên chép: `acceptable`, `sheet`, `reviewer_model` của từng bước, `[review] max_direct_rounds`; thiếu thì dùng mặc định. Cách gọn: chép cả file template, rồi ghi lại giá trị riêng của project.
2. `P next` và `P validate` in `migrate <id>` cho mỗi asset có status.json còn bước cũ; `P validate` in cả asset có `rubric.md` còn mục cũ. Mọi lệnh khác trên asset đó dừng với cùng dòng. Chạy `P migrate <id>`:
   - Asset chưa tới bước view, hoặc thẻ có `views: none`: không đổi gì.
   - Asset đã duyệt cả hai bước cũ: front và bộ view đã duyệt gộp thành `views` v1 đã duyệt. Asset đi tiếp ở bước đang đứng.
   - Asset đang ở giữa một bước cũ, hoặc mới duyệt front: asset làm lại bước `views` từ `todo`.
   Thư mục cũ giữ nguyên trên đĩa. Lệnh cũng đổi `rubric.md` của asset và `production/rubrics/*.md` sang một mục `## views`. Key chỉ có ở `## views_front` chuyển sang `## views`; lệnh in tên các key đó. Chạy lại lệnh không đổi gì thêm.
3. `policy.yaml`: khóa `views_rest` đọc thành `views`; lần ghi sau lưu tên mới. Không cần sửa tay.

## Pipeline đứng im

- Thấy pipeline không chạy: bấm Esc, rồi bảo Producer chạy `P next`. Asset kẹt: `P stall <id>`; asset `blocked` hoặc `waiting_human` vì kẹt: `P retry <id>`. Trạng thái nằm trong file, nên không mất gì.
- Hook `SubagentStop` (`P on-stop`) ghi xuống đĩa mỗi lần subagent dừng, kể cả khi Producer không nhận thông báo. `install.py` gộp hook này và biến `env` Bash timeout (`BASH_DEFAULT_TIMEOUT_MS` 600000, `BASH_MAX_TIMEOUT_MS` 3600000) vào settings của project; `P preflight` báo khi thiếu.
- Hook `Stop` (`P on-main-stop`) từ chối cho phiên chính dừng khi còn report chưa ingest (cả `report-script.md` của bước script), hoặc còn dòng giao việc chưa giao. `install.py` gộp hook này cùng các hook trên; hook `Stop` của người dùng vẫn giữ. Bản Codex: `install.py` gộp ba hook vào `.codex/hooks.json`; Codex chỉ chạy chúng khi project được tin; người dùng tin hook một lần sau khi cài, bước giao diện này chưa kiểm (`references/runtime.md`).
- Ngưỡng kẹt và chế độ giao: `dispatch`, `watch` trong `policy.yaml`. Thời gian thường lệ mặc định mỗi bước: `usual_min` trong `pipeline.toml`.

## Review page

`P serve` mở http://127.0.0.1:8765 (chỉ máy local). Trang `index.html` đọc `/api/board`. Nút Duyệt, Cần sửa, Ghi chú ghi thẳng vào feedback.md và status.json. `P ab board` mở trang so cặp A/B ở http://127.0.0.1:8766 (`SKILL.md`, mục So A/B).

## Dọn file

- Người dùng DUYỆT 2 (`assemble`) thì script xóa ngay trong lệnh duyệt, sau khi chép `deliver/<id>/` và ghi `RUN-REPORT.md`. Bản Codex cũng vậy.
- Trước khi xóa, `P next` và nút DUYỆT 2 hiện một dòng: số file, dung lượng, "sau lệnh này không `redo` được". Nút cần bấm hai lần.
- Không xóa khi: `P keep <id>` chạy trước lần duyệt; `policy.yaml` có `purge: off`; Producer tự duyệt (`test_mode`). Khi đó xóa sau bằng `P purge <id> --by "<nguyên văn>" [--zip <file>]`.
- `purge_zip: <thư mục>` trong `policy.yaml` nén phần sắp xóa vào `<thư mục>/<id>.zip` trước khi xóa. `--zip <file>` ở `P purge` và ở `P feedback <id> "<nguyên văn>" --action approve` của DUYỆT 2 ghi đè thư mục đó.
- File `purge-pending.json` của v0.7: script không tự chạy. `P next` nhắc chạy `purge` hoặc `keep`.
- Còn lại: `deliver/<id>/`; mọi file text ngoài `work/` (status, findings, report, brief, `heartbeat.log`, `part_graph.json`, `sources.json`, `spec.json`, `texture_spec.json`); `feedback/`; ảnh trang duyệt trỏ tới, thu về cạnh dài 1024 px. Mọi thứ khác xóa thật, cả `production/show/<id>*`, file đẩy lên trang của asset, file PID của asset và mọi `*.rejected-*.md`. Manifest: `production/assets/<id>/purge-manifest.json`. Sau đó `redo` bị từ chối.
- A/B: `production-<runtime>/` không xóa trước khi cặp có `ab prefer` hoặc đủ hai lần `ab judge`; `P purge` từ chối và nêu kết quả còn thiếu.
- `P disk`: dung lượng theo asset, bước, loại file. `P next` cảnh báo khi `production/` vượt `disk_warn_gb` của `policy.yaml`.
- Xong hẳn: `P archive <id>`.
