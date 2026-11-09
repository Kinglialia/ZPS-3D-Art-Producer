# Spec — Producer (v2)

Tên kỹ thuật: `zps-3dp-producer`. Tên hiển thị: ZPS-3DP · Producer.
v1 duyệt: 2026-11-08. v2: 2026-11-09 (D21–D26). Quyết định nền: `docs/decisions.md` (D14, D21–D26 và các quyết định trước còn hiệu lực).

**Nền:** skill `producer` anh đã làm (`producer-skill.zip`: `SKILL.md`, `scripts/producer.py`, `references/`, `templates/`). Spec này giữ cơ chế của skill đó và ghi những chỗ thay đổi.

---

## 1. Vai trò

Producer là **skill chạy trong phiên chính**. Producer chỉ điều phối:
- Chạy script `producer.py` (gọi tắt `P`).
- Giao việc cho worker và reviewer bằng file brief do script sinh ra.
- Chạy `P ingest` để script đọc báo cáo và chuyển trạng thái.
- Chuyển câu hỏi của agent cho anh, và chuyển nguyên văn feedback của anh vào file.

Producer **không** mở ảnh, JSON, log hay file dự án (D6). Producer **không** tự ghi trạng thái (D21.5): mọi đánh dấu (version cũ, số lần gọi Meshy, hash) do script tính. Trạng thái nằm trong file, không nằm trong trí nhớ của Producer.

## 2. Giữ nguyên từ skill nền

| Cơ chế | Mô tả |
|---|---|
| Trạng thái trong file | `production/assets/<id>/status.json` (chỉ script ghi), `ledger.md` (chỉ ghi thêm) |
| Script quyết định thứ tự | `P next` cho biết bước tiếp theo của từng asset |
| Giao việc bằng file | `P brief <id>` sinh brief, in JSON (`role`, `agent`, `model`, `resume`, `brief`, `report`) |
| Báo cáo contract | Dòng `KEY: value` ở đầu file report. Script kiểm định dạng, không đoán |
| `pipeline.toml` | Nơi duy nhất định nghĩa bước, agent, model, gate, output bắt buộc, giới hạn chạy song song |
| Version theo bước | `<bước>/vN/` có `final/`, `work/`, brief, report |
| Resume | Vòng sửa ≤ `resume_rounds` (2): gửi tiếp cho đúng worker cũ. Sau đó: worker mới, có thể dùng `escalate_model` |
| Ruling | Quyết định Producer tự đưa ra được ghi bằng `P rule "<id>: <quyết định> — <lý do> — <cái giá nếu sai>"` |
| Cảnh báo đổi nguồn | Concept, thẻ, profile hoặc art direction đổi sau khi asset bắt đầu → cảnh báo ⚠, hỏi anh làm lại hay giữ (mục 11, D21.5) |
| Trang duyệt local | `P serve` (127.0.0.1:8765): nút Duyệt / Cần sửa / Ghi chú, xem GLB xoay được |
| Hook và lệnh phụ | SessionStart chạy `P next --session`; `dashboard`, `validate`, `cleanup` (dry-run trước), `archive` |

## 3. Pipeline 6 bước (`pipeline.toml`, D14.2)

| # | `id` | Worker | Kiểm | Gate |
|---|---|---|---|---|
| 1 | `blockout` | `zps-3dp-step-blockout` | `zps-3dp-check-blockout` | `review_human` |
| 2 | `views_front` | `zps-3dp-step-views` | `zps-3dp-check-views` (chỉ front) | `review` |
| 3 | `views_rest` | `zps-3dp-step-views` | `zps-3dp-check-views` (cả bộ) | `review_human` |
| 4 | `model` | `zps-3dp-step-model` | `zps-3dp-check-clay` | `review_human` (DUYỆT 1) |
| 5 | `texture` | `zps-3dp-step-texture` | `zps-3dp-check-texture` | `review` |
| 6 | `assemble` | Script `assemble.py`, không có agent (D22.11) | Kiểm trong chính script (mục 6.4) | `checks_human` (DUYỆT 2) |

**Ba loại gate:**

| Gate | Sau khi worker xong |
|---|---|
| `review` | Reviewer PASS → bước sau |
| `review_human` | Reviewer PASS → `waiting_human` → duyệt theo chính sách (mục 4) → bước sau |
| `checks_human` (mới, D21.6, D22.11) | Script của bước pass → `waiting_human` → anh duyệt. Script fail → `blocked`, không có vòng sửa; Producer báo anh kèm điểm fail |

- **Producer sắp xếp reviewer** qua script. Worker không gọi reviewer, không gọi agent khác.
- Bỏ `final_human_gate`, vì `assemble` đã có gate người duyệt (D14.3).
- Model của từng bước có agent theo D16: pilot dùng Opus cho mọi bước; sau pilot hạ từng bước theo bảng D16.2.
- `assemble` không có agent (D22.11): mọi việc của bước này là việc xác định. Texture đã được check-texture chấm trên model ở bước `texture`.
- Mỗi bước khai báo loại `TOP_FIX` được phép và kiểu sửa (mục 6).

**Tên agent và chặn gọi nhầm** (D23.2, thay phần tên agent của D6.5):
- Agent của Producer đặt tên theo **bước pipeline**, không theo vai trò: worker `zps-3dp-step-<bước>`, reviewer `zps-3dp-check-<bước>`. Tên hiển thị `3DP Step · <Bước>`, `3DP Check · <Bước>`. Lý do: kit có `zps-concept-views`, `zps-3d-artist`, `zps-texture-artist`; tên theo vai trò làm Claude chọn nhầm khi anh gọi skill của kit.
- Trong `pipeline.toml`, `agent` của mỗi bước là `step-<bước>`, reviewer là `check-<bước>`.
- Description của mọi agent bước và kiểm mở đầu bằng câu cố định: "Bước pipeline của zps-3dp-producer. Chỉ chạy khi Producer giao file brief. Không dùng khi người dùng gọi trực tiếp."
- Tên vai trò (Blockout, Concept Views, 3D Artist, Texture Artist) chỉ dùng trong văn bản spec để dễ đọc, không dùng làm tên kỹ thuật.
- **Bản Codex** (D24.5): tên thêm hậu tố `-codex`, ví dụ `zps-3dp-step-model-codex`, theo đúng quy ước `skill_suffix` của kit. Description tối đa 300 ký tự, vì Codex rút gọn description dài hơn (`DESC_MAX` của kit); câu chặn gọi nhầm đặt đầu tiên. Script build kiểm độ dài.

## 4. Ai duyệt (D14.4, D21.3)

**Chính sách nằm trong `production/policy.yaml`**, tách khỏi profile. Lý do: đổi người duyệt không ảnh hưởng cách dựng asset, nên không được làm đổi hash profile và bật cảnh báo cho mọi asset đang chạy.

```yaml
# production/policy.yaml — chỉ script ghi
approvals:
  blockout:   human    # human | reviewer
  views_rest: human
  model:      human    # đổi sang reviewer cần --confirm-spend
  # assemble: luôn human, không có khóa
review_board: local    # local | local+remote
delegations: []        # ghi bởi P delegate
```

