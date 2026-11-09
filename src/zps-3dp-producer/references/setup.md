# Cài đặt và tuỳ chỉnh

Cần Python 3.11+ (`python3 --version`). Script cần PyYAML, nên chạy trong venv của skill. Việc riêng của runtime (cách gọi agent, hook, quyền, sandbox, lệnh mở phiên mới) nằm trong `references/runtime.md`.

## Cài bộ skill (một lần cho mỗi project, chạy lại khi nâng cấp)

1. Trong repo bộ skill: `python3 build.py`. Lệnh tạo `dist/zps-3dp-claude-v<ver>/` và `dist/zps-3dp-codex-v<ver>/`, và dừng khi một kiểm tĩnh sai.
2. `python3 dist/zps-3dp-<runtime>-v<ver>/install.py --project <thư mục project>`. Lệnh chép hai skill (`zps-3dp-producer`, `zps-3dp-project-setup`) vào thư mục skill của runtime. Bản Claude Code chép thêm file agent vào thư mục agent của project. Thư mục `agents/` trong skill giữ `tools/` và `references/` của từng agent; file agent đọc chúng qua dòng `TOOLS:` của brief, nên bản chép phẳng vẫn đúng đường dẫn. Cài lại thì skill cũ được thay, các thư mục `.deps/` được giữ.
3. Chạy một lần: `bash .claude/skills/zps-3dp-producer/scripts/setup_deps.sh` (tạo `scripts/.deps/venv` với pyyaml, pytest, Pillow, numpy). Rồi `bash .../agents/<agent>/tools/setup_deps.sh` cho bốn agent bước (`zps-3dp-step-blockout`, `-views`, `-model`, `-texture`). Từ đây `P` là python của venv chạy `producer.py`.
4. Làm các việc của runtime trong `references/runtime.md`: hook mở phiên và quyền (Claude Code), rules Blender ngoài sandbox (Codex).
5. Thêm vào file hướng dẫn luôn được nạp của project (Claude Code: `CLAUDE.md`; Codex: `AGENTS.md`), để skill được dùng kể cả khi người dùng chỉ nói "tiếp tục":
   ```markdown
   Project này dùng skill zps-3dp-producer để điều phối art. Mọi việc về asset, concept trong _approved, feedback, tiến độ: dùng skill zps-3dp-producer, bắt đầu từ output của `producer.py next`.
   ```
6. Mở phiên mới để runtime nạp skill và agent.

Đổi prompt agent hoặc script: sửa `src/` trong repo bộ skill, build và cài lại. Không sửa bản đã cài.

## Lệnh môi trường và chính sách duyệt

- `P preflight`: kiểm Blender (`BLENDER`, rồi Blender.app, rồi PATH), codex CLI, `MESHY_API_KEY` trong `paths.env_file` của profile (mặc định `.env`; script không in key), và `preflight.py` của kit khi có (mặc định skill `zps-3d-artist` cạnh skill này; nơi khác: biến môi trường `PRODUCER_KIT=<đường dẫn preflight.py>`). Ghi `production/preflight.json`. Chạy một lần mỗi phiên.
- `P approvals set <bước> <human|reviewer> --by "<nguyên văn>"`: ghi `production/policy.yaml`. `model reviewer` cần `--confirm-spend`. `P approvals set review_board <local|local+remote> --by "<nguyên văn>"`: đổi trang duyệt.
- `P delegate <bước> <id> ... --by "<nguyên văn>"`: reviewer duyệt bước đó cho các asset này. Thứ tự: `delegate` > `approvals` > `human`.
- `[limits]` trong `pipeline.toml`: số tiến trình cùng lúc. Worker ghi PID mỗi lệnh Blender vào `production/pids/blender/<id>.pid` (brief ghi lệnh mẫu); `gen_image_codex.py` tự ghi `production/pids/codex_image/<id>-<pid>.pid` cho mỗi lần chạy. `P next` chỉ đếm PID còn sống.
- `PRODUCER_ROOT`: thư mục làm việc (mặc định `production`); gói cuối vào thư mục `deliver` cùng hậu tố (`production-codex` → `deliver-codex`). Dùng khi so A/B hai runtime.

