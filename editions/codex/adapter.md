# Runtime: Codex

File này chỉ ghi cơ chế của runtime. Quy tắc nghiệp vụ nằm trong `SKILL.md`, brief và file agent. Bản này viết cho codex-cli 0.164.0. Dòng ghi "đã chạy thật" đã thử trên máy ngày 2026-11-13. Dòng ghi "chưa chạy thật" lấy từ tài liệu Codex.

## Gọi agent

- Codex không có file agent riêng. Gọi `spawn_agent` với `task_name` (tên ngắn, ví dụ `<id>-<bước>-v<N>-<vai>`) và `message` đúng nội dung sau:
  > Vai của bạn nằm trong `<agent_file>`: đọc file đó trước tiên. Rồi đọc `<brief>`: đó là toàn bộ yêu cầu của bạn. Ghi báo cáo đầy đủ vào `<report>`. Chỉ trả về các dòng brief yêu cầu.
- Không truyền `agent_type`: sub-agent là agent thường và đọc file vai. `agent_file` là khóa của `P brief`. Dòng `tools:` trong file agent không áp dụng trên Codex.
- Các tool sub-agent (đã chạy thật): `spawn_agent(task_name, message, agent_type, model, reasoning_effort, fork_turns)`, `wait_agent(timeout_ms)`, `followup_task(target, message)`, `send_message(target, message)`, `interrupt_agent(target)`, `list_agents(path_prefix)`.
- `target` là `task_name` đã đặt khi giao. `list_agents` in tên các agent. Truyền `task_name` làm `--agent-id` của `P ingest`.
- Sub-agent dùng chung quyền mạng và sandbox của phiên gốc. `production/` và `production-*/` nằm trong thư mục project, nên sandbox `workspace-write` cho ghi report ở đó mà không cần thêm writable root.
- Dừng agent: mục Dừng agent.

## Dừng agent

- Dừng bằng `interrupt_agent` với `target` của agent đó. Codex không có tool đóng agent.
- `P stall` chờ agent cũ dừng rồi mới giao agent mới, như bản Claude. Hook SubagentStop ghi lần dừng. Không có hook thì agent im thêm `stall_min` phút sau lần xin dừng là đủ: `P stall` sau đó giao agent mới. Lệnh không bao giờ chờ mãi.
- `P stall` in id agent mà hook ghi. Tool từ chối id đó thì dùng `task_name`.

## Resume

- `resume` có giá trị (vòng sửa, ảnh reviewer xin, report sai contract): gửi bằng `followup_task` tới agent đó. Agent giữ ngữ cảnh lần trước (đã chạy thật).
- Câu nudge của `P stall`: `send_message` khi agent còn chạy, `followup_task` khi agent đã xong lượt.

## Model

- `P brief` in `model` và `reasoning_effort`. Có giá trị thì truyền đúng giá trị đó vào `model` và `reasoning_effort` của `spawn_agent` (đã chạy thật). `null` thì không truyền: sub-agent chạy bằng model của phiên, ledger ghi "model của phiên".

## Token

- Script đọc số từ rollout của Codex. Producer: rollout chính (`transcript_path` của hook SessionStart). Mỗi lần giao: rollout của sub-agent (`agent_transcript_path` của hook SubagentStop). Không truyền số tay, không chờ số.
- Không có hook thì script không biết rollout nào: report ghi "không có số".

## Hook mở phiên

- `install.py` gộp `installer/codex_hooks.json` vào `<project>/.codex/hooks.json`: hook SessionStart chạy `P next --session`, hook SubagentStop chạy `P on-stop`, hook Stop (`P on-main-stop`). Hook khác của người dùng giữ nguyên. Chạy lại không đổi gì.
- Codex chỉ chạy hook của project khi project được tin (trusted). Sau khi cài, người dùng mở Codex trong project và tin hook một lần. Bước giao diện này chưa kiểm. Project chưa tin thì hook không chạy (đã chạy thật với `codex exec`).
- Hook Stop: còn report chưa ingest, hoặc còn dòng giao việc chưa giao, thì hook thoát với mã 2 và một dòng stderr. Codex đưa dòng đó cho model và phiên chạy tiếp. Hook tìm lệnh `spawn_agent`, `followup_task` hoặc `send_message` nêu brief trong rollout chính.
- Ba hook trong project đã tin: chưa chạy thật.
- Không có hook (project chưa tin): chạy `P next --session` khi mở phiên. Luật trong `SKILL.md` "Nhận kết quả" là chỗ chặn duy nhất khi Producer kết thúc lượt; giữ nó đúng từng chữ. Nhịp tim, hạn chót, `P stall`, `P wait` dựa trên file nên vẫn dùng được.
- DUYỆT 2 xóa file trung gian ngay trong lệnh duyệt, như bản Claude. Không cần hook.

