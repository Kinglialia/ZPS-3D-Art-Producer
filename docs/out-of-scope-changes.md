# Thay đổi cần làm ở các skill ngoài scope Producer

Anh sẽ tự cập nhật các skill này sau. Producer và các sub-agent dựa vào các đầu ra ghi dưới đây.
Nguồn: báo cáo `PROCESS-AND-CHECKLIST.md`, `PROCESS-3D.md`, và các quyết định trong `docs/decisions.md` (D2, D3).
Bản kit đã đọc: v0.10.4, commit `905dc93`.

---

## 1. zps-concept-artist

Producer bắt đầu từ thư mục `approved Concept/`. Mỗi công trình cần có đủ các mục dưới đây trước khi Producer gọi Blockout.

### 1.1 Material Handoff (D3.1)

- Giao file Material Handoff cùng concept. File này dùng chung cho cả dự án, có thể có thêm phần riêng cho từng công trình.
- Mỗi vật liệu có **một mã cố định** (ví dụ `STONE`, `TIMBER`, `BRASS`). Blockout, Concept Views, 3D Artist và Texture đều dùng các mã này.
- Hai vùng khác màu hoặc khác chất liệu phải có hai mã riêng. Ví dụ: kính đèn và khung đồng là hai mã. Lý do: báo cáo ghi lỗi "Đo đồng gộp kính đèn → dE sai".
- Ghi rõ mã nào áp dụng cho vùng nào của từng công trình, khi vùng đó khác quy tắc chung.

### 1.2 Ghi chú real / texture_only (D3.4)

- Concept brief ghi các chi tiết **bắt buộc** dựng khối (`real`) hoặc **bắt buộc** chỉ vẽ texture (`texture_only`) của từng công trình.
- Chỉ ghi những chi tiết có ý định thiết kế rõ ràng. 3D Artist quyết phần còn lại.

### 1.3 Phần khuất và quy tắc mặc định (D3.5)

- Brief ghi phần khuất của từng mặt không thấy: cửa, cửa sổ, mái, biển. Nếu không biết, ghi "chưa biết".
- Quy tắc phần khuất mặc định của dự án nằm trong project profile. Concept Artist áp dụng khi viết brief. Quy tắc từ báo cáo: tường trơn; chỉ kéo dài hoa văn hoặc gờ có sẵn; cửa sổ chỉ khi mảng tường > 3,6 m, tối đa 1 cửa, đặt giữa, copy mẫu của chính nhà; có ngoại lệ theo chức năng (ví dụ sau kệ rượu thì không có cửa sổ).
- Ghi có đối xứng hay không (trái/phải, trước/sau).

### 1.4 Kích thước cho asset lẻ

- Asset không có map: brief ghi kích thước thật, có đơn vị, mốc đo và nguồn (đo hay ước lượng).

### 1.5 Bài học từ báo cáo, bước 1

| Lỗi | Thay đổi cần làm |
|---|---|
| Tường ám đỏ/cam, mất chất đá | Thêm bước chốt style chất liệu: 3 option trên 1 công trình chuẩn, đo hex/S/H một mảng tường phẳng |
| Nền ảnh kem/hồng ám màu lên vật thể | Nền mặc định off-white trung tính |
| Ghi chú cũ mâu thuẫn ảnh mới | Khi đổi concept: cập nhật README, Material Handoff và record cùng lúc |

### 1.6 Một file Material Handoff cho mỗi công trình (D5.1)

- Xuất một file Material Handoff cho mỗi công trình. Tên file chứa mã công trình, ví dụ `05-warehouse.material.md`.
- Bảng mã vật liệu dùng chung có thể nằm trong một file chung của dự án. Blockout đọc cả file chung lẫn file của công trình.

### 1.7 Thẻ asset `asset-card.yaml` (D13, D14.7)

Brief của mỗi concept có một **thẻ asset** theo mẫu trong `docs/project-profile.md` §4: `tier`, `texture_res` (bỏ trống = 2048), `tris_max`, `scale_overrides`, `symmetric`, `real_texture_only_notes`. Thẻ là file `asset-card.yaml` đặt trong `_approved/<id>/`, có thêm `type` (`building | prop | tree | rock`) và `hidden_sides`. Mẫu và hướng dẫn nằm trong `GUIDELINE.md` (do `P init` sinh). Lúc anh chốt, Concept Artist soạn thẻ, hỏi anh một lần các trường còn trống kèm gợi ý, viết material handoff, chạy `check_card.py`, rồi báo anh. Trong lúc skill chưa cập nhật, anh gửi `GUIDELINE.md` ở đầu phiên Concept Artist.

