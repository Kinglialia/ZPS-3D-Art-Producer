---
name: zps-3dp-project-setup
description: Tạo PROJECT-PROFILE.yaml và policy.yaml cùng người dùng cho zps-3dp-producer. Chỉ gọi tường minh: Producer nạp khi profile thiếu hoặc sai, hoặc người dùng gọi /zps-3dp-project-setup.
disable-model-invocation: true
---

# ZPS-3DP · Project Setup

Bạn làm cùng người dùng trong phiên chính. Bạn hỏi và đề xuất; người dùng quyết. Bạn chỉ ghi `D/PROJECT-PROFILE.yaml`. `D/policy.yaml` chỉ đổi qua `P approvals set`.

`S` = `.claude/skills/zps-3dp-producer` (thư mục skill Producer). `PY` = `S/scripts/.deps/venv/bin/python`. `P` = `PY S/scripts/producer.py`, chạy từ gốc project. Thiếu `PY`: bảo người dùng chạy `bash S/scripts/setup_deps.sh` một lần. `D` = thư mục làm việc của Producer: `$PRODUCER_ROOT` của phiên, mặc định `production`; `P init` in ra thư mục này.

## Tạo profile

1. Chưa có `D/`: hỏi tên dự án và thư mục concept, rồi chạy `P init --project "<tên>" --concepts "<thư mục>"`.
2. Chọn preset: đọc `S/presets/*.yaml` (camera, trần tris theo hạng). Đề xuất một preset kèm lý do một dòng. Người dùng chọn.
3. Chưa có `D/PROJECT-PROFILE.yaml`: chép `S/templates/PROJECT-PROFILE.yaml` vào đó. Hỏi từng nhóm, mỗi lần một nhóm, kèm giá trị gợi ý:
   - `has_map`: dự án có map không. `false` thì mọi thẻ asset phải có `size_m`.
   - `scale_refs`: thước tỉ lệ (nhân vật, cửa, …), đơn vị mét.
   - `style`: `light_convention` (`unlit_flat` | `painted_top_light`), `top_vs_side_L`, `view_bg` (`null` = script tự chọn).
   - `hidden_side_rules`: quy tắc phần khuất mặc định.
   - `paths`: `approved` (thư mục `_approved`), `env_file` (file chứa `MESHY_API_KEY`; bỏ khóa này thì bước texture chỉ VẼ MỚI). Không đọc, in hay chép file `.env`.
   - `texture_simple`: giữ mặc định khi người dùng không có ý kiến.
4. Giá trị người dùng chốt: thêm `_source: "anh chốt <YYYY-MM-DD>"`. Giá trị mặc định: `_source: "mặc định"`.
5. `pilot_asset: null` khi chưa có pilot. Không ghi `approvals` hay `review_board` vào profile. Không ghi trường của một loại asset (cửa, tường, mái). Chỉ ghi `overrides` khi người dùng muốn đổi số của preset.

## Tạo chính sách

6. Hỏi ai duyệt từng điểm duyệt `blockout`, `views_rest`, `model`: `human` hoặc `reviewer`. Gợi ý cho pilot: `human` hết. Mỗi điểm khác `human`: `P approvals set <bước> reviewer --by "<nguyên văn>"`. `model reviewer` tốn credit Meshy: hỏi lại người dùng, rồi thêm `--confirm-spend`.
7. Hỏi trang duyệt: `local` hoặc `local+remote`. `local+remote` chỉ dùng được khi runtime có tool Artifact (`S/references/runtime.md`, mục Review Board). Khác `local`: `P approvals set review_board local+remote --by "<nguyên văn>"`.

## Kiểm và kết thúc

8. Chạy `PY S/scripts/check_profile.py D/PROJECT-PROFILE.yaml`. Có lỗi thì sửa cùng người dùng. Không in gì là xong.
9. Nhắc người dùng mở phiên mới bằng lệnh của runtime (`S/references/runtime.md`, mục Phiên mới), rồi gọi lại Producer. Phiên mới không dựa vào cuộc trao đổi này.

## Cập nhật sau pilot

- Pilot qua DUYỆT 2: đề xuất `pilot_asset: <id>` và `detail_examples` (`geometry`, `texture_only`) từ `README.md` của gói pilot trong thư mục deliver của runtime. Người dùng duyệt thì ghi, kèm `_source: "từ pilot <id>"`. Không tự sửa profile.
- Ghi xong: chạy lại bước 8, rồi nhắc mở phiên mới như bước 9.
