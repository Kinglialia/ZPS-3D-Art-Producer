const MODEL_VIEWER_VERSION = "3.5.0";
const MODEL_VIEWER_URL = `https://cdn.jsdelivr.net/npm/@google/model-viewer@${MODEL_VIEWER_VERSION}/dist/model-viewer.min.js`;
const SWIPE_PX = 50, MAX_ZOOM = 6, TAP_ZOOM = 2.5, DOUBLE_TAP_MS = 300, MIN_MARK = 0.01, STEP_MARK = 0.003, MAX_POINTS = 500;
const ACTIONS = [["Duyệt", "approve"], ["Cần sửa", "redo"], ["Ghi chú", "note"]];
const SHAPES = [["circle", "○", "Vòng tròn"], ["rect", "▭", "Chữ nhật"], ["free", "✎", "Nét tự do"]];
const LIGHT = "--bg:#f6f6f4;--card:#fff;--fg:#1d1d1f;--muted:#6b6b6b;--line:#ddd;--accent:#2f6fde;--warn:#b7791f;color-scheme:light";
const DARK = "--bg:#151517;--card:#1f1f22;--fg:#eee;--muted:#9a9a9a;--line:#333;--accent:#6a9bff;--warn:#f0b429;color-scheme:dark";
const CSS = `
:root{${LIGHT}}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){${DARK}}}
:root[data-theme=dark]{${DARK}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif}
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
textarea,.mrow input{width:100%;box-sizing:border-box;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px;font:16px/1.3 system-ui}
textarea{margin-top:8px}
.row{display:flex;gap:8px;margin-top:6px;flex-wrap:wrap}
button{border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:8px 16px;cursor:pointer;font:inherit}
button.ok{background:var(--accent);color:#fff;border-color:var(--accent)}
.msg{margin-top:6px;font-weight:600}
.marks{margin-top:8px}
.mrow{display:flex;gap:6px;align-items:center;margin:4px 0}
.mrow .num{background:#e61e1e;color:#fff;border:0;border-radius:99px;min-width:32px;padding:4px 8px}
.mrow .img{flex:none;max-width:35%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#ov{position:fixed;inset:0;z-index:9;background:#000;display:none;touch-action:none;overflow:hidden;color:#fff}
#ov.on{display:block}
#ov .stage{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}
#ov .box{position:relative;flex:none;transform-origin:center}
#ov .box img{display:block;width:100%;height:100%;user-select:none;-webkit-user-drag:none}
#ov svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
#ov .mk{fill:none;stroke:#ff3b30;stroke-width:3px;vector-effect:non-scaling-stroke}
#ov .labs{position:absolute;inset:0;pointer-events:none}
#ov .lab{position:absolute;transform:translate(-50%,-50%);pointer-events:auto;background:#e61e1e;border:0;border-radius:99px;min-width:26px;height:26px;padding:0 6px;font:600 13px/26px system-ui}
#ov .lab.sel{outline:2px solid #fff}
#ov model-viewer{width:100%;height:100%}
#ov button{background:#000a;color:#fff;border:1px solid #fff4;border-radius:8px;font:inherit;cursor:pointer}
#ov .nav{position:absolute;z-index:2;font-size:22px;padding:6px 14px;min-width:44px;min-height:44px}
#ov .x{top:10px;right:10px}#ov .l{left:10px;top:50%}#ov .r{right:10px;top:50%}
#ov .tools{position:absolute;top:10px;left:10px;z-index:2;display:flex;gap:6px}
#ov .tool{min-width:44px;min-height:44px;padding:6px 12px;font-size:16px}
#ov .tool.on{background:#e61e1e;border-color:#e61e1e}
#ov .bar{position:absolute;left:10px;right:10px;bottom:34px;z-index:2;display:none;gap:6px;align-items:center;background:#000c;padding:8px;border-radius:10px}
#ov .bar.on{display:flex}
#ov .bar input{flex:1;min-width:0;font:16px system-ui;padding:8px;border-radius:6px;border:1px solid #fff4;background:#111;color:#fff}
#ov .bar button{padding:8px 12px}
#ov .cap{position:absolute;bottom:10px;left:0;right:0;text-align:center;font-size:12px;pointer-events:none}
`;

