# Hai bản: Claude Code và Codex

Hai bản build từ cùng `src/` (D6.4, D24.5). Bảng dưới là mọi khác biệt. Thêm một khác biệt thì thêm vào đây và vào `editions/`.

| Mục | Claude Code | Codex |
|---|---|---|
| Thư mục skill trong project | `.claude/skills/` | `.agents/skills/` |
| Tên skill và agent | `zps-3dp-<tên>` | `zps-3dp-<tên>-codex` |
| Tiêu đề `SKILL.md` | `# ZPS-3DP · <Tên>` | `# ZPS-3DP · <Tên> - Codex` |
| File agent | Chép phẳng vào `.claude/agents/<agent>.md` | Ở lại `agents/` trong skill; `P brief` in thêm `agent_file` |
| Adapter (`references/runtime.md`) | `editions/claude/adapter.md`: tool Agent, SendMessage, hook SessionStart, `SendUserFile`, `/clear` | `editions/codex/adapter.md`: `spawn_agent` với `agent_file`, `send_message`, không hook, Blender ngoài sandbox, `/new` |
| `models` (ledger ghi giá trị này) | `opus`, `sonnet`, `haiku` (Claude Code chọn model thật) | `null`: model của phiên, tới khi chạy thật |
| Skill chỉ gọi tường minh | `disable-model-invocation: true` | `agents/openai.yaml` với `allow_implicit_invocation: false` |
| `agents/openai.yaml` | Không | Có: tên hiển thị |
| `templates/settings.snippet.json` | Có | Bỏ |
| Rules Blender | Không cần | `installer/codex_rules.py` ghi `$CODEX_HOME/rules/zps-3dp-producer.rules` |
| Review Board | `local`, `local+remote` | `local` |
| `runtime.json` (script đọc) | `runtime: claude` | `runtime: codex`, `suffix: -codex`, `agent_file: true` |

## Build và cài

```sh
python3 build.py                      # cả hai bản → dist/zps-3dp-<bản>-v<VERSION>/
python3 dist/zps-3dp-claude-v0.7.0/install.py --project <thư mục project>
```

Build dừng với mã 1 khi một kiểm sai:
- `name` khớp tên thư mục hoặc file (có hậu tố); description không rỗng và ≤ 300 ký tự (Codex rút gọn description dài).
- Description của agent mở đầu bằng câu cố định của D23.2.
- File agent chỉ trỏ tới `T/…` (dòng `TOOLS:` của brief) và `R/…` (`R` = `T/../references`); mọi file được nhắc phải có. Đường dẫn trần `references/…` hỏng khi chép phẳng.
- Link markdown không hỏng. Bản Codex không có đường dẫn `.claude/`. Bản Claude không có tên `-codex`.
- `adapter.md` chỉ có các mục cơ chế runtime (D22.9).
- Phần tĩnh của eval kích hoạt (dưới).

## Eval kích hoạt

`evals/triggers.json` có một mục cho mỗi skill và agent, cùng format với kit (`rule`, `cases[] = {query, should_trigger, kind, why}`).

**Phần tĩnh** (build chạy): đủ mục cho mọi skill và agent; mỗi mục có câu dương và câu âm; mỗi mục có một câu âm trùng một skill của kit (`why` nêu tên skill kit); câu dương của agent có file brief, câu âm của agent không có (D23.2: agent chỉ chạy khi Producer giao brief).

**Phần chạy thật** (tốn lượt model, chưa chạy). Làm trong một project thử có cài cả kit và bộ Producer:
1. Claude Code: với mỗi câu, chạy `claude -p "<query>" --output-format stream-json --verbose` từ gốc project thử. Câu kích hoạt khi stream có `tool_use` tên `Skill` với `skill` là tên mục, hoặc tool Agent với `subagent_type` là tên mục.
2. Codex: đổi tên trong câu sang tên `-codex` (`/zps-3dp-project-setup` thành `$zps-3dp-project-setup-codex`). Chạy `codex exec --json "<query>"`. Câu kích hoạt khi stream đọc `SKILL.md` hoặc file agent của mục đó.
3. So với `should_trigger`. Ghi kết quả từng câu vào `docs/coding-checklist.md` dòng 81, 92. Câu `edge` ghi kết quả, không tính là fail.

## Rules Blender trên Codex

Sau khi cài bản Codex, từ gốc project:

```sh
python3 dist/zps-3dp-codex-v0.7.0/installer/codex_rules.py           # xem trước và tự kiểm bằng `codex execpolicy check`
python3 dist/zps-3dp-codex-v0.7.0/installer/codex_rules.py --write   # ghi file rules
```

Rule chỉ cho phép `<Blender> -b --python <script đã cài>.py -- …`, `<Blender> -b --python-exit-code 1 --python <script đã cài>.py -- …`, `assemble.py --blender <Blender> -- …` và `producer.py preflight` bằng python venv của skill. Codex chỉ so phần đầu lệnh, nên mỗi rule dừng ở chỗ chương trình thôi đọc option: Blender chuyển phần sau `--` cho script, `assemble.py` chỉ đọc tham số vị trí sau `--`, `preflight` không có option (kit ở chỗ khác: biến `PRODUCER_KIT`). `meshy_call.py`, `gen_image_codex.py`, `gen_api.py`, `generate_image.py` không bao giờ khớp. `self_build/assembly.py`, `param_fit.py`, `apply_edit.py` chạy `parts_lib.py` trong thư mục làm việc, mà agent ghi được file này, nên cũng không khớp. `build_parts.py` khớp: nó chỉ chạy `custom_lib.py` và dựng lưới từ JSON bằng `mesh_from_json.py`, không chạy `custom_parts.py` do agent viết (D32.2). `custom_mesh.py` chạy file đó bằng Python của tool, trong sandbox, và tự dừng khi chạy trong Blender. Rule không khớp `custom_mesh.py`. Chạy lại sau mỗi lần nâng cấp, rồi khởi động lại Codex.

**Part `custom` chỉ gọi hàm của hai file** (D27.13, D32). Quy tắc này áp cho cả hai bản, nên bảng khác biệt ở trên không có dòng cho nó. Skill Producer kèm `custom_lib.py`, chỉ chứa hàm chung có tham số. Hàm riêng của một asset nằm trong `production/assets/<id>/custom_parts.py`, agent viết: Python thuần, chỉ `math`, kiểm danh sách trắng trước khi chạy, chạy ngoài Blender và ra lưới JSON (D32.2). File giữ sau DUYỆT 2 (D32.3). Hai bản giữ giống nhau để so A/B.

## So A/B

`PRODUCER_ROOT=production-claude` cho phiên Claude Code, `PRODUCER_ROOT=production-codex` cho phiên Codex. Gói cuối vào `deliver-<runtime>/`. Mọi dòng ledger có cột runtime. Thư mục `production-<runtime>` chỉ nhận lệnh ghi của đúng runtime đó. `ab/` ở gốc project chứa `mapping.json`, `preferences.jsonl`, `judge/`, `compare.md`. Lệnh: `SKILL.md` mục So A/B.
