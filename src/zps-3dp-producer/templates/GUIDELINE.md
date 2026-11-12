# {{PROJECT}} — Guideline cho agent · v1.4 · {{DATE}}

Đọc hết trước khi làm. File này nói Concept Artist phải giao gì để pipeline 3D (ZPS-3DP) nhận việc ngay lần đầu. Người dùng có thể gửi lại file này giữa chừng: luôn theo bản mới nhất.

Concept Artist đọc mục 1–7. AD đọc thêm mục 8. Mọi agent theo mục 9.

## 1. Thư mục và vai trò (gốc: `{{CONCEPTS}}/`)

| Đường dẫn | Ai được ghi | Ai đọc |
|---|---|---|
| `<id>/` | Concept Artist, View Concept Artist | Người dùng |
| `_approved/<id>/` | **Chỉ người dùng** chép vào | Producer và pipeline 3D |
| `art-direction/` | AD, sau khi người dùng approve | Mọi agent |

Không ghi, sửa hay xoá ở thư mục không thuộc vai của mình. Cần thay đổi ở đó: đề xuất cho người dùng.

Concept Artist vẽ concept, soạn thẻ asset và viết Material Handoff. Người dùng duyệt concept rồi chép thư mục đã đủ sang `_approved/<id>/`. Pipeline dựng blockout, view, model, texture.

## 2. Mã asset (`id`)

- Chữ thường, tiếng Anh không dấu, nối bằng gạch ngang. Được có số thứ tự đầu: `05-warehouse`, `blacksmith`, `market-stall`.
- Một asset giữ đúng một `id` từ concept tới 3D. Không tự đổi. Trùng hoặc mơ hồ thì hỏi người dùng.
- `id` dùng cho tên thư mục, tên file và trường `asset` trong thẻ. Ba chỗ phải giống hệt nhau.

## 3. Gói giao cho mỗi asset

Khi chốt, thư mục `<id>/` phải có đủ các file dưới đây, **đúng tên**. Thiếu một file hoặc sai tên thì pipeline không nhận asset.

| File | Bắt buộc | Nội dung |
|---|---|---|
| `concept_albedo.png` | Có | Concept **không ánh sáng**: màu gốc và chất liệu, không bóng đổ, không bóng tự thân, không AO, không highlight. Pipeline lấy màu và đo hình khối từ ảnh này |
| `concept_shadow.png` | Có | Cùng concept, **có ánh sáng một hướng**, chỉ để đọc khối và độ sâu. Không ai lấy màu từ ảnh này |
| `concept_34.png` | Không | Cùng vật nhìn góc 3/4, không ánh sáng, nền phẳng như ảnh chính. Cạnh dài ≥ 1024 px. Không cần trùng khung với hai ảnh trên |
| `asset-card.yaml` | Có | Thẻ asset, mục 5. Đây là "concept brief" của pipeline, không có file brief riêng |
| `<id>.material.md` | Có | Material Handoff, mục 4 |
| `<id>.layout.md` | Chỉ khi profile có `has_map: true` | MapLayout làm. Concept Artist không viết |

### Yêu cầu chung cho ảnh concept

1. **Hai ảnh `concept_albedo.png` và `concept_shadow.png` trùng khung tuyệt đối:** cùng góc máy, cùng kích thước, cùng vị trí vật. Pipeline đặt chồng hai ảnh lên nhau.
2. **Nền phẳng một màu, không gradient, không đất, không bóng đổ xuống nền.** Mặc định off-white trung tính, không ngả kem hay hồng, vì nền ám màu sẽ ám lên vật. Vật có vùng gần trắng thì chọn màu nền khác xa mọi màu của vật. Ghi màu nền vào dòng `BG:` của Material Handoff. Pipeline tách vật khỏi nền bằng màu khoá trên toàn ảnh.
3. **Vật nằm trọn trong ảnh**, có lề, không bị cắt. Cạnh dài của ảnh ≥ 1024 px.
4. **Vẽ `concept_albedo.png` chính diện phẳng.** Pipeline đo hình khối trên ảnh này, và góc 3/4 thêm sai số vào mọi số đo. Cần cho thấy khối mà ảnh chính diện giấu: vẽ thêm `concept_34.png`, không đổi ảnh chính. Chỉ dùng góc khác cho ảnh chính khi người dùng yêu cầu. Khi đó ghi góc đã dùng vào `view` (mục 5).
5. **Không chữ, không watermark, không ký hiệu giả**, trừ biển hiệu có trong thiết kế. Khi có biển: ghi vào `real_texture_only_notes` và ghi mã vật liệu của biển vào `text_codes`.
6. **Mọi chi tiết phải có lý do:** mỗi vật, phụ kiện, hoa văn, nguồn sáng thấy được phải truy được về yêu cầu thiết kế, chức năng hoặc tài liệu style. Không thêm đá quý, dây, ánh lấp lánh, khói, lá bay không ai yêu cầu.
7. **Props đếm được:** số thùng, trụ, đèn… trên concept là số pipeline sẽ dựng. Props phải tách rời, nhìn rõ từng cái.

