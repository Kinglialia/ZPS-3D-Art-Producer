# {{PROJECT}} — Guideline cho agent · v1 · {{DATE}}

Đọc hết trước khi làm. File này ngắn và phải theo đúng. Người dùng có thể gửi lại file này giữa chừng: luôn theo bản mới nhất.

## Thư mục (gốc: `{{CONCEPTS}}/`)
| Đường dẫn | Ai được ghi | Ai đọc |
|---|---|---|
| `<building-id>/` | Concept Artist, View Concept Artist | Người dùng |
| `_approved/<building-id>/` | **Chỉ người dùng** chép vào | Producer và pipeline 3D |
| `art-direction/` | AD, sau khi người dùng approve | Mọi agent |

Không ghi, sửa hay xoá ở thư mục không thuộc vai của mình. Cần thay đổi ở đó: đề xuất cho người dùng.

## Đặt tên
- `building-id`: chữ thường, tiếng Anh không dấu, nối bằng gạch ngang. Vd `blacksmith`, `town-hall`.
- Mỗi building giữ một id từ concept đến 3D. Không tự đổi id; trùng hoặc mơ hồ thì hỏi người dùng.

## Bàn giao vào `_approved/<id>/` (`<id>` là building-id)
Tên file là quy ước bắt buộc. Thiếu một file hoặc sai tên thì `P intake` không nhận asset.

| File | Nội dung |
|---|---|
| `concept_albedo.png` | Concept màu đã duyệt |
| `concept_shadow.png` | Concept có bóng, chỉ để đọc khối |
| `asset-card.yaml` | Thẻ asset, là concept brief. Mẫu ở dưới |
| `<id>.material.md` | Material handoff: mỗi vật liệu một mã cố định. Hai vùng khác màu hoặc chất liệu thì hai mã |
| `<id>.layout.md` | Chỉ khi profile có `has_map: true`. MapLayout xuất, một file cho mỗi asset |

Mẫu `asset-card.yaml` (ví dụ `05-warehouse`). `null` nghĩa là để trống và hiểu theo ghi chú:
```yaml
asset: 05-warehouse            # bắt buộc. Đúng tên thư mục
type: building                 # bắt buộc. building | prop | tree | rock. character, creature: v1 chưa hỗ trợ
tier: standard                 # bắt buộc. hero | standard | background. Hạng chỉ quyết định trần tris
texture_res: null              # null = 2048. Hoặc số nguyên
tris_max: null                 # null = theo hạng. Hoặc số nguyên
scale_overrides:               # [] = dùng thước của profile. Ví dụ cửa riêng của công trình này
  - {name: cửa, height_m: 1.6}
symmetric: {left_right: true, front_back: true}   # bắt buộc
size_m: {w: 12, d: 8, h: 6}    # mét. Bắt buộc khi profile có has_map: false. Khi has_map: true thì null
hidden_sides:                  # bắt buộc, ít nhất một dòng. Chưa rõ thì ghi "chưa biết"
  - "mặt sau: tường trơn, chưa biết cửa"
real_texture_only_notes: []    # bắt buộc, có thể rỗng. Chi tiết bắt buộc dựng khối (real) hoặc chỉ vẽ texture (texture_only)
```

Cách làm lúc chốt (Concept Artist):
1. Soạn thẻ từ những gì đã thảo luận.
2. Hỏi người dùng một lần các trường còn trống, kèm gợi ý.
3. Viết material handoff.
4. Chạy `{{CHECK_CARD}} <thư mục asset> --profile {{PROFILE}}`. Sửa đến khi không còn lỗi.
5. Báo người dùng. Người dùng chép thư mục đã đủ vào `_approved/`.

## Art direction
- AD không ghi số kỹ thuật trong tài liệu style. Muốn đổi số thì đề xuất với người dùng.
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

## Quy tắc chung
- Xong một bản: báo người dùng đường dẫn file. Không tự coi là đã duyệt.
- Mâu thuẫn giữa yêu cầu trong chat và art direction: hỏi người dùng trước khi làm.