## Gửi file

- Không có tool gửi file. Báo người dùng đường dẫn file.

## Đường dẫn

- Skill: `.agents/skills/zps-3dp-producer/`. File agent: `agents/` trong thư mục skill.
- Nạp skill khác (ví dụ `zps-3dp-project-setup`): đọc `SKILL.md` của skill đó trong `.agents/skills/`.

## Sandbox

- Blender crash trong sandbox trên macOS. Sau khi cài và sau mỗi lần nâng cấp, người dùng chạy `python3 installer/codex_rules.py --write` của bản build, rồi khởi động lại Codex.
- Viết lệnh Blender bằng đường dẫn tuyệt đối: `<BLENDER> -b --python <script đã cài>.py -- …` hoặc `<BLENDER> -b --python-exit-code 1 --python <script đã cài>.py -- …`. Dòng `TOOLS:` và `BLENDER:` của brief đã tuyệt đối. Biến shell hoặc đường dẫn tương đối không khớp rule.
- `P preflight`, lệnh `command` của bước `assemble` và lệnh `RUN:` của brief có cờ `--blender` chạy ngoài sandbox qua rule. Các lệnh khác chạy trong sandbox.
- `run_tool.py` chỉ nhận Blender ghi trong `production/preflight.json`. Trên Codex nó chỉ nhận tool trong `agents/*/tools/`, và từ chối `meshy_call.py`, `gen_image_codex.py`, `gen_api.py`, `generate_image.py`, `self_build/assembly.py`, `self_build/param_fit.py` và `custom_mesh.py`, để rule của nó không mở lối quanh các quy tắc dưới đây. Chạy các script đó, và mọi script trong `scripts/`, bằng lệnh riêng như trước.
- `meshy_call.py` cần mạng. Xin người dùng duyệt từng lần chạy. Rule không bao giờ cho phép script này.
- `gen_image_codex.py --direct` chỉ kiểm file ảnh và ghi dưới `production*/`, nên chạy trong sandbox, không cần mạng, không cần rule. Rule không bao giờ cho phép `gen_image_codex.py`.
- `self_build/assembly.py`, `param_fit.py` chạy `parts_lib.py` do agent viết. Rule không cho phép hai script này. Lệnh Blender của chúng (part `custom`) chạy ngoài sandbox thì xin người dùng duyệt từng lần.
- `build_parts.py` chỉ chạy `custom_lib.py` và dựng lưới từ JSON bằng `mesh_from_json.py`; không chạy `custom_parts.py` do agent viết. Rule cho phép script này như trước `3a4f64b`. `custom_mesh.py` chạy `custom_parts.py` do agent viết bằng Python của tool, trong sandbox; chạy trong Blender thì script tự dừng. Rule không bao giờ cho phép `custom_mesh.py`.

## Phiên mới

- Lệnh mở phiên sạch: `/new`.
- So A/B: mở phiên bằng `PRODUCER_ROOT=production-codex codex` từ gốc project.

## Review Board

- Chỉ dùng được `local`: Codex không có tool Artifact.

## Ảnh

- Bước views và texture: worker làm theo dòng `GEN_MODE` của brief. Bản này gen ảnh trực tiếp: worker gọi tool tạo ảnh của phiên với `prompt` và `referenced_image_paths` (đúng thứ tự brief), chép PNG từ `$CODEX_HOME/generated_images/<thread id>/` (mặc định `~/.codex/`) vào `--out` bằng `cp`, rồi chạy `gen_image_codex.py --direct …` để kiểm file.
- Đã chạy thật trên `gpt-6-astra`: ảnh ngang ra 1536x1024; prompt ghi "PORTRAIT, 2:3, 1024x1536" ra đúng 1024x1536; `cp` chạy được trong sandbox `workspace-write`.
- Không có `codex exec` lồng, nên gen ảnh không cần duyệt mạng. Bản này không bao giờ chạy `gen_image_codex.py` thiếu `--direct`.
- Lệnh lỗi thì báo người dùng. Không tự đổi sang tool ảnh khác.
