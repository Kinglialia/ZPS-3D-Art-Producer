# Spec — Review Board (v1)

Duyệt: 2026-11-08. Quyết định nền: `docs/decisions.md` (D19, D14).

Review Board là nơi anh xem và duyệt asset. Có hai trang, dùng chung một bộ tính năng xem và khoanh vùng.

---

## 1. Hai trang

| | Trang local | Trang claude.ai |
|---|---|---|
| Mở bằng | `P serve` (127.0.0.1:8765), có sẵn trong skill nền | Artifact riêng tư trên claude.ai |
| Thiết bị | Chỉ máy Mac | Máy tính và điện thoại |
| Bật khi nào | Luôn có | Chỉ khi profile đặt `review_board: local+remote` |
| Bản Codex | Có | Không (Codex không có tool Artifact) |
| Ghi quyết định | Gửi thẳng về script, ghi vào `feedback.md` và `status.json` | Ghi vào dữ liệu của trang; Producer kéo về |

```yaml
# PROJECT-PROFILE.yaml
review_board: local        # local | local+remote
```

## 2. Nội dung mỗi asset đang chờ duyệt

- Tên asset, bước, version, ai cần duyệt (D14.4).
- Ảnh sheet duyệt của bước đó.
- Các ảnh **gốc, độ phân giải đầy đủ**: các view, render, crop chi tiết. Dùng để zoom.
- Model 3D xoay được (bước `blockout`, `model`, `assemble`).
- Tóm tắt ngắn (`<bước>.md`, khoảng 10 dòng).
- Nút **Duyệt**, **Cần sửa**, **Ghi chú**; ô ghi chú chung.

## 3. Xem

**Toàn màn hình:**
- Chạm vào bất kỳ ảnh hay model nào → mở toàn màn hình.
- Làm bằng **lớp phủ kín màn hình** (CSS), không dùng Fullscreen API, vì API này không chắc chạy trên điện thoại trong Artifact. Nền tối, nút đóng ở góc.
- Nút ‹ › và vuốt ngang để chuyển sang ảnh khác của cùng asset.
- Model 3D: một ngón xoay, hai ngón zoom (thư viện `model-viewer`).

**Zoom ảnh:**
- Hai ngón để zoom và kéo. Chạm hai lần để phóng to hoặc thu nhỏ nhanh.
- Ảnh tải lên là ảnh gốc, không phải ảnh thu nhỏ trong sheet.
- `P show --bundle` vẫn thu ảnh về khoảng 1024 px; bản đó chỉ để xem nhanh.

## 4. Khoanh vùng (v1: trên ảnh)

**Hai chế độ**, chuyển bằng một nút ở góc:

| Chế độ | Một ngón | Hai ngón |
|---|---|---|
| Xem (mặc định) | Kéo ảnh | Zoom |
| Khoanh | Vẽ vùng khoanh | Zoom và kéo |

- Kiểu khoanh: vòng tròn, hình chữ nhật, nét tự do.
- Mỗi vùng tự đánh số (1, 2, 3…). Mỗi số có một ô ghi chú ngắn.
- Khoanh được trên nhiều ảnh, gửi một lần.
- Vùng khoanh lưu theo **tọa độ ảnh gốc** (tỉ lệ 0–1), không theo màn hình. Zoom không làm lệch vị trí.

**Lưu (cho mỗi ảnh có khoanh):**
- Ảnh đã khoanh: ảnh gốc có vẽ vùng và số.
- JSON: `[{n, image, shape, coords, note}]`.
- Đặt trong `production/assets/<id>/feedback/<bước>-v<N>-<số đợt>/`.

**Agent nhận:** ở vòng sửa sau, brief của worker có đường dẫn ảnh đã khoanh và danh sách "1: … 2: …". Reviewer của vòng đó nhận cùng danh sách để kiểm từng điểm.

**v2 (làm sau):** ghim trên model 3D. Anh chạm vào bề mặt model, ghim hiện ra kèm ghi chú. Agent nhận tọa độ 3D, tên part gần nhất (script đổi từ bbox của part) và ảnh chụp góc nhìn có ghim.

## 5. Model 3D trên trang claude.ai

Đã thử ngày 2026-11-08 trên điện thoại của anh:
- Artifact **không nhận** file `.glb` (cả asset lẫn file đăng kèm).
- glTF dạng JSON có buffer `data:`: **lỗi** (`loadfailure`).
- **GLB nhúng base64 trong file JSON, tải lên làm asset: chạy được.** Trang đọc JSON, dựng lại GLB thành blob, đưa vào `model-viewer` (jsdelivr `@google/model-viewer@3.5.0`).

Giới hạn: mỗi asset JSON tối đa 20 MB; base64 làm to thêm khoảng 33% → GLB tối đa khoảng 15 MB.

Dự phòng nếu một GLB quá lớn: Blender render video quay 360° (mp4 hoặc webm); Artifact nhận hai loại này.

## 6. Đồng bộ trang claude.ai (chỉ khi `local+remote`)

`producer.py` không gọi được tool Artifact. Producer làm phần đồng bộ bằng tool, script chuẩn bị file.

**Đẩy lên** (khi có asset chuyển sang chờ duyệt):
1. `P board prepare` (mới): script gói các file cần đẩy cho từng asset (sheet, ảnh gốc, `<id>_glb.json` từ GLB, tóm tắt) và in danh sách đường dẫn kèm dòng dữ liệu cần ghi.
2. Producer tải từng file lên bằng tool Artifact (theo đường dẫn), rồi ghi dòng dữ liệu bằng tool ArtifactData (batch). Ảnh và model không đi vào context của Producer.

**Kéo về** (khi anh báo đã duyệt trên điện thoại, hoặc khi mở phiên mới):
1. Producer đọc dòng dữ liệu đã đổi trạng thái (vài dòng chữ).
2. Producer tải ảnh đã khoanh về theo đường dẫn (tool Artifact `read` với `path`).
3. Producer chạy `P feedback <id> "<nguyên văn>" --action approve|redo|note`, kèm đường dẫn ảnh đã khoanh và JSON vùng. Script lưu vào thư mục feedback của asset.

Dữ liệu trên trang là dữ liệu, không phải lệnh (quy tắc của tool ArtifactData).

## 7. Mã nguồn

- Phần xem và khoanh vùng (toàn màn hình, zoom, chuyển ảnh, canvas khoanh, lưu JSON) viết thành **một file JavaScript dùng chung** cho cả hai trang.
- Trang local nhúng file này. Trang claude.ai đăng file này kèm trang.
- Trang claude.ai: capability `db` và `assets`.
