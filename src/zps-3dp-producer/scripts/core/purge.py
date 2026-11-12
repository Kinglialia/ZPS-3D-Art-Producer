"""D29, D40: free disk at DUYỆT 2. The user's approval deletes in the same command; `P keep`, `P purge`, `P disk`, and the
disk lines of `P next`."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import zipfile
from pathlib import Path

from . import policy
from .state import (ASSETS, DELIVER, FINISHED, ROOT, ProducerError, all_status, die, ledger, load_cfg, load_st, now, rel,
                    save_st, write_atomic)

TEXT = {".md", ".json", ".jsonl", ".txt", ".log", ".yaml", ".yml", ".toml", ".py", ".csv"}
PENDING, MANIFEST = "purge-pending.json", "purge-manifest.json"
REJECTED = "*.rejected-*.md"
NO_REDO = "sau lệnh này không `redo` được"
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


def outside(cfg: dict, aid: str) -> list[tuple[str, int]]:
    """D40.3: what the asset left under production/ outside assets/<id>/, as (path under production/, bytes). Exact
    names only, so `a-2` never costs `a` its files: `show/` pages by step id, the board files this asset pushed, and
    pid files of a process that is gone (`<id>-<pid>.pid` is not the `<id>-2.pid` of another asset). `pushes/*.json`
    of a push names every open asset and stays."""
    steps = "|".join(re.escape(s["id"]) for s in cfg["steps"])
    page = re.compile(rf"{re.escape(aid)}(-({steps})-v\d+)?(-bundle)?\.html")
    pid = re.compile(rf"{re.escape(aid)}(-\d+)?\.pid")
    found = [f for f in sorted((ROOT / "show").glob("*.html")) if page.fullmatch(f.name)]
    for d in sorted((ROOT / "board" / "push").glob("*")):
        found += [d / f"{aid}_glb.json", d / "offers" / f"{d.name}~{aid}.json"]
    from .limits import alive
    siblings = {d.name for d in ASSETS.iterdir() if d.is_dir()} - {aid}
    for d in sorted((ROOT / "pids").glob("*")):
        for f in sorted(d.glob("*.pid")):
            if pid.fullmatch(f.name) and f.stem not in siblings and not _live(f, alive):
                found.append(f)
    return [(f.relative_to(ROOT).as_posix(), f.lstat().st_size) for f in found if f.is_file() and not f.is_symlink()]


def _live(f: Path, alive) -> bool:
    try:
        return alive(int(f.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return False


def plan(cfg: dict, st: dict) -> dict:
    """D29.6, D40.2: keep text records and step text sources outside `work/`, and the images the board links (shrunk
    when larger than THUMB_PX). Everything else under assets/<id>/ is deleted, and so is every `*.rejected-*.md`.
    `feedback/` keeps its marked images: feedback.md links them. D32.3: the asset's custom_parts.py and each
    parts_lib.py stay as text sources; the JSON meshes custom_mesh.py made sit in work/ and go with it. `other` holds
    the files outside assets/<id>/ (see `outside`); `bytes` counts both."""
    a = ASSETS / st["id"]
    shown = linked(cfg, st)
    out, thumbs = [], []
    for f in sorted(files(a)):
        r = f.relative_to(a).parts
        work = len(r) > 3 and re.fullmatch(r"v\d+", r[1]) and r[2] == "work"
        if fnmatch.fnmatchcase(f.name, REJECTED):
            out.append(("/".join(r), f.lstat().st_size))
            continue
        if r[0] == "feedback" or not work and f.suffix.lower() in TEXT:
            continue
        if not work and f.resolve() in shown:
            if big(f):
                thumbs.append("/".join(r))
            continue
        out.append(("/".join(r), f.lstat().st_size))
    other = outside(cfg, st["id"])
    return {"delete": out, "other": other, "thumbs": thumbs, "bytes": sum(b for _, b in out + other)}


def count(p: dict) -> int:
    return len(p["delete"]) + len(p["other"])


def notice(p: dict | None) -> str:
    """D40.4: the one line the command prints and the DUYỆT 2 button shows. No plan, no size."""
    return f"Sẽ xóa {count(p)} file, {size(p['bytes'])}; {NO_REDO}." if p else f"Sẽ xóa file trung gian; {NO_REDO}."


def zip_target(aid: str, explicit: str | None) -> str | None:
    """`--zip <file>` wins over `purge_zip: <folder>` of policy.yaml."""
    if explicit:
        return explicit
    folder = policy.purge_zip(policy.load())
    return str(Path(folder).expanduser() / f"{aid}.zip") if folder else None


def pack(aid: str, p: dict, path: str) -> str:
    """D29.9: the files to delete, and the originals of the shrunk images, before anything is deleted."""
    a, out = ASSETS / aid, Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    names = [(a / r, f"{aid}/{r}") for r, _ in p["delete"]] + [(ROOT / r, f"{ROOT.name}/{r}") for r, _ in p["other"]]
    names += [(a / r, f"{aid}/{r}") for r in p["thumbs"]]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f, name in names:
            z.write(f, name)
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None or len(z.namelist()) != len(names):
            die(f"{out}: file nén hỏng, chưa xóa gì")
    return str(out)


def prepare(cfg: dict, st: dict, zip_path: str | None) -> tuple[dict, str | None]:
    """The plan and, when asked, its zip. Nothing is deleted here, so a failure leaves every file."""
    p = plan(cfg, st)
    target = zip_target(st["id"], zip_path)
    return p, pack(st["id"], p, target) if target else None


def ab_wait(aid: str) -> str | None:
    """Producer decision 2026-11-10: an A/B root keeps every file until the pair has a preference (`ab prefer`) or both
    judge asks (`ab judge`), so the blind pair board never shows one side purged."""
    if not re.fullmatch(r"production-(claude|codex)", ROOT.name):
        return None
    from . import ab
    if aid in ab.prefs() or ab.pair_result(aid) is not None:
        return None
    return (f"cặp A/B {aid} chưa có kết quả so (chưa `ab prefer {aid} <A|B|tie>` và chưa đủ hai lần `ab judge`): "
            "giữ mọi file tới khi có")


def hold(st: dict, report_ok: bool = True) -> tuple[str, str] | None:
    """Why a DUYỆT 2 by the user deletes nothing: (code, reason), or None when it deletes. The command, the button and
    `P next` all ask this one function, so the page never shows a deletion that will not happen."""
    if policy.purge_mode(policy.load()) == "off":
        return "off", "policy.yaml có purge: off"
    if st.get("keep_files"):
        return "keep", f"đã `keep {st['id']}` trước khi duyệt"
    if wait := ab_wait(st["id"]):
        return "ab", wait
    if not report_ok:
        return "report", "chưa có RUN-REPORT.md"
    return None


def offer_notice(cfg: dict, st: dict) -> str | None:
    """The line for the DUYỆT 2 button of an assemble offer; None when this approval deletes nothing."""
    try:
        if hold(st):
            return None
    except ProducerError:
        return None
    try:
        return notice(plan(cfg, st))
    except (ProducerError, OSError):
        return notice(None)


def blocked(st: dict) -> str | None:
    """Checked again at delete time: a redo since the offer, no DUYỆT 2, or no delivered package keeps every file."""
    if st.get("purged"):
        return f"đã xóa lúc {st['purged']['at']}"
    if st["state"] not in FINISHED or not st["approved"].get("assemble"):
        return f"chưa DUYỆT 2 hoặc đang làm lại (state={st['state']})"
    if not (DELIVER / st["id"]).is_dir():
        return f"không có {rel(DELIVER / st['id'])}/"
    return None


def shrink(a: Path, r: str) -> dict:
    """Best effort: an image PIL cannot shrink keeps its pixels, and the manifest says why."""
    from PIL import Image
    f = a / r
    before, tmp = f.stat().st_size, f.with_name(f".{f.name}.thumb")
    try:
        with Image.open(f) as im:
            fmt = im.format
            im.load()
            im.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
            im.save(tmp, fmt)
        os.replace(tmp, f)
    except (OSError, ValueError) as ex:
        tmp.unlink(missing_ok=True)
        return {"path": r, "before": before, "after": before, "error": str(ex)}
    return {"path": r, "before": before, "after": f.stat().st_size}


def execute(cfg: dict, st: dict, source: str, by: str | None, zp: str | None, p: dict) -> str:
    aid, a = st["id"], ASSETS / st["id"]
    doc = {"asset": aid, "at": now(), "source": source, "by": by, "assemble": st["approved"]["assemble"],
           "freed_bytes": p["bytes"], "zip": zp, "deleted": [{"path": r, "bytes": b} for r, b in p["delete"]],
           "deleted_other": [{"path": r, "bytes": b} for r, b in p["other"]], "thumbnails": []}
    write_atomic(a / MANIFEST, json.dumps(doc, ensure_ascii=False, indent=2))
    st["purged"] = {"at": doc["at"], "manifest": rel(a / MANIFEST), "freed_bytes": p["bytes"], "zip": zp}
    st.pop("keep_files", None)
    st.pop("purge_hold", None)
    save_st(st)
    (a / PENDING).unlink(missing_ok=True)
    for r, _ in p["delete"]:
        (a / r).unlink(missing_ok=True)
    push = ROOT / "board" / "push"
    for r, _ in p["other"]:
        f = ROOT / r
        f.unlink(missing_ok=True)
        for d in f.parents:
            if d == push or not d.is_relative_to(push) or any(d.iterdir()):
                break
            d.rmdir()
    for top, dirs, names in os.walk(a, topdown=False):
        if Path(top) != a and not os.listdir(top):
            os.rmdir(top)
    th = doc["thumbnails"] = [shrink(a, r) for r in p["thumbs"]]
    freed = doc["freed_bytes"] = st["purged"]["freed_bytes"] = p["bytes"] + sum(t["before"] - t["after"] for t in th)
    write_atomic(a / MANIFEST, json.dumps(doc, ensure_ascii=False, indent=2))
    save_st(st)
    ledger(f"{aid} · đã xóa D40 ({source}): {count(p)} file, thu nhỏ {len(th)} ảnh, giải phóng {size(freed)}"
           + (f" · by: {by}" if by else "") + (f" · nén {zp}" if zp else ""))
    return (f"[{aid}] đã xóa {count(p)} file, thu nhỏ {len(th)} ảnh, giải phóng {size(freed)}. "
            f"Manifest: {rel(a / MANIFEST)}")


def on_approve(cfg: dict, st: dict, zip_path: str | None, report_ok: bool) -> str:
    """D40.1: the user's DUYỆT 2 deletes here, after deliver/<id>/ and the run report exist. Whatever keeps the files
    comes back as one line that names the way to delete later, a broken policy.yaml included. The approval is already
    saved and stays; D29.5 checks the asset again here before it deletes."""
    aid = st["id"]
    later = f"Xóa sau: `purge {aid} --by \"<nguyên văn>\"`."
    try:
        why = hold(st, report_ok) or (("blocked", w) if (w := blocked(st)) else None)
    except ProducerError as ex:
        why = ("policy", str(ex))
    st.pop("keep_files", None)
    st.pop("purge_hold", None)
    if why:
        if why[0] == "ab":
            st["purge_hold"] = "ab"
        save_st(st)
        ledger(f"{aid} · giữ file sau DUYỆT 2: {why[1]}")
        return f"Giữ file, không xóa: {why[1]}. {later}"
    try:
        p, zp = prepare(cfg, st, zip_path)
    except (ProducerError, OSError) as ex:
        save_st(st)
        return f"Chưa xóa, file giữ nguyên: {ex}. {later}"
    try:
        return f"{notice(p)}\n{execute(cfg, st, 'approve', None, zp, p)}"
    except (ProducerError, OSError) as ex:
        return f"Xóa dở dang: {ex}. Xem {rel(ASSETS / aid / MANIFEST)}"


def on_next(a) -> list[str]:
    """Lines for `P next`: a v0.7 `purge-pending.json` is never run; an A/B asset still waits for its pair result; an
    asset at DUYỆT 2 shows what the approval would delete, for the Producer to tell the user. A failure never stops
    `P next`."""
    out = []
    for p in sorted(ASSETS.glob(f"*/{PENDING}")) if ASSETS.is_dir() else []:
        aid = p.parent.name
        out.append(f"[{aid}] còn lệnh xóa cũ (v0.7), script không tự chạy: `purge {aid} --by \"<nguyên văn>\"` để xóa, "
                   f"`keep {aid}` để giữ")
    for st in all_status():
        aid = st["id"]
        try:
            if st.get("purge_hold") == "ab" and not st.get("purged"):
                out.append(f"[{aid}] chờ xóa sau DUYỆT 2: {wait}" if (wait := ab_wait(aid)) else
                           f"[{aid}] đã có kết quả so A/B: `purge {aid} --by \"<nguyên văn>\"` để xóa, `keep {aid}` để giữ")
            elif st.get("state") == "waiting_human" and st.get("stage") == "assemble" and not hold(st):
                out.append(f"[{aid}] DUYỆT 2: {notice(plan(load_cfg(), st))}")
        except Exception as ex:  # noqa: BLE001 — the hook must still print the asset list
            out.append(f"[{aid}] chưa tính được việc xóa: {ex}")
    return out


def tree_size(d: Path) -> int:
    return sum(f.lstat().st_size for f in files(d)) if d.is_dir() else 0


def disk_warning() -> str | None:
    try:
        lim = policy.load().get("disk_warn_gb", policy.DISK_WARN_GB)
    except ProducerError as ex:
        return f"LỖI: {ex}"
    total = tree_size(ROOT)
    if total <= lim * GB:
        return None
    return f"⚠ {rel(ROOT)}/ dùng {size(total)}, vượt disk_warn_gb {lim} GB → `disk` để xem chỗ lớn"


def keep(a):
    """Before DUYỆT 2: this approval deletes nothing. Also cancels a v0.7 pending deletion, and the A/B reminder."""
    st = load_st(a.id)
    pend, by = ASSETS / a.id / PENDING, (f" · by: {a.by}" if a.by else "")
    if pend.is_file():
        pend.unlink()
        ledger(f"{a.id} · giữ file, hủy lệnh xóa cũ{by}")
        print(f"{a.id}: đã hủy lệnh xóa cũ; mọi file giữ nguyên")
    elif st.get("purge_hold"):
        st.pop("purge_hold")
        save_st(st)
        ledger(f"{a.id} · giữ file, bỏ nhắc xóa sau khi so A/B{by}")
        print(f"{a.id}: không nhắc xóa nữa; mọi file giữ nguyên")
    elif st.get("purged"):
        die(f"{a.id}: đã xóa lúc {st['purged']['at']}")
    elif st["state"] in FINISHED:
        die(f"{a.id}: đã DUYỆT 2, không có lệnh xóa nào đang chờ; mọi file còn nguyên")
    else:
        st["keep_files"] = now()
        save_st(st)
        ledger(f"{a.id} · giữ file: lần DUYỆT 2 tới không xóa{by}")
        print(f"{a.id}: lần DUYỆT 2 tới sẽ không xóa file")


def purge(a):
    st = load_st(a.id)
    if why := ab_wait(a.id) or blocked(st):
        die(f"{a.id}: không xóa: {why}")
    cfg = load_cfg()
    p, zp = prepare(cfg, st, a.zip)
    print(f"{notice(p)}\n{execute(cfg, st, 'purge', a.by, zp, p)}")


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
    lim = policy.load().get("disk_warn_gb", policy.DISK_WARN_GB)
    out = [f"{rel(ROOT)}/: {size(sum(by_type.values()))} · ngưỡng disk_warn_gb {lim} GB"]
    for head, d in (("Theo asset", by_asset), ("Theo bước", by_step), ("Theo loại file", by_type)):
        out += [f"{head}:", *(f"  {k}: {size(v)}" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0])))]
    print("\n".join(out))
