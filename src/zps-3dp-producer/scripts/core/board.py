"""Dashboard and local review page (base board until T7 replaces it)."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from urllib.parse import quote, unquote

from .hashes import concept_images
from .loop import next_action
from .state import IMAGE_EXT, PORT, ROOT, ProducerError, all_status, load_cfg, load_st, now, rel, sort_key, vdir

MODEL_VIEWER_JS = "https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js"


def build_outputs(cfg: dict):
    sts = sorted(all_status(), key=sort_key)
    (ROOT / "dashboard.md").write_text(render_dashboard(sts), encoding="utf-8")
    (ROOT / "review.html").write_text(render_review(cfg, sts), encoding="utf-8")


def render_dashboard(sts: list[dict]) -> str:
    active = [s for s in sts if s.get("state") != "done"]
    out = [f"# Dashboard — tự sinh {now()}, đừng sửa tay", "",
           "| Asset | Bước | State | Phiên bản | Rubric gần nhất | Deadline | Việc tiếp |",
           "|---|---|---|---|---|---|---|"]
    for s in active:
        vers = " ".join(f"{k}:v{v}" for k, v in s.get("versions", {}).items()) or "-"
        out.append(f"| {s['id']} | {s.get('stage')} | {s.get('state')} | {vers} | {s.get('last_rubric') or '-'} "
                   f"| {s.get('deadline') or '-'} | {next_action(s)} |")
    done = [s["id"] for s in sts if s.get("state") == "done"]
    if done:
        out += ["", f"Done ({len(done)}): " + ", ".join(done)]
    return "\n".join(out) + "\n"


def _url(p: Path) -> str:
    return quote(os.path.relpath(p, ROOT).replace(os.sep, "/"))


def render_review(cfg: dict, sts: list[dict]) -> str:
    e = html.escape
    cards = []
    for s in sts:
        aid = s["id"]
        blocks = []
        glb = None
        for step in cfg["steps"]:
            n = s.get("versions", {}).get(step["id"])
            if not n:
                continue
            imgs = []
            for v in range(n, max(0, n - 3), -1):
                fd = vdir(aid, step["id"], v) / "final"
                pics = sorted(p for p in fd.glob("*") if p.suffix.lower() in IMAGE_EXT) if fd.exists() else []
                appr = " ✓" if s.get("approved", {}).get(step["id"]) == v else ""
                thumbs = "".join(f'<a href="{_url(p)}" target="_blank"><img src="{_url(p)}" alt="{e(p.name)}"></a>' for p in pics)
                imgs.append(f'<div class="ver"><div class="vlabel">{e(step["id"])} v{v}{appr}</div>'
                            f'<div class="pics">{thumbs or "<span class=muted>chưa có preview</span>"}</div></div>')
                if v == n and fd.exists():  # glb của bản mới nhất, bước sau ghi đè bước trước
                    glb = next(iter(sorted(fd.glob("*.glb"))), glb)
            blocks.append("".join(imgs))
        if s.get("concept_dir"):
            cd = Path(s["concept_dir"])
            cpics = "".join(
                f'<a href="/_concept/{quote(aid)}/{quote(p.relative_to(cd).as_posix())}" target="_blank">'
                f'<img src="/_concept/{quote(aid)}/{quote(p.relative_to(cd).as_posix())}" alt="{e(p.name)}"></a>'
                for p in concept_images(cd)[:6])
            blocks.insert(0, f'<div class="ver"><div class="vlabel">concept đã duyệt</div><div class="pics">{cpics}</div></div>')
        viewer = (f'<model-viewer src="{_url(glb)}" camera-controls auto-rotate shadow-intensity="1"></model-viewer>'
                  if glb else "")
        steps_opt = "".join(f'<option value="{e(x["id"])}"{" selected" if x["id"] == s.get("stage") else ""}>{e(x["id"])}</option>'
                            for x in cfg["steps"])
        waiting = s.get("state") == "waiting_human"
        cards.append(f"""
<section class="card{' wait' if waiting else ''}{' done' if s.get('state') == 'done' else ''}" id="{e(aid)}">
  <header><h2>{e(s.get('title', aid))}</h2>
    <span class="badge s-{e(s.get('state', ''))}">{e(s.get('stage', ''))} · {e(s.get('state', ''))}</span></header>
  <p class="meta">{e(aid)} · deadline {e(s.get('deadline') or '-')} · rubric: {e(s.get('last_rubric') or '-')}</p>
  <p class="next">{e(next_action(s))}</p>
  <div class="body"><div class="vers">{''.join(blocks) or '<span class=muted>chưa có phiên bản</span>'}</div>{viewer}</div>
  <form class="fb" data-id="{e(aid)}">
    <textarea name="text" rows="2" placeholder="Feedback (ghi nguyên văn vào feedback.md)"></textarea>
    <div class="row"><label>bước <select name="step">{steps_opt}</select></label>
      <button name="action" value="approve">Duyệt</button>
      <button name="action" value="redo">Làm lại</button>
      <button name="action" value="note">Chỉ ghi chú</button></div>
  </form>
