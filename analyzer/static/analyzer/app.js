/* Chess Coach — JavaScript sans dépendance externe.
   Apparence (thèmes), onglets, graphiques interactifs, échiquier animé, suivi des analyses. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const root = document.documentElement;
  const CLS_COLORS = {
    best: "var(--c-best)", good: "var(--c-good)", inaccuracy: "var(--c-inaccuracy)",
    mistake: "var(--c-mistake)", blunder: "var(--c-blunder)",
  };
  const CLS_GLYPH = { best: "★", good: "✓", inaccuracy: "?!", mistake: "?", blunder: "??" };
  const ERRORS = ["inaccuracy", "mistake", "blunder"];
  const EASE = "cubic-bezier(.2,.7,.2,1)";

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function fmt(n, d) { return n == null ? "—" : Number(n).toFixed(d == null ? 0 : d).replace(".", ","); }
  const store = {
    get(k, d) { try { const v = window.localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* stockage indisponible */ } },
  };
  function motionOK() {
    return root.getAttribute("data-motion") !== "off" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function icon(name) { return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`; }

  // ================================================================ apparence
  function effectiveDark() {
    const m = root.getAttribute("data-mode");
    if (m === "dark") return true;
    if (m === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function initAppearance() {
    const drawer = $("#appearance"), backdrop = $(".drawer-backdrop");
    let lastFocus = null;
    function sync() {
      $all("[data-set]").forEach(b => b.setAttribute("aria-checked", String(root.getAttribute("data-" + b.dataset.set) === b.dataset.value)));
      $all("[data-set-toggle]").forEach(i => { i.checked = root.getAttribute("data-" + i.dataset.setToggle) !== "off"; });
    }
    function set(key, value) {
      root.setAttribute("data-" + key, value);
      store.set("cc-" + key, value);
      sync();
      document.dispatchEvent(new CustomEvent("cc:theme", { detail: { key, value } }));
    }
    function open() {
      lastFocus = document.activeElement;
      drawer.hidden = false; backdrop.hidden = false;
      const first = $("[aria-checked='true']", drawer) || $("button", drawer);
      if (first) first.focus();
    }
    function close() {
      drawer.hidden = true; backdrop.hidden = true;
      if (lastFocus) lastFocus.focus();
    }
    $all("[data-open-appearance]").forEach(b => b.addEventListener("click", open));
    $all("[data-close-appearance]").forEach(b => b.addEventListener("click", close));
    document.addEventListener("keydown", ev => { if (ev.key === "Escape" && !drawer.hidden) close(); });
    $all("[data-set]").forEach(b => b.addEventListener("click", () => set(b.dataset.set, b.dataset.value)));
    $all("[data-set-toggle]").forEach(i => i.addEventListener("change", () => set(i.dataset.setToggle, i.checked ? "on" : "off")));
    $all("[data-mode-toggle]").forEach(b => b.addEventListener("click", () => set("mode", effectiveDark() ? "light" : "dark")));
    sync();
  }

  // ================================================================ éléments communs
  function initCommon() {
    $all(".toast").forEach(t => {
      const btn = $("[data-dismiss]", t);
      const hide = () => { t.style.transition = "opacity .3s, transform .3s"; t.style.opacity = "0"; t.style.transform = "translateY(-4px)"; setTimeout(() => t.remove(), 300); };
      if (btn) btn.addEventListener("click", hide);
      if (!t.classList.contains("toast-error")) setTimeout(hide, 8000);
    });
    $all("[data-open-dialog]").forEach(b => b.addEventListener("click", () => {
      const d = document.getElementById(b.dataset.openDialog);
      if (d && d.showModal) d.showModal();
    }));
    $all("dialog").forEach(d => {
      d.addEventListener("click", ev => { if (ev.target === d) d.close(); });
      $all("[data-close-dialog]", d).forEach(b => b.addEventListener("click", () => d.close()));
    });
  }

  // ================================================================ onglets
  function tabs(name, opts) {
    opts = opts || {};
    const bar = $(`[data-tabs="${name}"]`);
    if (!bar) return null;
    const scope = opts.scope || document;
    const tabEls = $all("[data-tab]", bar);
    const ids = tabEls.map(t => t.dataset.tab);
    const panels = $all("[data-panel]", scope).filter(p => ids.includes(p.dataset.panel));
    let current = null;
    function activate(id, how) {
      if (!ids.includes(id)) id = ids[0];
      current = id;
      tabEls.forEach(t => {
        const on = t.dataset.tab === id;
        t.setAttribute("aria-selected", String(on));
        t.classList.toggle("active", on);
        t.tabIndex = on ? 0 : -1;
      });
      panels.forEach(p => {
        const on = p.dataset.panel === id;
        if (opts.classMode) p.classList.toggle("is-active", on); else p.hidden = !on;
      });
      if (opts.onChange) opts.onChange(id, how);
    }
    tabEls.forEach(t => t.addEventListener("click", ev => {
      ev.preventDefault();
      activate(t.dataset.tab, "click");
      if (opts.hash) history.replaceState(null, "", "#" + t.dataset.tab);
    }));
    bar.addEventListener("keydown", ev => {
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      const i = ids.indexOf(current), j = (i + (ev.key === "ArrowRight" ? 1 : ids.length - 1)) % ids.length;
      tabEls[j].focus(); tabEls[j].click(); ev.preventDefault();
    });
    return { activate, ids, get current() { return current; } };
  }

  // ================================================================ accueil
  function initHome() {
    const card = $(".add-card");
    if (card) tabs("add", { scope: card });
    $all("[data-dropzone]").forEach(dz => {
      const input = $("input[type=file]", dz), label = $(".dz-file", dz), text = $(".dz-text", dz);
      function show() {
        const f = input.files && input.files[0];
        if (f) { label.textContent = f.name; label.hidden = false; text.hidden = true; }
      }
      input.addEventListener("change", show);
      ["dragenter", "dragover"].forEach(e => dz.addEventListener(e, ev => { ev.preventDefault(); dz.classList.add("dragover"); }));
      ["dragleave", "drop"].forEach(e => dz.addEventListener(e, () => dz.classList.remove("dragover")));
      dz.addEventListener("drop", ev => {
        ev.preventDefault();
        if (ev.dataTransfer && ev.dataTransfer.files.length) { input.files = ev.dataTransfer.files; show(); }
      });
    });
  }

  // ================================================================ suivi des tâches
  function poll(url, onData, intervalMs) {
    let stopped = false;
    async function tick() {
      if (stopped) return;
      try {
        const r = await fetch(url, { headers: { "Accept": "application/json" } });
        if (r.ok && onData(await r.json()) === false) { stopped = true; return; }
      } catch (e) { /* serveur momentanément indisponible */ }
      setTimeout(tick, intervalMs || 3000);
    }
    setTimeout(tick, intervalMs || 3000);
  }

  function initJobPanel() {
    const panel = $("#job-panel");
    if (!panel || !panel.dataset.running) return;
    let lastDone = null;
    poll(panel.dataset.statusUrl, function (d) {
      const bar = $("#job-bar"); if (bar) bar.style.width = d.pct + "%";
      const cnt = $("#job-count"); if (cnt) cnt.textContent = d.done + " / " + d.total + " parties analysées";
      const msg = $("#job-message"); if (msg && d.message) { msg.textContent = d.message; msg.hidden = false; }
      const sm = $("#sync-message"); if (sm && d.sync_message) sm.textContent = d.sync_message;
      if (!d.analysis_running && !d.sync_running) { location.reload(); return false; }
      // Recharge de temps en temps pour rafraîchir le tableau de bord pendant l'analyse
      if (lastDone !== null && d.done - lastDone >= 25) { location.reload(); return false; }
      if (lastDone === null) lastDone = d.done;
    });
  }

  function initGameJob() {
    const el = $("#game-job");
    if (!el || !el.dataset.running) return;
    poll(el.dataset.statusUrl, function (d) {
      if (!d.running) { location.reload(); return false; }
    }, 2000);
  }

  // ================================================================ liste des parties
  function initGameFilters() {
    const rows = $all("#games-table tbody tr[data-q]");
    const q = $("#f-q"), color = $("#f-color"), result = $("#f-result"), status = $("#f-status"), bl = $("#f-blunder");
    if (!q) return;
    function apply() {
      const text = q.value.trim().toLowerCase();
      let n = 0;
      rows.forEach(r => {
        let ok = (!text || r.dataset.q.includes(text))
          && (!color.value || r.dataset.color === color.value)
          && (!result.value || r.dataset.result === result.value)
          && (!status.value || r.dataset.status === status.value);
        if (ok && bl.value !== "") {
          const b = r.dataset.blunders === "" ? null : parseInt(r.dataset.blunders, 10);
          ok = b !== null && (bl.value === "1" ? b > 0 : b === 0);
        }
        r.hidden = !ok;
        if (ok) n++;
      });
      $("#f-count").textContent = n + " partie" + (n > 1 ? "s" : "");
      const empty = $("#f-empty"); if (empty) empty.hidden = n > 0 || !rows.length;
    }
    [q, color, result, status, bl].forEach(el => el.addEventListener("input", apply));
    rows.forEach(r => r.addEventListener("click", ev => {
      if (ev.target.closest("a, button") || window.getSelection().toString()) return;
      location.href = r.dataset.href;
    }));
    apply();
  }

  // ================================================================ tableau de bord
  function initDashboard() {
    const container = $('[data-tab-panels="dash"]');
    if (!container) return;
    container.classList.add("js-tabs");
    const subnav = $(".subnav");
    const t = tabs("dash", {
      scope: container, classMode: true, hash: true,
      onChange(id, how) {
        if (how === "click" && subnav) {
          const top = subnav.getBoundingClientRect().top + window.scrollY - 58;
          if (window.scrollY > top) window.scrollTo({ top, behavior: motionOK() ? "smooth" : "auto" });
        }
        if (id === "progression") window.dispatchEvent(new Event("resize"));
      },
    });
    const fromHash = () => location.hash.slice(1);
    t.activate(t.ids.includes(fromHash()) ? fromHash() : t.ids[0], "load");
    window.addEventListener("hashchange", () => { if (t.ids.includes(fromHash())) t.activate(fromHash(), "hash"); });
    // Le filtre de cadence garde l'onglet ouvert
    $all('.segmented a[href^="?"]').forEach(a => a.addEventListener("click", () => {
      a.setAttribute("href", a.getAttribute("href").split("#")[0] + "#" + t.current);
    }));
    initPlan();
    initEloChart();
    // Liens « Entraînement associé » -> élément du plan
    $all("[data-jump-plan]").forEach(a => a.addEventListener("click", ev => {
      const target = document.getElementById(a.getAttribute("href").slice(1));
      if (!target) return;
      ev.preventDefault();
      target.scrollIntoView({ behavior: motionOK() ? "smooth" : "auto", block: "center" });
      target.animate && motionOK() && target.animate(
        [{ boxShadow: "0 0 0 0 transparent" }, { boxShadow: "0 0 0 4px var(--accent)" }, { boxShadow: "0 0 0 0 transparent" }],
        { duration: 1400, easing: "ease-in-out" });
    }));
  }

  function initPlan() {
    const box = $("[data-plan]");
    if (!box) return;
    const key = "cc-plan-" + box.dataset.plan;
    const items = $all("[data-plan-item]", box);
    let done = [];
    try { done = JSON.parse(store.get(key, "[]")) || []; } catch (e) { done = []; }
    function update() {
      const n = items.filter(i => i.checked).length;
      $("[data-plan-count]", box).textContent = n + " / " + items.length;
      $("[data-plan-bar]", box).style.width = (items.length ? 100 * n / items.length : 0) + "%";
    }
    items.forEach(i => {
      i.checked = done.includes(i.dataset.planItem);
      i.addEventListener("change", () => {
        store.set(key, JSON.stringify(items.filter(x => x.checked).map(x => x.dataset.planItem)));
        update();
      });
    });
    const reset = $("[data-plan-reset]", box);
    if (reset) reset.addEventListener("click", () => { items.forEach(i => { i.checked = false; }); store.set(key, "[]"); update(); });
    update();
  }

  // ================================================================ graphiques
  let chartUid = 0;
  function lineChart(container, values, opts) {
    opts = opts || {};
    const n = values.length;
    if (!n) return null;
    const uid = "c" + (++chartUid);
    const min = opts.min != null ? opts.min : Math.min.apply(null, values);
    const max = opts.max != null ? opts.max : Math.max.apply(null, values);
    const span = max - min || 1;
    let W = 0, H = opts.height || 180, svg = null, cursorIdx = null, x = null, y = null;
    const P = { l: 38, r: 12, t: 12, b: opts.xLabels ? 24 : 10 };
    const tip = document.createElement("div");
    tip.className = "chart-tip";

    function draw() {
      const w = Math.round(container.clientWidth);
      if (!w || w === W) return;
      W = w;
      x = i => P.l + (n === 1 ? 0 : i * (W - P.l - P.r) / (n - 1));
      y = v => P.t + (1 - (v - min) / span) * (H - P.t - P.b);
      const pts = values.map((v, i) => x(i).toFixed(1) + "," + y(v).toFixed(1)).join(" ");
      let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(opts.label || "")}">`;
      s += `<defs><linearGradient id="${uid}-g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity=".28"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient>`;
      if (opts.baseline != null) {
        const yb = y(opts.baseline);
        s += `<clipPath id="${uid}-up"><rect x="0" y="0" width="${W}" height="${yb}"/></clipPath><clipPath id="${uid}-dn"><rect x="0" y="${yb}" width="${W}" height="${H - yb}"/></clipPath>`;
      }
      s += "</defs>";
      (opts.gridValues || [min, (min + max) / 2, max]).forEach(g => {
        s += `<line class="${g === opts.baseline ? "mid-line" : "grid-line"}" x1="${P.l}" x2="${W - P.r}" y1="${y(g)}" y2="${y(g)}"/>`;
        s += `<text x="${P.l - 7}" y="${y(g) + 3.5}" text-anchor="end">${esc(opts.gridFormat ? opts.gridFormat(g) : Math.round(g))}</text>`;
      });
      if (opts.baseline != null) {
        const yb = y(opts.baseline);
        const poly = `${x(0)},${yb} ${pts} ${x(n - 1)},${yb}`;
        s += `<polygon class="area-up" clip-path="url(#${uid}-up)" points="${poly}"/><polygon class="area-down" clip-path="url(#${uid}-dn)" points="${poly}"/>`;
      } else {
        s += `<polygon fill="url(#${uid}-g)" points="${x(0)},${y(min)} ${pts} ${x(n - 1)},${y(min)}"/>`;
      }
      s += `<polyline class="line" points="${pts}" ${opts.lineColor ? `style="stroke:${opts.lineColor}"` : ""}/>`;
      s += `<line class="hover-line" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" visibility="hidden"/>`;
      (opts.markers || []).forEach(m => {
        const r = m.hollow ? 3.5 : 4.5;
        s += `<circle class="marker" data-i="${m.i}" cx="${x(m.i)}" cy="${y(values[m.i])}" r="${r}" fill="${m.hollow ? "var(--surface)" : m.color}" stroke="${m.hollow ? m.color : "var(--surface)"}" stroke-width="${m.hollow ? 2 : 1.5}"/>`;
      });
      if (opts.xLabels) opts.xLabels.forEach(l => { s += `<text x="${x(l.i)}" y="${H - 6}" text-anchor="${l.anchor || "middle"}">${esc(l.text)}</text>`; });
      if (opts.cursor) {
        s += `<g class="cursor-g"><line class="cursor" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}"/><circle class="cursor-dot" cx="0" cy="0" r="5"/></g>`;
      }
      s += `<rect class="hit" x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}" fill="transparent"/>`;
      s += "</svg>";
      container.innerHTML = s;
      container.appendChild(tip);
      svg = container.querySelector("svg");
      bind();
      if (cursorIdx != null) setCursor(cursorIdx, true);
    }

    function indexFromEvent(ev) {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) * W / r.width;
      return Math.max(0, Math.min(n - 1, Math.round((px - P.l) * (n - 1) / (W - P.l - P.r))));
    }
    function bind() {
      const hit = svg.querySelector(".hit"), hl = svg.querySelector(".hover-line");
      function move(ev) {
        const i = indexFromEvent(ev);
        hl.setAttribute("x1", x(i)); hl.setAttribute("x2", x(i)); hl.setAttribute("visibility", "visible");
        if (opts.tooltip) {
          const r = svg.getBoundingClientRect(), sc = r.width / W;
          tip.innerHTML = opts.tooltip(i);
          tip.style.left = Math.max(40, Math.min(r.width - 40, x(i) * sc)) + "px";
          tip.style.top = (y(values[i]) * sc) + "px";
          tip.classList.add("show");
        }
      }
      function leave() { hl.setAttribute("visibility", "hidden"); tip.classList.remove("show"); }
      [hit].concat($all(".marker", svg)).forEach(el => {
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerleave", leave);
        if (opts.onClick) el.addEventListener("click", ev => opts.onClick(indexFromEvent(ev)));
      });
    }
    function setCursor(i, instant) {
      cursorIdx = i;
      if (!svg) return;
      const g = svg.querySelector(".cursor-g");
      if (!g) return;
      const line = g.querySelector(".cursor"), dot = g.querySelector(".cursor-dot");
      [line, dot].forEach(el => { if (instant) el.style.transition = "none"; });
      line.style.transform = `translate(${x(i)}px, 0px)`;
      dot.style.transform = `translate(${x(i)}px, ${y(values[i])}px)`;
      if (instant) requestAnimationFrame(() => [line, dot].forEach(el => { el.style.transition = ""; }));
    }

    draw();
    if (window.ResizeObserver) new ResizeObserver(() => draw()).observe(container);
    else window.addEventListener("resize", draw);
    return { setCursor };
  }

  function initEloChart() {
    const el = $("#elo-chart"), dataEl = $("#elo-data");
    if (!el || !dataEl) return;
    const series = JSON.parse(dataEl.textContent);
    if (series.length < 2) return;
    const vals = series.map(p => p[1]);
    const d = s => (s || "").slice(0, 10).replace(/\./g, "-").split("-").reverse().join("/");
    const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    const pad = Math.max(10, Math.round((hi - lo) * .12));
    lineChart(el, vals, {
      label: "Évolution de l'Elo", height: 220, min: lo - pad, max: hi + pad,
      gridValues: [lo, Math.round((lo + hi) / 2), hi],
      xLabels: [{ i: 0, text: d(series[0][0]), anchor: "start" }, { i: series.length - 1, text: d(series[series.length - 1][0]), anchor: "end" }],
      tooltip: i => `${esc(d(series[i][0]))} · <b>${vals[i]}</b>`,
    });
  }

  // ================================================================ échiquier
  function parseFen(fen) {
    const map = {}, rows = fen.split(" ")[0].split("/");
    rows.forEach((row, r) => {
      let f = 0;
      for (const ch of row) {
        if (/\d/.test(ch)) { f += parseInt(ch, 10); continue; }
        map[String.fromCharCode(97 + f) + (8 - r)] = ch;
        f++;
      }
    });
    return map;
  }

  function material(fen) {
    const v = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 }, out = { w: 0, b: 0 };
    Object.values(parseFen(fen)).forEach(ch => {
      const lower = ch.toLowerCase();
      out[ch === lower ? "b" : "w"] += v[lower] || 0;
    });
    return out;
  }

  function createBoard(el, pieces) {
    let orientation = "w", prevMap = null;
    const S = 45;
    el.innerHTML = `<svg viewBox="0 0 360 360" xmlns="${NS}">` +
      `<defs><radialGradient id="cc-check"><stop offset="0" stop-color="#ff2d20" stop-opacity=".95"/><stop offset=".5" stop-color="#e0312a" stop-opacity=".5"/><stop offset="1" stop-color="#e0312a" stop-opacity="0"/></radialGradient></defs>` +
      `<g class="squares"></g><g class="hl"></g><g class="coords"></g><g class="ghosts"></g><g class="pieces"></g><g class="hints"></g><g class="marks"></g><g class="overlay"></g></svg>`;
    const svg = el.firstChild;
    const L = name => svg.querySelector("." + name);
    let sq = "";
    for (let r = 0; r < 8; r++) for (let f = 0; f < 8; f++) {
      sq += `<rect class="${(r + f) % 2 ? "sq-d" : "sq-l"}" x="${f * S}" y="${r * S}" width="${S}" height="${S}"/>`;
    }
    L("squares").innerHTML = sq;

    function xy(s) {
      let x = s.charCodeAt(0) - 97, yy = 8 - parseInt(s[1], 10);
      if (orientation === "b") { x = 7 - x; yy = 7 - yy; }
      return [x, yy];
    }
    function drawCoords() {
      let s = "";
      for (let i = 0; i < 8; i++) {
        const file = orientation === "b" ? String.fromCharCode(104 - i) : String.fromCharCode(97 + i);
        const rank = orientation === "b" ? i + 1 : 8 - i;
        // Bas : case (i, 7) claire si i impair ; gauche : case (0, i) claire si i pair
        s += `<text class="${i % 2 ? "co-d" : "co-l"}" x="${i * S + 42}" y="357" font-size="8.5" font-weight="700" text-anchor="end" font-family="system-ui, sans-serif">${file}</text>`;
        s += `<text class="${i % 2 ? "co-l" : "co-d"}" x="2.5" y="${i * S + 10}" font-size="8.5" font-weight="700" font-family="system-ui, sans-serif">${rank}</text>`;
      }
      L("coords").innerHTML = s;
    }
    function pieceSvg(ch) { return (pieces[ch] || "").replace(/\sid="[^"]*"/g, ""); }
    function pieceG(s, ch, cls) {
      const [x, yy] = xy(s);
      return `<g class="piece ${cls || ""}" data-sq="${s}" transform="translate(${x * S},${yy * S})"><g class="pi">${pieceSvg(ch)}</g></g>`;
    }
    function arrow(uci, color) {
      const [x1, y1] = xy(uci.slice(0, 2)), [x2, y2] = xy(uci.slice(2, 4));
      const ax = x1 * S + 22.5, ay = y1 * S + 22.5, bx = x2 * S + 22.5, by = y2 * S + 22.5;
      const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
      const head = 14, ex = bx - ux * head, ey = by - uy * head, px = -uy, py = ux;
      const sx = ax + ux * 8, sy = ay + uy * 8;
      return `<g opacity=".86" style="pointer-events:none"><line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" stroke="${color}" stroke-width="7.5" stroke-linecap="round"/>` +
        `<polygon points="${bx},${by} ${ex + px * 10.5},${ey + py * 10.5} ${ex - px * 10.5},${ey - py * 10.5}" fill="${color}" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/></g>`;
    }
    function badge(s, cls) {
      const [x, yy] = xy(s);
      const cx = Math.min(x * S + 40, 350.5), cy = Math.max(yy * S + 5, 9.5);
      const glyph = CLS_GLYPH[cls] || "";
      const fs = glyph.length > 1 ? 8 : 10;
      return `<g class="badge-sq" style="pointer-events:none"><circle cx="${cx}" cy="${cy}" r="9" fill="${CLS_COLORS[cls]}" stroke="#fff" stroke-width="1.6"/>` +
        `<text x="${cx}" y="${cy + fs * .36}" text-anchor="middle" font-size="${fs}" font-weight="800" fill="#fff" font-family="system-ui, sans-serif" letter-spacing="-.5">${glyph}</text></g>`;
    }

    function render(fen, o) {
      o = o || {};
      selected = null; drag = null;
      L("hints").innerHTML = ""; L("marks").innerHTML = "";
      if (o.orientation && o.orientation !== orientation) { orientation = o.orientation; drawCoords(); }
      else if (!L("coords").firstChild) drawCoords();
      const map = parseFen(fen);
      // Cases surlignées : dernier coup + roi en échec
      let hl = "";
      (o.lastMove || []).forEach(s => {
        const [x, yy] = xy(s);
        hl += o.lastColor
          ? `<rect x="${x * S}" y="${yy * S}" width="${S}" height="${S}" fill="${o.lastColor}" fill-opacity=".42"/>`
          : `<rect class="hl-last" x="${x * S}" y="${yy * S}" width="${S}" height="${S}"/>`;
      });
      if (o.check) {
        const [x, yy] = xy(o.check);
        hl += `<rect x="${x * S}" y="${yy * S}" width="${S}" height="${S}" fill="url(#cc-check)"/>`;
      }
      L("hl").innerHTML = hl;
      // Pièces
      let ps = "";
      Object.keys(map).forEach(s => { ps += pieceG(s, map[s]); });
      L("pieces").innerHTML = ps;
      L("ghosts").innerHTML = "";
      // Animation (uniquement pour un déplacement d'un demi-coup)
      if (o.movers && prevMap && motionOK()) {
        const dur = o.duration || 210;
        const froms = new Set(o.movers.map(m => m.from)), tos = new Set(o.movers.map(m => m.to));
        o.movers.forEach(m => {
          const g = L("pieces").querySelector(`[data-sq="${m.to}"] .pi`);
          if (!g || !g.animate) return;
          const [fx, fy] = xy(m.from), [tx, ty] = xy(m.to);
          g.parentNode.parentNode.appendChild(g.parentNode); // la pièce qui bouge passe au-dessus
          g.animate([{ transform: `translate(${(fx - tx) * S}px, ${(fy - ty) * S}px)` }, { transform: "translate(0px, 0px)" }],
            { duration: dur, easing: EASE });
        });
        let gh = "";
        Object.keys(prevMap).forEach(s => { if (map[s] !== prevMap[s] && !froms.has(s)) gh += pieceG(s, prevMap[s], "ghost"); });
        L("ghosts").innerHTML = gh;
        $all(".ghost", L("ghosts")).forEach(g => {
          const a = g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: dur, easing: "ease-in", fill: "forwards" });
          a.onfinish = () => g.remove();
        });
        Object.keys(map).forEach(s => {
          if (map[s] !== prevMap[s] && !tos.has(s)) {
            const g = L("pieces").querySelector(`[data-sq="${s}"]`);
            if (g && g.animate) g.animate([{ opacity: 0 }, { opacity: 1 }], { duration: dur, easing: "ease-out" });
          }
        });
      }
      prevMap = map;
      // Flèches et pastille de classement
      let ov = "";
      (o.arrows || []).forEach(a => { if (a.uci) ov += arrow(a.uci, a.color); });
      if (o.badge) ov += badge(o.badge.sq, o.badge.cls);
      L("overlay").innerHTML = ov;
      if (o.badge && motionOK()) {
        const b = L("overlay").querySelector(".badge-sq");
        if (b && b.animate) {
          b.style.transformBox = "fill-box"; b.style.transformOrigin = "center";
          b.animate([{ opacity: 0, transform: "scale(.6)" }, { opacity: 1, transform: "scale(1)" }],
            { duration: 260, easing: "cubic-bezier(.3,1.6,.5,1)", delay: o.movers ? 120 : 0, fill: "backwards" });
        }
      }
    }
    // ------------------------------------------------ saisie des coups (clic ou glisser-déposer)
    let input = null, selected = null, drag = null;
    const colorOf = ch => (ch === ch.toUpperCase() ? "w" : "b");
    function sqFromEvent(ev) {
      const r = svg.getBoundingClientRect();
      const x = Math.floor((ev.clientX - r.left) / r.width * 8), y = Math.floor((ev.clientY - r.top) / r.height * 8);
      if (x < 0 || x > 7 || y < 0 || y > 7) return null;
      const f = orientation === "w" ? x : 7 - x, rank = orientation === "w" ? 8 - y : y + 1;
      return String.fromCharCode(97 + f) + rank;
    }
    function dests(from) { return input ? input.legal.filter(u => u.slice(0, 2) === from).map(u => u.slice(2, 4)) : []; }
    function showHints(from) {
      let h = "";
      if (from) {
        const [x, yy] = xy(from);
        h += `<rect x="${x * S}" y="${yy * S}" width="${S}" height="${S}" fill="var(--c-last)"/>`;
        Array.from(new Set(dests(from))).forEach(to => {
          const [tx, ty] = xy(to);
          h += prevMap && prevMap[to]
            ? `<circle cx="${tx * S + 22.5}" cy="${ty * S + 22.5}" r="20" fill="none" stroke="rgba(20,20,20,.25)" stroke-width="4"/>`
            : `<circle cx="${tx * S + 22.5}" cy="${ty * S + 22.5}" r="7" fill="rgba(20,20,20,.22)"/>`;
        });
      }
      L("hints").innerHTML = h;
      el.classList.toggle("has-selection", !!from);
    }
    function tryMove(from, to, dragged) {
      const cands = input.legal.filter(u => u.slice(0, 4) === from + to);
      selected = null; showHints(null);
      if (!cands.length) return false;
      const cb = input.onMove;
      if (cands.length > 1 && input.choosePromotion) input.choosePromotion(cands, uci => cb(uci, { dragged }));
      else cb(cands[0], { dragged });
      return true;
    }
    function pointerPos(ev) {
      const r = svg.getBoundingClientRect();
      return [(ev.clientX - r.left) / r.width * 360, (ev.clientY - r.top) / r.height * 360];
    }
    svg.addEventListener("pointerdown", ev => {
      if (!input || ev.button > 0) return;
      const s = sqFromEvent(ev);
      if (!s) return;
      if (selected && dests(selected).includes(s)) { tryMove(selected, s, false); ev.preventDefault(); return; }
      const ch = prevMap && prevMap[s];
      if (ch && colorOf(ch) === input.color && dests(s).length) {
        selected = s; showHints(s);
        const g = L("pieces").querySelector(`[data-sq="${s}"]`);
        if (g) {
          const [x0, y0] = pointerPos(ev);
          drag = { sq: s, g, x0, y0, moved: false, base: g.getAttribute("transform") };
          try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
        }
        ev.preventDefault();
      } else { selected = null; showHints(null); }
    });
    svg.addEventListener("pointermove", ev => {
      if (!drag) return;
      const [px, py] = pointerPos(ev);
      if (!drag.moved && Math.hypot(px - drag.x0, py - drag.y0) < 4) return;
      if (!drag.moved) { drag.moved = true; L("pieces").appendChild(drag.g); el.classList.add("dragging"); }
      drag.g.setAttribute("transform", `translate(${px - 22.5},${py - 22.5})`);
    });
    function endDrag(ev, cancel) {
      if (!drag) return;
      const d = drag;
      drag = null;
      el.classList.remove("dragging");
      if (!d.moved) return;
      const s = cancel ? null : sqFromEvent(ev);
      if (!s || s === d.sq || !tryMove(d.sq, s, true)) {
        d.g.setAttribute("transform", d.base);
        if (s !== d.sq) { selected = null; showHints(null); }
      }
    }
    svg.addEventListener("pointerup", ev => endDrag(ev, false));
    svg.addEventListener("pointercancel", ev => endDrag(ev, true));

    function enableInput(opts) { input = opts; el.classList.add("interactive"); }
    function disableInput() { input = null; selected = null; drag = null; showHints(null); el.classList.remove("interactive"); }
    function annotate(o) {
      let h = "";
      (o.rings || []).forEach(s => {
        const [x, yy] = xy(s);
        h += `<circle class="pulse-ring" cx="${x * S + 22.5}" cy="${yy * S + 22.5}" r="20" fill="none" stroke="var(--c-arrow-best)" stroke-width="3.5"/>`;
      });
      (o.arrows || []).forEach(a => { h += arrow(a.uci, a.color); });
      L("marks").innerHTML = h;
    }

    return { render, enableInput, disableInput, annotate, get orientation() { return orientation; } };
  }

  // Choix de la pièce de promotion (petit menu par-dessus l'échiquier)
  function promotionPicker(container, pieces, color) {
    return function (cands, cb) {
      if (!container) return cb(cands[0]);
      const order = ["q", "r", "b", "n"].filter(p => cands.some(u => u[4] === p));
      container.innerHTML = order.map(p => {
        const key = color === "w" ? p.toUpperCase() : p;
        const svgPiece = (pieces[key] || "").replace(/\sid="[^"]*"/g, "");
        return `<button type="button" data-p="${p}" aria-label="Promouvoir"><svg viewBox="0 0 45 45">${svgPiece}</svg></button>`;
      }).join("");
      container.hidden = false;
      container.onclick = ev => {
        const b = ev.target.closest("[data-p]");
        if (!b) return;
        container.hidden = true;
        cb(cands.find(u => u[4] === b.dataset.p));
      };
    };
  }

  // Déplacements à animer pour un coup UCI (le roque déplace aussi la tour)
  function moversFor(uci, fenBefore) {
    const from = uci.slice(0, 2), to = uci.slice(2, 4), out = [{ from, to }];
    const p = parseFen(fenBefore)[from];
    if (p && p.toLowerCase() === "k" && Math.abs(from.charCodeAt(0) - to.charCodeAt(0)) === 2) {
      const rank = from[1], kingside = to[0] === "g";
      out.push({ from: (kingside ? "h" : "a") + rank, to: (kingside ? "f" : "d") + rank });
    }
    return out;
  }

  function kingSquare(fen, color) {
    const map = parseFen(fen), k = color === "w" ? "K" : "k";
    return Object.keys(map).find(s => map[s] === k) || null;
  }

  function fmtClock(sec) {
    if (sec == null) return "";
    sec = Math.max(0, Math.round(sec));
    const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
  }

  // ================================================================ analyse d'une partie
  function initGame(startPly) {
    const dataEl = $("#game-data");
    if (!dataEl) return;
    const data = JSON.parse(dataEl.textContent);
    const boardEl = $("#board"), info = $("#move-info"), list = $("#movelist");
    const N = data.fens.length - 1;
    const pc = data.player_color;
    const moveColor = data.moves.map(m => data.fens[m.i].split(" ")[1]);
    let orientation = data.orientation, k = -1, showBest = true, timer = null;
    const board = createBoard(boardEl, data.pieces);
    const panelTabs = tabs("game", { scope: $(".panel") });

    // Liste des coups
    let html = "";
    data.moves.forEach((m, idx) => {
      if (idx === 0 && m.i % 2 === 1) html += `<span class="no">${Math.floor(m.i / 2) + 1}.</span><span></span>`;
      if (m.i % 2 === 0) html += `<span class="no">${Math.floor(m.i / 2) + 1}.</span>`;
      const err = ERRORS.includes(m.cls);
      html += `<span class="mv ${m.cls ? "cls-" + m.cls : ""} ${err ? "is-error" : ""}" data-k="${m.i + 1}" title="${esc(m.cls_label || "")}" role="button" tabindex="-1">` +
        `${m.cls ? '<span class="dot"></span>' : ""}<span>${esc(m.san)}</span>${m.symbol ? `<span class="sym">${esc(m.symbol)}</span>` : ""}</span>`;
    });
    list.innerHTML = html || '<span></span><span class="faint">Aucun coup.</span>';
    list.addEventListener("click", ev => { const t = ev.target.closest(".mv"); if (t) { stop(); go(parseInt(t.dataset.k, 10)); } });

    // Courbe
    let chart = null;
    const chartEl = $("#wp-chart");
    if (chartEl && data.wp) {
      const markers = data.moves
        .filter(m => (m.mine && (m.cls === "blunder" || m.cls === "mistake")) || (m.mine === false && m.cls === "blunder"))
        .map(m => ({ i: m.i + 1, color: CLS_COLORS[m.cls], hollow: !m.mine }));
      chart = lineChart(chartEl, data.wp, {
        min: 0, max: 100, height: 170, baseline: 50, gridValues: [0, 50, 100], gridFormat: v => v + " %",
        markers, cursor: true, lineColor: "var(--muted)", label: "Tes chances de gain coup par coup",
        tooltip: i => {
          if (i === 0) return `Départ · <b>${fmt(data.wp[0])} %</b>`;
          const m = data.moves[i - 1];
          return `${esc(m.label)}${m.symbol ? `<span style="color:${CLS_COLORS[m.cls]}">${esc(m.symbol)}</span>` : ""} · <b>${fmt(data.wp[i])} %</b>`;
        },
        onClick: i => { stop(); go(i); },
      });
    }

    function playerBar(el, color, kk) {
      if (!el) return;
      const p = data.players[color] || {};
      const mat = material(data.fens[kk]);
      const diff = mat[color] - mat[color === "w" ? "b" : "w"];
      let clock = null;
      for (let i = Math.min(kk, data.moves.length) - 1; i >= 0; i--) {
        if (moveColor[i] === color && data.moves[i].clock != null) { clock = data.moves[i].clock; break; }
      }
      if (clock == null) clock = data.initial_clock;
      const toMove = kk < N && data.fens[kk].split(" ")[1] === color;
      el.classList.toggle("to-move", toMove);
      el.innerHTML = `<span class="side side-${color}"></span><span class="name">${esc(p.name || "?")}</span>` +
        `${p.elo ? `<span class="elo">${p.elo}</span>` : ""}${color === pc ? '<span class="you">toi</span>' : ""}` +
        `${diff > 0 ? `<span class="faint small tabular">+${diff}</span>` : ""}` +
        `<span class="clock ${clock != null && clock < 30 ? "low" : ""}">${fmtClock(clock)}</span>`;
    }

    function evalBar(kk) {
      const bar = $("#evalbar");
      if (!bar || !data.wp) return;
      const white = pc === "w" ? data.wp[kk] : 100 - data.wp[kk];
      bar.classList.toggle("flipped", orientation === "b");
      $(".fill", bar).style.height = white + "%";
      const whiteEnd = orientation === "w" ? "bottom" : "top", blackEnd = whiteEnd === "bottom" ? "top" : "bottom";
      $(".ev-label." + whiteEnd, bar).textContent = white >= 50 ? Math.round(white) : "";
      $(".ev-label." + blackEnd, bar).textContent = white < 50 ? Math.round(100 - white) : "";
      bar.title = `Chances de gain des Blancs : ${fmt(white)} %`;
    }

    function bubble(kk) {
      const m = kk > 0 ? data.moves[kk - 1] : null;
      info.className = "coach-bubble" + (m && m.cls ? " cls-" + m.cls : "");
      if (!m) {
        const nKey = (data.key || []).length;
        info.innerHTML = `<div class="cb-head"><span class="cls-icon" style="--cls-c:var(--accent)">${icon("play")}</span>` +
          `<div><div class="cb-title">Position de départ</div><div class="cb-sub">${data.wp ? (nKey ? `${nKey} moment${nKey > 1 ? "s" : ""} clé${nKey > 1 ? "s" : ""} à revoir` : "Aucune erreur marquante") : "Partie non analysée : rejoue les coups librement."}</div></div></div>` +
          `<p class="cb-empty" style="margin:.7rem 0 0">Utilise <kbd>←</kbd> <kbd>→</kbd>, la lecture automatique ou clique sur un coup${data.wp ? " ou sur la courbe" : ""}.</p>`;
        return;
      }
      const who = m.mine === true ? "ton coup" : m.mine === false ? "coup adverse" : "";
      let h = `<div class="cb-head">`;
      h += m.cls ? `<span class="cls-icon">${m.cls === "best" ? icon("star") : m.cls === "good" ? icon("check") : esc(m.symbol)}</span>`
        : `<span class="cls-icon" style="--cls-c:var(--border-strong)">${icon("next")}</span>`;
      h += `<div><div class="cb-title"><span class="mono">${esc(m.label)}${m.symbol ? esc(m.symbol) : ""}</span>${m.cls ? ` · ${esc(m.cls_label)}` : ""}</div>`;
      h += `<div class="cb-sub">${[who, m.phase].filter(Boolean).map(esc).join(" · ")}</div></div>`;
      if (data.wp) {
        const d = data.wp[kk] - data.wp[kk - 1];
        const dcls = Math.abs(d) < 1 ? "faint" : d > 0 ? "v-good" : "v-bad";
        h += `<div class="cb-wp"><div class="v">${fmt(data.wp[kk])} %</div><div class="d ${dcls}">${d > 0 ? "+" : d < 0 ? "−" : "±"}${fmt(Math.abs(d))} pts</div></div>`;
      }
      h += "</div>";
      if (m.explain && m.explain.length) h += `<ul class="cb-list">${m.explain.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`;
      const showsBest = (m.explain || []).some(t => t.indexOf("Meilleur") === 0);
      if (ERRORS.includes(m.cls) && m.best && m.best !== m.san && !showsBest) {
        h += `<div class="cb-best">${icon("bulb")} Meilleur selon Stockfish : <b>${esc(m.best)}</b></div>`;
      }
      if (!m.cls && !data.wp) h += `<p class="cb-empty" style="margin:.6rem 0 0">Lance l'analyse pour obtenir le classement et l'explication de chaque coup.</p>`;
      info.innerHTML = h;
    }

    function scrollMoveIntoView(el) {
      const box = el.closest(".panel-scroll");
      if (!box || box.offsetParent === null) return;
      const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
      if (r.top < b.top + 4) box.scrollTop -= (b.top - r.top) + 40;
      else if (r.bottom > b.bottom - 4) box.scrollTop += (r.bottom - b.bottom) + 40;
    }

    function go(newK, opts) {
      opts = opts || {};
      newK = Math.max(0, Math.min(N, newK));
      if (newK === k && !opts.force) return;
      let movers = null;
      if (!opts.force && k >= 0 && Math.abs(newK - k) === 1) {
        if (newK > k) movers = moversFor(data.moves[newK - 1].uci, data.fens[k]);
        else movers = moversFor(data.moves[k - 1].uci, data.fens[newK]).map(mv => ({ from: mv.to, to: mv.from }));
      }
      k = newK;
      const m = k > 0 ? data.moves[k - 1] : null;
      const arrows = [];
      if (m && showBest && m.best_uci && m.best_uci !== m.uci && ERRORS.includes(m.cls)) arrows.push({ uci: m.best_uci, color: "var(--c-arrow-best)" });
      board.render(data.fens[k], {
        orientation, movers,
        lastMove: m ? [m.uci.slice(0, 2), m.uci.slice(2, 4)] : [],
        lastColor: m && ERRORS.includes(m.cls) ? CLS_COLORS[m.cls] : null,
        check: m && /[+#]$/.test(m.san) ? kingSquare(data.fens[k], data.fens[k].split(" ")[1]) : null,
        arrows, badge: m && m.cls ? { sq: m.uci.slice(2, 4), cls: m.cls } : null,
      });
      $all(".mv.current", list).forEach(e => e.classList.remove("current"));
      const cur = list.querySelector(`.mv[data-k="${k}"]`);
      if (cur) { cur.classList.add("current"); scrollMoveIntoView(cur); }
      $all(".moment").forEach(el => el.classList.toggle("current", parseInt(el.dataset.goto, 10) === k));
      if (chart) chart.setCursor(k);
      const top = orientation === "w" ? "b" : "w";
      playerBar($("#bar-top"), top, k);
      playerBar($("#bar-bottom"), orientation, k);
      evalBar(k);
      bubble(k);
      const url = new URL(location.href);
      if (k > 0) url.searchParams.set("coup", k - 1); else url.searchParams.delete("coup");
      history.replaceState(null, "", url);
      updatePlay();
    }

    // Lecture automatique
    const playBtn = $('[data-nav="play"]');
    function updatePlay() {
      if (!playBtn) return;
      $("use", playBtn).setAttribute("href", timer ? "#i-pause" : "#i-play");
      playBtn.title = timer ? "Pause (Espace)" : "Lecture automatique (Espace)";
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; updatePlay(); } }
    function play() {
      if (timer) { stop(); return; }
      if (k >= N) go(0);
      timer = setInterval(() => { if (k >= N) stop(); else go(k + 1); }, 950);
      updatePlay();
    }

    const keys = (data.key || []).map(i => i + 1);
    if (!keys.length) $all('[data-nav$="-key"]').forEach(b => { b.disabled = true; b.title = "Aucun moment clé dans cette partie"; });
    function nextKey() { const t = keys.find(x => x > k); if (t != null) go(t); }
    function prevKey() { const t = keys.slice().reverse().find(x => x < k); if (t != null) go(t); }
    function flip() { orientation = orientation === "w" ? "b" : "w"; go(k, { force: true }); }
    function toggleBest(btn) {
      showBest = !showBest;
      if (btn) { btn.classList.toggle("active", showBest); btn.setAttribute("aria-pressed", String(showBest)); }
      go(k, { force: true });
    }

    $all("[data-nav]").forEach(b => b.addEventListener("click", () => {
      const a = b.dataset.nav;
      if (a === "play") return play();
      stop();
      if (a === "first") go(0); else if (a === "prev") go(k - 1); else if (a === "next") go(k + 1);
      else if (a === "last") go(N); else if (a === "flip") flip(); else if (a === "best") toggleBest(b);
      else if (a === "next-key") nextKey(); else if (a === "prev-key") prevKey();
    }));
    document.addEventListener("keydown", ev => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if ($("#appearance") && !$("#appearance").hidden) return;
      const keyMap = {
        ArrowLeft: () => go(k - 1), ArrowRight: () => go(k + 1), Home: () => go(0), End: () => go(N),
        ArrowUp: prevKey, ArrowDown: nextKey, f: flip, F: flip, b: () => toggleBest($('[data-nav="best"]')), B: () => toggleBest($('[data-nav="best"]')),
      };
      if (ev.key === " " && !(document.activeElement && document.activeElement.tagName === "BUTTON")) { play(); ev.preventDefault(); return; }
      if (keyMap[ev.key]) {
        if (ev.key === "ArrowUp" || ev.key === "ArrowDown") { if (!keys.length) return; }
        stop(); keyMap[ev.key](); ev.preventDefault();
      }
    });
    // Glisser sur l'échiquier (mobile) : coup suivant / précédent
    let sx = null, sy = null;
    boardEl.addEventListener("pointerdown", ev => { sx = ev.clientX; sy = ev.clientY; });
    boardEl.addEventListener("pointerup", ev => {
      if (sx == null) return;
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      sx = null;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) { stop(); go(k + (dx < 0 ? 1 : -1)); }
    });
    $all("[data-goto]").forEach(el => el.addEventListener("click", () => {
      stop();
      go(parseInt(el.dataset.goto, 10));
      if (window.innerWidth <= 980) boardEl.scrollIntoView({ behavior: motionOK() ? "smooth" : "auto", block: "center" });
    }));
    if (panelTabs) panelTabs.activate("moves");
    go(startPly != null ? startPly : 0, { force: true });
  }

  // ================================================================ outils partagés (exercices, références)
  // Fait défiler la liste des coups sans faire bouger la page
  function scrollIntoBox(el) {
    const box = el.closest(".panel-scroll");
    if (!box || box.offsetParent === null) return;
    const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
    if (r.top < b.top + 4) box.scrollTop -= (b.top - r.top) + b.height / 3;
    else if (r.bottom > b.bottom - 4) box.scrollTop += (r.bottom - b.bottom) + b.height / 3;
  }
  function csrf() {
    const el = $("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }
  function postJSON(url, body) {
    return fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
    }).then(r => (r.ok ? r.json() : Promise.reject(r)));
  }
  function squaresOf(uci) { return uci ? [uci.slice(0, 2), uci.slice(2, 4)] : []; }
  function checkSquare(san, fen) { return /[+#]$/.test(san || "") ? kingSquare(fen, fen.split(" ")[1]) : null; }
  function simpleBar(el, color, name, fen, opts) {
    if (!el) return;
    opts = opts || {};
    const mat = material(fen), diff = mat[color] - mat[color === "w" ? "b" : "w"];
    const toMove = !opts.over && fen.split(" ")[1] === color;
    el.classList.toggle("to-move", toMove);
    el.innerHTML = `<span class="side side-${color}"></span><span class="name">${esc(name)}</span>` +
      `${opts.you ? '<span class="you">toi</span>' : ""}${diff > 0 ? `<span class="faint small tabular">+${diff}</span>` : ""}` +
      `<span class="spacer"></span>${toMove ? '<span class="badge badge-accent">au trait</span>' : ""}`;
  }

  function initRatingChart() {
    const el = $("#rating-chart"), dataEl = $("#rating-data");
    if (!el || !dataEl) return;
    const vals = JSON.parse(dataEl.textContent);
    if (vals.length < 2) return;
    const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = Math.max(15, Math.round((hi - lo) * .15));
    lineChart(el, vals, {
      height: 150, min: lo - pad, max: hi + pad, gridValues: [lo, hi], label: "Évolution du classement",
      tooltip: i => (i === 0 ? "Départ" : `Essai ${i}`) + ` · <b>${vals[i]}</b>`,
    });
  }

  function initTrainingHome() {
    initRatingChart();
    const mini = $("[data-mini-board]"), piecesEl = $("#pieces-data");
    if (mini && piecesEl) {
      createBoard(mini, JSON.parse(piecesEl.textContent)).render(mini.dataset.fen, {
        orientation: mini.dataset.color, lastMove: squaresOf(mini.dataset.last),
      });
    }
    $all("[data-gen-status][data-running]").forEach(card => {
      if (!card.dataset.running) return;
      poll(card.dataset.genStatus, d => {
        const msg = $("[data-gen-message]", card), cnt = $("[data-gen-count]", card);
        if (msg && d.message) { msg.textContent = d.message; msg.hidden = false; }
        if (cnt) cnt.textContent = d.n_puzzles;
        if (!d.running) { setTimeout(() => location.reload(), 800); return false; }
      }, 2500);
    });
  }

  // ================================================================ exercices
  function initPuzzle(cfg) {
    const pieces = JSON.parse($("#pieces-data").textContent);
    let data = JSON.parse($("#puzzle-data").textContent);
    const boardEl = $("#board"), board = createBoard(boardEl, pieces);
    const statusEl = $("#pz-status"), detailsEl = $("#pz-details"), sessionEl = $("#session");
    const btn = { hint: $("#pz-hint"), sol: $("#pz-solution"), retry: $("#pz-retry"), next: $("#pz-next") };
    const seen = [data.id], session = [];
    let st = null, orientation = data.color, last = null, timer = null;

    const STATUS_ICON = { play: "target", good: "check", bad: "x", win: "trophy", done: "eye", hint: "bulb", wait: "clock", info: "bulb" };
    function status(kind, text) {
      statusEl.className = "pz-status is-" + kind;
      statusEl.innerHTML = `<span class="pz-status-icon">${icon(STATUS_ICON[kind] || "bulb")}</span><span>${text}</span>`;
    }
    function show(fen, opts) {
      last = { fen, opts: Object.assign({}, opts, { movers: null }) };
      board.render(fen, Object.assign({ orientation }, opts));
    }
    function turnBar() {
      const c = data.color;
      $("#turn-bar").innerHTML = `<span class="side side-${c}"></span><b>${c === "w" ? "Les Blancs" : "Les Noirs"} jouent</b><span class="spacer"></span>` +
        `<span class="faint small">${data.steps.length > 1 ? data.steps.length + " coups à trouver" : "1 coup à trouver"}</span>`;
    }
    function startTimer() {
      stopTimer();
      const t = $("#pz-timer");
      timer = setInterval(() => {
        const sec = Math.floor((Date.now() - st.t0) / 1000);
        t.textContent = Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
      }, 1000);
    }
    function stopTimer() { if (timer) { clearInterval(timer); timer = null; } }
    function enable() {
      const step = data.steps[st.step];
      board.enableInput({ color: data.color, legal: Object.keys(step.legal), onMove, choosePromotion: promotionPicker($("#promo"), pieces, data.color) });
    }
    function reset(p, practice) {
      data = p;
      orientation = p.color;
      st = { step: 0, failed: false, hint: 0, reported: !!practice, practice: !!practice, done: false, mistakes: 0, t0: Date.now(), busy: true };
      detailsEl.hidden = true;
      btn.retry.hidden = btn.next.hidden = true;
      btn.hint.hidden = btn.sol.hidden = false;
      $("#pz-timer").textContent = "0:00";
      turnBar();
      show(p.start_fen, {});
      status("wait", "L'adversaire joue…");
      setTimeout(() => {
        show(p.setup.fen, { lastMove: squaresOf(p.setup.uci), check: checkSquare(p.setup.san, p.setup.fen), movers: moversFor(p.setup.uci, p.start_fen) });
        st.busy = false;
        st.t0 = Date.now();
        status("play", `${practice ? "Nouvel essai (non compté) — " : ""}Ton tour : trouve le meilleur coup pour les <b>${p.color === "w" ? "Blancs" : "Noirs"}</b>.`);
        enable();
        startTimer();
      }, 650);
    }
    function onMove(uci, info) {
      if (st.busy || st.done) return;
      const step = data.steps[st.step], mv = step.legal[uci];
      if (!mv) return;
      const ok = step.accept.includes(uci) || mv.mate;
      const isLast = st.step === data.steps.length - 1;
      board.disableInput();
      const movers = info && info.dragged ? null : moversFor(uci, step.fen);
      show(mv.fen, { movers, lastMove: squaresOf(uci), check: checkSquare(mv.san, mv.fen), badge: { sq: uci.slice(2, 4), cls: ok ? "best" : "blunder" } });
      if (ok) {
        if (mv.mate || isLast) return finish(true);
        status("good", `<b>${esc(mv.san)}</b> : bien joué ! Continue…`);
        st.busy = true;
        setTimeout(() => {
          const r = step.reply;
          show(r.fen, { movers: moversFor(r.uci, mv.fen), lastMove: squaresOf(r.uci), check: checkSquare(r.san, r.fen) });
          st.step++;
          st.busy = false;
          status("play", `L'adversaire a répondu <b>${esc(r.san)}</b>. À toi de trouver la suite.`);
          enable();
        }, 500);
      } else {
        st.mistakes++;
        if (!st.failed) { st.failed = true; report(false); }
        status("bad", `<b>${esc(mv.san)}</b> n'est pas le bon coup. Réessaie, ou regarde la solution.`);
        st.busy = true;
        setTimeout(() => {
          const back = moversFor(uci, step.fen).map(m => ({ from: m.to, to: m.from }));
          const prev = st.step === 0 ? data.setup : data.steps[st.step - 1].reply;
          show(step.fen, { movers: back, lastMove: squaresOf(prev.uci), check: checkSquare(prev.san, step.fen) });
          st.busy = false;
          enable();
        }, 900);
      }
    }
    function report(solved) {
      if (st.reported) return;
      st.reported = true;
      postJSON(cfg.attemptUrl.replace(/\/0\/tentative\/$/, `/${data.id}/tentative/`), {
        solved, mistakes: st.mistakes, used_hint: st.hint > 0, seconds: (Date.now() - st.t0) / 1000, theme: cfg.theme,
      }).then(d => {
        $("#pz-rating").textContent = d.rating_after;
        const delta = $("#pz-delta");
        delta.hidden = false;
        delta.className = "delta " + (d.delta >= 0 ? "up" : "down");
        delta.textContent = (d.delta > 0 ? "+" : d.delta < 0 ? "−" : "±") + Math.abs(d.delta);
        $("#pz-streak span").textContent = d.streak;
        if (motionOK() && delta.animate) delta.animate([{ transform: "scale(.6)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], { duration: 350, easing: "cubic-bezier(.3,1.6,.5,1)" });
      }).catch(() => status("info", "Résultat non enregistré (serveur injoignable)."));
    }
    function finish(success) {
      st.done = true;
      stopTimer();
      board.disableInput();
      const solved = success && !st.failed && !st.hint;
      if (!st.practice) {
        report(solved);
        session.push({ ok: solved });
        sessionEl.innerHTML = session.map((r, i) => `<span class="sess ${r.ok ? "ok" : "ko"}" title="Exercice ${i + 1} : ${r.ok ? "réussi" : "raté"}">${r.ok ? "✓" : "✗"}</span>`).join("");
      }
      if (solved) status("win", "Exercice réussi du premier coup !");
      else if (success) status("done", "Résolu… avec un peu d'aide. Il reviendra dans tes révisions.");
      else status("done", "Voici la solution. Cet exercice reviendra dans tes révisions.");
      if (solved && motionOK() && boardEl.animate) boardEl.animate([{ boxShadow: "0 0 0 0 transparent" }, { boxShadow: "0 0 0 6px var(--c-best)" }, { boxShadow: "0 0 0 0 transparent" }], { duration: 900 });
      btn.hint.hidden = btn.sol.hidden = true;
      btn.retry.hidden = btn.next.hidden = false;
      btn.next.focus({ preventScroll: true });
      details();
    }
    function details() {
      const line = [];
      data.steps.forEach((s, i) => {
        line.push(`<b>${esc(s.solution_san)}</b>`);
        if (s.reply && i < data.steps.length - 1) line.push(esc(s.reply.san));
      });
      let h = `<div class="pz-line"><span class="kpi-label">Solution</span><div class="mono">${line.join(" · ")}</div></div>`;
      if (data.steps[0].accept.length > 1) h += `<p class="small muted" style="margin:.4rem 0 0">Autres coups acceptés : ${data.steps[0].accept.slice(1).map(u => esc(data.steps[0].legal[u] ? data.steps[0].legal[u].san : u)).join(", ")}.</p>`;
      h += `<div class="row row-tight" style="margin-top:.8rem"><span class="badge">Difficulté ${data.rating}</span>` +
        data.themes.filter(t => !["longueur"].includes(t.category)).map(t => `<a class="chip" href="${cfg.playUrl.replace("THEME", t.key)}">${icon(t.icon)} ${esc(t.label)}</a>`).join("") + "</div>";
      if (data.note) h += `<p class="small" style="margin:.8rem 0 0">${icon("king")} ${esc(data.note)}${data.game_url ? ` <a href="${data.game_url}">Voir dans ta partie ${icon("arrow-right")}</a>` : ""}</p>`;
      detailsEl.innerHTML = h;
      detailsEl.hidden = false;
    }
    function hint() {
      if (!st || st.done || st.busy) return;
      st.hint++;
      const step = data.steps[st.step];
      if (st.hint === 1) {
        board.annotate({ rings: [step.solution.slice(0, 2)] });
        status("hint", "Indice : c'est cette pièce qu'il faut jouer.");
      } else {
        board.annotate({ arrows: [{ uci: step.solution, color: "var(--c-arrow-best)" }] });
        status("hint", "Indice : joue ce coup.");
      }
    }
    function solution() {
      if (!st || st.done || st.busy) return;
      st.hint = Math.max(st.hint, 1);
      if (!st.failed) { st.failed = true; report(false); }
      board.disableInput();
      st.busy = true;
      (function playStep() {
        const step = data.steps[st.step], mv = step.legal[step.solution];
        show(mv.fen, { movers: moversFor(step.solution, step.fen), lastMove: squaresOf(step.solution), check: checkSquare(mv.san, mv.fen), badge: { sq: step.solution.slice(2, 4), cls: "best" } });
        if (st.step === data.steps.length - 1 || mv.mate) { st.busy = false; return finish(false); }
        setTimeout(() => {
          const r = step.reply;
          show(r.fen, { movers: moversFor(r.uci, mv.fen), lastMove: squaresOf(r.uci), check: checkSquare(r.san, r.fen) });
          st.step++;
          setTimeout(playStep, 650);
        }, 650);
      })();
    }
    function next() {
      btn.next.disabled = true;
      fetch(`${cfg.nextUrl}?theme=${encodeURIComponent(cfg.theme)}&exclude=${seen.join(",")}`)
        .then(r => r.json())
        .then(d => {
          btn.next.disabled = false;
          if (d.empty || !d.puzzle) { status("info", "Tu as fait le tour de ce thème ! Choisis-en un autre ou passe aux révisions."); return; }
          seen.push(d.puzzle.id);
          const url = new URL(location.href); url.searchParams.set("id", d.puzzle.id); history.replaceState(null, "", url);
          reset(d.puzzle, false);
        })
        .catch(() => { btn.next.disabled = false; status("info", "Impossible de charger l'exercice suivant."); });
    }
    btn.hint.addEventListener("click", hint);
    btn.sol.addEventListener("click", solution);
    btn.next.addEventListener("click", next);
    btn.retry.addEventListener("click", () => reset(data, true));
    const sw = $("#theme-switch");
    if (sw) sw.addEventListener("change", () => { location.href = cfg.playUrl.replace("THEME", sw.value); });
    document.addEventListener("keydown", ev => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (ev.key === "Enter" && st && st.done) { next(); ev.preventDefault(); }
      else if ((ev.key === "f" || ev.key === "F") && last) {
        orientation = orientation === "w" ? "b" : "w";
        board.render(last.fen, Object.assign({}, last.opts, { orientation }));
        if (st && !st.done && !st.busy) enable();
      }
    });
    reset(data, false);
  }

  // ================================================================ course contre la montre
  function initSprint(cfg) {
    const pieces = JSON.parse($("#pieces-data").textContent);
    const boardEl = $("#board"), board = createBoard(boardEl, pieces);
    const startEl = $("#sprint-start"), liveEl = $("#sprint-live"), overEl = $("#sprint-over");
    const flash = $("#flash");
    let st = null;
    board.render("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", { orientation: "w" });

    function fmtTime(ms) {
      const sec = Math.max(0, Math.ceil(ms / 1000));
      return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
    }
    function fetchMore() {
      if (st.loading) return st.loading;
      const seen = st.queue.map(p => p.id).join(",");
      st.loading = fetch(`${cfg.batchUrl}?start=${cfg.start}&offset=${st.queue.length}&n=12&exclude=${seen}`)
        .then(r => r.json()).then(d => { st.queue.push(...d.puzzles); st.loading = null; })
        .catch(() => { st.loading = null; });
      return st.loading;
    }
    function hearts() {
      $all("#sprint-hearts .icon").forEach((h, i) => h.classList.toggle("lost", i < st.mistakes));
    }
    function pulse(ok) {
      if (!flash || !motionOK()) return;
      flash.className = "sprint-flash " + (ok ? "ok" : "ko");
      void flash.offsetWidth;
      flash.classList.add("on");
    }
    function load() {
      if (!st || st.over) return;
      if (st.queue.length - st.idx < 5) fetchMore();
      const p = st.queue[st.idx];
      if (!p) { (st.loading || fetchMore()).then(() => { if (st.queue[st.idx]) load(); else end("Plus d'exercices disponibles !"); }); return; }
      st.p = p; st.step = 0; st.busy = true;
      $("#turn-bar").innerHTML = `<span class="side side-${p.color}"></span><b>${p.color === "w" ? "Les Blancs" : "Les Noirs"} jouent</b><span class="spacer"></span><span class="badge">exercice ${st.idx + 1} · ${p.rating}</span>`;
      board.render(p.start_fen, { orientation: p.color });
      setTimeout(() => {
        if (st.over || st.p !== p) return;
        board.render(p.setup.fen, { orientation: p.color, movers: moversFor(p.setup.uci, p.start_fen), lastMove: squaresOf(p.setup.uci), check: checkSquare(p.setup.san, p.setup.fen) });
        st.busy = false;
        enable();
      }, 280);
    }
    function enable() {
      const step = st.p.steps[st.step];
      board.enableInput({ color: st.p.color, legal: Object.keys(step.legal), onMove, choosePromotion: promotionPicker($("#promo"), pieces, st.p.color) });
    }
    function result(ok) {
      st.results.push({ id: st.p.id, ok, rating: st.p.rating });
      if (ok) { st.score++; st.bestRating = Math.max(st.bestRating || 0, st.p.rating); } else { st.mistakes++; hearts(); }
      $("#sprint-score").textContent = st.score;
      $("#sprint-strip").innerHTML = st.results.map(r => `<span class="sess ${r.ok ? "ok" : "ko"}">${r.ok ? "✓" : "✗"}</span>`).join("");
      pulse(ok);
      if (st.mistakes >= cfg.maxMistakes) return end(`${cfg.maxMistakes} erreurs : la course s'arrête.`);
      st.idx++;
      setTimeout(load, ok ? 250 : 650);
    }
    function onMove(uci, info) {
      if (!st || st.over || st.busy) return;
      const p = st.p, step = p.steps[st.step], mv = step.legal[uci];
      if (!mv) return;
      const ok = step.accept.includes(uci) || mv.mate;
      board.disableInput();
      board.render(mv.fen, { orientation: p.color, movers: info && info.dragged ? null : moversFor(uci, step.fen), lastMove: squaresOf(uci), check: checkSquare(mv.san, mv.fen), badge: { sq: uci.slice(2, 4), cls: ok ? "best" : "blunder" } });
      if (!ok) { st.busy = true; return result(false); }
      if (mv.mate || st.step === p.steps.length - 1) { st.busy = true; return result(true); }
      st.busy = true;
      setTimeout(() => {
        if (st.over || st.p !== p) return;
        const r = step.reply;
        board.render(r.fen, { orientation: p.color, movers: moversFor(r.uci, mv.fen), lastMove: squaresOf(r.uci), check: checkSquare(r.san, r.fen) });
        st.step++;
        st.busy = false;
        enable();
      }, 260);
    }
    function tick() {
      const left = st.end - Date.now();
      $("#sprint-clock").textContent = fmtTime(left);
      $("#sprint-clock").classList.toggle("low", left < 20000);
      if (left <= 0) end("Temps écoulé !");
    }
    function end(reason) {
      if (!st || st.over) return;
      st.over = true;
      clearInterval(st.timer);
      board.disableInput();
      liveEl.hidden = true;
      overEl.hidden = false;
      overEl.innerHTML = `<div class="sprint-final"><div class="kpi-label">${esc(reason)}</div><div class="sprint-big">${st.score}</div><div class="muted">exercice${st.score > 1 ? "s" : ""} résolu${st.score > 1 ? "s" : ""}</div><div id="sprint-record" class="small" style="margin-top:.4rem"></div></div>` +
        `<div class="sprint-review">${st.results.map((r, i) => `<a class="sess ${r.ok ? "ok" : "ko"}" href="${cfg.playUrl}?id=${r.id}" title="Exercice ${i + 1} (${r.rating}) : le revoir">${r.ok ? "✓" : "✗"}</a>`).join("")}</div>` +
        `<p class="faint small" style="margin:.3rem 0 0">Clique sur un exercice pour le refaire tranquillement.</p>` +
        `<div class="row row-tight" style="margin-top:1rem"><button type="button" class="btn btn-primary" data-again>${icon("refresh")} Rejouer</button><a class="btn btn-ghost" href="${location.pathname}">Changer de durée</a></div>`;
      $("[data-again]", overEl).addEventListener("click", () => start(st.duration));
      postJSON(cfg.resultUrl, { duration: st.duration, score: st.score, mistakes: st.mistakes, best_rating: st.bestRating || null })
        .then(d => { $("#sprint-record").innerHTML = d.record ? `<span class="badge badge-win">${icon("trophy")} Nouveau record !</span>` : `Record : <b>${d.best}</b>`; })
        .catch(() => {});
    }
    function start(duration) {
      if (st && st.timer) clearInterval(st.timer);
      st = { duration, queue: [], idx: 0, score: 0, mistakes: 0, results: [], over: false, loading: null, bestRating: 0 };
      startEl.hidden = true; overEl.hidden = true; liveEl.hidden = false;
      $("#sprint-score").textContent = "0"; $("#sprint-strip").innerHTML = ""; hearts();
      $("#sprint-clock").textContent = fmtTime(duration * 1000);
      fetchMore().then(() => {
        st.end = Date.now() + duration * 1000;
        st.timer = setInterval(tick, 200);
        load();
      });
    }
    $all("[data-duration]").forEach(b => b.addEventListener("click", () => start(parseInt(b.dataset.duration, 10))));
  }

  // ================================================================ parties de référence
  function initReference() {
    const data = JSON.parse($("#ref-data").textContent);
    const pieces = JSON.parse($("#pieces-data").textContent);
    const boardEl = $("#board"), board = createBoard(boardEl, pieces);
    const info = $("#move-info"), list = $("#movelist");
    const N = data.fens.length - 1;
    let orientation = data.orientation, k = -1, timer = null, guess = null;
    const panelTabs = tabs("ref", { scope: $(".panel") });

    let html = "";
    data.moves.forEach((m, idx) => {
      const n = m.label.match(/^\d+/)[0];
      if (idx === 0 && m.color === "b") html += `<span class="no">${n}.</span><span></span>`;
      if (m.color === "w") html += `<span class="no">${n}.</span>`;
      html += `<span class="mv ${m.note ? "has-note" : ""}" data-k="${m.i + 1}" role="button" tabindex="-1">${m.note ? '<span class="dot" style="--cls-c:var(--accent)"></span>' : ""}<span>${esc(m.san)}</span></span>`;
    });
    list.innerHTML = html;
    list.addEventListener("click", ev => { const t = ev.target.closest(".mv"); if (t && !guess) { stop(); go(parseInt(t.dataset.k, 10)); } });

    function bubble(msg) {
      const m = k > 0 ? data.moves[k - 1] : null;
      let h = "";
      if (msg) h += `<div class="cb-head"><span class="cls-icon" style="--cls-c:${msg.color || "var(--accent)"}">${icon(msg.icon || "target")}</span><div><div class="cb-title">${msg.title}</div>${msg.sub ? `<div class="cb-sub">${msg.sub}</div>` : ""}</div></div>`;
      if (!m && !msg) {
        h = `<div class="cb-head"><span class="cls-icon" style="--cls-c:var(--accent)">${icon("book")}</span><div><div class="cb-title">Position de départ</div><div class="cb-sub">${esc(data.players.w.name)} – ${esc(data.players.b.name)}</div></div></div>` +
          `<p class="cb-empty" style="margin:.7rem 0 0">Avance coup par coup : les moments clés sont commentés. Ou essaie le mode « devine le coup ».</p>`;
      } else if (m) {
        if (!msg) h += `<div class="cb-head"><span class="cls-icon" style="--cls-c:${m.note ? "var(--accent)" : "var(--border-strong)"}">${icon(m.note ? "bulb" : "next")}</span><div><div class="cb-title"><span class="mono">${esc(m.label)}</span></div><div class="cb-sub">${m.color === "w" ? esc(data.players.w.name) : esc(data.players.b.name)}</div></div></div>`;
        if (m.note) h += `<p style="margin:.7rem 0 0">${esc(m.note)}</p>`;
        if (k === N) h += `<p class="cb-empty" style="margin:.6rem 0 0">Fin de la partie : ${esc(data.result)}.</p>`;
      }
      info.innerHTML = h;
    }
    function go(newK, opts) {
      opts = opts || {};
      newK = Math.max(0, Math.min(N, newK));
      if (newK === k && !opts.force) return;
      let movers = null;
      if (!opts.force && k >= 0 && Math.abs(newK - k) === 1) {
        if (newK > k) movers = moversFor(data.moves[newK - 1].uci, data.fens[k]);
        else movers = moversFor(data.moves[k - 1].uci, data.fens[newK]).map(mv => ({ from: mv.to, to: mv.from }));
      }
      k = newK;
      const m = k > 0 ? data.moves[k - 1] : null;
      board.render(data.fens[k], {
        orientation, movers, lastMove: m ? squaresOf(m.uci) : [], check: m ? checkSquare(m.san, data.fens[k]) : null,
        badge: opts.badge ? { sq: m.uci.slice(2, 4), cls: opts.badge } : null,
      });
      $all(".mv", list).forEach(e => {
        const kk = parseInt(e.dataset.k, 10);
        e.classList.toggle("current", kk === k);
        e.classList.toggle("future", !!guess && kk > k);
      });
      const cur = list.querySelector(".mv.current");
      if (cur) scrollIntoBox(cur);
      $all(".moment").forEach(el => el.classList.toggle("current", parseInt(el.dataset.goto, 10) === k));
      const top = orientation === "w" ? "b" : "w";
      simpleBar($("#bar-top"), top, data.players[top].name, data.fens[k], { you: guess && top === data.hero, over: k === N });
      simpleBar($("#bar-bottom"), orientation, data.players[orientation].name, data.fens[k], { you: guess && orientation === data.hero, over: k === N });
      bubble(opts.msg);
      updatePlay();
      if (guess) guessTurn();
    }

    // Lecture automatique
    const playBtn = $('[data-nav="play"]');
    function updatePlay() { if (playBtn) $("use", playBtn).setAttribute("href", timer ? "#i-pause" : "#i-play"); }
    function stop() { if (timer) { clearInterval(timer); timer = null; updatePlay(); } }
    function play() {
      if (guess) return;
      if (timer) return stop();
      if (k >= N) go(0);
      timer = setInterval(() => { if (k >= N) stop(); else go(k + 1); }, 1100);
      updatePlay();
    }

    // Mode « devine le coup »
    const toggle = $("#guess-toggle"), guessBar = $("#guess-bar");
    function guessScore() { $("#guess-score").textContent = `${guess.correct} / ${guess.total}`; }
    function guessTurn() {
      board.disableInput();
      if (k >= N) {
        const pct = guess.total ? Math.round(100 * guess.correct / guess.total) : 0;
        bubble({ title: `Score : ${guess.correct} / ${guess.total} (${pct} %)`, sub: "Bravo d'être allé jusqu'au bout ! Rejoue la partie pour améliorer ton score.", icon: "trophy", color: "var(--c-best)" });
        const url = $("#study-done") && $("#study-done").dataset.url;
        if (url && guess.total) postJSON(url, { guess_total: guess.total, guess_correct: guess.correct }).catch(() => {});
        return;
      }
      const m = data.moves[k];
      if (m.color !== data.hero || !m.legal) {
        guess.timer = setTimeout(() => go(k + 1), 900);
        return;
      }
      const who = data.players[data.hero].name;
      if (!info.querySelector(".guess-feedback")) {
        const p = document.createElement("p");
        p.className = "cb-empty guess-feedback";
        p.style.margin = ".7rem 0 0";
        p.innerHTML = `${icon("target")} À toi : quel coup a joué <b>${esc(who)}</b> ?`;
        info.appendChild(p);
      }
      board.enableInput({
        color: data.hero, legal: m.legal, choosePromotion: promotionPicker($("#promo"), pieces, data.hero),
        onMove(uci) {
          guess.total++;
          const ok = uci === m.uci;
          if (ok) guess.correct++;
          guessScore();
          const msg = ok
            ? { title: `Bien vu : ${esc(m.label)}`, icon: "check", color: "var(--c-best)" }
            : { title: `${esc(who)} a joué ${esc(m.label)}`, sub: "Pas tout à fait : compare avec ton idée.", icon: "x", color: "var(--c-mistake)" };
          go(k + 1, { msg, badge: ok ? "best" : null });
        },
      });
    }
    function setGuess(on) {
      stop();
      if (guess && guess.timer) clearTimeout(guess.timer);
      guess = on ? { correct: 0, total: 0 } : null;
      toggle.classList.toggle("active", on);
      toggle.setAttribute("aria-pressed", String(on));
      guessBar.hidden = !on;
      if (on) {
        orientation = data.hero;
        guessScore();
        if (panelTabs) panelTabs.activate("moves");
        go(0, { force: true });
      } else {
        board.disableInput();
        go(k, { force: true });
      }
    }
    if (toggle) toggle.addEventListener("click", () => setGuess(!guess));

    $all("[data-nav]").forEach(b => b.addEventListener("click", () => {
      const a = b.dataset.nav;
      if (a === "play") return play();
      if (a === "flip") { orientation = orientation === "w" ? "b" : "w"; return go(k, { force: true }); }
      if (guess) return;
      stop();
      if (a === "first") go(0); else if (a === "prev") go(k - 1); else if (a === "next") go(k + 1); else if (a === "last") go(N);
    }));
    document.addEventListener("keydown", ev => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (ev.key === "f" || ev.key === "F") { orientation = orientation === "w" ? "b" : "w"; go(k, { force: true }); return; }
      if (guess) return;
      const map = { ArrowLeft: () => go(k - 1), ArrowRight: () => go(k + 1), Home: () => go(0), End: () => go(N) };
      if (ev.key === " " && document.activeElement.tagName !== "BUTTON") { play(); ev.preventDefault(); }
      else if (map[ev.key]) { stop(); map[ev.key](); ev.preventDefault(); }
    });
    $all("[data-goto]").forEach(el => el.addEventListener("click", () => {
      if (guess) setGuess(false);
      stop(); go(parseInt(el.dataset.goto, 10));
      if (window.innerWidth <= 980) boardEl.scrollIntoView({ behavior: motionOK() ? "smooth" : "auto", block: "center" });
    }));
    const done = $("#study-done");
    if (done) done.addEventListener("click", () => {
      postJSON(done.dataset.url, { completed: true }).then(() => {
        done.disabled = true; done.classList.remove("btn-primary");
        done.innerHTML = `${icon("check")} Partie étudiée`;
      }).catch(() => {});
    });
    if (panelTabs) panelTabs.activate("lessons");
    go(0, { force: true });
  }

  initCommon();
  initAppearance();
  window.ChessCoach = {
    initJobPanel, initGameJob, initGameFilters, initEloChart, initGame, initHome, initDashboard,
    initPuzzle, initReference, initTrainingHome, initRatingChart, initSprint,
  };
})();