- Project Setup hỏi anh các giá trị này lúc khởi tạo, ghi file. Gợi ý: pilot để `human` hết.
- Khóa hợp lệ: `blockout`, `views_rest`, `model`. Script từ chối khóa khác. `views_front` và `texture` chỉ do reviewer duyệt. `assemble` luôn do anh duyệt.
- `reviewer`: reviewer PASS (không còn finding `blocker`, `major`, `unclear` đang mở) thì script tự duyệt, ghi ledger "reviewer duyệt theo chính sách dự án".
- **Đổi chính sách:** anh nói trong chat. Producer chạy `P approvals set <bước> <human|reviewer> --by "<nguyên văn>"`. Có hiệu lực ngay, không cần phiên mới, không bật cảnh báo.
- **`model: reviewer` cần `--confirm-spend`** (D21.8). Bước ngay sau `model` gọi Meshy (tốn credit) trên mesh vừa khóa. Không có cờ này, script từ chối và in lý do để Producer hỏi lại anh.
- **Ngoại lệ theo lô:** Producer chạy `P delegate <bước> <id> ...`. Thứ tự ưu tiên: `delegate` > `approvals` > `human`.
- Mọi lần duyệt ghi **ai duyệt** (anh, chính sách, ủy quyền). Anh bấm Cần sửa được bất cứ lúc nào.

## 5. Xem kết quả

Anh nói trong chat. Producer chạy script và chuyển đường dẫn cho anh. Producer không mở file.

| Anh nói | Producer chạy | Anh nhận |
|---|---|---|
| "Tiến độ?" | `P dashboard` | Bảng ngắn: asset, bước, trạng thái, việc anh cần làm |
| "Cho anh xem <asset>" | `P show <id>` | Một file HTML: concept, sheet duyệt, render, GLB, tóm tắt report các bước |
| "Xem <bước> v<N> của <asset>" | `P show <id> --step <bước> --version <N>` | HTML của đúng version đó |
| "Duyệt cả lô" | `P serve` | Trang duyệt local |

- Producer đưa file cho anh bằng tool gửi file của runtime (Claude Code: `SendUserFile`). Nội dung không vào context Producer.
- `P show --bundle`: nhúng ảnh (thu cạnh dài về tối đa 1024 px; crop dưới 2 MB giữ nguyên; file trên 25 MB bị từ chối) và GLB nhỏ vào một file HTML, để xem trên điện thoại. Khi anh dùng Remote Control, Producer tự thêm `--bundle`.
- Câu hỏi "vì sao …?": trả lời bằng dòng lý do và danh sách finding có id trên trang duyệt. Không gọi thêm agent (D22.17).
- `P show`, `--bundle`, `P serve` và `P ab board` dùng chung một renderer, là file JavaScript của Review Board (D22.15). `P show` là trang board của một asset xuất thành file tĩnh.
- Duyệt bằng nút, khoanh vùng, xem toàn màn hình và zoom: Review Board (`docs/review-board.md`, D19).

## 6. Contract

### 6.1 Reviewer (D14.10, D21.1, D25.A, D25.B)

```
VERDICT: PASS | FIX | ESCALATE
RUBRIC: <key>=pass|fail|unclear; ...
COUNTS: blocker=N; major=N; minor=N; preference=N; unclear=N
TOP_FIX: <loại>: F<n>[, F<m> ...]
EVIDENCE_OPENED: <nhãn các ảnh và file đã mở>
COMPARE: F<n>=better|same|worse; ...   (vòng sửa: so với bản gốc, cho các finding trong TOP_FIX vòng trước)
PICK: <a|b|c>                          (chỉ khi worker nộp phương án cho lỗi param, mục 7)
FINDINGS:
- F<n> [blocker|major|minor|preference|unclear] <loại>
  region: <ở đâu> | viewing_condition: <góc, kích thước xem> | evidence: <ảnh, số đo>
  consequence: <hậu quả> | confidence: high|medium|low
  repair: <sửa thế nào> | preserve: <phải giữ nguyên gì> | acceptance: <dấu hiệu đã sửa xong>
PRIOR:
- F<n>: resolved | open | regressed | superseded
```

**Bộ trường finding lấy từ `issue-fields.json` của kit** (D25.A), dùng chung với AD critique. Finding của reviewer, finding `H<n>` của anh và nhận xét của AD agent cùng một format, chuyển qua lại được. `ingest` kiểm đủ trường.
- `resolved` chỉ khi bản mới chứng minh được `acceptance`. Không thấy lỗi nữa nhưng không có bằng chứng cho `acceptance` thì vẫn `open`.
- `superseded`: yêu cầu đã đổi (anh hoặc AD đổi, có `ack`). Không tính vào tiến bộ hay thụt lùi.
- `preference`: khẩu vị, không chặn PASS. Ghi riêng để anh xem; nếu reviewer thấy anh phải chọn thì ESCALATE.
- Tên VERDICT của mình ứng với verdict của kit: PASS = `meets_checked_criteria`, FIX = `needs_revision`, `need_evidence` = `insufficient_evidence`.

**Quy tắc chung của 4 reviewer** (D25.B, theo `3d-critic.md` của kit; test D1 kiểm cả 4 file có đủ):
- Brief kèm **ảnh cùng góc của bản trước** khi đây là vòng sửa, để so trực tiếp.
- Ghi `EVIDENCE_OPENED`. Finding phải dẫn nhãn ảnh trong danh sách đó. Nhãn không chứa dấu phẩy hay chấm phẩy. Trích dẫn trong `PRIOR` cũng phải dùng **đúng nguyên văn** một nhãn đã liệt kê ở `EVIDENCE_OPENED` (D27.5).
- Finding loại `note` (`note`, `note_texture`, `note_exception`) luôn ở mức `minor` (D27.5). Hai quy tắc này ghi trong file agent của cả 4 reviewer. Run 4: `ingest` từ chối contract 2 lần vì thiếu chúng.
- **Reviewer tự ghi file report** (D27.5, mục 6.5). Reviewer chỉ ghi đúng đường dẫn report trong brief, không ghi chỗ nào khác.
- **`preserve` phải cụ thể** (D27.11): nêu tên các chi tiết nằm cạnh vùng sửa có thể bị đụng tới (ví dụ "nét mực khe nắp", "bản lề trái"). Không ghi chung chung "giữ phần còn lại". Run 4: sửa F6 ở texture v3 xóa mất nét mực khe nắp.
- Câu cố định trong file agent: "Bạn có xu hướng duyệt dễ. Ảnh sạch với chỉ số cao vẫn có thể sai khối hoặc sai style; kiểm từng tiêu chí."
- Không tự đo; số đọc từ JSON của script. Chỉ chấm trong phạm vi bước (ví dụ không chấm màu ở bước clay).
- **So theo cặp** (D26.1, theo GPTEval3D): ở vòng sửa, với mỗi finding trong `TOP_FIX` vòng trước, reviewer so ảnh cùng góc của bản mới với bản gốc và ghi `COMPARE`: tốt hơn / như cũ / xấu hơn. `PRIOR` phải nhất quán với `COMPARE`: `resolved` cần `better` và bằng chứng cho `acceptance`; `worse` thì là `regressed`. Lệch nhau → `ingest` báo lỗi contract. Lý do: so hai ảnh đặt cạnh nhau ổn định hơn chấm điểm tuyệt đối từng ảnh.

