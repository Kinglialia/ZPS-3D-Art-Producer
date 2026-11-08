# Spec — Project Profile, thẻ asset và skill Project Setup (v1)

Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D13).

---

## 1. Thông số nằm ở đâu

Agent đọc theo thứ tự dưới đây. Lớp sau ghi đè lớp trước.

| # | Lớp | Chứa gì | Ai viết |
|---|---|---|---|
| 1 | **Mặc định của skill** | Số chung, không gắn với dự án nào. Ví dụ: ngưỡng pixel 3 px / 16 px, 3 vòng review (D11), 4 nhóm kiểm texture | Có sẵn trong bộ skill |
| 2 | **Preset** theo loại game | Thông số kỹ thuật theo camera và nền tảng. Ví dụ: camera, texel tối thiểu, padding, trần tris theo hạng | Có sẵn vài preset trong bộ skill. Thêm preset mới khi cần |
| 3 | **Profile dự án** (`PROJECT-PROFILE.yaml`) | Chỉ những gì giống nhau cho mọi asset của dự án đó | Skill Project Setup, cùng anh |
| 4 | **Thẻ asset** (file `asset-card.yaml` trong `_approved/<id>/`; brief trỏ tới file này) | Những gì khác nhau giữa các asset | Concept Artist (ngoài scope) |

## 2. Preset

Mỗi preset là một file YAML trong bộ skill, ví dụ `presets/topdown-mobile-lowpoly.yaml`.

```yaml
camera: {azimuth_deg: 0, elevation_deg: 35, fov_v_deg: 40, target_px_height: 400}
tiers:                      # hạng → trần tris
  hero: 5000
  standard: 3000
  background: 1000
uv: {padding_px: 16, texel_min_px_per_m: 64}   # tính ở độ phân giải làm việc
screen_tris_max_small_ratio: null              # null = chỉ cảnh báo (D7.7)
```

Hạng chỉ quyết định trần tris. Hạng **không** quyết định độ phân giải texture.

## 3. Profile dự án

Ngắn, khoảng 15–20 dòng. Không có trường gắn với một loại asset (không có trường "cửa", "tường", "mái").

```yaml
project: <tên>
preset: topdown-mobile-lowpoly
paths: {approved: "<thư mục concept>/_approved", production: "production", deliver: "deliver"}
has_map: true                                # true: intake bắt buộc có <id>.layout.md; false: W×D×H lấy từ size_m của thẻ asset
pilot_asset: <mã asset pilot đã duyệt>      # dùng để so tris/m² và màu vật liệu
scale_refs:                                  # danh sách mở; mỗi dự án tự đặt tên
  - {name: nhân vật, height_m: 1.6, _source: "..."}
hidden_side_rules:                           # chữ tự do
  - "..."
style:
  light_convention: unlit_flat | painted_top_light
  top_vs_side_L: 0
  view_bg: null                              # null = pick_bg.py tự chọn
approvals:                                   # ai duyệt sau khi reviewer PASS (D14.4)
  blockout: human                            # human | reviewer
  views_rest: human
  model: human
  assemble: human                            # luôn human
review_board: local                          # local | local+remote (D19)
detail_examples:                             # có sau pilot
  geometry: [...]
  texture_only: [...]
texture_simple:                              # ngưỡng D10
  max_materials: 2
  max_color_clusters: 6
overrides: {}                                # chỉ khi cần đổi số của preset
```

- Mỗi giá trị có thể kèm `_source`: "anh chốt <ngày>", "từ pilot <mã>", "mặc định".
- Mọi agent ghi **hash của profile** đã dùng vào báo cáo. Khi profile đổi, Producer biết asset nào làm theo bản cũ.

## 4. Thẻ asset

Thẻ asset là file `asset-card.yaml` trong `_approved/<id>/`. Brief trỏ tới file này. Concept Artist ghi (ngoài scope, xem `out-of-scope-changes.md`).

