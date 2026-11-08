# So sánh ZPS Art Assets Kit v0.10.4 với báo cáo quy trình New Last Order

- Nguồn kit: `Kinglialia/ZPS-Art-Assets-Kit`, nhánh `main`, commit `905dc93` (v0.10.4, 2026-11-06).
- Bản chép ra để đọc: `upstream/zps-art-assets-kit-v0.10.4/`.
- Bản cài ở `~/.claude/skills/` giống repo. Chỉ khác số version trong frontmatter (0.5.6 → 0.10.4).
- Báo cáo quy trình: `/Users/trungnk/MyWorks/Concepts/New Last Order/PIPELINE/PROCESS-AND-CHECKLIST.md`.
- Skill đã đọc: zps-concept-artist, zps-concept-views, zps-3d-artist (SKILL, paths, pipeline, self_build, texture-handoff, agents, config), zps-texture-artist, zps-texture-planning, zps-surface, zps-texture-review, `.art-production-support` (rules, templates), `.art-director-support/workflows/art-direction.md`.

Tài liệu này chỉ nhận xét. Nó chưa thiết kế skill Producer.

---

## 1. Báo cáo yêu cầu, kit đã có

Producer không cần định nghĩa lại các mục này. Producer chỉ cần gọi đúng skill.

| Mục trong báo cáo | Kit đã có ở đâu |
|---|---|
| Concept albedo không bóng làm nguồn màu | Concept Artist: flat-lit → albedo, có gate bóng và `structure_diff.py` |
| Hình học lấy từ blockout, AI chỉ tô màu | Concept Views: blockout bằng part graph của 3D Artist |
| 3D tiếp tục từ cùng blockout | `output/<asset>/work/self_build/part_graph.json` dùng chung; self-model path đọc lại graph này |
| Nhà đối xứng: gen một bên, lật sang bên kia | Concept Views process.md, Way A bước 4 |
| Không sửa ảnh để pass, không đổi threshold | Concept Views Rules; 3D Artist Rules |
| Self-review phải ghi rõ | art-operation.md; 3d-critic.md |
| Một material | `config.yaml` → `max_materials: 1`; texture-handoff mặc định một material |
| Gộp nhiều object thành một | pipeline.md: optimize path join mọi mesh thành một object |
| Trần ~3.000 tris cho công trình | `config.yaml` → `budgets.environment: 3000` |
| `manifold3d` | Đã có trong `VENV_PKGS` của `setup_deps.sh`. Chỉ thiếu `shapely`, `rtree` |
| Meshy retexture giữ UV (~10 credit) | `paths/meshy.md` bước 6, `enable_original_uv: true` |
| Tối đa 3 vòng gen lại, rồi dừng và báo | Concept Views bước 5 |

---

## 2. Báo cáo có quy tắc, kit chưa có

| # | Quy tắc trong báo cáo | Tình trạng trong kit |
|---|---|---|
| G1 | Tách nền theo màu khóa toàn ảnh | `measure_views.py:80` `flood_background` chỉ lấy vùng nối mép ảnh. Khe giữa cột vẫn bị tính là vật thể. Xác nhận ghi chú 1 của báo cáo |
| G2 | Detail pass bắt buộc, bảng "thêm gì – vì sao – tris" | Không có. self_build chỉ nói "giữ chi tiết đổi silhouette". Không có bước, không có bảng |
| G3 | Quét mặt đồng phẳng trùng và mặt ngược normal sau khi gộp | Audit tìm interior faces. Không có kiểm mặt đồng phẳng bị che (nóc thân dưới mái) |
| G4 | Tách đỉnh ở cạnh gắt > 20° trước UV | Không có quy tắc cụ thể |
| G5 | Review bằng render CÓ ÁNH SÁNG (sun + sky, alpha bật), 4 góc cố định | Critic và `render_rig` dùng clay xám, normal, overlay. Không có render có ánh sáng |
| G6 | Chốt style chất liệu bằng 3 option trên 1 công trình chuẩn | Concept Artist không có bước này |
| G7 | MAP-LAYOUT: kích thước theo nhân vật, cửa làm thước | Không skill nào có. Bước 2 của báo cáo làm tay |
| G8 | Câu bắt buộc "giữ mép mái, diềm, nền, bệ trụ đúng độ cao" | Prompt mẫu có "keep exactly the silhouette". Không nhắc riêng mốc cao |
| G9 | Crop phóng to chân nhà trong sheet blockout | Không có |
| G10 | Kiểm kết cấu: mọi mái tựa lên tường/cột/dầm | Gate contact có, nhưng chỉ kiểm tiếp xúc, không kiểm "có gì đỡ" |
| G11 | Gói View Concept: README có NGOẠI LỆ, TEXTURE NOTE, khối thật vs texture-only; kiểm hash | Hand-off chỉ liệt kê file. Không có README, không có TEXTURE NOTE, không kiểm hash |
| G12 | Bàn giao `3D/0X-<tên>/` theo cấu trúc cố định | Kit dùng `output/<asset>/`. Không có bước bàn giao sau duyệt |
| G13 | Texture: đo L* dưới diềm, chênh 4 hướng ≤ 3, seam p90 ≤ 4 | Texture Review chỉ có checklist định tính. Không có số |
| G14 | Lửa: card unlit; viền < 25 cm dựng hình học | Không có |
| G15 | Script đo texture tổng quát (`tex_measure.py`, `id_map.py`) | Chưa có trong kit. Bản pilot hardcode nhãn warehouse |

