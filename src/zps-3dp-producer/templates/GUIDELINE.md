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

## Art direction
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