```yaml
asset: 05-warehouse
type: building                 # building | prop | tree | rock
tier: standard                 # hero | standard | background
texture_res: null              # null = 2048
tris_max: null                 # null = theo hạng
scale_overrides:               # ví dụ cửa riêng của công trình này
  - {name: cửa, height_m: 1.6}
symmetric: {left_right: true, front_back: true}
size_m: null                   # {w, d, h} (mét); bắt buộc khi has_map: false; check_card.py kiểm
hidden_sides: [...]            # thiết kế phần khuất
real_texture_only_notes: [...]
```

- **Độ phân giải texture:** làm theo thẻ asset. Nếu thẻ không ghi, mặc định 2048. Muốn đổi cho một asset cụ thể, anh dùng một agent khác cập nhật sau. Bộ skill không tự thu nhỏ hay phóng to texture.
- Thẻ asset thắng profile và preset.

## 5. Skill Project Setup

Tên kỹ thuật: `zps-3dp-project-setup`. Đây là **skill chạy trong phiên chính**, không phải sub-agent, vì phải hỏi anh.

| Việc | Cách làm |
|---|---|
| Tạo profile | Chọn preset. Hỏi anh các trường riêng của dự án: thước tỉ lệ, quy ước style, quy tắc phần khuất, đường dẫn, dự án có map hay không (`has_map`; `false` thì mọi thẻ asset phải có `size_m`), và **ai duyệt từng điểm duyệt** (`approvals`; gợi ý: pilot để `human` hết). Ghi `PROJECT-PROFILE.yaml` |
| Cập nhật sau pilot | Agent **đề xuất** nội dung mới (`detail_examples`, `pilot_asset`). Anh duyệt, rồi skill ghi. Agent không tự sửa profile |
| Kiểm định dạng | `check_profile.py`: đủ trường bắt buộc, đúng kiểu, preset tồn tại. Mọi agent chạy script này trước khi làm việc |

MapLayout (ngoài scope) đọc thước tỉ lệ từ profile, không tự giữ thước riêng.

## 6. Flow khởi tạo dự án

1. Anh gọi Producer.
2. Producer chạy `check_profile.py`.
   - **Chưa có hoặc thiếu trường bắt buộc:** Producer vào chế độ khởi tạo, nạp skill Project Setup trong phiên chính, và làm cùng anh.
   - **Đã đủ:** Producer vào chế độ điều phối.
3. Khi đủ thông tin: Project Setup ghi `PROJECT-PROFILE.yaml`, chạy lại `check_profile.py`.
4. **Producer nhắc anh xóa context và mở phiên mới**, với đúng câu lệnh của runtime (lấy từ adapter):
   - Claude Code: "Profile đã xong. Anh gõ `/clear` (hoặc mở phiên mới), rồi gọi lại `/zps-3dp-producer` để bắt đầu với context sạch."
   - Codex: "Profile đã xong. Anh gõ `/new`, rồi gọi lại Producer để bắt đầu với context sạch."
5. Phiên mới: Producer chỉ đọc profile và sổ trạng thái `status.json` / `dashboard.md`. Producer không dựa vào trí nhớ của cuộc trao đổi lúc khởi tạo.

**Producer cũng nhắc anh mở phiên mới khi:**
- Profile vừa được cập nhật sau pilot.
- Context của Producer đã dài sau một lô.

## 7. Sửa theo D14

- `visual_checks` bỏ khỏi profile, chuyển vào rubric theo loại (`production/rubrics/<loại>.md`), chia mục theo bước.
- Thêm `approvals`. Đổi bằng `P approvals set` (script), không cần Project Setup và không cần phiên mới.
- Đường dẫn: `_approved/` (đầu vào), `production/` (làm việc), `deliver/` (kết quả đã duyệt).

## 8. Việc cần kiểm khi viết code

Ghi trong `docs/coding-checklist.md`.