## 4. Material Handoff (`<id>.material.md`)

Mỗi vật liệu một **mã cố định** viết hoa (`STONE`, `TIMBER`, `BRASS`…). Blockout, View, Model, Texture đều dùng các mã này. Vùng nào không có mã thì pipeline dừng lại hỏi, không đoán.

- **Hai vùng khác màu hoặc khác chất liệu phải là hai mã khác nhau.** Ví dụ kính đèn và khung đồng là hai mã. Gộp lại thì đo màu sai.
- Hai vật liệu kề nhau nên khác màu rõ. Pipeline đo đường biên giữa chúng, nên hai màu quá gần thì đường biên mờ. Nếu không tránh được, ghi cặp mã đó vào ghi chú dưới bảng.
- Mã dùng chung cho cả dự án nên lấy từ bảng mã chung, nếu dự án có. Mã mới thì báo người dùng.
- Giữ đúng tên ba cột `Mã`, `Màu chính (hex)` và `Ô lấy màu (x, y, w, h)`. Pipeline đọc bảng theo tên cột. Các cột khác và thứ tự cột tùy ý.
- **Ô lấy màu** là `x, y, w, h` tính bằng pixel trên `concept_albedo.png`, gốc ở góc trên trái. Chọn ô nằm trọn trong một vùng phẳng của vật liệu đó, cách xa nét viền, mép và chỗ đổi sắc. Mỗi mã một ô. Pipeline đo lại màu trong ô này để so với model. Ô dính viền hoặc vùng khác thì màu chuẩn sai.
- **Hex** là trung vị màu đo trong ô, không phải màu chọn bằng mắt. Đo bằng code, như đoạn Python này. Hex lệch số đo thì pipeline báo cảnh báo.

```python
import numpy as np
from PIL import Image
px = np.asarray(Image.open("concept_albedo.png").convert("RGB"))[y:y + h, x:x + w].reshape(-1, 3)
print("#%02X%02X%02X" % tuple(int(v) for v in np.median(px, axis=0)))
```

- **Nền ảnh** là một dòng riêng, đúng dạng `BG: #RRGGBB`, nằm trên bảng. Pipeline đọc dòng này bằng máy.

Mẫu:

```markdown
# Material Handoff — 05-warehouse

BG: #EEEDEA

| Mã | Tên | Màu chính (hex) | Ô lấy màu (x, y, w, h) | Chất liệu, bề mặt | Áp cho vùng nào trên asset này |
|---|---|---|---|---|---|
| STONE | Đá tường | #8F8A80 | 150, 700, 120, 80 | Đá xếp, mòn cạnh | Toàn bộ tường, bệ nền |
| TIMBER | Gỗ dầm | #5A4030 | 560, 330, 60, 100 | Gỗ thô, vân dọc | Dầm ngang, khung cửa |
| ROOF_TILE | Ngói | #7A3B2E | 400, 120, 160, 60 | Ngói xếp lớp theo dốc | Mái |
| BRASS | Đồng | #B08A3C | 700, 380, 20, 20 | Kim loại mờ | Khung đèn, tay nắm |
| LAMP_GLASS | Kính đèn | #F2D27A | 712, 300, 16, 16 | Kính mờ phát sáng | Mặt kính đèn |

Ghi chú khác quy tắc chung: bậc cửa dùng TIMBER thay vì STONE.
```

## 5. Thẻ asset (`asset-card.yaml`)