const $ = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.flat().filter(k => k != null));
  return e;
};
const svgEl = (tag, attrs) => {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
};
const unit = v => Math.round(Math.min(1, Math.max(0, v)) * 1e4) / 1e4;
const msgs = {}, marks = {}, drafts = {};
let transport = { load: null, send: null }, last = null, view;

async function modelURL(it) {
  if (it.json) return modelURL({ u: "data:model/gltf-binary;base64," + (await (await fetch(it.u)).json()).base64 });
  if (it.u.startsWith("data:")) return URL.createObjectURL(await (await fetch(it.u)).blob());
  return it.u;
}

function overlay(onclose) {
  const ov = $("div", { id: "ov" });
  const stage = $("div", { className: "stage" });
  const tools = $("div", { className: "tools" });
  const bar = $("div", { className: "bar" });
  const cap = $("div", { className: "cap" });
  const S = { items: [], i: 0, s: 1, x: 0, y: 0, box: null, img: null, svg: null, labs: null, aid: null, can: false,
              mode: "view", shape: "rect", draft: null, sel: null };
  const ptr = new Map();
  let pinch = null, multi = false, lastTap = 0, moved = 0, start = [0, 0];
  const nav = (cls, txt, fn, label) => $("button", { className: "nav " + cls, textContent: txt, onclick: fn, ariaLabel: label });
  const go = d => show((S.i + d + S.items.length) % S.items.length);
  ov.append(stage, tools, bar, nav("x", "×", close, "Đóng"), nav("l", "‹", () => go(-1), "Ảnh trước"),
            nav("r", "›", () => go(1), "Ảnh sau"), cap);
  const list = () => marks[S.aid] || (marks[S.aid] = []);
  const mine = () => list().filter(m => m.image === S.items[S.i].n);
  const paint = () => S.box && (S.box.style.transform = `translate(${S.x}px,${S.y}px) scale(${S.s})`);
  const pts = () => [...ptr.values()];
  const dist = () => { const [a, b] = pts(); return Math.hypot(a[0] - b[0], a[1] - b[1]); };
  const mid = () => { const [a, b] = pts(); return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; };
  const at = e => { const r = S.box.getBoundingClientRect(); return [unit((e.clientX - r.left) / r.width), unit((e.clientY - r.top) / r.height)]; };
  function zoomAt(s, p, o) {
    const r = stage.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    S.s = Math.min(MAX_ZOOM, Math.max(1, s));
    S.x = p[0] - cx - (o.m[0] - cx - o.x) / o.s * S.s;
    S.y = p[1] - cy - (o.m[1] - cy - o.y) / o.s * S.s;
  }
  function fit() {
    if (!S.img || !S.img.naturalWidth) return;
    const r = stage.getBoundingClientRect(), k = Math.min(r.width / S.img.naturalWidth, r.height / S.img.naturalHeight);
    S.box.style.width = S.img.naturalWidth * k + "px";
    S.box.style.height = S.img.naturalHeight * k + "px";
  }
  function anchor(m) { return m.shape === "free" ? m.coords[0] : m.coords; }
  function drawMarks() {
    if (!S.svg) return;
    S.svg.replaceChildren(...[...mine(), ...(S.draft ? [S.draft] : [])].map(m => {
      const c = m.coords;
      if (m.shape === "free") return svgEl("polyline", { class: "mk", points: c.map(p => p.join(",")).join(" ") });
      if (m.shape === "rect") return svgEl("rect", { class: "mk", x: c[0], y: c[1], width: c[2] - c[0], height: c[3] - c[1] });
      return svgEl("ellipse", { class: "mk", cx: (c[0] + c[2]) / 2, cy: (c[1] + c[3]) / 2, rx: (c[2] - c[0]) / 2, ry: (c[3] - c[1]) / 2 });
    }));
    S.labs.replaceChildren(...mine().map(m => $("button", {
      className: "lab" + (S.sel === list().indexOf(m) ? " sel" : ""), textContent: m.n, ariaLabel: `Vùng ${m.n}`,
      style: `left:${anchor(m)[0] * 100}%;top:${anchor(m)[1] * 100}%`,
      onpointerdown: e => { e.stopPropagation(); select(list().indexOf(m)); } })));
  }
  function select(k) {
    S.sel = k;
    const m = k == null ? null : list()[k];
    bar.classList.toggle("on", !!m);
    bar.replaceChildren(...(m ? [
      $("b", { textContent: `Vùng ${m.n}` }),
      $("input", { value: m.note, placeholder: "Ghi chú ngắn", maxLength: 500, oninput: e => { m.note = e.target.value; } }),
      $("button", { textContent: "Xóa", onclick: () => { list().splice(k, 1); list().forEach((x, j) => { x.n = j + 1; }); select(null); } }),
      $("button", { textContent: "Xong", onclick: () => select(null) })] : []));
    drawMarks();
    if (m && !m.note) bar.querySelector("input").focus();
  }
  function drawTools() {
    const it = S.items[S.i];
    ov.classList.toggle("marking", S.mode === "mark");
    tools.replaceChildren(...(S.can && !it.model ? [
      $("button", { className: "tool" + (S.mode === "mark" ? " on" : ""), textContent: S.mode === "mark" ? "Thoát khoanh" : "Khoanh",
                    ariaLabel: S.mode === "mark" ? "Chế độ xem" : "Chế độ khoanh",
                    onclick: () => { S.mode = S.mode === "mark" ? "view" : "mark"; drawTools(); } }),
      ...(S.mode === "mark" ? SHAPES.map(([k, t, label]) => $("button", {
        className: "tool" + (S.shape === k ? " on" : ""), textContent: t, ariaLabel: label,
        onclick: () => { S.shape = k; drawTools(); } })) : [])] : []));
    cap.textContent = `${S.i + 1}/${S.items.length} · ${it.n}` + (S.mode === "mark" ? " · một ngón vẽ, hai ngón zoom" : "");
  }
  function show(i) {
    Object.assign(S, { i, s: 1, x: 0, y: 0, draft: null, img: null, box: null, svg: null, labs: null });
    const it = S.items[i];
    stage.replaceChildren();
    if (it.model) {
      const mv = $("model-viewer");
      mv.setAttribute("camera-controls", "");
      mv.setAttribute("auto-rotate", "");
      stage.append(mv);
      modelURL(it).then(u => { mv.src = u; }, () => { cap.textContent = "Không mở được model 3D"; });
    } else {
      S.img = $("img", { src: it.u, alt: it.n, draggable: false, onload: fit });
      S.svg = svgEl("svg", { viewBox: "0 0 1 1", preserveAspectRatio: "none" });
      S.labs = $("div", { className: "labs" });
      S.box = $("div", { className: "box" }, S.img, S.svg, S.labs);
      stage.append(S.box);
      if (S.img.complete) fit();
    }
    select(null);
    drawTools();
  }
  function finish(d) {
    const c = d.coords, xs = d.shape === "free" ? c.map(p => p[0]) : [], ys = d.shape === "free" ? c.map(p => p[1]) : [];
    const ok = d.shape === "free"
      ? c.length >= 2 && Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) > MIN_MARK
      : c[2] - c[0] > MIN_MARK && c[3] - c[1] > MIN_MARK;
    if (!ok) return;
    list().push({ n: list().length + 1, image: S.items[S.i].n, shape: d.shape, coords: c, note: "" });
    select(list().length - 1);
  }
  function grow(d, q) {
    if (d.shape !== "free") {
      d.coords = [Math.min(d.p0[0], q[0]), Math.min(d.p0[1], q[1]), Math.max(d.p0[0], q[0]), Math.max(d.p0[1], q[1])];
      return;
    }
    const l = d.coords[d.coords.length - 1];
    if (d.coords.length < MAX_POINTS && Math.hypot(q[0] - l[0], q[1] - l[1]) > STEP_MARK) d.coords.push(q);
  }
  function close() { ov.classList.remove("on"); stage.replaceChildren(); S.mode = "view"; select(null); onclose(); }
  stage.addEventListener("pointerdown", e => {
    if (!S.img) return;
    stage.setPointerCapture(e.pointerId);
    ptr.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptr.size === 1) {
      moved = 0; multi = false; start = [e.clientX, e.clientY];
      if (S.mode === "mark") { const p = at(e); S.draft = { shape: S.shape, p0: p, coords: S.shape === "free" ? [p] : [...p, ...p] }; }
    }
    if (ptr.size === 2) {
      multi = true; S.draft = null; drawMarks();
      pinch = { d: dist() || 1, s: S.s, x: S.x, y: S.y, m: mid() };
    }
  });
  stage.addEventListener("pointermove", e => {
    const p = ptr.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p[0], dy = e.clientY - p[1];
    ptr.set(e.pointerId, [e.clientX, e.clientY]);
    moved += Math.abs(dx) + Math.abs(dy);
    if (ptr.size === 2 && pinch) zoomAt(pinch.s * dist() / pinch.d, mid(), pinch);
    else if (S.draft) { grow(S.draft, at(e)); drawMarks(); return; }
    else if (S.s > 1) { S.x += dx; S.y += dy; }
    paint();
  });
  const up = e => {
    if (!ptr.delete(e.pointerId)) return;
    pinch = null;
    if (S.s <= 1.01) { S.s = 1; S.x = S.y = 0; paint(); }
    if (ptr.size) return;
    if (S.draft) { const d = S.draft; S.draft = null; if (e.type !== "pointercancel") finish(d); drawMarks(); return; }
    if (e.type === "pointercancel" || multi || S.mode === "mark") return;
    if (moved < 10 && e.timeStamp - lastTap < DOUBLE_TAP_MS) {
      lastTap = 0;
      const s = S.s > 1 ? 1 : TAP_ZOOM;
      if (s === 1) { S.s = 1; S.x = S.y = 0; } else zoomAt(s, [e.clientX, e.clientY], { s: 1, x: 0, y: 0, m: [e.clientX, e.clientY] });
      paint();
    } else if (moved < 10) lastTap = e.timeStamp;
    else if (S.s === 1) {
      const dx = e.clientX - start[0], dy = e.clientY - start[1];
      if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    }
  };
  stage.addEventListener("pointerup", up);
  stage.addEventListener("pointercancel", up);
  addEventListener("resize", fit);
  document.addEventListener("keydown", e => {
    if (!ov.classList.contains("on")) return;
    if (e.target.tagName === "INPUT") { if (e.key === "Enter" || e.key === "Escape") select(null); return; }
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
  });
  document.body.append(ov);
  return (items, i, o = {}) => {
    Object.assign(S, { items, aid: o.aid, can: !!o.can, mode: o.mode || "view" });
    ov.classList.add("on");
    show(i);
  };
}

