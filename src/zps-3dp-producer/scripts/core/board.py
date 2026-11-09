"""Dashboard and the local review board: one JSON payload, one shell, one JS renderer (docs/review-board.md §2, §3, §7)."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from . import findings
from .contract import FIELDS
from .loop import next_action, shown
from .state import FINISHED, IMAGE_EXT, ROOT, SKILL_DIR, all_status, load_cfg, locked, now, sort_key, vdir, write_atomic

BOARD_DIR = SKILL_DIR / "scripts" / "board"
SUMMARY_FILE = {"blockout": "blockout.md", "views_front": "report/VIEWS.md", "views_rest": "report/VIEWS.md",
                "model": "model.md", "texture": "texture/notes.md", "assemble": "README.md"}
SHEET = "game_cam.png"
SUMMARY_LINES = 3
LINE_FIELDS = ("region", "evidence", "repair")
HOSTS = ("127.0.0.1", "localhost")


def build_outputs(_cfg: dict):
    sts = sorted(all_status(), key=sort_key)
    write_atomic(ROOT / "dashboard.md", render_dashboard(sts))


def render_dashboard(sts: list[dict]) -> str:
    active = [s for s in sts if s.get("state") not in FINISHED]
    out = [f"# Dashboard — tự sinh {now()}, đừng sửa tay", "",
           "| Asset | Bước | State | Phiên bản | Rubric gần nhất | Deadline | Việc tiếp |",
           "|---|---|---|---|---|---|---|"]
    for s in active:
        vers = " ".join(f"{k}:v{v}" for k, v in s.get("versions", {}).items()) or "-"
        out.append(f"| {s['id']} | {s.get('stage')} | {s.get('state')} | {vers} | {s.get('last_rubric') or '-'} "
                   f"| {s.get('deadline') or '-'} | {next_action(s)} |")
    done = [s["id"] for s in sts if s.get("state") in FINISHED]
    if done:
        out += ["", f"Done ({len(done)}): " + ", ".join(done)]
    return "\n".join(out) + "\n"


def _url(root: str, base: Path, f: Path) -> str:
    return f"/{root}/" + quote(f.relative_to(base).as_posix())


def finding_view(fid: str, f: dict) -> dict:
    head = " — ".join(f[k] for k in LINE_FIELDS if f.get(k))
    acc = f" — acceptance: {f['acceptance']}" if f.get("acceptance") else ""
    return {"line": f"{fid} [{f['priority']}] {head}{acc}",
            "fields": {k: f[k] for k in FIELDS if k not in (*LINE_FIELDS, "acceptance") and f.get(k)}}


def summary_lines(path: Path) -> list[str]:
    return [l.rstrip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.is_file() else []


def images_of(d: Path | None) -> list[Path]:
    return sorted(p for p in d.rglob("*") if p.suffix.lower() in IMAGE_EXT) if d and d.is_dir() else []


def asset_view(cfg: dict, st: dict) -> dict:
    aid, step = st["id"], st["stage"]
    n = shown(st, step)
    approved = cfg["paths"]["approved"]
    final = vdir(aid, step, n) / "final" if n else None
    pics = sorted(images_of(final), key=lambda p: p.name != SHEET)
    images = [{"u": _url("p", ROOT, p), "n": p.relative_to(final).as_posix()} for p in pics]
    cd = Path(st["concept_dir"]) if st.get("concept_dir") else None
    if cd and approved and cd.resolve().is_relative_to(approved.resolve()):
        images += [{"u": _url("a", approved.resolve(), p.resolve()), "n": "concept/" + p.relative_to(cd).as_posix()}
                   for p in images_of(cd)]
    glb = next(iter(sorted(final.glob("*.glb"))), None) if final and final.is_dir() else None
    lines = summary_lines(final / SUMMARY_FILE[step]) if final and step in SUMMARY_FILE else []
    op = findings.open_of(findings.load(aid, step, n))
    waiting = st["state"] == "waiting_human"
    note = (st.get("note") or "").splitlines()
    return {
        "id": aid, "step": step, "version": n, "waiting": waiting,
        "header": f"{st.get('title', aid)} · {step}{f' v{n}' if n else ''} · {'chờ anh duyệt' if waiting else st['state']}",
        "sheet": images[0]["u"] if pics and pics[0].name == SHEET else None,
        "images": images,
        "glb": _url("p", ROOT, glb) if glb else None,
        "summary": lines[:SUMMARY_LINES], "more": lines[SUMMARY_LINES:],
        "reason": note[0] if note else "",
        "label": st.get("label") or "",
        "stale": f"dựng từ {src} — cũ" if (src := (st.get("stale") or {}).get(f"{step} v{n}")) else None,
        "decided": (st.get("decisions") or {}).get(f"{step} v{n}", {}).get("at"),
        "open": [finding_view(i, f) for i, f in op.items() if f["priority"] != "preference"],
        "preference": [finding_view(i, f) for i, f in op.items() if f["priority"] == "preference"],
    }


def board_payload(cfg: dict) -> dict:
    sts = sorted(all_status(), key=lambda s: (s.get("state") != "waiting_human", *sort_key(s)))
    return {"project": cfg.get("project", {}).get("name", "Producer"),
            "assets": [asset_view(cfg, s) for s in sts if not s.get("broken")]}


def safe_file(cfg: dict, url_path: str) -> Path | None:
    """`/p/<path under the production root>` or `/a/<path under _approved/>`; anything else is None."""
    key, _, rest = unquote(url_path).lstrip("/").partition("/")
    base = {"p": ROOT, "a": cfg["paths"]["approved"]}.get(key)
    if base is None or not rest or rest.startswith("/") or "\0" in rest or ".." in PurePosixPath(rest).parts:
        return None
    f = (base / rest).resolve()
    return f if f.is_file() and f.is_relative_to(base.resolve()) else None


def dashboard():
    build_outputs(load_cfg())
    print(f"OK: {ROOT / 'dashboard.md'}")


def make_server(port: int):
    import mimetypes
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from .loop import human_action

    class Handler(BaseHTTPRequestHandler):
        def send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def local(self) -> bool:
            if self.headers.get("Host", "").rsplit(":", 1)[0] in HOSTS:
                return True
            self.send_error(403)
            return False

        def do_GET(self):
            if not self.local():
                return
            path = urlsplit(self.path).path
            if path == "/api/board":
                return self.send(200, json.dumps(board_payload(load_cfg()), ensure_ascii=False).encode(),
                                 "application/json; charset=utf-8")
            if path in ("/", "/index.html", "/board.js"):
                name = "board.js" if path == "/board.js" else "index.html"
                return self.send(200, (BOARD_DIR / name).read_bytes(), mimetypes.guess_type(name)[0] + "; charset=utf-8")
            f = safe_file(load_cfg(), path)
            if f is None:
                return self.send_error(404)
            self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

        def do_POST(self):
            if not self.local():
                return
            if urlsplit(self.path).path != "/api/feedback":
                return self.send_error(404)
            if self.headers.get_content_type() != "application/json":
                return self.send_error(403)
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                with locked():
                    msg, code = human_action(data["id"], data["action"], data.get("text", ""), data.get("step")), 200
            except Exception as ex:  # noqa: BLE001
                msg, code = f"Lỗi: {ex}", 400
            self.send(code, json.dumps({"message": msg}, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int):
    with locked():
        build_outputs(load_cfg())
    srv = make_server(port)
    print(f"Review page: http://127.0.0.1:{port}  (Ctrl+C để dừng)")
    srv.serve_forever()


