# Runtime: Claude Code

File này chỉ ghi cơ chế của runtime. Quy tắc nghiệp vụ nằm trong `SKILL.md`, brief và file agent.

## Gọi agent

- Tạo subagent bằng tool Agent: `subagent_type` = khóa `agent` của `P brief`, `model` = khóa `model`, prompt đúng như `SKILL.md`.
- File agent nằm ở `.claude/agents/<agent>.md`. Claude Code chỉ nạp agent mới khi mở phiên.

## Resume

- `resume` có giá trị: gửi tiếp bằng SendMessage tới agent id đó.
- Agent id lấy từ kết quả của lần giao trước. Truyền id này cho `P ingest <id> --agent-id <agent id>`.

## Model

- `opus`, `sonnet`, `haiku` là tên tool Agent nhận. Claude Code chọn model thật của tên đó. Ledger ghi tên đã truyền.

## Token

- Kết quả subagent có khối usage: số token (`subagent_tokens` hoặc `total_tokens`) → `--tokens <N>`, `duration_ms` → `--duration-ms <M>` của `P ingest`. Thiếu số nào thì bỏ cờ đó.

## Hook mở phiên

- Gộp `templates/settings.snippet.json` vào `.claude/settings.json`: hook SessionStart in `P next --session`; allow rule cho `P`, `codex exec` và lệnh ghi file dưới `production/`, `production-*/` (report của subagent), để subagent chạy nền không chờ xin quyền. Rule không ăn thì thêm bằng `/permissions`.

## Gửi file

- Gửi file cho người dùng bằng `SendUserFile` theo đường dẫn. Không mở file.

## Đường dẫn

- Skill: `.claude/skills/zps-3dp-producer/`. Agent: `.claude/agents/`. Lệnh `P` như `SKILL.md`.

## Phiên mới

- Lệnh mở phiên sạch: `/clear`.
- So A/B: mở phiên bằng `PRODUCER_ROOT=production-claude claude` từ gốc project.

## Review Board

- Dùng được `local` và `local+remote`: phiên có tool Artifact và ArtifactData.

## Ảnh

- Bước view và texture gọi `codex exec` qua `gen_image_codex.py`, theo lệnh trong brief. Máy cần Codex CLI đã đăng nhập.
