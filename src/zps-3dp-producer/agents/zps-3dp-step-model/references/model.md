# Model: detail pass, `model.md`, kết quả tool

Nguồn: `docs/agents/3d-artist.md` §4–§7. Số trong mục này đọc từ `F/spec.json` (`make_spec.py`), không đọc lại profile hay thẻ.

## 1. Detail pass

Blockout chỉ để đo. Detail pass là bắt buộc: `check_detail.py` fail khi part build của `F` không nhiều tris hơn part build của blockout.

Lớp 1, quy tắc chung:

1. Silhouette trước. Chi tiết đổi đường viền ở camera game hoặc góc 3/4: dựng hình học. Chi tiết chỉ đổi màu hay hoa văn trên mặt phẳng: để texture.
2. Quy đổi ra pixel bằng `spec.model.px_per_m` (= `target_px_height` / chiều cao thật). Nhô hoặc lõm ≥ `relief_min_px` px (mặc định 3): dựng hình học. Viền mỏng hoặc chi tiết cần alpha: độ rộng × texel (px/m) < `alpha_min_px` px (mặc định 16): dựng hình học, không dùng alpha.
3. Mặt phẳng giữ tối thiểu. Chỉ thêm cạnh khi cạnh đó tạo silhouette, tạo bevel, hoặc cần cho UV.
4. Chi tiết nhận diện nhỏ hơn ngưỡng: phóng to độ sâu, không bỏ chi tiết. Không đổi param trong `fixed_params`.
5. Vật tròn: đủ segment để viền không gãy ở camera game. `join_mesh.py` đặt smooth shading và tách cạnh > 20°.
6. Vật phát sáng hoặc chuyển động (lửa, khói, nước): card unlit.
7. Ghi chú real/texture_only của thẻ (`real_texture_only_notes`) thắng các quy tắc trên.
8. Bevel chỉ khi `spec.model.bevel` là true, cùng ngưỡng pixel.

Lớp 2: `detail_examples` của profile (`geometry`, `texture_only`), có sau pilot. Không có thì chỉ dùng lớp 1.

Part mới theo hợp đồng part graph của blockout. Hai mặt trùng khít cùng hướng (part chìm phẳng mặt trong part khác) gây z-fighting: `check_mesh.py` fail. Để part nhô ít nhất 1 mm, hoặc để chi tiết đó cho texture.

## 2. Gộp mesh và UV

- `join_mesh.py`: một object, một mesh, một material, tên là mã asset. Không weld, không boolean. Xóa mặt không tia nào từ ngoài chạm tới (mặt một part giấu trong hoặc sát part khác). Tách cạnh gắt > 20°. Origin tâm đáy.
- `unwrap.py`: `xatlas_unwrap()` của kit ở `uv.resolution`, padding `uv.min_padding_px` giữa các đảo, rồi thu UV vào trong để mép atlas cũng cách đúng padding. Không có xatlas: lỗi, không có đường dự phòng.
- Làm và giao ở `texture_res` của spec. Không đổi độ phân giải.

## 3. `model.md`

Review page hiện ba dòng đầu (bỏ dòng trống) làm tóm tắt cho người dùng:

```text
# Model <id> v<N>
<chi tiết chính đã dựng, một dòng, ví dụ "diềm mái, đầu dầm, bậc cửa">
<tris part blockout> → <tris cuối> / trần <trần>; <tris/m²> tris/m²
```

Các mục sau, đúng thứ tự:

1. Bảng detail pass: `| Thêm gì | Vì sao (đổi silhouette ở góc nào, bao nhiêu px) | Tris |`.
2. Thông số: trần tris, `texture_res`, padding, texel, ngưỡng pixel, mỗi số kèm nguồn trong `spec.json` `sources`; nguồn "mặc định" ghi "dùng mặc định".
3. Ghi chú real/texture_only, chép nguyên từ thẻ.
4. `screen_tris_check`: tỉ lệ tam giác nhỏ ở camera game (chỉ cảnh báo).
5. `sun`, `concept_cam` đã ghi vào `spec.json`, và cách ước lượng.
6. Phương án `param` (vòng sửa): giá trị của a, b, c.
7. Thay đổi so với version trước: part nào, param nào, vì sao.
8. Nguồn mâu thuẫn: cả hai nguồn và lựa chọn.

## 4. Kết quả tool

Mọi JSON cùng dạng kit: `overall`, `checks[]` (`check`, `status`, `value`, `threshold`, `note`), `data`.

| File | Ghi bởi |
|---|---|
| `F/spec.json` | `make_spec.py`; `sun`, `concept_cam` do worker thêm |
| `F/assembly.json`, `F/parts/`, `F/assembled.glb` | `self_build/assembly.py` |
| `F/review/gates/<part>.json` | `self_build/gates.py --out` |
| `F/<id>.blend`, `F/review/join.json` | `join_mesh.py` |
| `F/<id>-untextured.glb`, `F/review/unwrap.json` | `unwrap.py` |
| `F/review/checks/{inputs,detail,mesh,uv_edge}.json` | `check_*.py` |
| `F/review/checks/qa_<q>.json` | QA kit `asset_checks/<q>.py` |
| `F/review/renders/` (`clay_*`, `normal_*`, `parts_*`) | `self_build/render_views.py` |
| `F/review/{lit_*,clay_lit_concept,wire_34,thumb,lineup,model_sheet}.png`, `review.json` | `render_review.py` |