```yaml
# Trường nào không ghi "tùy chọn" là bắt buộc. Thiếu thì pipeline không nhận asset.
asset: 05-warehouse            # = id = tên thư mục
type: building                 # building | prop | tree | rock (nhân vật, sinh vật: chưa hỗ trợ)
tier: standard                 # hero | standard | background. Quyết định trần tam giác
view: front                    # góc của concept_albedo.png: front | '34' | game_camera
view_side: null                # bắt buộc khi có ảnh 3/4 (view '34' hoặc concept_34.png). left | right, xem 5c
texture_res: null              # tùy chọn. null = 2048. Chỉ ghi khi người dùng chốt khác
tris_max: null                 # tùy chọn. null = theo hạng của dự án
bevel: null                    # tùy chọn. null = theo bo cạnh chung của dự án; none | toon nếu asset này khác
views: back                    # none | back | full | full_top, xem 5a
counts:                        # {} nếu không có thành phần lặp lại, xem 5b
  doors: 2                     # 1 mặt trước + 1 mặt sau theo hidden_sides
  windows: 2                   # 1 mặt trước + 1 bên trái theo hidden_sides
light: {from: left, elevation_deg: 45}   # tùy chọn. Hướng sáng của concept_shadow.png, xem 5c
marks:                         # tùy chọn. 2–3 độ cao thấy rõ trên concept, xem 5c
  - {name: mặt bệ, z_m: 0.4}
  - {name: mép trên tường, z_m: 3.8}
bottom_visible: false          # tùy chọn. true chỉ khi người chơi thấy mặt đáy
text_codes: []                 # tùy chọn. Mã vật liệu mang chữ thật
scale_overrides:               # tùy chọn. Kích thước riêng của asset này, mét
  - {name: cửa, height_m: 1.8}
symmetric: {left_right: true, front_back: false}
size_m: {w: 12, d: 8, h: 6}    # mét. Bắt buộc khi dự án không có map; có map thì null
hidden_sides:                  # đủ 4 mặt. Chưa biết thì ghi đúng chữ "chưa biết"
  back: "cửa kép rộng 2,4 m ở giữa tường, có mái che nhô 0,6 m"
  left: "1 cửa sổ giữa tường, cùng mẫu cửa sổ mặt trước"
  right: "chưa biết"
  top: "mái hai dốc, không ống khói"
real_texture_only_notes:       # có thể là []. Chi tiết dựng khối (real) hoặc chỉ vẽ texture (texture_only)
  - "real: bậc cửa 2 bậc, nhô 20 cm"
  - "real: dầm ngang nhô khỏi tường"
  - "texture_only: vân đá, vết mòn, rêu chân tường"
```

Trường tùy chọn: ghi `null` hoặc bỏ dòng, đều được. Bo cạnh ghi ở trường `bevel`, **không** ghi trong ghi chú chữ, vì tool không đọc ghi chú.

Quy ước hướng: vật quay mặt về phía trước (camera concept chính diện). `left` là bên trái **của chính vật**, không phải bên trái người nhìn.

**Quy tắc phần khuất mặc định** (cho `hidden_sides`, nếu dự án không có quy tắc khác): biết thiết kế của mặt khuất thì ghi thiết kế. Chưa biết thì ghi "chưa biết", và pipeline áp quy tắc này rồi ghi lại. Mặt khuất trơn. Chỉ kéo dài hoa văn, gờ hoặc bộ phận đã có trên concept. Không thêm bộ phận mới. Công trình: cửa sổ chỉ khi mảng tường > 3,6 m, tối đa 1 cửa, đặt giữa, cùng mẫu cửa sổ của chính asset. Có ngoại lệ theo chức năng (ví dụ sau kệ rượu thì không có cửa sổ).

### 5a. Chọn `views`

Pipeline có thể gen thêm ảnh các mặt khác của asset (view) để 3D Artist biết chi tiết mặt khuất. Bước này tốn thời gian và chi phí, nên chỉ bật khi cần. Hỏi một câu: mặt khuất có chi tiết nào mà người dựng 3D không suy ra được từ concept và `hidden_sides`? Không có thì chọn `none`. Có thì chọn giá trị nhỏ nhất che đủ mặt đó.

