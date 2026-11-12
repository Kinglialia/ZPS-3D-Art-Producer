# Spec — sub-agent Blockout (v1.3)

Tên kỹ thuật: `zps-3dp-step-blockout`. Tên hiển thị: 3DP Step · Blockout. Reviewer: `zps-3dp-check-blockout` (D6.5, đổi tên theo D23.2).

Duyệt: 2026-11-08. Sửa v1.1 cùng ngày (D5). v1.2: 2026-11-09 (D21). v1.3: 2026-11-09 (D22). Quyết định nền: `docs/decisions.md` (D1–D5, D21, D22).
Nguồn kỹ năng: ZPS Art Assets Kit v0.10.4, commit `905dc93` (zps-3d-artist, zps-concept-views).

---

## 1. Mục tiêu và phạm vi

Blockout dựng khối hình học **để đo** cho từng công trình. Blockout là nguồn hình học duy nhất cho Concept Views và 3D Artist. Sau khi duyệt, `sources.json` là nguồn duy nhất cho số hình học ở mọi bước sau (D22.13).

**Dùng cho:** công trình, props cứng, cây và đá low-poly (dùng part `custom`). Part `custom` gọi hàm chung trong `custom_lib.py` của skill, hoặc hàm riêng của asset trong `production/assets/<id>/custom_parts.py` (D27.13, D32). Hàm của asset là Python thuần, chỉ `math`; `custom_mesh.py` chạy nó ngoài Blender và ghi lưới JSON, Blender chỉ dựng từ JSON (D32.2). Cần hàm mới thì Blockout tự viết vào file của asset; không cần anh duyệt. Blockout không sửa thư viện chung.
**Không dùng cho:** nhân vật, sinh vật (D9). Nếu gặp loại này, hoặc dáng quá phức tạp so với primitive, Blockout báo Producer.

| Làm | Không làm |
|---|---|
| Đếm thành phần, đo trên concept, dựng `part_graph.json` + `parts_lib.py` | Quyết định vật liệu, phần khuất, tỉ lệ (việc của Concept Artist và MapLayout) |
| Gắn mã vật liệu từ Material Handoff | Ghi file MAP-LAYOUT |
| Đánh dấu part là khối chính (`mass`) hay mốc đo (`marker`) | Quyết định real / texture_only (việc của 3D Artist) |
| Tự quyết phần khuất khi mô tả không có, và ghi lại | Gen view, detail pass, UV, texture |
| Tự kiểm bằng gate và script, render bộ review | Tự duyệt |

## 2. Đầu vào

| Nguồn | Lấy gì |
|---|---|
| Concept albedo | Hình khối và tỉ lệ để đo. Bản có bóng chỉ để đọc khối |
| Thẻ asset `asset-card.yaml` (concept brief, D22.3) | Phần khuất (`hidden_sides`), đối xứng (`symmetric`), ghi chú real/texture_only (`real_texture_only_notes`) |
| Thẻ asset (`asset-card.yaml`) | Khi `has_map: false`: W×D×H từ `size_m`, chiều cao cửa từ `scale_overrides` |
| File Material Handoff của công trình (và file chung của dự án, nếu có) | Mã vật liệu |
| `<id>.layout.md` (MAP-LAYOUT) trong `_approved/<id>/`, chỉ khi profile có `has_map: true` | W×D×H, có gồm nền bậc hay không, chiều cao cửa, lệch cố ý, chiều cao nhân vật |
| Project profile | Quy tắc phần khuất mặc định, camera game. Khi `has_map: false`: chiều cao nhân vật từ `scale_refs` |

**Nguồn tỉ lệ khi `has_map: false`** (D20.12):
- W×D×H lấy từ `size_m` của thẻ asset.
- `character_h` lấy từ `scale_refs` của profile.
- `door_h` lấy từ `scale_overrides` của thẻ asset.
- Nếu thẻ không có cửa, Blockout đo cửa trên concept, lấy `character_h` làm thước. Blockout ghi giá trị và cách đo vào `sources.json`.
- `files.layout` trong `sources.json` trỏ tới `asset-card.yaml`.

