# Intent: GĐ 6, hai bản Claude Code và Codex, và so A/B

## Problem

GĐ 1–5 chạy hết pipeline trên Claude Code từ cây `src/`. Chưa có bản Codex, chưa có script build, và cách cài cũ chép phẳng file agent nên mất đường dẫn `references/` (ghi chú GĐ 1 T6.9, GĐ 3 note 27). `docs/producer.md` §16, §18 hàng GĐ 6 cần một lõi, hai bản, installer rules Blender cho Codex, eval kích hoạt, skill Project Setup và so A/B mù giữa hai runtime.

## Outcome

- `build.py` ở gốc repo, theo `build.py` của kit: `dist/zps-3dp-<edition>-v<VERSION>/` cho `claude` và `codex`, có `skills/`, `install.py`, `manifest.json`; bản Claude thêm `agents/` (file agent phẳng), bản Codex thêm `installer/codex_rules.py`. Build fail khi một kiểm tĩnh sai.
- `editions/{claude,codex}/edition.json` (`skill_suffix`, `display_suffix`, `install_root`, `models`, …) và `adapter.md` chỉ chứa cơ chế runtime. `docs/EDITIONS.md` là bảng khác biệt.
- Bản Codex: hậu tố `-codex` cho mọi skill và agent; description ≤ 300 ký tự; câu chặn gọi nhầm đứng đầu description của agent.
- Script biết runtime của mình qua `runtime.json` do build ghi. Mọi dòng ledger có cột runtime. Ledger ghi model thật mỗi lần giao (theo `models` của edition). `deliver-<runtime>/` theo `PRODUCER_ROOT`.
- `evals/triggers.json`: câu dương và âm cho mọi skill và agent, có câu âm trùng kit. Build chạy phần tĩnh.
- Skill `zps-3dp-project-setup`: chỉ gọi tường minh; tạo `PROJECT-PROFILE.yaml` và `policy.yaml` cùng người dùng.
- A/B: `P ab board` (trang so cặp mù, dùng renderer chung), `P ab prefer`, `P ab judge` (reviewer so cặp hai lần đổi thứ tự), `P compare [--reveal]`.

## Surfaces

- Người dùng: chạy `build.py` và `install.py`; duyệt hai bản cạnh nhau trên trang A/B; bấm "Bản nào tốt hơn".
- Producer trên mỗi runtime: đọc `references/runtime.md` (adapter) để biết cách gọi agent, resume, hook, gửi file.
- Codex: file rules cho Blender ngoài sandbox.

## Constraints

- Một lõi: sửa prompt agent ở một chỗ (`src/`). Adapter không chứa quy tắc nghiệp vụ (D22.9).
- Không gọi dịch vụ trả phí, không chạy `codex` thật, không chạy eval kích hoạt thật.
- Trang A/B không lộ tên runtime, tên model hay thư mục runtime, kể cả URL ảnh và tên file tải về.
- Không sửa file chép từ kit.

## Out of scope

Chạy thật trên Codex (spawn, resume, `codex exec` lồng, token); eval kích hoạt thật; chọn model Codex thật.

## Decisions

Của người dùng (qua task): chép cấu trúc kit; Codex `-codex`, description ≤ 300; rules chỉ cho Blender chạy script đã cài; eval tĩnh trong build, eval thật chỉ ghi cách chạy; A/B theo review-board §8.

Của em:
- Runtime đọc từ `runtime.json` (build ghi), `PRODUCER_RUNTIME` ghi đè; cây `src/` là `src`. `production-<runtime>` chỉ nhận lệnh ghi của đúng runtime đó.
- Trang A/B chạy một tiến trình con `producer.py ab side` cho mỗi bên với `PRODUCER_ROOT` của bên đó, vì `ROOT` là hằng của module. Mọi chữ trên trang qua bộ lọc tên runtime và tên model.
- `P compare` không có `--reveal` chỉ in theo asset với nhãn A/B; tổng theo runtime, token theo model và Elo chỉ có khi `--reveal`.
- `--reveal` cần: mọi asset trong lô đã DUYỆT 2 ở cả hai bên và có lựa chọn "Bản nào tốt hơn".
- Reviewer so cặp đọc bản chép ảnh của gói cuối trong `ab/judge/`, không đọc thư mục runtime.
- Model Codex trong `edition.json` để `null` (model của phiên) tới khi chạy thật.

## Open questions

- Codex `spawn_agent` có nhận model không; resume bằng `send_message` (checklist 61, 73 phía Codex).
- `codex exec` lồng trong phiên Codex lấy được ảnh không (checklist 74).
- Runtime nào báo token theo lần giao (checklist 63).
- Eval kích hoạt thật trên cả hai runtime (checklist 81, 92).
- Rules Blender với lệnh ghép của dòng PID (checklist 91).