### 1.8 Bàn giao

- Mỗi công trình trong `approved Concept/`: concept albedo, concept có bóng (chỉ để đọc khối), brief (mục 1.2–1.4), và Material Handoff.
- Producer kiểm danh sách này trước khi gọi Blockout. Thiếu mục nào thì Producer dừng và báo.

---

## 2. MapLayout — skill mới (D3.2)

Skill này thảo luận cùng anh để cân đối các chỉ số, rồi chốt `MAP-LAYOUT.md`. Blockout chỉ đọc file này.

Cần chốt khi làm skill: skill này có phải sub-agent của Producer không, hay anh gọi trực tiếp.

| Nội dung | Từ báo cáo, bước 2 |
|---|---|
| Đo chiều cao trên concept riêng, lấy cửa làm thước | Lỗi: đo trên map tổng → nhà quá cao, người lọt thỏm |
| Blockout map bằng khối đơn giản, render top + 3/4 trước khi chốt | Lỗi: map quá chật hoặc quá rộng, khoảng trống dồn sai chỗ |
| Ghi rõ W×D "bao ngoài gồm nền bậc" hay không | Lỗi: W×D hiểu nhầm |
| Một đường dẫn cố định; mọi README trỏ tới; kiểm tồn tại trước mỗi bước | Lỗi: file MAP-LAYOUT bị mất khi sắp xếp thư mục |
| Ghi "lệch cố ý" khi concept vẽ props sai tỉ lệ, kèm số cho model | Lỗi: concept vẽ đe, bếp quá to |
| Render lineup nhà cạnh nhân vật | Kiểm tỉ lệ |

Xuất **một file cho mỗi công trình** (D5.1). Tên file chứa mã công trình, ví dụ `05-warehouse.layout.md`. Các quy ước chung (chiều cao nhân vật, kích thước tham chiếu) có thể nằm trong một file chung.

Đầu ra Blockout cần đọc, cho mỗi công trình: W×D×H, có gồm nền bậc hay không, chiều cao cửa, và các chỗ lệch cố ý. Cả dự án: chiều cao nhân vật và các kích thước tham chiếu.

---

## 3. Agent làm sau, theo từng object (D7)

| Agent | Việc | Nguồn quyết định |
|---|---|---|
| Thu nhỏ texture | Từ 2048 xuống mức thấp hơn, tùy object | D7.4 |
| LOD | Giảm tam giác nhỏ khi đã chốt camera | D7.7 |
| Bộ agent nhân vật, sinh vật (`zps-3dp-char-*`, version sau) | Xem bảng ở mục 3.1 | D9 |

### 3.1 Luồng nhân vật, sinh vật — khác luồng v1 ở đâu

| Bước | Luồng v1 (công trình, props, cây, đá) | Luồng nhân vật, sinh vật |
|---|---|---|
| Blockout | Part graph | Ma-nơ-canh có tham số (chiều cao, tỉ lệ đầu/thân, tay chân, vai, hông), A-pose hoặc T-pose |
| Concept Views | Khóa hình, IoU chặn | IoU so với ma-nơ-canh chỉ báo. Chặn bằng tỉ lệ, vị trí khớp, cặp view đối xứng, màu so với front. Reviewer kiểm "cùng một nhân vật" |
| Phần khuất | Blockout tự quyết khi thiếu | Bắt buộc có trong brief của Concept Artist |
| 3D | Self-model, detail pass | Gen mesh (Meshy, Tripo, ZPS 3D Gen) bằng multi-view, rồi retopo |
| Sau 3D | Bàn giao | Thường có rig và animation |
| Reviewer | Khối, kết cấu, chân nhà | Giải phẫu, tỉ lệ, trang phục, nét nhận diện |
| Dùng chung | Producer, Review Board, mẫu báo cáo ngắn, D1, D8. Texture Artist: chốt khi bàn spec Texture | |

MapLayout đọc thước tỉ lệ chung từ `PROJECT-PROFILE.yaml` (D13), không tự giữ thước riêng.

## 4. Project profile — đã có chủ (D13)

Đã chốt: skill Project Setup giữ profile. Xem `docs/project-profile.md`. Phần dưới là ghi chú cũ.

Nhiều skill cần cùng một file thông số của từng dự án: kích thước tham chiếu, quy tắc phần khuất mặc định, camera game, thông số texture/UV.

Cần chốt: ai tạo và ai sửa file này (Producer, MapLayout, hay anh).