**Finding có id cố định qua các vòng.** Script lưu finding **theo từng version**: `<bước>/vN/findings.json` (id, mức, loại, trạng thái, vòng xuất hiện đầu, vòng gần nhất) (D22.1). Brief vòng sửa lấy danh sách finding của bản được chọn làm gốc (bản tốt nhất), không phải của bản mới nhất. Brief của reviewer có danh sách đó và số id bắt đầu cho finding mới. Reviewer phải ghi `PRIOR` cho **mọi** finding đang mở. Thiếu một dòng → `ingest` báo lỗi contract.

- Khi anh `redo` (đợt feedback mới): finding còn mở của bản gốc được chép sang đợt mới, cộng finding của anh. Bộ đếm vòng đặt lại (D11.4).
- Mỗi key chấm `unclear` trong `RUBRIC` phải có ít nhất một finding mức `unclear` (D22.6).
- **Tin nhắn trả về cho Producer** chỉ gồm hai dòng `VERDICT` và `COUNTS` (D22.6). `RUBRIC`, `FINDINGS`, `PRIOR` nằm trong file report. **Ngoại lệ** (D27.5): lệnh ghi file report bị chặn thì reviewer trả cả report giữa dòng `--- report ---` và dòng `--- end ---` (mục 6.5).
- **`P ingest` in luôn lệnh giao việc tiếp theo** (D27.2): khi kết quả ingest dẫn tới một lần giao (reviewer sau worker, worker vòng sửa sau FIX), `ingest` in thêm đúng dòng JSON mà `P brief` sẽ in. Producer giao ngay trong cùng lượt, bớt một lượt mỗi vòng.

**Chọn VERDICT** (theo thứ tự, dừng ở dòng đầu tiên khớp). Finding `preference` không tính vào các dòng dưới:

| # | Điều kiện | VERDICT | TOP_FIX |
|---|---|---|---|
| 1 | Lựa chọn thẩm mỹ anh phải quyết, hoặc rubric mâu thuẫn brief | ESCALATE | — |
| 2 | Còn finding `blocker` hoặc `major` đang mở | FIX | Loại có finding nặng nhất. Hai loại cùng mức: `structure` trước `param`, `fix_uv_mesh` trước `repaint`, vì sửa cấu trúc có thể làm finding kia mất hiệu lực. Finding `unclear` để vòng sau chấm lại |
| 3 | Chỉ còn finding `unclear` | FIX | `need_evidence` |
| 4 | Không còn `blocker`, `major`, `unclear` | PASS | — |

**Loại `TOP_FIX` theo bước** (khai báo trong `pipeline.toml`; script từ chối loại khác):

| Bước | Loại | Kiểu sửa |
|---|---|---|
| `blockout`, `model` | `structure` | **Đơn**: đúng một finding mỗi vòng. Thay đổi cấu trúc cần tách riêng để biết cái nào gây lỗi mới |
| | `param` | **Lô**: mọi finding `param` đang mở |
| `views_front`, `views_rest` | `regen` | **Lô**: mọi view có finding `regen`. Mỗi view độc lập |
| `views_rest` | `regen_front` | Front sai so với bộ (D22.4). Script chạy `redo --step views_front`; các bước sau tự chạy lại |
| | `note_exception`, `note_texture` | Chỉ ghi chú, không gây FIX |
| `texture` | `repaint` | **Lô**: mọi vùng có finding `repaint`. Mỗi vùng độc lập |
| | `fix_uv_mesh` | Script chạy `redo --step model`. DUYỆT 1 lại |
| | `meshy_regen` | Script đặt `waiting_human` (mục 6.3) |
| | `note` | Chỉ ghi chú, không gây FIX |
| Mọi bước có reviewer | `need_evidence` | Vòng xin bằng chứng (mục 7) |

Script kiểm `TOP_FIX` liệt kê đúng: kiểu đơn có đúng một id; kiểu lô có đủ mọi finding đang mở cùng loại.

### 6.2 Worker

Giữ như skill nền: `STATUS / OUTPUT / RUBRIC / ISSUES`. Thêm:
- `PROFILE_HASH: <hash>`: **chép từ brief**. Script tính hash khi sinh brief (mục 10); `ingest` so với hash trong brief. Lệch → báo lỗi, không chuyển trạng thái.
- `FIXED: F<n>, ...` (vòng sửa): finding worker cho là đã sửa. Chỉ để đối chiếu; reviewer quyết.
- Texture Artist: `UNFIXABLE: yes|no`.
- `RESOLVED_NOTES: <mục>, ...` (D27.8): ghi chú của bước trước (TEXTURE NOTE, `note_texture`, ghi chú trong `ISSUES`) mà worker bước này đã làm. Reviewer của bước này xác nhận từng mục trong report. Chỉ mục được xác nhận mới rời khỏi "Việc còn mở" của README (mục 6.4).

Worker tự ghi file report như reviewer (D27.5, mục 6.5).

Worker không khai số lần gọi Meshy. Script tính từ file `budget-<mesh_hash>.json` (mục 6.3).

**Kiểm đầu vào** (D22.12): chỉ script kiểm hash đầu vào, khi sinh brief và khi ingest (mục 11). `check_inputs.py` của agent chỉ kiểm file có tồn tại.

**Brief bước `texture`:** script sinh brief từ các `final/` đã duyệt (`blockout` để đọc `sources.json`, `model`, `views_rest`) và file concept trong `_approved/<id>/`. Script chép mục `ISSUES` của report bước `model` đã duyệt vào brief. Không có file handoff.

### 6.3 Meshy (D20.14, D21.2, D24.2, D24.3)

**Gọi qua wrapper, không sửa kit.** Texture Artist chỉ gọi Meshy qua `meshy_call.py` (tool của Producer). Wrapper gọi `gen_api.py texture` của kit (chép nguyên, không sửa, theo D2). Chỉ Texture Artist gọi Meshy.

**Key API** (D24.3): lấy từ file `.env` trong thư mục project, đường dẫn ghi ở `paths.env_file` của profile (mặc định `.env`), trong file có dòng `MESHY_API_KEY=...`.
- Wrapper chạy `gen_api.py` trong tiến trình con với biến môi trường `ZPS_ART_ENV_FILE=<đường dẫn tuyệt đối tới .env>`, và **xóa `MESHY_API_KEY` khỏi môi trường của tiến trình con**. Lý do: gen_api ưu tiên biến môi trường hơn file, nên nếu shell còn key khác thì key của project sẽ bị bỏ qua.
- Không agent nào đọc, in hay chép nội dung `.env`. Brief không chứa key hay đường dẫn tới `.env`; wrapper tự đọc đường dẫn từ profile.
- `P init` thêm `.env` vào `.gitignore` của project.
- Trước khi giao bước `texture`, script chạy `gen_api.py keys` (chỉ báo có hay không, không in key). Profile có `env_file` mà thiếu key → asset `blocked`, Producer hỏi anh. Profile không có `env_file` → VẼ MỚI, như quy tắc cũ "không có key Meshy".

**Budget theo hash mesh, đúng định dạng của kit:** mỗi hash mesh một file `production/assets/<id>/texture/budget-<mesh_hash>.json` dạng `{"max_credits": N, "used_credits": 0}`, với `N = số lần được phép × giá một lần gọi`. Giá lấy từ `--dry-run`; mặc định 10 credit cho retexture theo bảng giá trong skill chính thức `meshy-dev/meshy-3d-agent` (D26.5). Số lần đã gọi = `used_credits / giá`. Script đọc file này; worker không tự khai.