---

## 3. Mâu thuẫn trực tiếp — cần anh quyết

Theo Rule 6, em không trộn hai bên. Mỗi dòng cần một quyết định.

| # | Kit nói | Báo cáo nói | Ghi chú |
|---|---|---|---|
| C1 | self_build: "Parts are unioned into one closed mesh by manifold3d" (boolean). Optimize Cleanup luôn "merge by distance" (weld) | "Gộp 1 mesh – chỉ join, KHÔNG weld, KHÔNG boolean" | Ảnh hưởng gate health, sweep, bake. Báo cáo mới hơn và đã test trên 7 công trình |
| C2 | Meshy path: remesh một lần ở số tris đã chọn (5 credit) | "Không dùng Meshy remesh; giảm mặt bằng kit" | Báo cáo mới hơn |
| C3 | Nền gen mặc định `#E8E8E8`, hoặc `#2B2B2B` cho vật xám | Nền `#3060C0` | Có thể giữ cả hai: mặc định theo bảng màu của vật. Cần anh chốt |
| C4 | `texture.max_res: 1024`, texel 256 px/m, padding 8 px ở 1024 | 2048 gốc (1024 để kiểm), texel ≥ 64 px/m, padding ≥ 16 px kể cả mép atlas, khe ≥ 32 px | Số texel khác nhau 4 lần. Cần chốt theo camera game |
| C5 | Bảng path: Self-model → Texture Artist vẽ texture | Phương án chốt: Self-model mesh → **Meshy retexture trên mesh đã khóa** → Surface sửa trên lớp Meshy | Kit chỉ cho Meshy retexture trong Meshy path. Đường lai này không có trong kit. Đây là khoảng trống lớn nhất |
| C6 | MCP Gen3D (app đang mở) hướng dẫn modelling bằng MỘT script `scripts/build_<name>.py` với archkit và `okf_context` | Kit và báo cáo dùng part graph `part_graph.json` + `parts_lib.py` | Hai cách dựng khác nhau trong cùng máy. Producer phải gọi một cách |

---

## 4. Nhận xét cho phần tổ chức và scope Producer

1. **Kit chưa có điểm vào điều phối.** `art-direction.md` ghi rõ: không có AD entrypoint bắt buộc. Các skill là "capabilities", không phải người. Producer là đúng chỗ trống này. Không mâu thuẫn với kit.
2. **Điểm duyệt.** Báo cáo có DUYỆT 1 (clay), DUYỆT 2 (texture) và nhiều điểm "User" từng bước. Kit cấm tự duyệt thay người. Producer phải dừng cứng ở mọi điểm User. Producer có thể làm "Reviewer" trong cột "Reviewer → User", nhưng không làm "User".
3. **Một người viết cho một nguồn.** art-operation.md và 3d-builder.md yêu cầu một writer cho mỗi asset. Producer không được chạy hai sub-agent sửa cùng một asset. Chạy song song chỉ được giữa các asset khác nhau.
4. **Critic phải có context mới.** 3d-critic.md và adapter Claude yêu cầu reviewer độc lập nhận chỉ artifact và brief. Producer cần spawn critic mới mỗi vòng, không dùng lại agent đã build.
5. **Credit.** Gen ảnh, Meshy, Tripo đều cần báo giá và chờ duyệt trước mỗi lần gọi. Kit có budget file theo asset. Producer nên gom báo giá cả lô một lần, nhưng vẫn không tự duyệt.
6. **Runtime.** Báo cáo nhắc Codex nhiều chỗ (Codex vẽ texture, Codex tự tải Blender). Kit có hai edition: claude và codex. Cần chốt sub-agent của Producer chạy trên runtime nào. Việc này đổi công cụ gen ảnh (Claude Code dùng Gen3D `generate_image`) và cách duyệt credit.
7. **Pilot trước, batch sau.** Báo cáo làm pilot 1 công trình, chốt bài học, rồi mới batch, duyệt theo lô. Producer cần hai chế độ: pilot và batch. Không chỉ một vòng lặp từng asset.
8. **"5 mặt".** Kit mặc định 4 view (front, back, left, right), top khi cần. Meshy, Tripo, ZPS 3D Gen chỉ nhận tối đa 4 view. Nếu "5 mặt" là 4 view + top, top chỉ dùng cho self-model.
9. **Bước 2 (MAP-LAYOUT) không thuộc skill nào.** Producer phải tự giữ bước này, hoặc giao cho một skill mới. Cần chốt.
10. **Nơi ghi bài học.** art-operation.md cấm sửa skill đã cài trong lúc làm task. Bài học đi vào task record hoặc Art Learning. Nếu Producer sửa skill con theo flow mới, việc đó làm trong repo nguồn, không làm trong `~/.claude/skills`.

---

## 5. Việc lặt vặt

- `upstream/zps-art-assets-kit-v0.10.4/` đang nằm trong working tree của repo mới và chưa commit. Cần chốt: giữ bản chép, dùng submodule, hay chỉ trỏ đường dẫn.