| Giá trị | Khi nào dùng | Pipeline gen |
|---|---|---|
| `none` | Prop, cây, đá, hoặc vật đối xứng: mặt khuất suy ra được từ concept và `hidden_sides` | Không gen view. Mặt khuất lấy từ `hidden_sides`, `real_texture_only_notes` và Material Handoff |
| `back` | Mặt sau có thiết kế riêng, không suy ra được (cửa sau, biển hiệu, ống khói lệch) | Front + back |
| `full` | Các mặt bên cũng có thiết kế riêng | Front + back + left (right = lật left khi đối xứng) |
| `full_top` | Như `full`, và mặt trên có thiết kế riêng không thấy được trên concept (sân thượng, vườn mái) | Như `full` + top |

Ở mọi giá trị, pipeline cho người dùng xem các mặt bên tô màu theo mã vật liệu khi duyệt blockout. Vì vậy chỉ cần ảnh vẽ cho mặt có thiết kế riêng.

Khi chọn `none`, `hidden_sides` và `real_texture_only_notes` là nguồn duy nhất cho mặt khuất. Viết cụ thể: "tường trơn, gờ chân tường kéo dài". Không viết "giống mặt trước".

### 5b. Ghi `counts`

Ghi số lượng các thành phần lặp lại mà người xem đếm được trên concept. Pipeline so số này với hình 3D. Lệch là phải sửa.

- **Tên khóa lấy từ danh sách khóa của dự án** (`counts_keys` trong profile dự án; người dùng hoặc AD duyệt). Không tự đặt tên khóa mới. Khóa ngoài danh sách bị cảnh báo và không được kiểm. Cần một khóa chưa có thì đề xuất với người dùng.
- Khóa có thể có trong một dự án (chỉ để minh hoạ, danh sách thật nằm trong profile):

| Loại vật | Ví dụ khóa |
|---|---|
| Công trình | `doors`, `windows`, `floors`, `chimneys` |
| Đồ vật | `drawers`, `shelves`, `legs`, `wheels`, `crates` |
| Cây | `main_branches`, `trunks` |
| Hàng rào, cầu, giàn | `posts`, `rails`, `spans` |

- Đếm trên **toàn bộ asset**, gồm cả mặt khuất theo `hidden_sides`. Cửa sổ: 1 ở trước, 1 ở bên trái theo `hidden_sides` → `windows: 2`.
- Chỉ đếm thành phần **rời, đếm được rõ ràng**. Vân hay họa tiết trên bề mặt (vân đá, ngói) thì không đếm. Ghi chúng vào `real_texture_only_notes`.
- Asset không có thành phần lặp lại: ghi `counts: {}`.
- Không chắc thì không ghi khóa đó, và hỏi người dùng ở bước 4 của quy trình chốt.

### 5c. Các trường tùy chọn mới

Mỗi trường giúp pipeline khỏi phải đoán. Ghi khi biết. Không biết thì bỏ trường, đừng đoán.

- **`view_side`**: ghi khi có ảnh 3/4, tức `view: '34'` hoặc có `concept_34.png`. Giá trị `left` hoặc `right`: mặt bên nào của vật hiện ra trên ảnh 3/4, theo bên của chính vật (như `hidden_sides`). Khi có ảnh 3/4, trường này bắt buộc. Pipeline cần nó để biết nhìn ảnh từ phía nào.
- **`light`**: `{from, elevation_deg}` mô tả ánh sáng trong `concept_shadow.png`. `from` là `left`, `right` hoặc `front`, theo ảnh: `left` nghĩa là mặt sáng ở phía mép trái ảnh và bóng đổ về mép phải. `elevation_deg` là độ cao nguồn sáng so với mặt nằm ngang, tính bằng độ. Model dựng ánh sáng theo hướng này. Thiếu thì model agent phải đoán.
- **`marks`**: 2–3 độ cao của những đường ngang rõ trên concept (mép trên thân, mặt bệ, mặt quầy). Mỗi mốc có `name` và `z_m`, là chiều cao tính từ đáy vật, bằng mét. Đo vị trí trên ảnh rồi đổi ra mét theo chiều cao thật của vật. Pipeline so tỉ lệ của blockout với các mốc này. Vật không có đường ngang rõ (cây, đá) thì bỏ trường.
- **`bottom_visible`**: `false` trừ khi người chơi thấy mặt đáy của vật (cầu, bục lơ lửng). Khi `false`, pipeline bỏ mặt đáy khỏi model.
- **`text_codes`**: danh sách mã vật liệu mang chữ hoặc biểu tượng thật (biển hiệu, nhãn). Pipeline kiểm texture bị lật ngược chỉ trên các mã này. Không có thì `[]`.