**Kit trừ budget trước khi gọi** (vì lời gọi có trả phí mà thất bại vẫn có thể đã tốn credit). Wrapper xử lý lỗi theo hai trường hợp:

| Lỗi | Nhận biết | Xử lý |
|---|---|---|
| Trước khi task được tạo (lỗi mạng, lỗi API lúc gửi) | `task.json` không có `task_id` | Wrapper hoàn lại khoản đã trừ trong file budget, rồi thử lại. Tối đa 3 lần (D8.3) |
| Sau khi task đã tạo (hết thời gian chờ, lỗi lúc tải file) | `task.json` có `task_id` | **Không tạo task mới.** Chờ tiếp đúng `task_id` đó và tải kết quả, dùng lại hàm `wait` và `download` của gen_api. Tối đa 3 lần |

Sau 3 lần lỗi ở một trong hai trường hợp: `STATUS: BLOCKED`, Producer hỏi anh.

**Các quy tắc còn lại giữ nguyên:**
1. Texture chưa đạt: Texture Artist sửa qua các vòng review thường.
2. **Không sửa được** (`TOP_FIX: meshy_regen` hoặc `UNFIXABLE: yes`): script đặt `waiting_human`. Anh duyệt → script tăng `max_credits` của file budget hiện tại thêm một lần gọi và ghi ledger ai duyệt. Brief sau ghi số lần còn được gọi.
3. **Mesh đổi** (sau `fix_uv_mesh` hoặc anh làm lại `model`): hash mới có file budget mới với `max_credits: 0`. Texture cũ làm trên UV cũ, không dùng được. Script đặt `waiting_human` với câu hỏi: "Mesh đổi, texture Meshy cũ mất hiệu lực. Gọi lại Meshy (tốn credit) hay VẼ MỚI?". Anh chọn Meshy → `max_credits` bằng giá một lần gọi; chọn VẼ MỚI → brief ghi chỉ định chế độ.

### 6.4 Bước `assemble` bằng script (D22.11)

`assemble.py` chạy khi bước `texture` được duyệt. Không có agent, không có reviewer.

1. Kiểm hash mesh khớp hash đã khóa khi duyệt `model`.
2. Gắn `albedo_<texture_res>.png` vào mesh đã khóa. Xuất GLB cuối: 1 mesh, 1 node, 1 material, unlit, base color only. Lưu `.blend`.
3. Chạy QA của kit trên GLB cuối: `mesh_check`, `uv_check`, `export_check` (với `expect_unlit: true`), `screen_tris_check`. Kết quả ghi vào `evidence/qa/` của thư mục làm việc.
3b. **Dùng `finalize.py` của kit làm cổng** (D24.4): finalize chỉ nhận kết quả QA gắn với sha256 của đúng file GLB này, và từ chối nếu thiếu `mesh_check` hoặc có kết quả fail hoặc lỗi. finalize từ chối → `assemble.py` fail.
4. **Kiểm GLB hiển thị đúng:** render một bộ nhỏ (3/4 trước, camera game) từ chính file GLB đã xuất, so pixel với render cùng góc của bước `texture`. Lệch quá ngưỡng → fail. Lý do: bắt lỗi phát sinh khi xuất (color space, alpha, unlit) mà render trong Blender không thấy.
5. Ghép gói cuối: `model/`, `texture/` (chép `albedo` và `notes.md` từ `final/` của bước `texture`), `review/` (sheet DUYỆT 1, render và `final_lit_vs_concept.png` của bước `texture`, ảnh so ở điểm 4, report reviewer).
6. Ghép `README.md` từ report các bước: dòng đầu là trạng thái và ngày; cách làm (chế độ texture, số lần gọi Meshy tính từ file budget); ngoại lệ (NGOẠI LỆ, TEXTURE NOTE, mục "Blockout tự quyết"); việc còn mở; những gì chưa kiểm (engine, camera chưa chốt, % tam giác nhỏ).
   **"Việc còn mở"** (D27.8) chỉ lấy finding còn mở trong `findings.json` của **version được duyệt** ở từng bước. Một ghi chú của bước trước rời khỏi danh sách khi worker bước sau ghi nó ở `RESOLVED_NOTES` và reviewer bước đó xác nhận (mục 6.2). Run 4: README liệt kê "3 hàng ván mặt sau" dù model đã dựng. Code hiện tại (`1620c40`) mới làm một trường hợp: bỏ finding `note_texture` khi review texture đã duyệt có `texture_note=pass`.
7. Pass → `waiting_human` (DUYỆT 2). Fail ở bất kỳ điểm nào → `blocked`, Producer báo anh kèm điểm fail.

Mỗi điểm fail ghi vào `assemble/vN/report-script.md` theo dạng finding để trang duyệt hiện được.

`assemble.py` lấy `production/` từ thư mục đang đứng, giống `producer.py` (D27.7). Thư mục đó không có `production/assets/<id>/status.json` thì script thoát mã 2 trước khi ghi bất kỳ file nào. Lệnh giữ nguyên dạng, nên rule Codex vẫn khớp. Run 4: chạy từ thư mục khác thì script ghi report `blocked` sai chỗ. Code: `9711540`.

### 6.5 Agent tự ghi file report (D27.5)

- Reviewer và worker tự ghi report vào đúng đường dẫn `report` của brief. Không ghi chỗ nào khác.
- **Đường dự phòng:** lệnh ghi bị chặn thì agent trả cả report trong tin nhắn cuối, giữa dòng `--- report ---` và dòng `--- end ---`. Producer ghi nguyên văn tin nhắn vào file report. `ingest` chỉ đọc phần giữa hai dòng đó, kể cả khi dòng có dấu cách thừa hoặc CRLF.
- Đường dự phòng phải hiếm. Lý do: report lưu hộ đi qua context Producer.
- Script ghi mỗi lần dự phòng vào ledger: sự kiện `report_fallback`, kèm vai trò và bước.
- Settings của project có rule allow cho lệnh ghi dưới `production/`, để bớt lần bị chặn (bản Claude: `templates/settings.snippet.json`).
- Ngoài đường dự phòng, tin nhắn trả về vẫn chỉ gồm `VERDICT` và `COUNTS` (D22.6).
- Code hiện tại (`170aadc`) bắt reviewer luôn trả report bằng chữ và Producer luôn lưu hộ. Code phải đổi theo mục này. Hai dòng đánh dấu và cách `ingest` đọc chúng (`170aadc`, `39c8ebf`) giữ cho đường dự phòng.

## 7. Vòng sửa (D11, D21.1, D21.4, bằng script)

