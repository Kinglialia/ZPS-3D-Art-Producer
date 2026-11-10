#!/usr/bin/env python3
"""Producer CLI: giữ trạng thái pipeline art trong file để Producer (LLM) không phải nhớ.

Chạy từ thư mục gốc project. Dữ liệu nằm ở ./production (đổi bằng biến môi trường PRODUCER_ROOT).
Cần Python 3.11+ (dùng tomllib).

Lệnh chính:  init · preflight · intake · new · ready · next · brief · ingest · retry · ack · feedback · waive · meshy
             texture-mode · approvals · delegate · rule · ledger · stats · dashboard · serve · show · board · validate
             cleanup · archive · texture-stats · ab · compare
Xem `producer.py <lệnh> -h` để biết tham số.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.state import PORT, ProducerError, load_cfg, locked  # noqa: E402

UNLOCKED = {"next", "ledger", "stats", "validate", "serve", "texture-stats", "ab", "compare"}


def cmd_init(a):
    from core.intake import init
    init(a)


def cmd_preflight(a):
    from core.preflight import run_preflight
    run_preflight(a)


def cmd_intake(a):
    from core.intake import run
    run(a, load_cfg())


def cmd_new(a):
    from core.intake import new
    new(a, load_cfg())


def cmd_ready(a):
    from core.intake import ready
    ready(a)


def cmd_ack(a):
    from core.hashes import ack
    ack(a)


def cmd_next(a):
    from core.limits import show_next
    show_next(a)


def cmd_brief(a):
    from core.briefs import run
    run(a)


def cmd_ingest(a):
    from core.loop import ingest
    ingest(a)


def cmd_retry(a):
    from core.loop import retry
    retry(a)


def cmd_waive(a):
    from core.loop import waive
    waive(a)


def cmd_feedback(a):
    import json
    from core.loop import after_feedback, human_action
    from core.state import load_st
    regions = json.loads(Path(a.regions).read_text(encoding="utf-8")) if a.regions else None
    st = load_st(a.id)
    before = (st["stage"], st["state"], len(st.get("decisions", {})))
    print(human_action(a.id, a.action, a.text, a.step, regions, a.offer))
    after_feedback(a.id, before)


def cmd_approvals(a):
    from core.policy import set_approval
    set_approval(a)


def cmd_delegate(a):
    from core.policy import delegate
    delegate(a)


def cmd_meshy(a):
    from core.texture import answer
    answer(a)


def cmd_texture_mode(a):
    from core.texture import set_choice
    set_choice(a)


def cmd_texture_stats(a):
    from core.texture import stats
    stats(a)


def cmd_rule(a):
    from core.state import rule
    rule(a)


def cmd_ledger(a):
    from core.state import ledger_tail
    ledger_tail(a)


def cmd_stats(a):
    from core.stats import run
    run(a)


def cmd_dashboard(_a):
    from core.board import dashboard
    dashboard()


def cmd_show(a):
    from core.board import show
    show(a)


def cmd_board(a):
    from core import remote
    getattr(remote, a.op)(a)


def cmd_ab(a):
    from core import ab
    if a.op == "prefer":
        a.id and a.choice or ab.die("ab prefer <asset> <A|B|tie> --by \"<nguyên văn>\"")
        print(ab.prefer(a.id, a.choice, a.by, "chat"))
    else:
        getattr(ab, a.op)(a)


def cmd_compare(a):
    from core.ab import compare
    compare(a)


def cmd_serve(a):
    from core.board import serve
    serve(a.port)


def cmd_validate(a):
    from core.state import validate
    validate(a)


def cmd_cleanup(a):
    from core.state import cleanup
    cleanup(a)


def cmd_archive(a):
    from core.state import archive
    archive(a)


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("init", help="tạo production/, rubric mẫu, _approved/ và GUIDELINE.md")
    x.add_argument("--project", required=True, help="tên project, vd \"New Last Order\"")
    x.add_argument("--concepts", required=True, help="thư mục concept của project")
    sub.add_parser("preflight", help="kiểm môi trường một lần mỗi phiên → production/preflight.json "
                                     "(preflight.py của kit: biến PRODUCER_KIT, mặc định skill zps-3d-artist cạnh skill này)")
    x = sub.add_parser("intake", help="quét _approved/: không tham số = chỉ liệt kê")
    x.add_argument("ids", nargs="*", help="building id cần đăng ký (làm trước)")
    x.add_argument("--all", action="store_true", help="đăng ký mọi building mới đủ ảnh")
    x.add_argument("--priority", type=int, default=2, choices=[1, 2, 3]); x.add_argument("--deadline")
    x = sub.add_parser("ack", help="ghi nhận concept/art direction đã đổi, tắt cảnh báo")
    x.add_argument("id"); x.add_argument("note", nargs="?", default="")
    x = sub.add_parser("new", help="tạo asset thủ công, không qua _approved/")
    x.add_argument("id"); x.add_argument("--title", required=True)
    x.add_argument("--type", default="asset"); x.add_argument("--priority", type=int, default=2, choices=[1, 2, 3])
    x.add_argument("--deadline", help="YYYY-MM-DD")
    sub.add_parser("ready", help="người dùng đã duyệt rubric: draft → todo").add_argument("ids", nargs="+")
    x = sub.add_parser("next", help="việc tiếp theo của mọi asset")
    x.add_argument("--session", action="store_true", help="dùng cho hook SessionStart")
    sub.add_parser("brief", help="sinh brief cho worker/reviewer, in JSON để giao việc").add_argument("id")
    x = sub.add_parser("ingest", help="đọc báo cáo, chuyển state")
    x.add_argument("id"); x.add_argument("--agent-id", help="id subagent worker, để resume vòng sửa")
    x.add_argument("--tokens", type=int, help="token runtime báo cho lần giao này, nếu runtime báo được (P compare, P stats)")
    x.add_argument("--duration-ms", type=int, help="thời lượng runtime báo cho lần giao này, mili giây (P stats)")
    x.add_argument("--fallback", action="store_true",
                   help="Producer đã lưu report agent trả bằng tin nhắn vì lệnh ghi bị chặn (ledger: report_fallback)")
    sub.add_parser("retry", help="giao lại asset đang blocked").add_argument("id")
    x = sub.add_parser("feedback", help="ghi feedback / quyết định của người dùng")
    x.add_argument("id"); x.add_argument("text"); x.add_argument("--action", default="note", choices=["approve", "redo", "note"])
    x.add_argument("--step", help="bước áp dụng (mặc định: bước hiện tại)")
    x.add_argument("--regions", help="JSON vùng khoanh [{n, image, shape, coords, note}] trên ảnh của thẻ đang chờ")
    x.add_argument("--offer", help="khóa lần đưa duyệt mà người dùng đã thấy; khóa cũ thì bỏ qua")
    x = sub.add_parser("waive", help="chấp nhận một finding là ngoại lệ (D30.1): ở mọi state, finding thành waived")
    x.add_argument("id"); x.add_argument("fid", help="id finding, vd F2"); x.add_argument("why", help="lý do")
    x.add_argument("--by", default="user", choices=["user", "producer"],
                   help="producer: chỉ khi policy.yaml có test_mode: true")
    x.add_argument("--step", help="bước của finding (mặc định: bước hiện tại)")
    x = sub.add_parser("approvals", help="đổi người duyệt một bước (hoặc review_board local|local+remote, test_mode true|false) trong policy.yaml")
    x.add_argument("op", choices=["set"]); x.add_argument("step"); x.add_argument("who")
    x.add_argument("--by", required=True, help="nguyên văn lời người dùng"); x.add_argument("--confirm-spend", action="store_true")
    x = sub.add_parser("delegate", help="ủy quyền reviewer duyệt bước này cho các asset")
    x.add_argument("step"); x.add_argument("ids", nargs="+"); x.add_argument("--by", default="")
    x.add_argument("--confirm-spend", action="store_true")
    x = sub.add_parser("meshy", help="trả lời câu hỏi Meshy của bước texture: call = gọi thêm, paint = VẼ MỚI")
    x.add_argument("id"); x.add_argument("choice", choices=["call", "paint"]); x.add_argument("--by", default="")
    x = sub.add_parser("texture-mode", help="chế độ texture người dùng chọn: auto = Meshy khi có key và budget, "
                                            "meshy = buộc Meshy, paint = VẼ MỚI")
    x.add_argument("id"); x.add_argument("mode", choices=["auto", "meshy", "paint"]); x.add_argument("--by", default="")
    sub.add_parser("texture-stats", help="đề xuất chế độ texture so với chế độ đã dùng, credit Meshy")
    sub.add_parser("rule", help="ghi quyết định Producer tự đưa ra").add_argument("text")
    x = sub.add_parser("ledger", help="xem cuối ledger")
    x.add_argument("--tail", type=int, default=20); x.add_argument("--rulings", action="store_true")
    sub.add_parser("stats", help="bảng theo bước: thời gian, token theo vai trò, chờ Producer").add_argument("id")
    sub.add_parser("dashboard", help="sinh lại dashboard.md")
    sub.add_parser("serve", help="mở review page có nút feedback").add_argument("--port", type=int, default=PORT)
    x = sub.add_parser("show", help="xuất trang board của một asset thành file HTML tĩnh")
    x.add_argument("id"); x.add_argument("--step"); x.add_argument("--version", type=int)
    x.add_argument("--bundle", action="store_true", help="nhúng ảnh (≤ 1024 px, crop giữ nguyên) và GLB ≤ 15 MB: xem trên điện thoại")
    x = sub.add_parser("board", help="trang claude.ai: prepare = gói file và dòng dữ liệu để đẩy; pull = áp dòng đã kéo về")
    x.add_argument("op", choices=["prepare", "pull"]); x.add_argument("--url", help="prepare: URL artifact của trang (lưu lại)")
    x.add_argument("--redo", action="store_true", help="prepare: đẩy lại mọi asset đang chờ (lần đẩy trước hỏng)")
    x.add_argument("--dir", help="pull: out_dir đã đưa cho ArtifactData list (mặc định production/board/inbox)")
    x = sub.add_parser("ab", help="so A/B hai runtime: board = trang so cặp mù; prefer = ghi bản tốt hơn; "
                                  "judge = giao reviewer so cặp; side = nội bộ của board")
    x.add_argument("op", choices=["board", "prefer", "judge", "side"]); x.add_argument("id", nargs="?")
    x.add_argument("choice", nargs="?", choices=["A", "B", "tie"]); x.add_argument("--by", default="")
    x.add_argument("--port", type=int, default=8766)
    x.add_argument("--fallback", action="store_true", help="judge: Producer đã lưu report agent trả bằng tin nhắn")
    sub.add_parser("compare", help="tổng hợp A/B theo asset; --reveal mở nhãn khi lô đã duyệt hết").add_argument(
        "--reveal", action="store_true")
    sub.add_parser("validate", help="kiểm tra cấu hình và status")
    x = sub.add_parser("cleanup", help="xoá work/ của phiên bản không được duyệt (mặc định dry-run)")
    x.add_argument("id"); x.add_argument("--yes", action="store_true"); x.add_argument("--all", action="store_true")
    x = sub.add_parser("archive", help="chuyển asset đã xong vào archive/")
    x.add_argument("id"); x.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    try:
        with locked(create=a.cmd in ("init", "preflight")) if a.cmd not in UNLOCKED else contextlib.nullcontext():
            globals()[f"cmd_{a.cmd.replace('-', '_')}"](a)
    except ProducerError as ex:
        sys.exit(f"LỖI: {ex}")


if __name__ == "__main__":
    main()