### 5d. Ví dụ thứ hai: một đồ vật rời

Thẻ này bỏ các dòng tùy chọn không dùng. Ghi chú dưới bảng cho thấy cách ghi hai mã kề nhau cùng tông.

```yaml
asset: market-stall
type: prop
tier: background
view: front
views: none                    # mặt khuất suy ra được từ concept và hidden_sides
counts: {posts: 4, crates: 3}
light: {from: right, elevation_deg: 50}
marks:
  - {name: mặt quầy, z_m: 0.9}
  - {name: mép dưới vải mái, z_m: 1.9}
text_codes: [SIGN]             # biển có chữ thật
symmetric: {left_right: true, front_back: false}
size_m: {w: 2.4, d: 1.6, h: 2.2}
hidden_sides:
  back: "hai trụ sau nối bằng một thanh ngang, không có quầy"
  left: "mặt hông trống, thấy hai trụ và mép vải mái"
  right: "mặt hông trống, thấy hai trụ và mép vải mái"
  top: "vải mái căng phẳng, dốc nhẹ về sau"
real_texture_only_notes:
  - "real: thanh ngang đỡ vải mái, nhô 8 cm khỏi trụ"
  - "texture_only: nếp vải, vân gỗ"
  - "texture_only: chữ trên biển SIGN"
```

```markdown
# Material Handoff — market-stall

BG: #E9E9E6

| Mã | Tên | Màu chính (hex) | Ô lấy màu (x, y, w, h) | Vùng |
|---|---|---|---|---|
| TIMBER | Gỗ trụ | #7A5A3A | 300, 600, 40, 120 | Trụ, quầy |
| CRATE | Gỗ thùng | #9C7A52 | 480, 700, 60, 40 | Thùng |
| CLOTH | Vải mái | #B8433A | 420, 220, 200, 60 | Vải mái |
| SIGN | Biển | #EFE6CF | 500, 330, 80, 30 | Biển treo, có chữ |

Ghi chú: TIMBER và CRATE kề nhau, cùng tông nâu. Đường biên nằm ở mép trên quầy.
```

## 6. Quy trình lúc chốt một asset

1. Người dùng duyệt concept.
2. Concept Artist xuất `concept_albedo.png` và `concept_shadow.png` theo mục 3, và `concept_34.png` nếu cần.
3. Soạn `asset-card.yaml` từ những gì đã thảo luận.
4. **Hỏi người dùng một lần.** Gom mọi trường còn trống hoặc chưa chắc vào một tin, mỗi trường kèm một gợi ý. Ví dụ: "`tier`: gợi ý `standard` vì là nhà phụ; `hidden_sides.right`: gợi ý tường trơn, hay để 'chưa biết'?"
5. Viết `<id>.material.md`. Đo ô lấy màu bằng code.
6. Tự kiểm theo mục 7.
7. Chạy `{{CHECK_CARD}} <thư mục asset> --profile {{PROFILE}}`. Script báo lỗi thì sửa rồi chạy lại, đến khi hết lỗi. Script báo cảnh báo thì sửa nếu cảnh báo đúng, hoặc nêu lý do khi báo người dùng.
8. Báo người dùng: đường dẫn thư mục, danh sách file, các trường người dùng đã chốt, các chỗ ghi "chưa biết".

Người dùng chép thư mục sang `_approved/<id>/` rồi bảo Producer nhận việc.

**Khi đổi concept sau khi đã chốt:** cập nhật cùng lúc cả hai ảnh, thẻ và Material Handoff, rồi báo người dùng chép lại. Ghi chú cũ mâu thuẫn ảnh mới là lỗi hay gặp nhất. Pipeline phát hiện concept đã đổi và hỏi người dùng làm lại hay giữ.