0. **Mục "Hiện hành" của `feedback.md`** (D27.4): `P feedback --action redo` ghi vào Log **và** thêm dòng đó vào "Hiện hành". Văn bản nhiều dòng được nối thành một dòng ở "Hiện hành"; Log giữ nguyên văn. Khi bước đó được duyệt (anh hoặc reviewer duyệt), script xóa các dòng redo của bước khỏi "Hiện hành". Dòng Producer gộp tay thì giữ. Ghi chú chỉ vào Log, vì ghi chú không phải quyết định. Reviewer không báo finding vì "Hiện hành" trống. Run 4: mọi reviewer texture đều báo mục này. Code: `dfba2eb`, `c7a904e`.
1. **Trần:** tối đa `max_fix_rounds` = 3 vòng mỗi bước, tính trong một đợt feedback. Feedback `redo` của anh mở đợt mới, đặt lại bộ đếm (D11.4).
2. **Mỗi vòng:** worker sửa đúng các finding liệt kê trong `TOP_FIX`, bắt đầu từ bản brief chỉ định (bản tốt nhất).
2b. **Brief vòng sửa kèm kết quả script** (D26.4, theo 3DCodeBench): ngoài finding của reviewer, brief liệt kê đường dẫn tới mọi file JSON gate và check **fail** của bản gốc (`gates.py`, `check_*.py`, QA của kit). Worker đọc nguyên văn lỗi của script trước, rồi mới tới nhận xét của reviewer. Lý do: phản hồi xác định từ Blender là thứ giúp vòng sửa hội tụ nhiều nhất.
2c. **Phương án cho lỗi `param`** (D26.2, theo BlenderAlchemy): khi `TOP_FIX` loại `param`, worker dựng 2–3 phương án giá trị (ví dụ độ chìa mái 0.25 / 0.30 / 0.35 m), render cùng bộ góc review, đặt ở `vN/variants/<a|b|c>/`; phương án a nằm ở `final/`. Reviewer chọn bằng dòng `PICK`. Nếu chọn khác a, script chép phương án đó vào `final/` rồi mới ingest. Vẫn tính một vòng. Không áp cho `structure` (giữ sửa đơn) và không áp cho bước có gen ảnh (tốn lượt gen).
3. **Tiến bộ** đo trên finding có id, không đo trên tổng số đếm. Một vòng có tiến bộ khi: có ít nhất một finding `blocker` hoặc `major` cũ chuyển `resolved`, và số finding chuyển `regressed` ít hơn số `resolved`. Finding mới phát hiện không tính là thụt lùi, vì reviewer có context mới mỗi lần nên có thể thấy thêm lỗi cũ chưa ai nêu.
4. **Dừng sớm:** từ vòng 2, nếu vòng không có tiến bộ → `waiting_human`, ghi "không tiến bộ ở vòng N" kèm danh sách finding còn mở.
4b. **Đổi nhánh không đặt lại bộ đếm** (D25.H): ví dụ Texture Artist chuyển từ Meshy sang VẼ MỚI trong cùng đợt feedback vẫn đếm tiếp vòng cũ. Chỉ feedback `redo` của anh mới mở đợt mới.
5. **Bản tốt nhất** (D11.3, D27.1): version có ít finding `blocker` + `major` đang mở nhất. Bằng nhau thì chọn version **giải quyết được nhiều** finding `blocker` + `major` hơn. Vẫn bằng nhau thì chọn version cũ hơn. Lý do (Run 4): v2 sửa xong F1 thì reviewer mới thấy F2; cả v1 và v2 đều còn một `major`; quy tắc cũ chọn v1, và vòng sau làm lại F1. Code: `bf10d36`. Brief vòng sửa trỏ tới bản tốt nhất. Khi gửi anh hoặc khi dừng, gửi bản tốt nhất.
5b. **Không giao bản đỡ tệ nhất như đã đạt** (D25.H): bản gửi anh vì hết vòng, dừng sớm hay ESCALATE mang nhãn **chưa đạt** trên trang duyệt, kèm finding còn mở. Anh vẫn duyệt được; khi đó finding còn mở được ghi vào mục "việc còn mở" của README gói cuối.
6. **Vòng xin bằng chứng (`need_evidence`):**
   - Chỉ dùng khi không còn `blocker`, `major` đang mở (mục 6.1, bảng VERDICT).
   - Worker của cùng bước chỉ render các ảnh reviewer xin, ghi vào `<bước>/vN/review/evidence-<k>/`. **Không tạo version mới.** Reviewer chấm lại chính `vN` với ảnh thêm.
   - Worker không được sửa `final/` (D22.5). Script so hash `final/` trước và sau vòng; lệch → báo lỗi, bỏ kết quả vòng đó.
   - Resume worker cũ nếu còn; vòng này không tính vào `resume_rounds`.
   - Không tính vào 3 vòng. Cùng bước xin lần thứ hai trong một đợt feedback → `waiting_human` (D20.15).
7. **Chuyển lên anh** (`waiting_human`): hết vòng 3 vẫn FIX (gửi bản tốt nhất kèm finding còn mở); dừng sớm; `ESCALATE`; `need_evidence` lần hai; Meshy (mục 6.3 điểm 5 và 6); `assemble.py` pass (DUYỆT 2). `assemble.py` fail → `blocked`.
8. **Cần sửa ở bước `assemble`** (D21.6, thay D20.4): không có agent và reviewer, nên khi anh bấm Cần sửa, trang duyệt hỏi sửa ở bước nào: `texture` (vẽ lại) hoặc `model` (mesh, UV). Script chạy `redo --step <bước>`; các bước sau tự chạy lại.

## 8. Thư mục

```
<thư mục concept>/_approved/<id>/      KHU 1 — ĐẦU VÀO. Anh chép vào. Pipeline chỉ đọc
  concept_albedo.png, concept_shadow.png, asset-card.yaml, <id>.material.md,
  <id>.layout.md                       chỉ khi profile có `has_map: true`

production/                            KHU 2 — LÀM VIỆC. Chỉ script và agent ghi
  PROJECT-PROFILE.yaml, policy.yaml, pipeline.toml, ledger.md, dashboard.md
  rubrics/<loại>.md
  assets/<id>/
    status.json, brief.md, rubric.md, feedback.md, feedback/
    <bước>/vN/{final, work, review, findings.json, brief-*.md, report-*.md}
    texture/budget-<mesh_hash>.json

deliver/<id>/                          KHU 3 — KẾT QUẢ CUỐI ĐÃ DUYỆT
  nội dung `assemble/vN/final/` đã duyệt: README.md, model/, texture/, review/
```

- **Chép khi duyệt** (D20.2): chỉ khi `assemble` được duyệt (DUYỆT 2), script chép `assemble/vN/final/` sang `deliver/<id>/`. Các bước giữa nằm lại trong `production/`.
- **Làm lại sau DUYỆT 2:** README trong `deliver/<id>/` ghi "đang làm lại". Bản cũ giữ cho tới khi có bản duyệt mới.
- **Version bị loại** (D22.2, thay D14.9): khi một bước được duyệt, script đánh dấu các version khác của bước đó là `rejected` trong `status.json`. **Không di chuyển thư mục**, vì brief cũ, `inputs`, ảnh khoanh, evidence và `ab/mapping.json` đều trỏ tới đường dẫn version.
- **Xóa:** chỉ qua `P cleanup`, chỉ khi asset đã xong, chạy dry-run trước, xóa thật khi anh đồng ý. Xóa `work/` của các version `rejected`; giữ preview và report. Sau đó `P archive`.
- **Agent chỉ đọc và ghi đường dẫn trong brief.** Mọi file agent có dòng: "Chỉ đọc file và thư mục brief chỉ định. Chỉ ghi trong thư mục version brief giao. Không quét thư mục asset."
- Bỏ thư mục `View Concept/` riêng. Brief bước sau trỏ thẳng tới `final/` đã duyệt của bước trước.

## 9. Nhận việc (intake)