MAP-LAYOUT và Material Handoff có **một file cho mỗi công trình**. Blockout đọc nguyên các file này.

**`sources.json`.** Blockout chép các giá trị cần kiểm từ các file markdown vào `sources.json`. Mỗi giá trị kèm dòng trích nguồn. File còn lưu hash của từng file nguồn. Các script chỉ đọc `sources.json`, không đọc markdown.

```json
{
  "files": {"layout": "<path>", "layout_sha256": "...", "material": "<path>", "material_sha256": "..."},
  "layout": {"w": 4.6, "d": 4.6, "h": 4.0, "includes_base": true, "source": "<dòng trích>"},
  "door_h": 1.6, "door_h_source": "<dòng trích, hoặc cách đo trên concept>", "character_h": 1.6,
  "materials": ["STONE", "TIMBER", "TEAL", "BRASS"],
  "camera": {"azimuth_deg": 0, "elevation_deg": 35, "fov_v_deg": 40}
}
```

Số trong ví dụ chỉ để minh họa định dạng. Khi `has_map: false`, `files.layout` là đường dẫn `asset-card.yaml`, và `layout` lấy từ `size_m`.

- Nếu thiếu concept, hoặc thiếu `<id>.layout.md` khi `has_map: true`, Blockout dừng và báo Producer.
- Nếu một vùng không có mã vật liệu, Blockout báo Producer. Blockout không đoán mã.
- Nếu mô tả không có phần khuất hoặc kích thước, Blockout tự quyết theo quy tắc mặc định của dự án và ghi lại (D3.5).
- Khi dựng lại một version, nếu hash của file nguồn không đổi, Blockout dùng lại `sources.json`.

## 3. Quy trình

| # | Bước | Kiểm bằng |
|---|---|---|
| 1 | Đọc nguồn, ghi `sources.json` | `check_inputs.py` |
| 2 | Đếm thành phần trên concept. Ghi một dòng vào `blockout.md` (ví dụ "4 trụ, 1 cửa, 3 thùng") | Reviewer (tiêu chí 5) |
| 3 | Đo trên concept riêng, không đo trên map tổng. Lấy cửa làm thước. In bảng đo: param, giá trị, nguồn, cách đo | — |
| 4 | Viết part graph theo schema `blockout-1` (mục 9). Primitive: `box`, `wedge`, `cylinder`, `custom` (D24.1). Mái dốc dùng `wedge` hoặc `custom`. Marker nhô hoặc lõm ít nhất 2 cm. Props là part rời. Kích thước lấy từ MAP-LAYOUT (hoặc `size_m` của thẻ asset khi `has_map: false`) nằm trong `fixed_params` | `check_schema.py` |
| 5 | **Khóa tỉ lệ chính trước**: dựng footprint, tường, mái, cửa, các tầng nền. Chạy gate. Chỉ khi các khối này pass mới thêm part phụ | `gates.py`, `check_layout.py` |
| 6 | Thêm part phụ, mỗi lần một part (`assembly.py --upto`) | `gates.py` |
| 7 | Chạy các script kiểm (mục 5). Nếu script fail, Blockout tự sửa trước khi báo cáo | Script |
| 8 | Render bộ review (mục 6). Ghi báo cáo contract (`STATUS / OUTPUT / RUBRIC / ISSUES`), rồi dừng | — |
| 9 | Producer giao check-blockout (D14.1). Nếu FIX, Producer giao lại Blockout với các finding trong `TOP_FIX` (D21.1): loại `structure` đúng một finding; loại `param` mọi finding `param` đang mở, kèm 2–3 phương án giá trị cho reviewer chọn (D26.2, `docs/producer.md` §7). Mỗi finding một lần sửa `part_graph.json`, chạy `check_fix.py` sau mỗi lần. Đọc file JSON gate và check fail mà brief liệt kê trước khi sửa (D26.4). Ghi `FIXED:` vào báo cáo | Reviewer, `check_fix.py` |
| 10 | Duyệt theo `approvals.blockout` (D14.4). Script khóa version bằng hash | Anh hoặc chính sách |