**Khi bắt đầu một nhóm asset mới:** chốt style chất liệu trên **một** asset chuẩn trước, với 3 phương án. Đo màu một mảng phẳng của mỗi phương án. Chốt xong mới vẽ cả nhóm. Lý do: lỗi ám màu (ví dụ tường ám đỏ, mất chất đá) lan ra cả lô nếu không chốt sớm.

## 7. Tự kiểm trước khi báo

- [ ] Tên thư mục, tên file và `asset` trong thẻ cùng một `id`.
- [ ] Đủ file bắt buộc, đúng tên (mục 3).
- [ ] Hai ảnh trùng khung. Albedo chính diện phẳng, không có ánh sáng, bóng, AO, highlight. Ảnh 3/4 nằm trong `concept_34.png`.
- [ ] Nền phẳng một màu, khác xa màu vật. Vật không bị cắt. Cạnh dài ≥ 1024 px.
- [ ] Không có chi tiết thừa không truy được lý do. Không chữ giả.
- [ ] Mọi vùng trên concept có mã vật liệu. Hai vùng khác màu là hai mã.
- [ ] Material Handoff có dòng `BG: #RRGGBB` đúng với màu nền ảnh. Mỗi mã có một ô nằm trọn trong một vùng phẳng của vật liệu đó. Hex là trung vị đo bằng code.
- [ ] Hai vật liệu kề nhau khác màu rõ, hoặc có ghi chú dưới bảng.
- [ ] Thẻ đủ trường bắt buộc, gồm `views` và `counts` (`{}` nếu không có thành phần lặp lại). `hidden_sides` đủ 4 mặt. `size_m` có giá trị nếu dự án không có map.
- [ ] `views` chọn theo 5a. Nếu `none` thì `hidden_sides` và ghi chú viết cụ thể.
- [ ] `counts` có cho mọi thành phần lặp lại đếm được, đúng tên khóa, khớp với concept.
- [ ] `view_side` có khi dùng ảnh 3/4. `marks` có khi vật có đường ngang rõ.
- [ ] Số props trên concept khớp với mô tả trong thẻ hoặc ghi chú.
- [ ] `check_card.py` chạy xong, không còn lỗi.

## 8. Art direction

- AD không ghi số kỹ thuật trong tài liệu style. Số kỹ thuật (tris, độ phân giải, kích thước chuẩn) nằm trong profile dự án và thẻ asset. Muốn đổi số thì đề xuất với người dùng.
- Chỉ AD sửa `art-direction/`, và chỉ sau khi người dùng approve. AD đề xuất thay đổi kèm lý do và asset bị ảnh hưởng; chờ approve rồi mới ghi.
- `art-direction/README.md` là cửa vào duy nhất. Mọi agent đọc README trước, rồi chỉ mở tài liệu README chỉ định cho việc của mình.
- README gồm hai phần, giữ đúng format vì script đọc tự động:

```
## Tài liệu
- `scale-and-poly.md` — kích thước, poly budget — steps: concept, model
- `palette-materials.md` — màu, chất liệu — steps: concept, texture
- `review-checklist.md` — lỗi hay gặp khi chấm — steps: review
- `mood.md` — không khí, câu chuyện — steps: none

## Thay đổi
- 2026-11-08 · hạ poly budget building còn 3k tris · ảnh hưởng: mọi building chưa xong model
```

- `steps:` liệt kê các bước cần đọc tài liệu đó: `concept`, `model`, `texture`, hoặc `none`. Reviewer của một bước tự nhận tài liệu của bước đó; tag `review` chỉ dành cho tài liệu riêng của việc chấm. Tài liệu không gắn tag sẽ không đến được pipeline 3D.
- Mỗi lần sửa chuẩn: thêm một dòng vào `## Thay đổi`, mới nhất ở cuối.
- Chưa có `art-direction/`: làm theo yêu cầu trong chat, ghi chú "chưa có art direction" khi báo cáo.

## 9. Quy tắc chung

- Xong một bản: báo người dùng đường dẫn file. Không tự coi là đã duyệt.
- Mâu thuẫn giữa yêu cầu trong chat và art direction: hỏi người dùng trước khi làm.
- Key API nằm trong file `.env` của project. Khi cần nói về key, chỉ nêu đường dẫn file `.env`. Không đính kèm và không dán nội dung `.env` vào chat: nội dung vào context và lộ mọi key trong đó.
