# Runtime: Codex

File này chỉ ghi cơ chế của runtime. Quy tắc nghiệp vụ nằm trong `SKILL.md`, brief và file agent.

## Gọi agent

- Codex không có file agent riêng. Gọi `spawn_agent` với đúng nội dung sau:
  > Vai của bạn nằm trong `<agent_file>`: đọc file đó trước tiên. Rồi đọc `<brief>`: đó là toàn bộ yêu cầu của bạn. Ghi báo cáo đầy đủ vào `<report>`. Chỉ trả về các dòng brief yêu cầu.
- `agent_file` là khóa của `P brief`. Dòng `tools:` trong file agent không áp dụng trên Codex.
- Sub-agent dùng chung quyền mạng và sandbox của phiên gốc. `production/` và `production-*/` nằm trong thư mục project, nên sandbox `workspace-write` cho ghi report ở đó mà không cần thêm writable root.

## Resume

- `resume` có giá trị: gửi tiếp bằng `send_message` tới agent đó. Tên tool có thể khác giữa các bản Codex.

## Model

- `P brief` in `model: null`: sub-agent chạy bằng model của phiên. Ledger ghi "model của phiên".

## Token

- Bản này không có transcript subagent cho script đọc, nên script ghi "không có số". Không chờ số.

## Hook mở phiên

- Không có hook SessionStart. Chạy `P next --session` khi mở phiên.
- Không có hook Stop: `P on-main-stop` không chạy, nên không có gì chặn Producer kết thúc lượt. Luật trong `SKILL.md` "Nhận kết quả" là chỗ chặn duy nhất; giữ nó đúng từng chữ.
- Không có hook SubagentStop (D33.20): `P on-stop` không chạy. Nhịp tim, hạn chót, `P stall`, `P wait` dựa trên file nên dùng như bản Claude. Chưa chạy thử bản Codex để biết có đứng im như Run 5 không.
- Không tự xóa file sau DUYỆT 2 (D29): `P next` nhắc lệnh xóa đang chờ; người dùng muốn xóa thì `P purge <id> --by "<nguyên văn>"`.

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
- `meshy_call.py` và `gen_image_codex.py` cần mạng. Xin người dùng duyệt từng lần chạy. Rule không bao giờ cho phép hai script này.
- `self_build/assembly.py`, `param_fit.py` chạy `parts_lib.py` do agent viết. Rule không cho phép hai script này. Lệnh Blender của chúng (part `custom`) chạy ngoài sandbox thì xin người dùng duyệt từng lần.
- `build_parts.py` chỉ chạy `custom_lib.py` và dựng lưới từ JSON bằng `mesh_from_json.py`; không chạy `custom_parts.py` do agent viết (D32.2). Rule cho phép script này như trước `3a4f64b`. `custom_mesh.py` chạy `custom_parts.py` do agent viết bằng Python của tool, trong sandbox; chạy trong Blender thì script tự dừng. Rule không bao giờ cho phép `custom_mesh.py`.

## Phiên mới

- Lệnh mở phiên sạch: `/new`.
- So A/B: mở phiên bằng `PRODUCER_ROOT=production-codex codex` từ gốc project.

## Review Board

- Chỉ dùng được `local`: Codex không có tool Artifact.

## Ảnh

- Đã test với codex-cli 0.164.0. `gen_image_codex.py` gọi `codex exec -s workspace-write --skip-git-repo-check` lồng trong phiên Codex, theo lệnh trong brief. Lệnh lỗi thì báo người dùng. Không tự đổi sang tool ảnh khác.