- Giữ cách của skill nền: chỉ đăng ký khi anh bảo; `P intake` liệt kê theo nhóm; `--all`, `--priority`.
- **Kiểm:** `asset-card.yaml` hợp lệ (`check_card.py`: trường bắt buộc, giá trị hợp lệ, `type` có rubric); đủ file bắt buộc (albedo, có bóng, thẻ, material handoff); profile hợp lệ (`check_profile.py`).
- **Concept brief = `asset-card.yaml`** (D22.3). Phần khuất (`hidden_sides`), đối xứng (`symmetric`), ghi chú real/texture_only (`real_texture_only_notes`) nằm trong thẻ. Không có file brief riêng. Khi spec agent nói "concept brief", nghĩa là thẻ này.
- **MAP-LAYOUT:** nếu profile có `has_map: true`, intake bắt buộc có `<id>.layout.md`. Nếu `has_map: false`, thẻ bắt buộc có `size_m: {w, d, h}` (mét); `check_card.py` kiểm trường này. Blockout lấy W×D×H từ `size_m` (D20.9).
- Thiếu hoặc sai → không đăng ký. Producer báo anh theo nhóm lỗi.
- Loại asset lấy từ `type` trong thẻ (`building`, `prop`, `tree`, `rock`). Loại `character`, `creature`: báo v1 chưa hỗ trợ (D9).
- **Ước lượng và báo giá theo lô** (D25.I): `P intake` in ước lượng thời gian và credit cho lô, dùng `estimate.py` của kit (dữ liệu của chính project trong `<project>/.zps-art/estimates.jsonl`; dưới 3 bản ghi thì dùng mặc định của kit). Tổng credit Meshy dự kiến của cả lô được đưa anh duyệt một lần. Mỗi asset xong, script ghi `estimate.py log` (phương pháp, số phút, credit, tris).
- **Pilot trước, lô sau** (D21.7): khi profile có `pilot_asset: null`, `intake --all` từ chối; chỉ đăng ký từng asset gọi đích danh, và chỉ khi không có asset nào khác đang chạy. Các phép so với pilot (tris/m², dE vật liệu) ghi `not_checked`, không fail.

## 10. Thông số và rubric

| Loại thông tin | Nằm ở |
|---|---|
| Số và quy ước script dùng | Mặc định skill → preset → profile → thẻ asset (D13) |
| Khi các nguồn mâu thuẫn | Xem thứ tự ưu tiên ngay dưới bảng (D25.G) |
| Ai duyệt, trang duyệt | `production/policy.yaml` (mục 4) |
| Tài liệu style | `art-direction/` (AD giữ, tag `steps:`), như skill nền. **Chỉ** ở đây (D22.16) |
| Tiêu chí chấm chung của bước | Trong file agent reviewer |
| Tiêu chí chấm riêng theo loại asset | `production/rubrics/<loại>.md`, chia mục theo bước. Anh duyệt một lần (`status: approved`). Chỉ chứa tiêu chí pass/fail kèm tham chiếu tới tài liệu AD (ví dụ "mái đúng `roofs.md` §2"), không mô tả style (D22.16) |
| Số hình học sau khi blockout được duyệt | `sources.json` của blockout là nguồn duy nhất cho các bước sau (D22.13). Profile và thẻ chỉ còn dùng cho thông số không phải hình học (`texture_res`, ngưỡng pixel, `detail_examples`) |

- **Thứ tự ưu tiên khi các nguồn mâu thuẫn** (D25.G, theo `art-operation.md` của kit): (1) quyết định hoặc feedback mới nhất của anh, brief của asset; (2) art direction đã duyệt; (3) spec, profile, thẻ asset, `sources.json`; (4) tài liệu của agent và reference của kit cho đúng loại việc; (5) quy tắc chung và mặc định. Agent gặp mâu thuẫn còn ảnh hưởng tới kết quả thì ghi cả hai nguồn và lựa chọn đã dùng vào báo cáo, không chọn âm thầm.
- Số không viết hai lần. Tài liệu art direction có thể nhắc số, nhưng số thật nằm trong YAML. Nếu lệch, YAML thắng (đây là trường hợp riêng của thứ tự trên: số kỹ thuật thuộc nhóm 3, không thuộc nhóm 2).
- **Hash profile** (D21.3) tính trên nội dung đã chuẩn hóa của `PROJECT-PROFILE.yaml`, **bỏ** `paths` và mọi khóa bắt đầu bằng `_` (ví dụ `_source`). Sửa ghi chú nguồn hay đường dẫn không làm đổi hash.
- `check_profile.py` do script chạy một lần khi `intake` và khi sinh brief. Agent không chạy lại.

## 11. Theo dõi đầu vào và version cũ (D21.5, bằng script, thay phần "Producer đánh dấu" của D2)

Mỗi version ghi trong `status.json` các đầu vào đã dùng. Script là tầng duy nhất kiểm các hash này, khi sinh brief và khi ingest (D22.12):

```json
"inputs": {"blockout": "<hash final đã duyệt>", "views_rest": "<hash>", "model": "<hash mesh>",
           "card": "<hash asset-card.yaml>", "concept": "<hash các file _approved/<id>/>",
           "profile": "<hash profile>", "art_direction": "<ngày thay đổi gần nhất>"}
```

- **Version cũ:** một version là "cũ" khi đầu vào của nó khác bản đã duyệt hiện tại của bước trước. Script tự suy ra; Producer không đánh dấu tay. Trang duyệt hiện nhãn "dựng từ blockout v1 — cũ".
- **Cảnh báo ⚠:** concept, thẻ, profile hoặc art direction đổi sau khi asset bắt đầu. Hỏi anh làm lại hay giữ, rồi `P ack <id>`.
- **Dùng lại:** worker bước sau đọc `inputs` của version trước (qua brief) để biết phần nào giữ được, ví dụ `diff_guides.py` của Concept Views.
- Concept dùng hash nội dung file, không dùng thời gian sửa: chép lại cùng file không bật cảnh báo (D23.1).

## 12. Giới hạn chạy song song (D21.9)

```toml
# pipeline.toml
[limits]
blender = 2        # số tiến trình Blender cùng lúc (blockout, model, texture render, assemble.py)
codex_image = 2    # số lệnh gen ảnh qua gen_image_codex.py cùng lúc
meshy = 1          # số lần gọi Meshy cùng lúc
```

- Mỗi bước khai báo tài nguyên dùng (`uses = ["blender", "codex_image"]`). `P next` chỉ đề xuất giao việc khi còn chỗ; asset chờ hiện "chờ slot <tài nguyên>".
- Mỗi runtime có `[limits]` riêng (mục 16). Hai runtime không chạy cùng lúc trên một máy.

## 13. GUIDELINE.md (D14.7)

`P init` sinh `GUIDELINE.md` cho dự án (skill nền), và thêm `.env` vào `.gitignore` của project (D24.3). Anh gửi GUIDELINE cho Concept Artist, View Artist, AD. Thêm:
1. Mẫu `asset-card.yaml` và hướng dẫn từng trường (bắt buộc / bỏ trống thì hiểu thế nào).
2. Danh sách file bắt buộc trong `_approved/<id>/`, đúng tên file. Tên file trong `_approved/` giờ là quy ước bắt buộc, thay cho "tên tự do" của skill nền.
3. Cách làm lúc chốt: Concept Artist soạn thẻ từ những gì đã thảo luận, hỏi anh một lần các trường còn trống kèm gợi ý, viết material handoff, chạy `check_card.py`, rồi báo anh. Anh chép thư mục đã đủ vào `_approved/`.
4. AD: viết tài liệu style có tag `steps:`. Không ghi số kỹ thuật; muốn đổi số thì đề xuất với anh.

