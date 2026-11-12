<!-- status: draft -->
# Rubric — building

<!-- Rubric chung cho mọi building lấy từ _approved/. Người dùng duyệt một lần: đổi dòng đầu thành `status: approved`.
     Sửa ở đây áp dụng cho building đăng ký SAU đó; building đã đăng ký giữ bản rubric riêng trong thư mục asset.
     Mỗi bước một mục `## <bước>`; brief của bước chỉ đọc mục đó. Mỗi tiêu chí một dòng `- key: tiêu chí pass/fail`,
     kèm tham chiếu tài liệu art direction khi có (ví dụ "mái đúng `roofs.md` §2"). Không mô tả style. -->

## blockout
- mass: khối trên clay đúng concept; khối giống ổ bánh mì hoặc hộp trơn là fail
- silhouette: silhouette khớp concept ở cùng góc
- identity: còn khối nhận diện của concept (trụ có bệ và mũ, nền nhiều tầng, diềm dày)
- open_closed: khối kín và khối hở đúng như concept
- props: thành phần đếm trên concept đủ số và là part rời
- foot: chân nhà, nền và đất ổn trên crop foot_front_*
- own_decisions: mục "Blockout tự quyết" theo `hidden_side_rules` của profile

## views
- style: style, chất liệu, mức chi tiết của từng view giống concept albedo
- shape: silhouette đúng guide; mép mái, diềm, nền, bệ trụ đúng độ cao như guide
- light: ánh sáng đều ở mọi view; không bóng đổ dưới mái hay diềm, không ánh sáng một hướng
- inventory: không thêm, không bớt chi tiết so với guide; cửa, cửa sổ, biển đúng số và vị trí
- sync: cùng vật liệu có cùng màu, texture, độ mòn như front
- hidden_sides: mặt khuất đúng `blockout.md` (phần khuất, "Blockout tự quyết")
- props: props đủ số và tách rời

## model
- mass: khối trên clay đúng concept (mái, tường, nền nhiều tầng); khối giống ổ bánh mì là fail
- detail: diềm, đầu dầm, bậc, khung cửa đổi silhouette ở camera game hoặc 3/4 là hình học; bảng detail pass khớp concept
- shading: ảnh clay có ánh sáng không có vệt đen, bóng chéo, mặt nhấp nháy dưới mái và ở chân tường
- planes: wireframe 3/4 không có cạnh thừa trên mảng tường và mái
- thumbnail: thumbnail kích thước thật còn đọc được mái, cửa, khối chính
- density: tris/m² không lệch quá 2 lần so với công trình pilot; chưa có pilot thì ghi pass
- blockout_match: bbox và `fixed_params` giữ như blockout đã duyệt
- shadow_read: clay_lit_concept đọc khối như concept có bóng (độ chìa mái, độ sâu hốc cửa, bóng đổ chính)

## texture
- light: không bóng bake, AO, glow ngoài quy ước ánh sáng của profile; 4 mặt bên cùng tông
- material: mỗi vật liệu giống concept và bộ đã duyệt
- thumbnail: đọc được ở kích thước thật trên màn hình
- seams: không thấy seam ở camera game; nét theo khối, không theo mép UV
- texture_note: mọi TEXTURE NOTE đã xử lý
- meshy_detail: chế độ SỬA giữ chi tiết Meshy đúng vị trí, không sửa quá tay
- geometry_match: ranh giới vật liệu trùng cạnh và khối của mesh
- inventory: mọi motif, chữ, biển, vết bẩn truy được về concept; không có lỗi ảnh AI
