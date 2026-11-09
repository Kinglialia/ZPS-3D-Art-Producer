# Runtime: Codex

File này chỉ ghi cơ chế của runtime. Quy tắc nghiệp vụ nằm trong `SKILL.md`, brief và file agent.

## Gọi agent

- Codex không có file agent riêng. Gọi `spawn_agent` với đúng nội dung sau:
  > Vai của bạn nằm trong `<agent_file>`: đọc file đó trước tiên. Rồi đọc `<brief>`: đó là toàn bộ yêu cầu của bạn. Ghi báo cáo đầy đủ vào `<report>`. Chỉ trả về các dòng brief yêu cầu.
- `role` là `reviewer`: hai câu cuối đổi thành "Trả cả report trong tin nhắn cuối, giữa dòng `--- report ---` và dòng `--- end ---`."
- `agent_file` là khóa của `P brief`. Dòng `tools:` trong file agent không áp dụng trên Codex.
- Sub-agent dùng chung quyền mạng và sandbox của phiên gốc.

## Resume

- `resume` có giá trị: gửi tiếp bằng `send_message` tới agent đó. Tên tool có thể khác giữa các bản Codex.

## Model

- `P brief` in `model: null`: sub-agent chạy bằng model của phiên. Ledger ghi "model của phiên".

## Token

- Kết quả sub-agent có số token thì thêm `--tokens <N>`, có thời lượng thì thêm `--duration-ms <M>` vào `P ingest`. Thiếu số nào thì bỏ cờ đó.

## Hook mở phiên

- Không có hook SessionStart. Chạy `P next --session` khi mở phiên.

## Gửi file

- Không có tool gửi file. Báo người dùng đường dẫn file.

## Đường dẫn

- Skill: `.agents/skills/zps-3dp-producer/`. File agent: `agents/` trong thư mục skill.
- Nạp skill khác (ví dụ `zps-3dp-project-setup`): đọc `SKILL.md` của skill đó trong `.agents/skills/`.

## Sandbox

- Blender crash trong sandbox trên macOS. Sau khi cài và sau mỗi lần nâng cấp, người dùng chạy `python3 installer/codex_rules.py --write` của bản build, rồi khởi động lại Codex.
- Viết lệnh Blender bằng đường dẫn tuyệt đối: `<BLENDER> -b --python <script đã cài>.py -- …` hoặc `<BLENDER> -b --python-exit-code 1 --python <script đã cài>.py -- …`. Dòng `TOOLS:` và `BLENDER:` của brief đã tuyệt đối. Biến shell hoặc đường dẫn tương đối không khớp rule.
- `P preflight` và lệnh `command` của bước `assemble` chạy ngoài sandbox qua rule. Các lệnh khác chạy trong sandbox.
- `meshy_call.py` và `gen_image_codex.py` cần mạng. Xin người dùng duyệt từng lần chạy. Rule không bao giờ cho phép hai script này.
- `self_build/assembly.py`, `param_fit.py`, `apply_edit.py` chạy `parts_lib.py` do agent viết. Rule không cho phép ba script này. Lệnh Blender của chúng (part `custom`) chạy ngoài sandbox thì xin người dùng duyệt từng lần.

## Phiên mới

- Lệnh mở phiên sạch: `/new`.
- So A/B: mở phiên bằng `PRODUCER_ROOT=production-codex codex` từ gốc project.

## Review Board

- Chỉ dùng được `local`: Codex không có tool Artifact.

## Ảnh

- `gen_image_codex.py` gọi `codex exec` lồng trong phiên Codex, theo lệnh trong brief. Lệnh lỗi thì báo người dùng. Không tự đổi sang tool ảnh khác.
