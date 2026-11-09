# Intent: GĐ 2, Concept Views (`views_front`, `views_rest`)

## Problem

GĐ 1 dừng ở `done_enabled` sau khi blockout được duyệt. `docs/producer.md` §18 hàng GĐ 2 cần hai bước view, công cụ gọi Codex sinh ảnh và đường quay lại `regen_front`. Chưa có agent, tool hay luồng nào cho các bước này.

## Outcome

- `pipeline.toml` bật `views_front` (gate `review`) và `views_rest` (gate `review_human`). Các bước sau vẫn tắt.
- Luồng chạy được: blockout đã duyệt → `views_front` → `views_rest` → `waiting_human` → duyệt → `done_enabled`.
- `TOP_FIX: regen_front` ở `views_rest` mở lại `views_front` từ bản đã duyệt. Finding đó đi theo sang `views_front`. Front được duyệt lại thì `views_rest` dựng lại cả bộ.
- Agent `zps-3dp-step-views` (worker) và `zps-3dp-check-views` (reviewer), cùng tool trong `agents/zps-3dp-step-views/tools/`.
- `scripts/gen_image_codex.py`: gọi `codex exec`, khung prompt cố định, kiểm ảnh, 3 lần lỗi kỹ thuật thì dừng, tự ghi PID cho slot `codex_image`.
- Một test e2e chạy CLI thật từ duyệt blockout qua hai bước view tới duyệt, có một vòng `regen_front`.

## Surfaces

- Người dùng: duyệt `views_rest` trên review board bằng `VIEWS_sheet.png`.
- Producer: chỉ chạy lệnh `P`, mỗi lệnh in một dòng.
- Subagent view: đọc brief, chạy tool, gọi Codex qua `gen_image_codex.py`.
- Codex CLI: chỉ vẽ. Mỗi lần gọi tốn lượt Codex thật.

## Constraints

- Test không gọi `codex` thật. Test dùng file `codex` giả trên `PATH`.
- File chép từ kit giữ nguyên byte, ghi sha256 trong `SOURCE.md`. Phần sửa nằm trong tool của mình.
- Brief chỉ nêu file cần đọc: `final/` đã duyệt của bước đầu vào và đúng các file concept bước đó cần.
- Acceptance của reviewer là điều thấy được trên ảnh cùng view, hoặc số không chuẩn hóa (dE). IoU và % vị trí chi tiết chuẩn hóa theo bbox, nên không làm ngưỡng acceptance.
- Mỗi lệnh `P` in một dòng ngắn. File agent ngắn, chi tiết nằm trong `references/`.

## Out of scope

`model`, `texture`, `assemble`; Way B (một ảnh nhiều view, `sheet.py` của kit); tool ảnh phía Claude khi Codex hỏng (D15.2: người dùng quyết); bản Codex của agent; chạy Codex thật.

## Decisions

Của người dùng (qua task):
- Bật hai bước view; bước sau tắt.
- Reviewer dùng contract của blockout; rubric có mục `## views_front`, `## views_rest`.
- Không chạy Codex thật trong việc này.

Của em:
- Guide và ID của 5 view nằm trong `views_front/vN/final/guides/`. Lý do: `views_rest` và reviewer cần guide, và guide phải nằm trong `final/` để hash khóa khi duyệt.
- `views_rest/final/` chỉ chứa thứ bước này tạo ra (4 view, README, report). Front, guide, `concept_colors.json`, `bg_color.json` ở lại `views_front/final/` (D22.14: không chép).
- `pipeline.toml` có thêm `inputs` (các bước đã duyệt mà brief trỏ tới) và `concept` (file concept bước cần). Mặc định: bước liền trước, mọi file bắt buộc.
- `views_front.uses` thêm `blender`, vì guide render trong Blender.
- `regen_front` là kiểu đơn (một id) và thắng `regen` khi cùng mức, vì front mới làm mọi view khác phải gen lại.
- `regen_front` chép finding sang `findings.json` của bản front đã duyệt với id mới, loại `regen`, và đặt `top_fix` của bản đó. Brief sửa front và reviewer front đọc nó như mọi finding.
- Đổi bước khi mở lại (regen_front, hoặc người dùng redo bước trước) thì không resume worker cũ. Lý do: worker cũ có context của bước khác.
- Front duyệt lại → `views_rest` dựng lại từ đầu (không phải vòng sửa từ bản cũ), vì front là chuẩn màu của mọi view.
- `regen_front` lần hai trong một đợt feedback → `waiting_human`. Lý do: mỗi lần tốn ít nhất 5 lần gọi Codex; giống luật `need_evidence` lần hai (D20.15).
- Finding mới ở `views_rest` có `region` mở đầu bằng tên view (`back: …`). Script từ chối finding về front, trừ `regen_front`. Lý do: checklist 69 kiểm được bằng script.
- Finding `note_exception`, `note_texture` phải ở mức `minor`. Lý do: loại ghi chú không gây FIX, nên mức nặng hơn tạo report không thể hợp lệ.
- `measure_views.py` của kit chép nguyên. Sửa G1 (tách nền theo màu khóa trên toàn ảnh) nằm trong `measure.py` của mình.
- Worker tự gen lại một lần cho view mà `measure` báo fail, rồi mới báo cáo. Phần còn lại do vòng review.
- `diff_guides.py`: view đổi khi > 0,5% diện tích vật đổi mã vật liệu hoặc tỉ lệ bbox đổi > 1%. View giữ lại vẫn được đo lại với guide mới.

## Open questions

- Cờ `codex exec` (`-c model_reasoning_effort=…`, `--skip-git-repo-check`, prompt qua stdin với `-`) chưa thử trên máy thật: cần một lần chạy có trả phí.
- Astra có lưu ảnh đúng đường dẫn và ghi `result.json` không (checklist 9, 74): cần chạy thật.
- Ngưỡng của `measure_views` mới thử trên ảnh tổng hợp.