</section>""")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review — {e(cfg.get('project', {}).get('name', 'Producer'))}</title>
<script type="module" src="{MODEL_VIEWER_JS}"></script>
<style>
:root{{--bg:#f6f6f4;--card:#fff;--fg:#1d1d1f;--muted:#777;--line:#ddd;--accent:#2f6fde;--wait:#e3a008;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151517;--card:#1f1f22;--fg:#eee;--muted:#999;--line:#333;--accent:#6a9bff;--wait:#f0b429;color-scheme:dark}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif}}
h1{{font-size:18px;margin:0 0 4px}} .muted,.meta{{color:var(--muted)}} .meta{{margin:2px 0;font-size:12px}}
#warn{{display:none;background:var(--wait);color:#000;padding:8px 12px;border-radius:8px;margin:8px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}}
.card.wait{{border-color:var(--wait);box-shadow:0 0 0 2px var(--wait) inset}} .card.done{{opacity:.6}}
header{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} h2{{font-size:16px;margin:0}}
.badge{{font-size:12px;padding:2px 8px;border-radius:99px;border:1px solid var(--line)}}
.next{{margin:6px 0;font-weight:600}}
.body{{display:flex;gap:12px;flex-wrap:wrap}} .vers{{flex:1 1 420px;min-width:0}}
.ver{{margin:6px 0}} .vlabel{{font-size:12px;color:var(--muted)}}
.pics{{display:flex;gap:6px;overflow-x:auto}} .pics img{{height:120px;border-radius:6px;border:1px solid var(--line);background:#888}}
model-viewer{{flex:1 1 280px;height:280px;background:var(--bg);border-radius:8px}}
.fb textarea{{width:100%;box-sizing:border-box;margin-top:8px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px}}
.row{{display:flex;gap:8px;align-items:center;margin-top:6px;flex-wrap:wrap}}
button{{border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:5px 12px;cursor:pointer}}
button[value=approve]{{background:var(--accent);color:#fff;border-color:var(--accent)}}
</style></head><body>
<h1>Review — {e(cfg.get('project', {}).get('name', 'Producer'))}</h1>
<p class="meta">Sinh lúc {now()} · asset chờ duyệt có viền vàng</p>
<div id="warn">Đang mở dạng file nên không gửi được feedback. Chạy <code>producer.py serve</code> rồi mở http://127.0.0.1:{PORT}</div>
{''.join(cards) or '<p class=muted>Chưa có asset.</p>'}
<script>
const live = location.protocol.startsWith('http');
if (!live) document.getElementById('warn').style.display = 'block';
document.querySelectorAll('form.fb').forEach(f => f.addEventListener('submit', async ev => {{
  ev.preventDefault();
  if (!live) return;
  const body = {{id: f.dataset.id, action: ev.submitter.value, text: f.text.value, step: f.step.value}};
  const r = await fetch('/api/feedback', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body)}});
  const j = await r.json();
  alert(j.message);
  if (r.ok) location.reload();
}}));
</script></body></html>
"""


def dashboard():
    build_outputs(load_cfg())
    print(f"OK: {rel(ROOT / 'dashboard.md')}, {rel(ROOT / 'review.html')}")


def serve(port: int):
    import mimetypes
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    from .loop import human_action

    class ReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kw):
            super().__init__(*args, directory=str(ROOT), **kw)

        def do_GET(self):
            if self.path.startswith("/_concept/"):
                return self.send_concept()
            if self.path in ("/", "/index.html"):
                build_outputs(load_cfg())
                self.path = "/review.html"
            return super().do_GET()

        def send_concept(self):
            """Ảnh concept nằm ngoài production/, chỉ phục vụ file nằm trong concept_dir của asset."""
            try:
                _, _, aid, relpath = self.path.split("/", 3)
                base = Path(load_st(unquote(aid))["concept_dir"]).resolve()
                f = (base / unquote(relpath)).resolve()
                if base not in f.parents or not f.is_file():
                    raise ValueError
            except (ValueError, ProducerError, TypeError, KeyError):
                return self.send_error(404)
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/api/feedback":
                return self.send_error(404)
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                msg, code = human_action(data["id"], data["action"], data.get("text", ""), data.get("step")), 200
            except (ProducerError, KeyError, json.JSONDecodeError) as ex:
                msg, code = f"Lỗi: {ex}", 400
            body = json.dumps({"message": msg}, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    build_outputs(load_cfg())
    print(f"Review page: http://127.0.0.1:{port}  (Ctrl+C để dừng)")
    ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler).serve_forever()
