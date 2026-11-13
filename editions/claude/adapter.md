# Runtime: Claude Code

File này chỉ ghi cơ chế của runtime. Quy tắc nghiệp vụ nằm trong `SKILL.md`, brief và file agent.

## Gọi agent

- Tạo subagent bằng tool Agent: `subagent_type` = khóa `agent` của `P brief`, `model` = khóa `model`, prompt đúng như `SKILL.md`.
- File agent nằm ở `.claude/agents/<agent>.md`. Claude Code chỉ nạp agent mới khi mở phiên.
- Dừng agent: mục Dừng agent.

## Dừng agent

- Subagent chạy nền thì dừng bằng tool TaskStop, `task_id` là id của agent đó. Subagent chạy thường: chỉ người dùng dừng được (Esc).

## Resume

- `resume` có giá trị: gửi tiếp bằng SendMessage tới agent id đó.
- Agent id lấy từ kết quả của lần giao trước. Truyền id này cho `P ingest <id> --agent-id <agent id>`.

## Model

- `opus`, `sonnet`, `haiku` là tên tool Agent nhận. Claude Code chọn model thật của tên đó. Ledger ghi tên đã truyền.

## Token

- `P ingest` tự đọc token và thời lượng từ `<transcript chính>/subagents/agent-<agent id>.jsonl` (transcript chính ghi trong `production/session.json`). Không tìm thấy thì script tìm transcript có prompt nêu brief của lần giao.
- Không chờ thông báo mang số.

## Hook mở phiên

- `install.py` gộp `templates/settings.snippet.json` vào `.claude/settings.json`: hook SessionStart chạy `P next --session`; allow rule cho `P` (dạng tương đối và dạng đường dẫn tuyệt đối), `run_tool.py`, `assemble.py`, Blender, `meshy_call.py`, `codex exec` và lệnh ghi file dưới `production/`, `production-*/` (report của subagent), để subagent chạy nền không chờ xin quyền. Installer chỉ thêm, không đổi giá trị có sẵn, in diff trước khi ghi. `P preflight` báo khi thiếu. Rule không ăn thì thêm bằng `/permissions`.
- `install.py` cũng gộp hook SubagentStop (`P on-stop`, ghi lần giao xuống đĩa khi subagent dừng) và khối `env` (`BASH_DEFAULT_TIMEOUT_MS` 600000, `BASH_MAX_TIMEOUT_MS` 3600000); khóa `env` người dùng đã đặt thì giữ.
- `install.py` gộp thêm hook Stop (`P on-main-stop`). Khi còn report chưa ingest, hoặc còn dòng giao việc chưa giao, hook thoát với mã 2 và một dòng stderr; Claude Code đưa dòng đó cho model và phiên chính chạy tiếp. Hook không từ chối khi `stop_hook_active` là true, khi asset chờ người dùng, hoặc khi subagent còn chạy. Hook của người dùng ở cùng sự kiện vẫn giữ.
- Hook nhận JSON qua stdin. `P next --session` ghi `source`, `session_id` và đường dẫn transcript vào `production/session.json`.

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
