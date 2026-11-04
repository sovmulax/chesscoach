/* Chess Coach — JavaScript sans dépendance : échiquier SVG, courbes, suivi des analyses. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const CLS_COLORS = {
    best: "var(--c-best)", good: "var(--c-good)", inaccuracy: "var(--c-inaccuracy)",
    mistake: "var(--c-mistake)", blunder: "var(--c-blunder)",
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function fmt(n, d) { return n == null ? "—" : Number(n).toFixed(d == null ? 0 : d).replace(".", ","); }

  // ---------------------------------------------------------------- suivi des tâches
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
      $("#job-bar").style.width = d.pct + "%";
      $("#job-count").textContent = d.done + " / " + d.total + " parties analysées";
      if (d.message) $("#job-message").textContent = d.message;
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

  // ---------------------------------------------------------------- filtres de la liste
  function initGameFilters() {
    const rows = $all("#games-table tr[data-q]");
    const q = $("#f-q"), color = $("#f-color"), result = $("#f-result"), status = $("#f-status"), bl = $("#f-blunder");
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
        r.style.display = ok ? "" : "none";
        if (ok) n++;
      });
      $("#f-count").textContent = n + " partie(s)";
    }
    [q, color, result, status, bl].forEach(el => el.addEventListener("input", apply));
    apply();
  }

  // ---------------------------------------------------------------- courbes
  function lineChart(container, values, opts) {
    opts = opts || {};
    const W = Math.max(300, Math.round(container.clientWidth || 640)), H = opts.height || 170, P = { l: 36, r: 10, t: 10, b: 22 };
    const n = values.length;
    if (!n) return null;
    const min = opts.min != null ? opts.min : Math.min.apply(null, values);
    const max = opts.max != null ? opts.max : Math.max.apply(null, values);
    const span = max - min || 1;
    const x = i => P.l + (n === 1 ? 0 : i * (W - P.l - P.r) / (n - 1));
    const y = v => P.t + (1 - (v - min) / span) * (H - P.t - P.b);
    const pts = values.map((v, i) => x(i).toFixed(1) + "," + y(v).toFixed(1));
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "")}">`;
    (opts.gridValues || [min, (min + max) / 2, max]).forEach(g => {
      s += `<line class="grid-line" x1="${P.l}" x2="${W - P.r}" y1="${y(g)}" y2="${y(g)}"/>`;
      s += `<text x="${P.l - 6}" y="${y(g) + 4}" text-anchor="end">${esc(opts.gridFormat ? opts.gridFormat(g) : Math.round(g))}</text>`;
    });
    if (opts.area) s += `<polygon class="area" points="${x(0)},${y(min)} ${pts.join(" ")} ${x(n - 1)},${y(min)}"/>`;
    s += `<polyline class="line" points="${pts.join(" ")}"/>`;
    (opts.markers || []).forEach(m => {
      s += `<circle cx="${x(m.i)}" cy="${y(values[m.i])}" r="4.5" fill="${m.color}" stroke="var(--surface)" stroke-width="1.5"><title>${esc(m.title || "")}</title></circle>`;
    });
    if (opts.xLabels) opts.xLabels.forEach(l => { s += `<text x="${x(l.i)}" y="${H - 6}" text-anchor="${l.anchor || "middle"}">${esc(l.text)}</text>`; });
    s += `<line class="cursor" id="${opts.cursorId || "chart-cursor"}" x1="-10" x2="-10" y1="${P.t}" y2="${H - P.b}"/>`;
    s += `<rect x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}" fill="transparent" class="hit"/>`;
    s += "</svg>";
    container.innerHTML = s;
    const svg = container.querySelector("svg");
    return {
      svg, x,
      indexFromEvent(ev) {
        const r = svg.getBoundingClientRect();
        const px = (ev.clientX - r.left) * W / r.width;
        return Math.max(0, Math.min(n - 1, Math.round((px - P.l) * (n - 1) / (W - P.l - P.r))));
      },
      setCursor(i) {
        const c = svg.querySelector(".cursor");
        c.setAttribute("x1", x(i)); c.setAttribute("x2", x(i));
      },
    };
  }

  function initEloChart() {
    const el = $("#elo-chart"), dataEl = $("#elo-data");
    if (!el || !dataEl) return;
    const series = JSON.parse(dataEl.textContent);
    if (series.length < 2) return;
    const vals = series.map(p => p[1]);
    const d = s => (s || "").slice(0, 10).split("-").reverse().join("/");
    lineChart(el, vals, {
      label: "Évolution de l'Elo", area: false,
      xLabels: [{ i: 0, text: d(series[0][0]), anchor: "start" }, { i: series.length - 1, text: d(series[series.length - 1][0]), anchor: "end" }],
    });
  }

  // ---------------------------------------------------------------- échiquier
  function squareXY(sq, orientation) {
    const f = sq.charCodeAt(0) - 97, rank = parseInt(sq[1], 10);
    let x = f, y = 8 - rank;
    if (orientation === "b") { x = 7 - x; y = 7 - y; }
    return [x, y];
  }

  function arrowSvg(uci, orientation, color) {
    if (!uci) return "";
    const [x1, y1] = squareXY(uci.slice(0, 2), orientation), [x2, y2] = squareXY(uci.slice(2, 4), orientation);
    const ax = x1 * 45 + 22.5, ay = y1 * 45 + 22.5, bx = x2 * 45 + 22.5, by = y2 * 45 + 22.5;
    const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
    const head = 15, ex = bx - ux * head, ey = by - uy * head, px = -uy, py = ux;
    return `<g opacity=".82"><line x1="${ax}" y1="${ay}" x2="${ex}" y2="${ey}" stroke="${color}" stroke-width="8" stroke-linecap="round"/>` +
      `<polygon points="${bx},${by} ${ex + px * 11},${ey + py * 11} ${ex - px * 11},${ey - py * 11}" fill="${color}"/></g>`;
  }

  function renderBoard(el, fen, orientation, pieces, opts) {
    opts = opts || {};
    const rows = fen.split(" ")[0].split("/");
    let s = `<svg viewBox="0 0 360 360" xmlns="${NS}" role="img" aria-label="Échiquier">`;
    for (let r = 0; r < 8; r++) for (let f = 0; f < 8; f++) {
      const light = (r + f) % 2 === 0;
      s += `<rect x="${f * 45}" y="${r * 45}" width="45" height="45" fill="${light ? "#ede6d6" : "#9c7b5b"}"/>`;
    }
    (opts.highlight || []).forEach(sq => {
      const [x, y] = squareXY(sq, orientation);
      s += `<rect x="${x * 45}" y="${y * 45}" width="45" height="45" fill="#e8c547" opacity=".45"/>`;
    });
    rows.forEach((row, r) => {
      let f = 0;
      for (const ch of row) {
        if (/\d/.test(ch)) { f += parseInt(ch, 10); continue; }
        const sq = String.fromCharCode(97 + f) + (8 - r);
        const [x, y] = squareXY(sq, orientation);
        const p = (pieces[ch] || "").replace(/\sid="[^"]*"/g, "");
        s += `<g transform="translate(${x * 45},${y * 45})">${p}</g>`;
        f++;
      }
    });
    for (let i = 0; i < 8; i++) {
      const file = orientation === "b" ? String.fromCharCode(104 - i) : String.fromCharCode(97 + i);
      const rank = orientation === "b" ? i + 1 : 8 - i;
      s += `<text x="${i * 45 + 41}" y="357" font-size="8" text-anchor="end" fill="${i % 2 ? "#ede6d6" : "#9c7b5b"}" font-family="sans-serif">${file}</text>`;
      s += `<text x="2" y="${i * 45 + 10}" font-size="8" fill="${i % 2 ? "#ede6d6" : "#9c7b5b"}" font-family="sans-serif">${rank}</text>`;
    }
    (opts.arrows || []).forEach(a => { s += arrowSvg(a.uci, orientation, a.color); });
    s += "</svg>";
    el.innerHTML = s;
  }

  function initGame(startPly) {
    const dataEl = $("#game-data");
    if (!dataEl) return;
    const data = JSON.parse(dataEl.textContent);
    const boardEl = $("#board"), info = $("#move-info"), list = $("#movelist");
    let orientation = data.orientation, k = 0;
    const N = data.fens.length - 1;

    // Liste des coups
    let html = "";
    data.moves.forEach((m, idx) => {
      if (idx === 0 && m.i % 2 === 1) html += `<span class="no">${Math.floor(m.i / 2) + 1}.</span><span></span>`;
      if (m.i % 2 === 0) html += `<span class="no">${Math.floor(m.i / 2) + 1}.</span>`;
      const sym = m.symbol ? `<span class="t-${m.cls}">${m.symbol}</span>` : "";
      html += `<span class="mv ${m.cls ? "cls-" + m.cls : ""}" data-k="${m.i + 1}" title="${esc(m.cls_label || "")}">${m.cls ? '<span class="dot"></span>' : ""}${esc(m.san)}${sym}</span>`;
    });
    list.innerHTML = html;
    list.addEventListener("click", ev => { const t = ev.target.closest(".mv"); if (t) go(parseInt(t.dataset.k, 10)); });

    // Courbe
    let chart = null;
    const chartEl = $("#wp-chart");
    if (chartEl && data.wp) {
      const markers = data.moves.filter(m => m.mine && (m.cls === "blunder" || m.cls === "mistake"))
        .map(m => ({ i: m.i + 1, color: CLS_COLORS[m.cls], title: m.label + " " + (m.cls_label || "") }));
      chart = lineChart(chartEl, data.wp, {
        min: 0, max: 100, area: true, height: 160, gridValues: [0, 50, 100], gridFormat: v => v + " %",
        markers, label: "Tes chances de gain coup par coup",
      });
      chart.svg.addEventListener("click", ev => go(chart.indexFromEvent(ev)));
    }

    function go(newK) {
      k = Math.max(0, Math.min(N, newK));
      const m = k > 0 ? data.moves[k - 1] : null;
      const arrows = [];
      if (m) {
        arrows.push({ uci: m.uci, color: m.cls ? CLS_COLORS[m.cls] : "#4a7fa8" });
        if (m.best_uci && m.best_uci !== m.uci && ["inaccuracy", "mistake", "blunder"].includes(m.cls)) {
          arrows.push({ uci: m.best_uci, color: "#3e9b5f" });
        }
      }
      renderBoard(boardEl, data.fens[k], orientation, data.pieces, {
        arrows, highlight: m ? [m.uci.slice(0, 2), m.uci.slice(2, 4)] : [],
      });
      $all(".mv.current", list).forEach(e => e.classList.remove("current"));
      const cur = list.querySelector(`.mv[data-k="${k}"]`);
      if (cur) { cur.classList.add("current"); cur.scrollIntoView({ block: "nearest" }); }
      if (chart) chart.setCursor(k);
      const bar = $("#evalbar-fill");
      if (bar && data.wp) bar.style.height = data.wp[k] + "%";
      if (!m) { info.innerHTML = '<span class="muted">Position de départ. Utilise les flèches du clavier ou clique sur un coup.</span>'; return; }
      let h = `<div class="row" style="gap:.5rem"><b>${esc(m.label)}${m.symbol ? `<span class="t-${m.cls}">${m.symbol}</span>` : ""}</b>`;
      if (m.cls) h += `<span class="badge" style="color:${CLS_COLORS[m.cls]}">${esc(m.cls_label)}</span>`;
      if (m.mine === true) h += '<span class="faint">ton coup</span>'; else if (m.mine === false) h += '<span class="faint">coup adverse</span>';
      if (m.wp_after != null) h += `<span class="spacer"></span><span class="muted">tes chances : ${fmt(data.wp[k])} %</span>`;
      h += "</div>";
      if (m.explain && m.explain.length) h += "<ul style='margin:.4rem 0 0;padding-left:1.1rem'>" + m.explain.map(t => `<li>${esc(t)}</li>`).join("") + "</ul>";
      else if (["inaccuracy", "mistake", "blunder"].includes(m.cls) && m.best && m.best !== m.san) h += `<p class="muted" style="margin:.4rem 0 0">Meilleur selon Stockfish : ${esc(m.best)}</p>`;
      info.innerHTML = h;
    }

    $all("[data-nav]").forEach(b => b.addEventListener("click", () => {
      const a = b.dataset.nav;
      if (a === "first") go(0); else if (a === "prev") go(k - 1); else if (a === "next") go(k + 1);
      else if (a === "last") go(N); else if (a === "flip") { orientation = orientation === "w" ? "b" : "w"; go(k); }
    }));
    document.addEventListener("keydown", ev => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
      if (ev.key === "ArrowLeft") { go(k - 1); ev.preventDefault(); }
      else if (ev.key === "ArrowRight") { go(k + 1); ev.preventDefault(); }
      else if (ev.key === "Home") go(0); else if (ev.key === "End") go(N);
    });
    $all("[data-goto]").forEach(el => el.addEventListener("click", () => {
      go(parseInt(el.dataset.goto, 10));
      boardEl.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    go(startPly != null ? startPly : 0);
  }

  window.ChessCoach = { initJobPanel, initGameJob, initGameFilters, initEloChart, initGame };
})();