Blockout không gọi reviewer, không gọi agent khác (D14.1). Chỉ đọc file và thư mục brief chỉ định.

`fit_view.py` và `param_fit.py` không bắt buộc. Chỉ dùng chúng khi concept vẽ ở góc 3/4. Chúng không được đổi param trong `fixed_params`.

## 4. Đầu ra mỗi công trình

Ghi vào `production/assets/<id>/blockout/vN/final/` (D14.8).

```
final/
  part_graph.json    ← "schema": "blockout-1", "version": "v01"
  parts_lib.py
  parts/             ← mỗi part một .glb
  assembled.glb
  sources.json
  blockout.md
  review/            ← bộ render, JSON gate và script, report reviewer (contract) từng vòng
```

`blockout.md` gồm các mục:

1. Version, và hash của `part_graph.json` + `parts_lib.py`.
2. Thành phần đếm trên concept (một dòng).
3. Bảng đo: param, giá trị, nguồn, cách đo.
4. Bbox so với MAP-LAYOUT (khi `has_map: true`) hoặc `size_m` của thẻ asset (khi `has_map: false`).
5. Ghi chú real/texture_only, chép nguyên từ concept.
6. **Blockout tự quyết**: từng chỗ phần khuất hoặc kích thước mà mô tả không có, kèm lý do.
7. Mâu thuẫn giữa các nguồn, và lựa chọn đã dùng.
8. Số lỗi mesh còn lại (non-manifold, zero-area). Blockout không bắt buộc mesh sạch.
9. Thay đổi so với version trước (từ v02 trở đi).
10. Trạng thái duyệt: chờ duyệt / anh duyệt / reviewer duyệt theo ủy quyền, kèm ngày.

## 5. Tự kiểm bằng script

| Kiểm | Tool | Nguồn |
|---|---|---|
| Đủ file đầu vào; `sources.json` đủ khóa; hash file nguồn còn khớp | `check_inputs.py` | Mới |
| `part_graph.json` đúng schema `blockout-1`; mọi part nối về part gốc qua chuỗi `attach` (không part mồ côi, không vòng lặp) (D26.3, theo kiểm liên thông của Procedura) | `check_schema.py` | Mới |
| Tiếp xúc, xuyên khối, part lơ lửng, health, bbox từng part | `gates.py` | Chép từ kit |
| Mọi part đứng trên mặt một part `tag: base` nằm trong mép part đó, cách mép ≥ 0,1 m | `check_base.py` | Mới |
| Dưới mỗi part `tag: roof` có ít nhất một part khác chạm đáy của nó, trong khoảng 1 cm | `check_support.py` | Mới |
| Bbox tổng khớp `layout` trong `sources.json` trong ±2% (MAP-LAYOUT hoặc `size_m`) | `check_layout.py` | Mới |
| Mọi part có mã vật liệu nằm trong `sources.json` | `check_materials.py` | Mới |
| Marker nhô hoặc lõm ≥ 2 cm | `check_markers.py` | Mới |
| Sau mỗi `top_fix`: `fixed_params` không đổi, bbox vẫn khớp ±2% | `check_fix.py` | Mới |

- `check_base.py` và `check_support.py` chỉ chạy trên các part có `tag`. Nếu graph không có part nào có tag tương ứng, script trả `not_checked`.
- Hai script này đọc bbox trong `assembly.json`, không dựng lại. Với mái dốc hoặc part tròn, bbox lớn hơn hình thật. Script có thể bỏ sót lỗi nhỏ, nhưng không báo lỗi sai. Reviewer kiểm phần còn lại trên crop.
- `check_fix.py` chạy **sau** khi áp dụng `top_fix`. Lý do: với `top_fix` loại `structure`, chỉ khi code đã sửa xong mới biết nó đổi gì. Script so `part_graph.json` cũ với bản mới. Nếu fail, Blockout chép lại bản đã lưu trước khi sửa (`work/edits/<F>/`) và ghi lý do vào JSON của vòng đó, để reviewer đọc ở vòng sau.