`check_card.py` đi kèm GUIDELINE, để Concept Artist tự kiểm.

## 14. Khởi tạo và phiên mới (D13)

1. Anh gọi Producer. Producer chạy `check_profile.py`.
1b. **`P preflight`** (D25.C): kiểm môi trường một lần mỗi phiên, gọi `preflight.py` của kit và kiểm thêm codex CLI, `gen_api.py keys` (Meshy), bản Blender. Kết quả ghi `production/preflight.json` gồm bảng tính năng bật/tắt. Bước nào cần tính năng đang tắt thì `P next` báo ngay và không giao việc bước đó. Chạy lại khi đổi tool hoặc cấu hình, không chạy lại cho từng asset.
2. Thiếu profile → nạp skill Project Setup, làm cùng anh (gồm cả `policy.yaml`).
3. Xong → **Producer nhắc anh gõ lệnh xóa context và mở phiên mới**, đúng câu lệnh của runtime (Claude Code: `/clear`; Codex: `/new`).
4. Producer cũng nhắc mở phiên mới sau khi cập nhật nội dung profile, và khi context đã dài sau một lô.
5. **Phiên mới khi `review_board: local+remote`** (D22.8): Producer kéo dữ liệu từ trang remote về trước khi chạy `P next`, để không bỏ sót quyết định anh đã bấm trên điện thoại.

**Quyết định không ghi trùng** (D22.8): mỗi bộ (asset, bước, version) chỉ nhận một quyết định Duyệt hoặc Cần sửa. Quyết định đến sau, từ trang local hay remote, bị bỏ qua và script báo lại. Ghi chú thì nhận nhiều lần.

## 15. Hỏi anh (D13.8)

Sub-agent không chat với anh. Đường duy nhất: worker trả `STATUS: NEEDS_CONTEXT` hoặc `BLOCKED` kèm câu hỏi → asset `blocked` → Producer hỏi anh (hoặc tự bổ sung nếu đã có thông tin, theo skill nền) → ghi vào mục "Làm rõ" của brief → `P retry`.

## 16. Runtime và so sánh A/B (D6.4, D21.10)

Bộ skill chạy trên **cả Claude Code và Codex**, để so bên nào cho kết quả tốt hơn.

**Một lõi, hai adapter** (D6.4: một nguồn chung, script build xuất hai bản). **Chép cấu trúc của kit** (D24.5) thay vì thiết kế mới: `build.py`, `editions/{claude,codex}/edition.json` (`skill_suffix`, `display_suffix`, `install_root`), `editions/*/adapter.md`, và thư mục `tests/`. Bảng khác biệt `docs/EDITIONS.md` là tóm tắt của hai thư mục `editions/`:

| Phần | Dùng chung | Theo runtime |
|---|---|---|
| `producer.py`, contract, schema, script kiểm, tool của agent | ✓ | |
| Prompt của từng agent (`agents/*.md`) | ✓ | |
| Cách gọi agent, resume, hook, tool gửi file, đường dẫn | | `adapters/claude.md`, `adapters/codex.md` |

- Spec agent viết trung lập với runtime: "sub-agent của runtime", không "sub-agent Claude" (D22.9).
- Adapter ghi cách quy đổi tên chung `opus`, `sonnet`, `haiku` sang model thật của runtime. Ledger ghi model thật đã dùng ở mỗi lần giao (D22.9).
- Claude Code: subagent qua Task; resume qua SendMessage; hook SessionStart; gửi file qua `SendUserFile`; Review Board `local+remote` dùng được (đã thử 2026-11-08).
- Codex: gọi agent qua `collaboration.spawn_agent`, resume qua `collaboration.send_message` (cần thử, `docs/coding-checklist.md`). Quyền mạng cấp ở phiên gốc. Review Board chỉ `local`.
- **Blender trong bản Codex** (D25.D): trên macOS Blender bị crash bên trong sandbox của Codex. Theo `installer/codex_rules.py` của kit, bản Codex có installer ghi file rules chỉ cho phép đúng các lệnh `<Blender> -b --python <script đã cài>.py …` của Producer và kit chạy ngoài sandbox. Mọi lệnh khác vẫn chạy trong sandbox. Thư mục skill chỉ đọc trong sandbox, nên agent không sửa được danh sách script được phép. Chạy lại installer sau mỗi lần nâng cấp.
- **Eval kích hoạt** (D25.E, theo `evals/triggers.json` của kit): mỗi skill và agent có bộ câu mẫu kèm kết quả mong đợi (kích hoạt hay không), gồm các câu âm trùng với kit, ví dụ "ZPS - 3D Artist dựng model cái rương" không được kích hoạt `zps-3dp-step-model`. Build chạy bộ eval này.
- Sửa prompt agent chỉ sửa một chỗ. Adapter không được chứa quy tắc nghiệp vụ.
- Thứ tự làm giữ như D6.4: bản Claude, chạy thử, rồi bản Codex. Chạy A/B khi cả hai bản đã qua một asset trọn vẹn.

**Chạy A/B:**

| Quy tắc | Chi tiết |
|---|---|
| Đầu vào chung | Cùng `_approved/`, cùng profile, cùng rubric, cùng art direction |
| Đầu ra riêng | `PRODUCER_ROOT=production-claude` / `production-codex`; `deliver-claude/`, `deliver-codex/`. Mỗi bên có `status.json`, `policy.yaml`, `[limits]` riêng |
| Chạy lệch giờ | Xong lô của bên này mới chạy bên kia, để thời gian đo được không lẫn tranh chấp tài nguyên |
| Phạm vi | 2–3 asset pilot. Chọn bên thắng, rồi chạy cả lô bằng bên đó. Lý do: credit Meshy nhân đôi |
| Duyệt mù | `P ab board` mở trang so cặp (review-board §8): mỗi asset hai bản đặt cạnh nhau, nhãn A/B gán ngẫu nhiên theo asset, lưu ở `ab/mapping.json`. Anh duyệt từng bản như thường; script ghi về đúng thư mục của runtime đó |
| Mở nhãn | `P compare --reveal`, chỉ sau khi anh đã duyệt hết các asset trong lô so sánh |
| Pilot | Mỗi runtime so với pilot nằm trong `deliver` của chính nó (D22.10) |

**Ledger ghi thời gian và token theo vai trò** (D27.3):
- Mỗi lần giao ghi `role` (worker, reviewer, script), thời điểm giao, thời điểm `ingest`, token và thời lượng của subagent.
- Producer truyền token và thời lượng mà runtime báo vào `P ingest` qua tham số mới. Hiện tại `P ingest` chỉ có `--tokens <N>` (một số cho lần giao).
- Runtime không báo số thì ledger ghi "không có số", không ghi 0.
- Script tính thêm **khoảng chờ Producer** = thời điểm giao lần sau − thời điểm ingest lần trước.
- `P stats <id>` in bảng theo bước: thời gian worker, reviewer, chờ Producer; token worker, reviewer, Producer.
- Run 4 chỉ có token gộp theo bước, nên chưa biết phần nào phình. Nếu chờ Producer > 15% thời gian bước, xem lại cách điều phối (lý do giữ Producer gọi reviewer: `docs/decisions.md` D27.3).

