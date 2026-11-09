#!/usr/bin/env python3
"""Producer CLI: giữ trạng thái pipeline art trong file để Producer (LLM) không phải nhớ.

Chạy từ thư mục gốc project. Dữ liệu nằm ở ./production (đổi bằng biến môi trường PRODUCER_ROOT).
Cần Python 3.11+ (dùng tomllib).

Lệnh chính:  init · intake · new · ready · next · brief · ingest · retry · ack · feedback · approvals · delegate · rule
             ledger · dashboard · serve · validate · cleanup · archive
Xem `producer.py <lệnh> -h` để biết tham số.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.state import PORT, ProducerError, load_cfg  # noqa: E402


def cmd_init(a):
    from core.intake import init
    init(a)


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


def cmd_feedback(a):
    from core.loop import human_action
    print(human_action(a.id, a.action, a.text, a.step))


def cmd_approvals(a):
    from core.policy import set_approval
    set_approval(a)


def cmd_delegate(a):
    from core.policy import delegate
    delegate(a)


def cmd_rule(a):
    from core.state import rule
    rule(a)


def cmd_ledger(a):
    from core.state import ledger_tail
    ledger_tail(a)


def cmd_dashboard(_a):
    from core.board import dashboard
    dashboard()


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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("init", help="tạo production/, rubric mẫu, _approved/ và GUIDELINE.md")
    x.add_argument("--project", required=True, help="tên project, vd \"New Last Order\"")
    x.add_argument("--concepts", required=True, help="thư mục concept của project")
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
    sub.add_parser("retry", help="giao lại asset đang blocked").add_argument("id")
    x = sub.add_parser("feedback", help="ghi feedback / quyết định của người dùng")
    x.add_argument("id"); x.add_argument("text"); x.add_argument("--action", default="note", choices=["approve", "redo", "note"])
    x.add_argument("--step", help="bước áp dụng (mặc định: bước hiện tại)")
    x = sub.add_parser("approvals", help="đổi người duyệt một bước trong policy.yaml")
    x.add_argument("op", choices=["set"]); x.add_argument("step"); x.add_argument("who")
    x.add_argument("--by", required=True, help="nguyên văn lời người dùng"); x.add_argument("--confirm-spend", action="store_true")
    x = sub.add_parser("delegate", help="ủy quyền reviewer duyệt bước này cho các asset")
    x.add_argument("step"); x.add_argument("ids", nargs="+"); x.add_argument("--by", default="")
    x.add_argument("--confirm-spend", action="store_true")
    sub.add_parser("rule", help="ghi quyết định Producer tự đưa ra").add_argument("text")
    x = sub.add_parser("ledger", help="xem cuối ledger")
    x.add_argument("--tail", type=int, default=20); x.add_argument("--rulings", action="store_true")
    sub.add_parser("dashboard", help="sinh lại dashboard.md + review.html")
    sub.add_parser("serve", help="mở review page có nút feedback").add_argument("--port", type=int, default=PORT)
    sub.add_parser("validate", help="kiểm tra cấu hình và status")
    x = sub.add_parser("cleanup", help="xoá work/ của phiên bản không được duyệt (mặc định dry-run)")
    x.add_argument("id"); x.add_argument("--yes", action="store_true"); x.add_argument("--all", action="store_true")
    x = sub.add_parser("archive", help="chuyển asset đã xong vào archive/")
    x.add_argument("id"); x.add_argument("--force", action="store_true")
    a = p.parse_args()
    try:
        globals()[f"cmd_{a.cmd}"](a)
    except ProducerError as ex:
        sys.exit(f"LỖI: {ex}")


if __name__ == "__main__":
    main()