## 6. Bộ review và rubric

**Bộ render gửi reviewer:**

- `render_views.py --mode critic` (chép từ kit): `clay_*`, `normal_*`, `overlay_*`, `parts_*` (mỗi part một màu, có đánh số), 4 view ortho và top.
- `render_review.py` (mới, mở Blender một lần):
  - `game_cam.png`: góc camera game theo `sources.json`. Nếu không có camera, ghi `not_checked`.
  - `lineup.png`: công trình đứng cạnh hình nhân vật (trụ + cầu) cao `character_h`.
  - `foot_front_left.png`, `foot_front_right.png`: crop sát góc nền–đất–chân tường, tìm theo bbox của part `tag: base`. Nếu không có part `base`, bỏ crop.
- Concept và blockout ở cùng góc.

**check-blockout** (model theo `pipeline.toml`, pilot dùng Opus theo D16; chỉ đọc, trừ file report của mình (D27.5); context mới mỗi lần):

1. Khối: chỉ chấm trên clay. Khối giống ổ bánh mì hoặc hộp trơn là fail, dù IoU cao.
2. Silhouette so với concept ở cùng góc.
3. Khối nhận diện còn giữ (ví dụ: trụ có bệ và mũ, nền nhiều tầng, diềm dày).
4. Khối kín và khối hở đúng như concept.
5. Props: so dòng "thành phần đếm trên concept" với concept và với `parts_*`. Đủ số và tách rời.
6. Chân nhà ổn trên crop.
7. Mục "Blockout tự quyết" hợp lý theo quy tắc mặc định.

- Reviewer không tự đo. Reviewer đọc số từ JSON.
- Theo quy tắc chung của 4 reviewer (`docs/producer.md` §6.1, D25.B): ảnh cùng góc của bản trước ở vòng sửa, `EVIDENCE_OPENED`, finding đủ trường của kit (`preserve`, `acceptance`…), cảnh báo xu hướng duyệt dễ, chỉ chấm trong phạm vi bước.
- Nếu một chi tiết nhỏ không rõ, reviewer trả `unclear` và xin crop.
- Output theo contract reviewer (D14.10, D21.1, `docs/producer.md` §6.1): `VERDICT`, `RUBRIC`, `COUNTS`, `TOP_FIX` (loại `structure` kiểu đơn, `param` kiểu lô, `need_evidence`), `FINDINGS` có id, `PRIOR` cho mọi finding đang mở.
- Duyệt theo ủy quyền (D1.5) chỉ khi không còn finding `blocker`, `major` hay `unclear` đang mở. Lỗi `minor` ghi vào `blockout.md` và không chặn duyệt.

## 7. Đổi version

1. Anh yêu cầu làm lại (Producer chạy `P feedback <id> "<nguyên văn>" --action redo --step blockout`), hoặc Producer quyết và ghi `P rule`. Lý do đổi nằm trong `feedback.md`, brief trỏ tới.
2. Blockout tạo version mới (`v01` → `v02`) và giữ nguyên version cũ.
3. `blockout.md` ghi mục "Thay đổi so với version trước": part nào đổi, param nào đổi, vì sao.
4. Version mới đi lại đủ các bước: tự kiểm, review, duyệt.
5. Script tự đánh dấu các view và model dựng từ version cũ là "cũ", dựa trên `inputs` của từng version (D21.5, `docs/producer.md` §11). Producer không đánh dấu tay.

Nếu Blockout thấy kích thước trong MAP-LAYOUT có vấn đề, Blockout chỉ báo Producer, không tự sửa (D3.2).

## 8. Tổ chức file