**`P compare`** tổng hợp từ ledger của hai bên (script ghi `runtime` vào mọi dòng ledger). Theo nguyên tắc Art Learning của kit (D25.J): đếm theo asset, không theo số lần gọi (thử lại trên cùng asset không phải bằng chứng độc lập); ghi cả lần thử bị loại; im lặng không tính là anh duyệt. Cùng nguyên tắc dùng cho việc hạ model sau pilot (D16.3):
- Số vòng sửa mỗi bước; tỉ lệ anh duyệt ngay lần đầu ở DUYỆT 1 và DUYỆT 2.
- Số lần `waiting_human` theo lý do.
- Thời gian thực mỗi bước và cả asset.
- Chi phí: token theo model (nếu runtime báo được), credit Meshy.
- Số lần reviewer chấm lệch so với quyết định của anh (cùng chỉ số với D16.3).
- Bên nào anh chọn ở nút "Bản nào tốt hơn" (D23.1).
- Tỉ lệ pass lần đầu của script kiểm mỗi bước.

**So cặp theo GPTEval3D** (D26.1): ngoài các chỉ số trên, `P compare` cho reviewer (chỉ đọc, context mới) so từng cặp A/B của cùng asset theo từng tiêu chí, **mỗi cặp hỏi hai lần với thứ tự A/B đổi chỗ**; kết quả lệch nhau giữa hai lần thì tính hòa. Tổng hợp thành Elo trên lô pilot, đặt cạnh lựa chọn của anh ở nút "Bản nào tốt hơn". Lựa chọn của anh là quyết định; Elo chỉ để xem reviewer có chấm giống anh không.

Kết quả so sánh gộp runtime và model đi kèm (Claude dùng Opus/Sonnet, Codex dùng model của nó). Kết luận là "bộ nào tốt hơn cho việc này", không tách riêng runtime hay model.

## 17. Thay đổi script cần làm (tóm tắt)

| Thay đổi | Hàm | Ước lượng |
|---|---|---|
| Gate `review_human`, `checks_human`; bỏ `final_human_gate` | `cmd_ingest`, `advance` | ~25 dòng |
| `assemble.py` (mục 6.4), dùng `finalize.py` và `export_check` của kit | mới | ~80 dòng |
| `COMPARE` và kiểm nhất quán với `PRIOR`; `PICK` và chép phương án `param`; brief kèm file JSON check fail (D26) | `cmd_ingest`, `worker_brief` | ~50 dòng |
| So cặp đổi thứ tự và Elo trong `P compare` (D26.1) | `P compare` | ~60 dòng |
| `meshy_call.py`: key từ `.env` của project, budget theo hash mesh, hoàn budget hoặc chờ tiếp `task_id` khi lỗi | mới | ~70 dòng |
| `policy.yaml`, `P approvals set` (+ `--confirm-spend`), `P delegate` | mới + `cmd_ingest` | ~50 dòng |
| Contract reviewer: `COUNTS`, `TOP_FIX` theo bước và kiểu sửa, `PRIOR`; `findings.json` theo version; chép finding khi `redo` | `cmd_ingest`, `parse_contract`, `review_brief` | ~90 dòng |
| Tiến bộ theo finding, dừng sớm, bản tốt nhất | `cmd_ingest`, `worker_brief` | ~40 dòng |
| `need_evidence` trong `vN/review/evidence-<k>/`, không tạo version, so hash `final/` | `cmd_brief`, `cmd_ingest` | ~30 dòng |
| `fix_uv_mesh` → redo model; file budget theo hash mesh; câu hỏi khi mesh đổi; kiểm key trước bước `texture` | `cmd_ingest`, mới | ~50 dòng |
| `PROFILE_HASH` sinh trong brief, so khi ingest; hash bỏ `paths` và khóa `_` | mới | ~30 dòng |
| `inputs` mỗi version, suy ra version cũ, cảnh báo theo hash | mới + `warnings_for` | ~60 dòng |
| `[limits]` và `uses`; `next` chờ slot | `cmd_next` | ~30 dòng |
| Chép sang `deliver/` (chỉ khi duyệt `assemble`), đánh dấu `rejected` | `approve_step` | ~20 dòng |
| `P texture-stats`: tổng hợp từ ledger và `texture_spec.json` khi cần | mới | ~30 dòng |
| D27: `ingest` in lệnh giao tiếp; thời gian và token theo vai trò, "không có số", `P stats`; agent tự ghi report, sự kiện `report_fallback`; `RESOLVED_NOTES` và xác nhận của reviewer | `cmd_ingest`, mới | ~110 dòng |
| Quyết định không ghi trùng | `human_action` | ~15 dòng |
| Pilot trước lô sau | `cmd_intake` | ~15 dòng |
| `P show`, `--bundle` (dùng renderer của Review Board) | mới | ~60 dòng |
| Finding theo bộ trường của kit (`issue-fields`), `EVIDENCE_OPENED`, `superseded`, `preference` | `parse_contract`, `cmd_ingest` | ~40 dòng |
| `P preflight` (gọi `preflight.py` của kit) | mới | ~40 dòng |
| Ước lượng và báo giá theo lô (`estimate.py` của kit) | `cmd_intake`, `approve_step` | ~30 dòng |
| Installer rules Blender cho bản Codex; eval kích hoạt | `editions/codex/installer/`, `tests/` | chép mẫu của kit |
| `P board prepare` (Review Board §6) | mới | — |
| `P ab board`, `P compare`, cột `runtime` trong ledger | mới | ~150 dòng |
| Intake: `check_card`, file bắt buộc, `type` từ thẻ, `check_profile` | `scan_approved`, `cmd_intake`, `create_asset` | ~60 dòng |
| Tên `zps-3dp-producer`, adapter, đường dẫn | `SKILL.md`, `setup.md`, `adapters/` | — |

## 18. Thứ tự code (D22.18)

Code theo lát dọc. Mỗi giai đoạn chạy được trên asset pilot rồi mới sang giai đoạn sau.

| GĐ | Nội dung | Kiểm chứng chính |
|---|---|---|
| 0 | Sửa tài liệu: concept brief = thẻ asset, `out-of-scope-changes.md`, mẫu rubric chỉ có tiêu chí và tham chiếu AD | — |
| 1 | Lõi `producer.py` (state, finding theo version, vòng sửa, policy, limits, kiểm hash) + `blockout` + `check-blockout` + trang duyệt local tối thiểu | Reviewer ghi đủ `PRIOR`; vòng sửa theo finding hội tụ; model và resume theo từng lần giao trên Claude Code |
| 2 | `views_front`, `views_rest`, `gen_image_codex.py`, `regen_front` | Ảnh view đúng guide; front không bị chấm lại |
| 3 | `model`, `check-clay`, khóa mesh | Detail pass, UV, DUYỆT 1 |
| 4 | `texture` (budget Meshy theo hash mesh), `assemble.py` | Meshy giữ UV; GLB hiển thị khớp render của bước `texture` |
| 5 | Review Board đầy đủ: khoanh vùng, trang remote, `P show`, quyết định không ghi trùng | Trên điện thoại và trang local |
| 6 | Bản Codex, adapter, A/B | `codex exec` lồng trong Codex; báo cáo token |

Lý do: phần rủi ro nhất của thiết kế (reviewer ghi `PRIOR`, vòng sửa theo finding) được kiểm ở GĐ 1. Nếu sai, các giai đoạn sau sửa theo trước khi viết.
