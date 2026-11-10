"""D29: free disk after DUYỆT 2. The user's approval arms a deletion; the next session's start deletes it; `P keep`,
`P purge`, `P disk`, and the disk lines of `P next`."""
from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

from . import policy, session
from .state import (ASSETS, DELIVER, FINISHED, ROOT, RUNTIME, ProducerError, die, ledger, load_cfg, load_st, locked, now,
                    rel, save_st, write_atomic)

TEXT = {".md", ".json", ".jsonl", ".txt", ".yaml", ".yml", ".toml", ".py", ".csv"}
PENDING, MANIFEST = "purge-pending.json", "purge-manifest.json"
NEW_SESSION = ("startup", "clear")
THUMB_PX = 1024
GB = 1 << 30


def size(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def files(d: Path):
    """Regular files under d, symlinks left out: a purge never follows a link out of the asset."""
    for top, dirs, names in os.walk(d):
        dirs[:] = [x for x in dirs if not os.path.islink(os.path.join(top, x))]
        for x in names:
            p = Path(top, x)
            if not p.is_symlink():
                yield p


def linked(cfg: dict, st: dict) -> set[Path]:
    """Every image a board card or `P show` links: the shown version of each step."""
    from .board import view_images
    from .loop import shown
    return {p.resolve() for s in cfg["steps"] if (n := shown(st, s["id"]))
            for p, _ in view_images(cfg, st, s["id"], n)}


def big(p: Path) -> bool:
    from PIL import Image
    try:
        with Image.open(p) as im:
            return max(im.size) > THUMB_PX
    except OSError:
        return False


def plan(cfg: dict, st: dict) -> dict:
    """D29.6: keep text records and step text sources outside `work/`, and the images the board links (shrunk when
    larger than THUMB_PX). Everything else under assets/<id>/ is deleted. `feedback/` keeps its marked images:
    feedback.md links them."""
    a = ASSETS / st["id"]
    shown = linked(cfg, st)
    out, thumbs = [], []
    for f in sorted(files(a)):
        r = f.relative_to(a).parts
        work = len(r) > 3 and re.fullmatch(r"v\d+", r[1]) and r[2] == "work"
        if r[0] == "feedback" or not work and f.suffix.lower() in TEXT:
            continue
        if not work and f.resolve() in shown:
            if big(f):
                thumbs.append("/".join(r))
            continue
        out.append(("/".join(r), f.lstat().st_size))
    return {"delete": out, "thumbs": thumbs, "bytes": sum(b for _, b in out)}


def groups(p: dict) -> list[str]:
    by: dict[str, list[int]] = {}
    for r, b in p["delete"]:
        parts = r.split("/")
        g = by.setdefault("/".join(parts[:2]) if len(parts) > 2 else parts[0], [0, 0])
        g[0], g[1] = g[0] + 1, g[1] + b
    return [f"  {k}: {n} file, {size(b)}" for k, (n, b) in by.items()]


def pack(aid: str, p: dict, path: str) -> str:
    """D29.9: the files to delete, and the originals of the shrunk images, before anything is deleted."""
    a, out = ASSETS / aid, Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    names = [r for r, _ in p["delete"]] + p["thumbs"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for r in names:
            z.write(a / r, f"{aid}/{r}")
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None or len(z.namelist()) != len(names):
            die(f"{out}: file nén hỏng, chưa xóa gì")
    return str(out)


def arm(cfg: dict, st: dict, zip_path: str | None) -> str:
    """D29.2, D29.3: only a DUYỆT 2 by the user calls this. Nothing is deleted in this session."""
    aid = st["id"]
    p = plan(cfg, st)
    zp = pack(aid, p, zip_path) if zip_path else None
    doc = {"asset": aid, "armed": now(), "assemble": st["approved"]["assemble"],
           "session": (session.load() or {}).get("session_id"), "bytes": p["bytes"], "zip": zp,
           "delete": [{"path": r, "bytes": b} for r, b in p["delete"]], "thumbs": p["thumbs"]}
    write_atomic(ASSETS / aid / PENDING, json.dumps(doc, ensure_ascii=False, indent=2))
    ledger(f"{aid} · lệnh xóa D29: {len(p['delete'])} file, {size(p['bytes'])}, thu nhỏ {len(p['thumbs'])} ảnh"
           + (f" · nén {zp}" if zp else ""))
    when = ("bản Codex không tự xóa: `purge` khi người dùng muốn" if RUNTIME == "codex"
            else "xóa ở đầu phiên sau (hook SessionStart: startup hoặc clear)")
    return "\n".join([f"Lệnh xóa D29: {len(p['delete'])} file, {size(p['bytes'])}; thu nhỏ {len(p['thumbs'])} ảnh "
                      f"trang duyệt trỏ tới; {when}. Giữ: `keep {aid}`. Xóa ngay: `purge {aid} --by \"<nguyên văn>\"`. "
                      f"Danh sách: {rel(ASSETS / aid / PENDING)}", *groups(p)])


def blocked(st: dict, doc: dict | None) -> str | None:
    """Checked again at delete time: a redo since the arm, a new DUYỆT 2, or no delivered package keeps every file."""
    if st.get("purged"):
        return f"đã xóa lúc {st['purged']['at']}"
    if st["state"] not in FINISHED or not st["approved"].get("assemble"):
        return f"chưa DUYỆT 2 hoặc đang làm lại (state={st['state']})"
    if doc and doc.get("assemble") != st["approved"]["assemble"]:
        return f"DUYỆT 2 đổi từ assemble v{doc.get('assemble')} sang v{st['approved']['assemble']}"
    if not (DELIVER / st["id"]).is_dir():
        return f"không có {rel(DELIVER / st['id'])}/"
    return None


def shrink(f: Path) -> tuple[int, int]:
    from PIL import Image
    before = f.stat().st_size
    with Image.open(f) as im:
        fmt = im.format
        im.load()
        im.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
        tmp = f.with_name(f".{f.name}.thumb")
        im.save(tmp, fmt)
    os.replace(tmp, f)
    return before, f.stat().st_size


def execute(cfg: dict, st: dict, source: str, by: str | None, zip_path: str | None = None) -> str:
    aid, a = st["id"], ASSETS / st["id"]
    pend = a / PENDING
    p = plan(cfg, st)
    zp = pack(aid, p, zip_path) if zip_path else (json.loads(pend.read_text(encoding="utf-8")).get("zip")
                                                   if pend.is_file() else None)
    for r, _ in p["delete"]:
        (a / r).unlink()
    for top, dirs, names in os.walk(a, topdown=False):
        if Path(top) != a and not os.listdir(top):
            os.rmdir(top)
    th = [{"path": r, "before": b0, "after": b1} for r in p["thumbs"] for b0, b1 in [shrink(a / r)]]
    freed = p["bytes"] + sum(t["before"] - t["after"] for t in th)
    doc = {"asset": aid, "at": now(), "source": source, "by": by, "assemble": st["approved"]["assemble"],
           "freed_bytes": freed, "zip": zp, "deleted": [{"path": r, "bytes": b} for r, b in p["delete"]],
           "thumbnails": th}
    write_atomic(a / MANIFEST, json.dumps(doc, ensure_ascii=False, indent=2))
    pend.unlink(missing_ok=True)
    st["purged"] = {"at": doc["at"], "manifest": rel(a / MANIFEST), "freed_bytes": freed, "zip": zp}
    save_st(st)
    ledger(f"{aid} · đã xóa D29 ({source}): {len(p['delete'])} file, thu nhỏ {len(th)} ảnh, giải phóng {size(freed)}"
           + (f" · by: {by}" if by else "") + (f" · nén {zp}" if zp else ""))
    return (f"[{aid}] đã xóa {len(p['delete'])} file, thu nhỏ {len(th)} ảnh, giải phóng {size(freed)}. "
            f"Manifest: {rel(a / MANIFEST)}")


def on_next(a) -> list[str]:
    """D29.4: delete only when the SessionStart hook says a new session started (`startup`, `clear`), in another
    session than the one that armed it. Codex has no hook: it only reminds. A failure never stops `P next`."""
    pend = sorted(ASSETS.glob(f"*/{PENDING}")) if ASSETS.is_dir() else []
    src = getattr(a, "source", None) if a.session else None
    auto = src in NEW_SESSION and RUNTIME != "codex"
    out = []
    for p in pend:
        aid = p.parent.name
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if not auto or (doc.get("session") and doc["session"] == getattr(a, "session_id", None)):
                how = ("bản Codex không tự xóa: `purge " + aid + " --by \"<nguyên văn>\"` khi người dùng muốn"
                       if RUNTIME == "codex" else "xóa ở đầu phiên sau")
                out.append(f"[{aid}] chờ xóa {size(doc.get('bytes') or 0)} sau DUYỆT 2: {how}; giữ: `keep {aid}`")
                continue
            with locked():
                st = load_st(aid)
                if why := blocked(st, doc):
                    p.unlink()
                    ledger(f"{aid} · hủy lệnh xóa D29: {why}")
                    out.append(f"[{aid}] hủy lệnh xóa: {why}")
                else:
                    out.append(execute(load_cfg(), st, src, None))
        except (ProducerError, OSError, ValueError) as ex:
            out.append(f"[{aid}] chưa xóa được: {ex}")
    return out


def tree_size(d: Path) -> int:
    return sum(f.lstat().st_size for f in files(d)) if d.is_dir() else 0


def disk_warning() -> str | None:
    lim = policy.load().get("disk_warn_gb")
    total = tree_size(ROOT)
    if lim is None or total <= lim * GB:
        return None
    return f"⚠ {rel(ROOT)}/ dùng {size(total)}, vượt disk_warn_gb {lim} GB → `disk` để xem chỗ lớn"


def keep(a):
    p = ASSETS / a.id / PENDING
    load_st(a.id)
    p.is_file() or die(f"{a.id}: không có lệnh xóa nào đang chờ")
    p.unlink()
    ledger(f"{a.id} · giữ file, hủy lệnh xóa D29" + (f" · by: {a.by}" if a.by else ""))
    print(f"{a.id}: đã hủy lệnh xóa; mọi file giữ nguyên")


def purge(a):
    st = load_st(a.id)
    if why := blocked(st, None):
        die(f"{a.id}: không xóa: {why}")
    print(execute(load_cfg(), st, "purge", a.by, a.zip))


def refused(st: dict) -> str:
    """D29: after a purge the finals keep only text, so no step can be built again from them."""
    p = st["purged"]
    return (f"{st['id']}: không làm lại được: file trung gian đã xóa lúc {p['at']} (manifest {p['manifest']}); final/ "
            "của các bước chỉ còn file text" + (f". Bản nén: {p['zip']}" if p.get("zip") else ""))


def disk(_a):
    by_asset: dict[str, int] = {}
    by_step: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for f in files(ROOT):
        b = f.lstat().st_size
        r = f.relative_to(ROOT).parts
        if len(r) > 2 and r[0] in ("assets", "archive"):
            by_asset[r[1]] = by_asset.get(r[1], 0) + b
            if len(r) > 3 and r[0] == "assets":
                by_step[r[2]] = by_step.get(r[2], 0) + b
        t = f.suffix.lower() or "(không đuôi)"
        by_type[t] = by_type.get(t, 0) + b
    lim = policy.load().get("disk_warn_gb")
    out = [f"{rel(ROOT)}/: {size(sum(by_type.values()))}" + (f" · ngưỡng disk_warn_gb {lim} GB" if lim else "")]
    for head, d in (("Theo asset", by_asset), ("Theo bước", by_step), ("Theo loại file", by_type)):
        out += [f"{head}:", *(f"  {k}: {size(v)}" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])))]
    print("\n".join(out))