## Project mới

```
.claude/skills/zps-3dp-producer/scripts/.deps/venv/bin/python .claude/skills/zps-3dp-producer/scripts/producer.py init --project "New Last Order" --concepts "~/MyWorks/Concepts/New Last Order"
```

Lệnh này tạo (không ghi đè file đã có):
- `production/`: pipeline.toml đã điền đường dẫn, policy.yaml (mọi bước `human`), `rubrics/` (default, building), ledger.md, schedule.md.
- Trong thư mục concept: `_approved/` và `GUIDELINE.md` đã điền tên project, đường dẫn và lệnh `check_card.py`.
- `.env` trong `.gitignore` của project, để key Meshy không bị commit.

Lệnh này không tạo `production/PROJECT-PROFILE.yaml`. Skill `zps-3dp-project-setup` tạo file này cùng người dùng, theo mẫu `templates/PROJECT-PROFILE.yaml`. Chưa có profile hợp lệ thì `P intake` từ chối. Kiểm profile bằng `scripts/check_profile.py production/PROJECT-PROFILE.yaml` (cùng python của venv). Profile nêu `preset` thì file `presets/<preset>.yaml` trong bộ skill phải có.

Sau đó:
1. Gửi `GUIDELINE.md` cho Concept Artist, View Concept Artist và AD khi làm việc với họ. Gửi file, không dán nội dung, để luôn chỉ có một bản. Sửa guideline thì tăng số phiên bản ở dòng đầu.
2. AD tạo `art-direction/README.md` theo format trong guideline. Chưa có cũng chạy được; brief sẽ ghi "chưa có art direction".
3. Duyệt `production/rubrics/building.md`, đổi dòng đầu thành `<!-- status: approved -->`.

Muốn đổi guideline cho mọi project sau này: sửa `templates/GUIDELINE.md` trong `src/`, build và cài lại. Project đã tạo giữ bản riêng của nó.

## Sửa pipeline

Mọi thay đổi workflow nằm ở `production/pipeline.toml`:
- **Thêm bước:** thêm khối `[[steps]]` đúng vị trí. Agent mới: thêm file agent vào `src/zps-3dp-producer/agents/` của repo bộ skill, thêm câu mẫu vào `evals/triggers.json`, build và cài lại, mở phiên mới. Id của bước cũng là tag `steps:` mà AD dùng trong README art direction.
- **Đổi model:** sửa `model`; `escalate_model` dùng khi vòng sửa vượt `resume_rounds`. Tên chung `opus`, `sonnet`, `haiku`; runtime đổi sang model thật (`references/runtime.md`, mục Model).
- **Đổi output bắt buộc:** sửa `outputs`. Thiếu file thì asset bị blocked.
- **Đổi chuẩn preview:** sửa `[preview].spec`. Brief đưa nguyên văn cho worker.
- **Lệnh ngoài:** `external_command` của bước (biến `{request}`, `{vdir}`, `{log}`); brief ghi lệnh cho worker chạy nền.
- **Ai duyệt bước:** `gate = "review"` (reviewer duyệt), `"review_human"` (reviewer chấm, người duyệt theo `policy.yaml`), `"checks_human"` (script kiểm, người dùng duyệt).

Script đọc lại pipeline mỗi lệnh, nên asset đang chạy theo pipeline mới ngay. Đổi `id` của bước mà asset đang đứng ở đó thì `validate` báo lỗi: sửa `stage` trong status.json của asset đó.

## Review page

`P serve` mở http://127.0.0.1:8765 (chỉ máy local). Trang `index.html` đọc `/api/board`. Nút Duyệt, Cần sửa, Ghi chú ghi thẳng vào feedback.md và status.json. `P ab board` mở trang so cặp A/B ở http://127.0.0.1:8766 (`SKILL.md`, mục So A/B).

## Dọn file

`P cleanup <id>` chỉ chạy khi asset đã done; mặc định dry-run, `--yes` để xoá work/ của phiên bản không được duyệt, `--all` để xoá cả work/ của bản đã duyệt. Xong hẳn: `P archive <id>`.