```
agents/zps-3dp-step-blockout/
  zps-3dp-step-blockout.md        ← file agent: quy trình + quy tắc cốt lõi
  references/
    part-graph.md            ← hợp đồng schema blockout-1, kiểu attach, quy tắc dựng
    craft.md                 ← chép từ kit: blockout.md §A, technique.md §1–2, preflight
  config.yaml                ← paths.blender, optimize.raster_size, khối self_build
  tools/
    self_build/              ← chép từ kit: graph, assembly, gates,
                               render_views, param_fit
    lib/                     ← chép từ kit: common, raster, bootstrap
    check_inputs.py, check_schema.py, check_base.py, check_support.py,
    check_layout.py, check_materials.py, check_markers.py, check_fix.py,
    render_review.py, concept_mask.py, fit_view.py      ← mới
    setup_deps.sh            ← rút gọn từ kit
  SOURCE.md                  ← nguồn kit v0.10.4, commit 905dc93, danh sách file đã chép kèm sha256
agents/zps-3dp-check-blockout.md   ← reviewer (D1)
```

- Blockout giữ bản chép riêng. Blockout không trỏ sang 3D Artist (D2). Không sửa code đã chép.
- Không chép `validate_concept.py`, vì file này phụ thuộc `optlib.py` của phần optimize. Thay bằng `concept_mask.py` (mới): tách nền theo màu khóa trên toàn ảnh, xuất mask trắng trên nền đen có viền đen, đúng dạng mà `raster.concept_mask` của kit đọc được.
- Thư viện cần cài: numpy, trimesh, scipy, manifold3d, opencv, Pillow, pyyaml.

## 9. Hợp đồng schema `blockout-1`

**Cấp file:** `schema`, `version`, `units` (m), `up` (+Z), `front` (−Y), `params`, `fixed_params` kèm lý do.

**Mỗi part:**

- Bắt buộc: `name`, `primitive` (`box` | `wedge` | `cylinder` | `custom`; đúng tập mà `graph.py` của kit nhận, D24.1), `dims` (hoặc `fn` + `args`), `attach`, `material` (mã trong `sources.json`), `role` (`mass` | `marker`).
- `fn` của part `custom` phải có trong `custom_lib.py` hoặc `custom_parts.py` của asset (D32). `check_schema.py` đọc tên hàm của file asset bằng `ast`, kiểm tĩnh file đó, và từ chối hàm khác.
- Tùy chọn: `tag` (`base` | `roof`), `segments` (8–24), `axis`, `rotation_deg` (chỉ 0, 90, 180, 270; kit từ chối góc khác). `check_schema.py` kiểm cả hai giới hạn này.
- Part `mirror_of` phải tự ghi `material`, `role` và `tag` (nếu có). Lý do: kit chỉ chép các field hình dạng sang part mirror. `check_schema.py` báo lỗi nếu thiếu.

**Hai loại kiểm:**

| Loại | Khi nào chạy | Ai chạy |
|---|---|---|
| Kiểm schema (`check_schema.py`) | Mỗi blockout, bước 4 | Blockout |
| Test hợp đồng | Mỗi lần sửa skill 3D Artist | Người sửa skill. Producer không chạy test này |

**Test hợp đồng:** repo có một blockout mẫu tự tạo, chỉ dùng primitive (một cái chòi nhỏ có nền, tường, mái, cửa dạng marker và 1 prop). Test cho 3D Artist đọc và dựng mẫu này. Nếu test fail, không dùng bản 3D Artist mới. Không dùng Warehouse làm mẫu. Khi chưa có 3D Artist của Producer, test chạy với `self_build/` của kit.

## 10. Việc cần kiểm khi viết code

- `graph.py` của kit đọc các field bằng `.get`, nên có thể bỏ qua field lạ như `role` và `tag`. Phải chạy thử để xác nhận.
- `gates.py` đọc khóa config `contact_dist_m`, `contact_samples`, `inset_depth_tolerance` (đổi tên bên trong). `config.yaml` phải dùng đúng tên này.
- `bootstrap.py` tìm thư viện ở `agents/zps-3dp-step-blockout/tools/.deps/blender-py<ver>`. Cần chạy `setup_deps.sh` trước các script chạy trong Blender.
- Nguồn tham khảo cho các điểm thêm ở D4: Code-as-Room, LL3M, arjun988/blender-skills (qa-review, vehicle proportion-blockout), Epic Modular Level Design.
