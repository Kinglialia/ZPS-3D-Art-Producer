# Material Handoff — wooden-chest

Phiên bản bàn giao: v10-final, giữ nguyên concept v07 đã được người dùng duyệt ngày 2026-11-09. Nền hai ảnh: **#EEEEEE**, RGB(238,238,238), một màu phẳng, không bóng nền. Nền không phải vật liệu asset.

Các mã dưới đây là mã mới, đã được người dùng đồng ý; chưa có bảng mã chung của dự án được cung cấp. Mã khác nhau cho vùng khác màu hoặc chất liệu. Mã màu là mẫu đại diện đo từ **concept_albedo.png**, không phải màu từ ảnh có ánh sáng, và không có nghĩa toàn bộ vùng phải là một màu đặc.

| Mã | Tên | Màu chính | Chất liệu, bề mặt | Vùng áp dụng |
|---|---|---|---|---|
| TIMBER | Gỗ nền | #B39776 | Gỗ sáng mờ; ván ghép; giữ màu ảnh đã duyệt, không phủ thêm tint đỏ/cam | Thân, nắp, hông, viền gỗ đứng và cong, mặt sau cùng vật liệu |
| TIMBER_GRAIN | Vân và mắt gỗ | #A08769 | Biến thiên sắc tố chạy dọc từng tấm ván; mắt gỗ có vòng vân | Nét vân, mắt và sợi gỗ trên TIMBER; texture-only, không khắc thành rãnh |
| LEATHER | Da nền | #372920 | Da nâu đậm mờ, hạt da và nếp gấp; đai dày có chức năng giữ/gia cố | Hai đai qua nắp và thân, tiếp tục về phía sau |
| LEATHER_WEAR | Vân, mép da mòn | #47362A | Hạt da sáng hơn, vết nhăn và mép cắt/mòn; biến thiên màu tự nhiên | Chi tiết bề mặt trên LEATHER, không tạo một lớp kim loại hoặc gờ riêng |
| THREAD | Chỉ may | #C5A784 | Chỉ màu be nhạt, đường may chạy hai mép mỗi đai | Các mũi chỉ; texture-only |
| IRON | Sắt khóa và đinh | #747475 | Sắt xám trung tính; bề mặt mờ, phản xạ nhẹ chỉ thể hiện trong ảnh shadow | Tấm khóa, chốt xoay, bốn đinh trên khóa, bốn đinh lớn trên đai ở mặt trước; hai bản lề phía sau |
| JOINT | Khe tối và lỗ | #120905 | Vùng tối do khe thật/lỗ, không phải AO phủ lên mặt gỗ | Khe nắp–thân, khe ván, lỗ khóa, lỗ chỉ; các nét viền tối dùng để đọc hình |

## Cách đọc và dựng

- Chỉ lấy màu và chi tiết từ `concept_albedo.png`. `concept_shadow.png` minh họa ánh sáng trung tính từ trên-trái/phía trước để đọc độ sâu, không dùng lấy màu.
- Mọi biến thiên vân gỗ, hạt da, nếp nhăn, chỉ may là màu bề mặt. Không bake ánh sáng của bản shadow vào base color.
- Phân biệt nét viền minh họa với khe thật: không dựng đường viền silhouette thành gờ hoặc vật liệu đen bao quanh asset.
- Giữ tương phản gỗ sáng / da tối / sắt xám trung gian. Không thay đai da bằng kim loại. Không thêm vàng, đá quý, dây hoặc phụ kiện.
- Cấu hình bo cạnh được đọc từ trường `bevel` trong asset-card.yaml; texture chi tiết theo concept đã duyệt. Không yêu cầu mô phỏng từng sợi, lỗ da hay vết xước bằng geometry.
- Không suy ra roughness/metallic số cụ thể từ ảnh. Bảng này giao ý đồ vật liệu; thông số shader thuộc pipeline và profile dự án.

## Nguồn đo màu

Tọa độ ảnh 1254 × 1254, gốc trên-trái; vùng [x0,y0,x1,y1), RGB median trừ khi ghi khác:

| Mã | Vùng đo | Phép đo |
|---|---|---|
| TIMBER | [550,410,600,430) | Median |
| TIMBER_GRAIN | [540,410,620,455) | Median nhóm 10% pixel tối nhất theo trung bình RGB |
| LEATHER | [440,700,490,730) | Median |
| LEATHER_WEAR | [440,700,490,730) | Median nhóm 10% pixel sáng nhất |
| THREAD | [414,680,435,750) | Median pixel có trung bình RGB > 140 |
| IRON | [700,620,760,650) | Median |
| JOINT | [550,765,600,775) | Median nhóm 10% pixel tối nhất |

Chuyển sắc giữa các mã là sắc tố/antialias, không phải vật liệu mới. Các mã chi tiết có thể là lớp màu trong cùng texture atlas; không buộc tạo bảy draw calls.

## Cấu tạo dùng khi views: none — v1.2

`asset-card.yaml` là nguồn cấu tạo mặt khuất. Thân có 3 tầng ván chạy quanh chu vi (không cộng số mặt thành 12 hàng). Vỏ nắp có tổng 2 dải ván ngang chiều rộng, một đường ghép; không thêm hàng ở phía sau. Viền gỗ và tấm đầu vòm dùng TIMBER nhưng không tính là hàng ván. Vân/mắt gỗ là TIMBER_GRAIN, không phải khe để chia thêm hàng. Hai đai LEATHER đi qua nắp xuống sau; hai bản lề IRON ở đường nắp-thân sau, thẳng hàng hai đai. Không bổ sung vật liệu hoặc phụ kiện.