function findingList(list) {
  return $("ul", {}, list.map(f => $("li", {}, $("details", {}, $("summary", { textContent: f.line }),
    $("div", { className: "fields", textContent: Object.entries(f.fields).map(([k, v]) => `${k}: ${v}`).join(" | ") })))));
}

function controls(a, items, open) {
  const L = marks[a.id] || [];
  const form = $("textarea", { rows: 2, placeholder: "Ghi chú chung", value: drafts[a.id] || "",
                               oninput: e => { drafts[a.id] = e.target.value; } });
  const out = $("div", { className: "msg", textContent: msgs[a.id] || "" });
  const where = a.redo_steps.length ? $("select", {}, a.redo_steps.map(s => $("option", { value: s, textContent: `Cần sửa ở ${s}` }))) : null;
  const acts = a.ask ? [[`Gọi Meshy thêm (${a.ask.price ?? "?"} credit)`, "approve"], ["VẼ MỚI", "paint"], ["Cần sửa", "redo"],
                        ["Ghi chú", "note"]] : ACTIONS;
  const send = async action => {
    const body = { id: a.id, action, text: form.value, step: action === "redo" && where ? where.value : a.step,
                   offer: a.key, regions: L.length ? L : null };
    out.textContent = "Đang gửi…";
    let r;
    try { r = await transport.send(body); } catch (ex) { r = { ok: false, message: `Lỗi: ${ex.message || ex}` }; }
    msgs[a.id] = r.message;
    if (r.ok) { delete marks[a.id]; delete drafts[a.id]; }
    reload();
  };
  const rows = L.map((m, k) => $("div", { className: "mrow" },
    $("button", { className: "num", textContent: m.n, ariaLabel: `Mở vùng ${m.n}`,
                  onclick: () => open(Math.max(0, items.findIndex(it => it.n === m.image)), "mark") }),
    $("span", { className: "muted img", textContent: m.image }),
    $("input", { value: m.note, placeholder: "ghi chú vùng", maxLength: 500, oninput: e => { m.note = e.target.value; } }),
    $("button", { textContent: "Xóa", onclick: () => { L.splice(k, 1); L.forEach((x, j) => { x.n = j + 1; }); render(last); } })));
  return [
    L.length ? $("div", { className: "marks" }, $("p", { className: "muted", textContent: `Vùng khoanh (${L.length}), gửi kèm nút bấm:` }), rows) : null,
    form,
    $("div", { className: "row" }, where, acts.map(([t, act]) => $("button", {
      textContent: t, className: act === "approve" ? "ok" : "", onclick: () => send(act) }))),
    out];
}

