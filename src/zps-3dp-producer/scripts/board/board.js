const MODEL_VIEWER_VERSION = "3.5.0";
const MODEL_VIEWER_URL = `https://cdn.jsdelivr.net/npm/@google/model-viewer@${MODEL_VIEWER_VERSION}/dist/model-viewer.min.js`;
const SWIPE_PX = 50, MAX_ZOOM = 6, TAP_ZOOM = 2.5, DOUBLE_TAP_MS = 300;
const ACTIONS = [["Duyệt", "approve"], ["Cần sửa", "redo"], ["Ghi chú", "note"]];
const CSS = `
:root{--bg:#f6f6f4;--card:#fff;--fg:#1d1d1f;--muted:#777;--line:#ddd;--accent:#2f6fde;--warn:#e3a008;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#151517;--card:#1f1f22;--fg:#eee;--muted:#999;--line:#333;--accent:#6a9bff;--warn:#f0b429}}
body{margin:0;padding:12px;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 auto 12px;max-width:960px}
.card.wait{border-color:var(--warn)}
h2{font-size:15px;margin:0 0 8px}
.sheet{width:100%;max-height:70vh;object-fit:contain;background:#888;border-radius:8px;cursor:zoom-in;display:block}
.thumbs{display:flex;gap:6px;overflow-x:auto;margin:8px 0}
.thumbs img{height:84px;border-radius:6px;border:1px solid var(--line);background:#888;cursor:zoom-in}
.tag{display:inline-block;padding:1px 8px;border-radius:99px;border:1px solid var(--warn);color:var(--warn);font-weight:600;margin-right:6px}
.muted{color:var(--muted)}
p{margin:4px 0}
ul{margin:4px 0;padding-left:18px}
summary{cursor:pointer}
li details:not([open])>summary{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fields{margin:2px 0 6px;color:var(--muted)}
textarea{width:100%;box-sizing:border-box;margin-top:8px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px}
.row{display:flex;gap:8px;margin-top:6px;flex-wrap:wrap}
button{border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:8px 16px;cursor:pointer;font:inherit}
button.ok{background:var(--accent);color:#fff;border-color:var(--accent)}
.msg{margin-top:6px;font-weight:600}
#ov{position:fixed;inset:0;z-index:9;background:#000;display:none;touch-action:none;overflow:hidden}
#ov.on{display:block}
#ov .stage{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}
#ov img{max-width:100%;max-height:100%;transform-origin:center;user-select:none;-webkit-user-drag:none}
#ov model-viewer{width:100%;height:100%}
#ov button{position:absolute;z-index:2;background:#0008;color:#fff;border-color:#fff4;font-size:22px;padding:6px 14px}
#ov .x{top:10px;right:10px}#ov .l{left:10px;top:50%}#ov .r{right:10px;top:50%}
#ov .cap{position:absolute;bottom:10px;left:0;right:0;text-align:center;color:#fff;font-size:12px}
`;

const $ = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.flat().filter(k => k != null));
  return e;
};
const msgs = {};

