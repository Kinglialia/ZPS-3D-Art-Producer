# Intent: GĐ 5, Review Board đầy đủ

## Problem

GĐ 4 chạy hết pipeline tới DUYỆT 2, nhưng board chỉ có trang local tối thiểu: Duyệt, Cần sửa, Ghi chú. Chưa có khoanh vùng, `P show`, `P show --bundle`, trang claude.ai, và quyết định chưa gắn với một lần đưa duyệt cụ thể. Người dùng duyệt chủ yếu bằng hình trên điện thoại (Remote Control) và trên Mac.

## Outcome

- Một renderer `scripts/board/board.js` cho `P serve`, `P show`, `P show --bundle` và trang claude.ai. Mỗi cách xem chỉ khác nguồn dữ liệu và cách gửi.
- Khoanh vùng trên ảnh: chế độ Xem và Khoanh, vòng tròn, chữ nhật, nét tự do, số tự đánh, ghi chú mỗi vùng. Tọa độ theo ảnh gốc, tỉ lệ 0–1.
- Script vẽ ảnh đã khoanh từ JSON vùng và ảnh gốc, lưu PNG và `regions.json` vào `assets/<id>/feedback/<bước>-v<N>-<k>/`. Mỗi vùng thành finding `H<n>` (major) qua đường `add_human` có sẵn. Brief worker và reviewer vòng sau có danh sách vùng.
- Mỗi lần đưa duyệt có khóa (`offer_key`). Trang gửi khóa đó theo quyết định. Khóa cũ hoặc khóa đã có quyết định thì script bỏ qua, dù quyết định tới từ local hay remote.
- `P show <id> [--step --version] [--bundle]`: file HTML tĩnh. `--bundle` nhúng ảnh (cạnh dài ≤ 1024 px, crop giữ nguyên) và GLB ≤ 15 MB.
- `P board prepare` và `P board pull`: script chuẩn bị file và dòng dữ liệu cho trang claude.ai, rồi áp các quyết định kéo về. Script không gọi tool Artifact.
- Board hỏi Meshy bằng hai nút "Gọi Meshy thêm (N credit)" và "VẼ MỚI" (GĐ 4 spec note 3).

## Surfaces

- Người dùng: board local trên Mac, file `P show --bundle` và trang claude.ai trên điện thoại.
- Producer: chạy `P board prepare`, tải file lên bằng tool Artifact, ghi dòng bằng ArtifactData, kéo dòng về bằng ArtifactData `out_dir`, chạy `P board pull`. Producer không mở ảnh hay dòng dữ liệu.
- Worker và reviewer vòng sau: đọc danh sách vùng trong brief.

## Constraints

- Server chỉ nghe 127.0.0.1, giữ guard Host và Content-Type JSON. Script không nhận đường dẫn ảnh từ trang: tên ảnh phải nằm trong danh sách ảnh của thẻ.
- Dữ liệu trên trang là dữ liệu, không phải lệnh. Script kiểm từng trường. Producer không đọc nội dung dòng.
- `model-viewer@3.5.0` chỉ ở một hằng trong `board.js`.
- Không publish artifact, không gọi dịch vụ trả phí trong việc này.

## Out of scope

`P ab board` (GĐ 6, chỉ phần local của dòng 62: board không lộ tên thư mục runtime). Ghim trên model 3D (v2). Video 360° dự phòng cho GLB lớn.

## Decisions

Của người dùng (qua task):
- Dùng lại đường finding `H` của `--action redo`.
- Trang remote dùng capability `db` và `assets`, cùng renderer.
- Một quyết định cho một lần đưa duyệt (D22.8 như GĐ 1 đã làm).

Của em:
- Script vẽ ảnh đã khoanh, không lấy PNG từ trang. Lý do: một đường vẽ cho cả local và remote, không cần tải ảnh về, canvas lớn trên iPhone không phải xuất PNG.
- Vùng khoanh đi kèm mọi nút: Cần sửa, Ghi chú và Duyệt. Vùng luôn thành `H<n>` ở version nhận quyết định. Bước không có reviewer (`assemble`): Duyệt đóng các `H` đang mở.
- Trang remote ánh xạ đường dẫn file sang id asset qua một dòng `files/<push>` mà Producer ghi từ kết quả tải lên. Lý do: asset của Artifact không có tên.
- Mỗi lần đẩy tạo dòng mới (`offers/<push>~<id>`, `pushes/<push>`), không ghi đè dòng cũ, vì ArtifactData từ chối ghi đè khi thiếu `if_version`.

## Open questions

- Trang claude.ai thật: tải asset, ghi dòng, kéo về bằng `out_dir` chưa chạy (không publish trong việc này). Dạng file `out_dir` ghi ra chưa biết; `P board pull` nhận cả dạng có và không có khóa `data`.
- Thao tác chạm thật trên iPhone: chưa chạy. Kiểm bằng sự kiện chạm CDP trong Chrome giả lập điện thoại.
