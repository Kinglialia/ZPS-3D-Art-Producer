# Cài đặt và tuỳ chỉnh

Cần Python 3.11+ (`python3 --version`). Không cần cài thư viện.

## Cài skill (một lần cho mỗi project Claude Code)

1. Copy thư mục skill vào `.claude/skills/zps-3dp-producer/`.
2. Copy 3 file trong `templates/agents/` vào `.claude/agents/`. Sửa dòng `skills:` của modeller.md cho khớp `name` trong frontmatter skill modeller. Agent phải cùng phạm vi với skill: skill ở `~/.claude/skills/` thì agent đặt ở `~/.claude/agents/`.
3. Thêm vào `CLAUDE.md` của project (file này luôn được nạp, nên skill được kích hoạt kể cả khi người dùng chỉ nói "tiếp tục"):
   ```markdown
   Project này dùng skill zps-3dp-producer để điều phối art. Mọi việc về asset, concept trong _approved, feedback, tiến độ: dùng skill zps-3dp-producer, bắt đầu từ output của `producer.py next`.
   ```
4. Gộp `templates/settings.snippet.json` vào `.claude/settings.json`:
   - Hook SessionStart in `next --session` vào context khi mở session.
   - Allow rules để subagent chạy nền không kẹt chờ xin quyền. Cú pháp rule có thể khác giữa các bản Claude Code; không ăn thì thêm bằng `/permissions`.
5. Mở session mới (agent file chỉ nạp lúc khởi động), chạy `/agents` để thấy modeller, texturer, reviewer.
6. Chạy tay `codex exec` một lần với skill texture để chắc cú pháp gọi skill và quyền ghi file khi chạy không tương tác. Sửa `external_command` trong pipeline.toml cho khớp.

## Project mới

```
python3 .claude/skills/zps-3dp-producer/scripts/producer.py init --project "New Last Order" --concepts "~/MyWorks/Concepts/New Last Order"
```

Lệnh này tạo (không ghi đè file đã có):
- `production/`: pipeline.toml đã điền đường dẫn, `rubrics/` (default, building), ledger.md, schedule.md.
- Trong thư mục concept: `_approved/` và `GUIDELINE.md` đã điền tên project và đường dẫn.

Sau đó:
1. Gửi `GUIDELINE.md` cho Concept Artist, View Concept Artist và AD khi làm việc với họ. Gửi file, không dán nội dung, để luôn chỉ có một bản. Sửa guideline thì tăng số phiên bản ở dòng đầu.
2. AD tạo `art-direction/README.md` theo format trong guideline. Chưa có cũng chạy được; brief sẽ ghi "chưa có art direction".
3. Duyệt `production/rubrics/building.md`, đổi dòng đầu thành `<!-- status: approved -->`.

Muốn đổi guideline cho mọi project sau này: sửa `templates/GUIDELINE.md` trong skill. Project đã tạo giữ bản riêng của nó.

## Sửa pipeline

Mọi thay đổi workflow nằm ở `production/pipeline.toml`:
- **Thêm bước:** thêm khối `[[steps]]` đúng vị trí, tạo file agent trong `.claude/agents/`, mở session mới. Id của bước cũng là tag `steps:` mà AD dùng trong README art direction.
- **Đổi model:** sửa `model`; `escalate_model` dùng khi vòng sửa vượt `resume_rounds`.
- **Đổi output bắt buộc:** sửa `outputs`. Thiếu file thì asset bị blocked.
- **Đổi chuẩn preview:** sửa `[preview].spec`. Brief đưa nguyên văn cho worker.
- **Ngưỡng ảnh concept:** `[intake].min_images`.
- **Bỏ review cho bước rẻ:** `gate = "none"`. Bước cần mắt người dùng: `gate = "human"`.

Script đọc lại pipeline mỗi lệnh, nên asset đang chạy theo pipeline mới ngay. Đổi `id` của bước mà asset đang đứng ở đó thì `validate` báo lỗi: sửa `stage` trong status.json của asset đó.

## Thêm worker gọi công cụ ngoài

Mẫu như texturer: model rẻ (sonnet), không preload skill. Lệnh ngoài đặt trong `external_command` của bước. Biến: `{request}`, `{vdir}`, `{log}`.

## Review page

`P serve` mở http://127.0.0.1:8765 (chỉ máy local). Mỗi asset hiện ảnh concept đã duyệt, các phiên bản gần nhất và model .glb xoay được. Nút Duyệt, Làm lại, Chỉ ghi chú ghi thẳng vào feedback.md và status.json. Mở `production/review.html` trực tiếp thì xem được nhưng không gửi feedback và không hiện ảnh concept.

`<model-viewer>` tải từ CDN của Google, cần mạng. Đổi phiên bản ở hằng `MODEL_VIEWER_JS` đầu script.

## Dọn file

`P cleanup <id>` chỉ chạy khi asset đã done; mặc định dry-run, `--yes` để xoá work/ của phiên bản không được duyệt, `--all` để xoá cả work/ của bản đã duyệt. Xong hẳn: `P archive <id>`.