function overlay() {
  const ov = $("div", { id: "ov" });
  const stage = $("div", { className: "stage" });
  const cap = $("div", { className: "cap" });
  const go = d => show((state.i + d + state.items.length) % state.items.length);
  const btn = (cls, txt, fn) => $("button", { className: cls, textContent: txt, onclick: fn });
  ov.append(stage, btn("x", "×", close), btn("l", "‹", () => go(-1)), btn("r", "›", () => go(1)), cap);
  const state = { items: [], i: 0, s: 1, x: 0, y: 0, img: null };
  const ptr = new Map();
  let pinch = null, lastTap = 0, moved = 0, start = [0, 0];
  const paint = () => state.img && (state.img.style.transform = `translate(${state.x}px,${state.y}px) scale(${state.s})`);
  const dist = () => { const [a, b] = [...ptr.values()]; return Math.hypot(a[0] - b[0], a[1] - b[1]); };
  function show(i) {
    state.i = i; state.s = 1; state.x = state.y = 0;
    const it = state.items[i];
    stage.replaceChildren();
    state.img = null;
    if (it.model) stage.append($("model-viewer", { src: it.u, cameraControls: true, autoRotate: true }));
    else stage.append(state.img = $("img", { src: it.u, draggable: false }));
    cap.textContent = `${i + 1}/${state.items.length} · ${it.n}`;
  }
  function close() { ov.classList.remove("on"); stage.replaceChildren(); }
  stage.addEventListener("pointerdown", e => {
    if (!state.img) return;
    stage.setPointerCapture(e.pointerId);
    ptr.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptr.size === 1) { moved = 0; start = [e.clientX, e.clientY]; }
    if (ptr.size === 2) pinch = { d: dist(), s: state.s };
  });
  stage.addEventListener("pointermove", e => {
    const p = ptr.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p[0], dy = e.clientY - p[1];
    ptr.set(e.pointerId, [e.clientX, e.clientY]);
    moved += Math.abs(dx) + Math.abs(dy);
    if (ptr.size === 2 && pinch) state.s = Math.min(MAX_ZOOM, Math.max(1, pinch.s * dist() / pinch.d));
    else if (state.s > 1) { state.x += dx; state.y += dy; }
    paint();
  });
  const up = e => {
    const p = ptr.get(e.pointerId);
    if (!p) return;
    ptr.delete(e.pointerId);
    pinch = null;
    if (state.s <= 1.01) { state.s = 1; state.x = state.y = 0; paint(); }
    if (ptr.size || e.type === "pointercancel") return;
    const r = stage.getBoundingClientRect(), now = e.timeStamp;
    if (moved < 10 && now - lastTap < DOUBLE_TAP_MS) {
      lastTap = 0;
      state.s = state.s > 1 ? 1 : TAP_ZOOM;
      state.x = state.s > 1 ? -(e.clientX - r.left - r.width / 2) * (state.s - 1) : 0;
      state.y = state.s > 1 ? -(e.clientY - r.top - r.height / 2) * (state.s - 1) : 0;
      paint();
    } else if (moved < 10) lastTap = now;
    else if (state.s === 1) {
      const dx = e.clientX - start[0], dy = e.clientY - start[1];
      if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    }
  };
  stage.addEventListener("pointerup", up);
  stage.addEventListener("pointercancel", up);
  document.addEventListener("keydown", e => {
    if (!ov.classList.contains("on")) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
  });
  document.body.append(ov);
  return (items, i) => { state.items = items; ov.classList.add("on"); show(i); };
}

function findingList(list) {
  return $("ul", {}, list.map(f => $("li", {}, $("details", {}, $("summary", { textContent: f.line }),
    $("div", { className: "fields", textContent: Object.entries(f.fields).map(([k, v]) => `${k}: ${v}`).join(" | ") })))));
}

function card(a, view) {
  const items = [...a.images, ...(a.glb ? [{ u: a.glb, n: "model 3D", model: true }] : [])];
  const form = $("textarea", { rows: 2, placeholder: "Ghi chú chung" });
  const out = $("div", { className: "msg", textContent: msgs[a.id] || "" });
  const send = async action => {
    const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: a.id, action, text: form.value, step: a.step }) });
    msgs[a.id] = (await r.json()).message;
    load();
  };
  const thumb = (im, i) => $("img", { src: im.u, alt: im.n, loading: "lazy", onclick: () => view(items, i) });
  return $("section", { className: "card" + (a.waiting ? " wait" : "") },
    $("h2", { textContent: a.header }),
    a.sheet ? $("img", { className: "sheet", src: a.sheet, alt: "sheet", onclick: () => view(items, 0) }) : null,
    $("div", { className: "thumbs" }, a.images.map(thumb), a.glb ? $("button", { textContent: "Model 3D", onclick: () => view(items, items.length - 1) }) : null),
    $("p", {}, a.label ? $("span", { className: "tag", textContent: a.label }) : null,
      a.stale ? $("span", { className: "tag", textContent: a.stale }) : null,
      a.decided ? $("span", { className: "muted", textContent: `đã có quyết định lúc ${a.decided}` }) : null),
    ...a.summary.map(l => $("p", { textContent: l })),
    a.more.length ? $("details", {}, $("summary", { textContent: "Xem thêm", className: "muted" }), ...a.more.map(l => $("p", { textContent: l }))) : null,
    a.reason ? $("p", { className: "muted", textContent: a.reason }) : null,
    a.open.length ? findingList(a.open) : null,
    a.preference.length ? $("details", {}, $("summary", { textContent: `Khẩu vị (${a.preference.length})`, className: "muted" }), findingList(a.preference)) : null,
    form,
    $("div", { className: "row" }, ACTIONS.map(([t, act]) => $("button", { textContent: t, className: act === "approve" ? "ok" : "", onclick: () => send(act) }))),
    out);
}

let view;
async function load() {
  const p = await (await fetch("/api/board")).json();
  document.title = `Review · ${p.project}`;
  if (p.assets.some(a => a.glb) && !document.getElementById("mv"))
    document.head.append($("script", { id: "mv", type: "module", src: MODEL_VIEWER_URL }));
  document.getElementById("app").replaceChildren(...p.assets.map(a => card(a, view)));
}

document.head.append($("style", { textContent: CSS }));
view = overlay();
load();