function card(a) {
  const items = [...a.images, ...(a.glb ? [{ u: a.glb, n: "model 3D", model: true, json: !!a.glb_json }] : [])];
  const can = !!transport.send;
  const open = (i, mode) => view(items, i, { aid: a.id, can, mode });
  const thumb = (im, i) => $("img", { src: im.u, alt: im.n, loading: "lazy", onclick: () => open(i) });
  return $("section", { className: "card" + (a.waiting ? " wait" : ""), id: "card-" + a.id },
    $("h2", { textContent: a.header }),
    a.sheet ? $("img", { className: "sheet", src: a.sheet, alt: "sheet", onclick: () => open(0) }) : null,
    $("div", { className: "thumbs" }, a.images.map(thumb),
      a.glb ? $("button", { textContent: "Model 3D", onclick: () => open(items.length - 1) }) : null),
    $("p", {}, a.label ? $("span", { className: "tag", textContent: a.label }) : null,
      a.stale ? $("span", { className: "tag", textContent: a.stale }) : null,
      a.decided ? $("span", { className: "muted", textContent: `đã có quyết định lúc ${a.decided}` }) : null),
    ...a.summary.map(l => $("p", { textContent: l })),
    a.more.length ? $("details", {}, $("summary", { textContent: "Xem thêm", className: "muted" }), ...a.more.map(l => $("p", { textContent: l }))) : null,
    a.reason ? $("p", { className: "muted", textContent: a.reason }) : null,
    a.open.length ? findingList(a.open) : null,
    a.preference.length ? $("details", {}, $("summary", { textContent: `Khẩu vị (${a.preference.length})`, className: "muted" }), findingList(a.preference)) : null,
    can ? controls(a, items, open) : null);
}

function render(p) {
  last = p;
  document.title = `Review · ${p.project}`;
  if (p.assets.some(a => a.glb) && !document.getElementById("mv"))
    document.head.append($("script", { id: "mv", type: "module", src: MODEL_VIEWER_URL }));
  document.getElementById("app").replaceChildren(...(p.assets.length ? p.assets.map(card)
    : [$("p", { className: "muted", textContent: p.empty || "Không có asset nào chờ duyệt." })]));
}

async function reload() {
  try { render(await transport.load()); }
  catch (ex) { document.getElementById("app").replaceChildren($("p", { className: "msg", textContent: `Lỗi tải board: ${ex.message || ex}` })); }
}

const LIVE = {
  load: async () => (await fetch("/api/board")).json(),
  send: async body => {
    const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return { ok: r.ok, message: (await r.json()).message };
  },
};
const STATIC = { load: async () => JSON.parse(document.getElementById("board-data").textContent), send: null };

document.head.append($("style", { textContent: CSS }));
view = overlay(() => last && render(last));
window.Board = { render, start(t) { transport = t; return reload(); } };
({ live: () => Board.start(LIVE), static: () => Board.start(STATIC) })[(window.BOARD || {}).mode || "live"]?.();
