<!-- status: draft -->
# Rubric mặc định

<!-- Người dùng duyệt xong: đổi dòng đầu thành `status: approved`. Asset tạo mới sẽ vào thẳng todo.
     Mỗi bước một mục `## <bước>`; brief của bước chỉ đọc mục đó. Mỗi tiêu chí một dòng `- key: tiêu chí pass/fail`.
     Key (a-z, 0-9, _) dùng trong dòng RUBRIC của báo cáo. Giữ 4–8 tiêu chí mỗi bước, chỉ những gì đo được bằng ảnh
     preview hoặc số liệu, kèm tham chiếu tài liệu art direction khi có.
     Gu thẩm mỹ thuần túy không đưa vào đây: đó là quyền duyệt cuối của người dùng. -->

## blockout
- mass: khối trên clay đúng concept; khối giống ổ bánh mì hoặc hộp trơn là fail
- silhouette: silhouette khớp concept ở cùng góc
- identity: còn khối nhận diện của concept
- open_closed: khối kín và khối hở đúng như concept
- props: thành phần đếm trên concept đủ số và là part rời
- foot: phần chạm đất ổn trên crop foot_front_*
- own_decisions: mục "Blockout tự quyết" theo `hidden_side_rules` của profile

## views
- style: style, chất liệu, mức chi tiết của từng view giống concept albedo
- shape: silhouette và mốc chiều cao của từng view đúng guide
- light: ánh sáng đều ở mọi view; không bóng đổ, không ánh sáng một hướng
- inventory: không thêm, không bớt chi tiết so với guide; mọi phần tử truy được về concept, guide hoặc thẻ
- sync: cùng vật liệu có cùng màu, texture, độ mòn như front
- hidden_sides: phần khuất đúng `blockout.md`
- props: props đủ số và tách rời

## model
- mass: khối trên clay đúng concept; khối giống ổ bánh mì là fail
- detail: chi tiết đổi silhouette ở camera game hoặc 3/4 là hình học; bảng detail pass khớp concept
- shading: ảnh clay có ánh sáng không có vệt đen, bóng chéo, mặt nhấp nháy
- planes: wireframe 3/4 không có cạnh thừa trên mặt phẳng
- thumbnail: thumbnail kích thước thật còn đọc được khối chính
- density: tris/m² không lệch quá 2 lần so với pilot; chưa có pilot thì ghi pass
- blockout_match: bbox và `fixed_params` giữ như blockout đã duyệt
- shadow_read: clay_lit_concept đọc khối như concept có bóng (độ chìa, độ sâu hốc, bóng đổ chính)

## texture
- light: không bóng bake, AO, glow ngoài quy ước ánh sáng của profile; 4 mặt bên cùng tông
- material: mỗi vật liệu giống concept và bộ đã duyệt
- thumbnail: đọc được ở kích thước thật trên màn hình
- seams: không thấy seam ở camera game; nét theo khối, không theo mép UV
- texture_note: mọi TEXTURE NOTE đã xử lý
- meshy_detail: chế độ SỬA giữ chi tiết Meshy đúng vị trí, không sửa quá tay
- geometry_match: ranh giới vật liệu trùng cạnh và khối của mesh
- inventory: mọi motif, chữ, biển, vết bẩn truy được về concept; không có lỗi ảnh AI
