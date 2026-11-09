<!-- status: draft -->
# Rubric — building

<!-- Rubric chung cho mọi building lấy từ _approved/. Người dùng duyệt một lần: đổi dòng đầu thành `status: approved`.
     Sửa ở đây áp dụng cho building đăng ký SAU đó; building đã đăng ký giữ bản rubric riêng trong thư mục asset.
     Mỗi bước một mục `## <bước>`; brief của bước chỉ đọc mục đó. Mỗi tiêu chí một dòng `- key: tiêu chí pass/fail`,
     kèm tham chiếu tài liệu art direction khi có (ví dụ "mái đúng `roofs.md` §2"). Không mô tả style (D22.16). -->

## blockout
- mass: khối trên clay đúng concept; khối giống ổ bánh mì hoặc hộp trơn là fail
- silhouette: silhouette khớp concept ở cùng góc
- identity: còn khối nhận diện của concept (trụ có bệ và mũ, nền nhiều tầng, diềm dày)
- open_closed: khối kín và khối hở đúng như concept
- props: thành phần đếm trên concept đủ số và là part rời
- foot: chân nhà, nền và đất ổn trên crop foot_front_*
- own_decisions: mục "Blockout tự quyết" theo `hidden_side_rules` của profile

## model
- concept_match: đúng hình khối, mái, tỉ lệ các khối so với concept đã duyệt, đối chiếu từng view
- silhouette: nhận ra building ở thumb.png (256px) và phân biệt được với building khác
- scale: cửa, tường, chiều cao đúng chuẩn kích thước của art direction
- budget: không vượt poly budget building của art direction
- lowpoly_detail: mặt khuất đơn giản; chi tiết nhỏ nằm trong texture, không nằm trong mesh
- clean_mesh: không lỗ thủng, mặt ngược

## texture
- edges_materials: cạnh mái và cạnh khối sắc; chất liệu phân biệt rõ trên preview
- clean_texture: không texture kéo giãn nhìn thấy được
