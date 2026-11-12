# Model: detail pass, `model.md`, kết quả tool

Nguồn: `docs/agents/3d-artist.md` §4–§7. Số trong mục này đọc từ `F/spec.json` (`make_spec.py`), không đọc lại profile hay thẻ.

## 1. Detail pass

Blockout chỉ để đo. Detail pass là bắt buộc: `check_detail.py` fail khi part build của `F` không nhiều tris hơn part build của blockout.

Lớp 1, quy tắc chung:

1. Silhouette trước. Chi tiết đổi đường viền ở camera game hoặc góc 3/4: dựng hình học. Chi tiết chỉ đổi màu hay hoa văn trên mặt phẳng: để texture.
2. Quy đổi ra pixel bằng `spec.model.px_per_m` (= `target_px_height` / chiều cao bbox trên màn hình ở camera game, cùng tỉ lệ với `thumb.png`). Nhô hoặc lõm ≥ `relief_min_px` px (mặc định 3): dựng hình học. Viền mỏng hoặc chi tiết cần alpha: độ rộng × texel (px/m) < `alpha_min_px` px (mặc định 16): dựng hình học, không dùng alpha.
3. Mặt phẳng giữ tối thiểu. Chỉ thêm cạnh khi cạnh đó tạo silhouette, tạo bevel, hoặc cần cho UV.
4. Chi tiết nhận diện nhỏ hơn ngưỡng: phóng to độ sâu, không bỏ chi tiết. Không đổi param trong `fixed_params`.
5. Vật tròn: đủ segment để viền không gãy ở camera game. `join_mesh.py` đặt smooth shading. Part tròn chỉ tách cạnh > 60°: `cylinder`, `bevel_box`, part `custom` có `"round": true`. Part khác tách cạnh > 20°. Hàm `custom` của asset dựng vật tròn: ghi `"round": true` vào part đó. Mặt phẳng lớn cạnh bevel vẫn phẳng: `join_mesh.py` cho mặt lớn giữ pháp tuyến của nó, chỉ dải bevel chuyển sáng. Không thêm vòng cạnh để chống vệt sáng trên mặt phẳng.
6. Vật phát sáng hoặc chuyển động (lửa, khói, nước): card unlit.
7. Ghi chú real/texture_only của thẻ (`real_texture_only_notes`) thắng các quy tắc trên.
8. Bevel chỉ khi `spec.model.bevel` khác `false`. Dùng đúng `radius_m` và `segments` của `spec.model.bevel`. Không áp ngưỡng pixel của quy tắc 2 cho bevel: bevel toon là style, bán kính của nó thường dưới 3 px. `make_spec.py` lấy kiểu bevel từ trường `bevel` của thẻ, không có thì `style.bevel` của profile; số lấy từ preset. Ghi chú chữ của thẻ không bật bevel.

9. Model nằm trong bbox của blockout ±2 % trên mỗi trục. `check_detail.py --before-join` so ngay sau mỗi lần dựng (`detail.bbox`). Chi tiết làm bbox vượt: thu vào trong.

Lớp 2: `detail_examples` của profile (`geometry`, `texture_only`), có sau pilot. Không có thì chỉ dùng lớp 1.

Part mới theo hợp đồng part graph của blockout. Hai mặt trùng khít cùng hướng (part chìm phẳng mặt trong part khác) gây z-fighting: `check_mesh.py` fail. Để part nhô ít nhất 1 mm, hoặc để chi tiết đó cho texture.

## 2. Gộp mesh và UV

- `build_model.py` chạy `join_mesh.py` rồi `unwrap.py` trong một phiên Blender, mỗi tool ghi file như khi chạy riêng.
- `join_mesh.py`: một object, một mesh, một material, tên là mã asset. Không weld, không boolean. Xóa mặt không tia nào từ ngoài chạm tới (mặt một part giấu trong hoặc sát part khác). Mặt đất dưới chân asset cũng chặn tia, nên mặt đáy nằm trên đất bị xóa. `spec.json` có `bottom_visible: true` thì giữ đáy. `join.removed_faces_seen` fail khi một mặt đã xóa vẫn thấy được từ 5 trục (cả từ dưới khi `bottom_visible`) hoặc từ trên. Tách cạnh theo quy tắc 5 của mục 1. Origin tâm đáy.
- `unwrap.py`: `xatlas_unwrap()` của kit ở `uv.resolution`, padding `uv.min_padding_px` giữa các đảo, rồi thu UV vào trong để mép atlas cũng cách đúng padding. Không có xatlas: lỗi, không có đường dự phòng.
- Padding của preset tính ở 2048. `make_spec.py` nhân với `texture_res` / 2048 (8 px ở 1024).
- `check_uv_edge.py` `uv.stretch`: phần diện tích có tỉ lệ hai giá trị kỳ dị của Jacobian UV lớn hơn `spec.model.uv_stretch.max_ratio`. Ngưỡng là số tạm, chưa đo trên asset thật. `review/uv_checker.png` cho thấy chỗ kéo giãn.
- Quy ước góc cho `sun`, `concept_cam`, `camera` và `concept.cameras` của `spec.json`: `azimuth_deg` 0 = camera (hoặc nắng) ở phía trước (−Y), nhìn về +Y; số dương đưa camera sang +X, bên phải người nhìn mặt trước; `elevation_deg` = số độ trên mặt đất. `camera_fit.json` của blockout dùng cùng quy ước.
- `make_spec.py` chép mask concept của blockout (`work/spec.json` của blockout) vào `F/concept/`, và camera đã khớp (`camera_fit.json`) vào `spec.concept`. `render_views.py --spec F/spec.json` vẽ `overlay_*` từ đó.
- Camera game của `spec.json` cố định (`distance_m`): asset cao `target_px_height` px trên màn 1080 px. `screen_tris_check` đo ở đúng cỡ đó.
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
| `F/spec.json`, `F/concept/` | `make_spec.py`; `sun`, `concept_cam` do worker thêm |
| `F/assembly.json`, `F/parts/`, `F/assembled.glb`, `F/parts_lib.py` | `gate_all.py` (gọi `build_parts.py` của blockout) |
| `F/review/gates/<part>.json` | `gate_all.py` (gọi `self_build/gates.py`) |
| `F/<id>.blend`, `F/review/join.json` | `build_model.py` (`join_mesh.py`) |
| `F/<id>-untextured.glb`, `F/review/unwrap.json` | `build_model.py` (`unwrap.py`) |
| `F/review/checks/{detail,mesh,uv_edge}.json` | `gate_all.py` sau khi gộp (`check_*.py`) |
| `F/review/checks/{detail_build,mesh_build}.json` | `gate_all.py` trước khi gộp (`check_detail.py`, `check_mesh.py` với `--before-join`) |
| `F/review/checks/inputs.json` | `check_inputs.py` |
| `F/review/checks/qa_<q>.json` | `qa_all.py` (QA kit `asset_checks/<q>.py`) |
| `F/review/renders/` (`clay_*`, `parts_*`, `overlay_*`, `renders.json`) | `render_all.py` (`self_build/render_views.py --work`) |
| `F/review/renders/normal_*`, `normal.json` | `render_all.py` (`self_build/render_views.py --input`, GLB đã join) |
| `F/review/{lit_*,clay_lit_concept,wire_34,thumb,lineup,uv_checker,model_sheet}.png`, `review.json` | `render_all.py` (`render_review.py`) |
