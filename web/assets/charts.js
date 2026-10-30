/* xC charts: small hand-drawn SVG and canvas helpers. No dependencies. Every number drawn here comes from the report object. */
(function (w) {
  const C = { a: "#2f49d4", b: "#d98f1f", both: "#1c7a5a", risk: "#b3243f", ink: "#161b24", ink2: "#4b5363", ink3: "#7b8394", rule: "#dfe2e8", soft: "#eceef3" };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (m) => (m && typeof m.value === "number" ? m.value : null);

  function usd(n) {
    if (n == null) return "n/a";
    const a = Math.abs(n);
    if (a >= 1e9) return "$" + (n / 1e9).toFixed(a >= 1e10 ? 0 : 1) + "B";
    if (a >= 1e6) return "$" + (n / 1e6).toFixed(a >= 1e8 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (a >= 1e3) return "$" + Math.round(n / 1e3) + "K";
    return "$" + Math.round(n);
  }
  const pct = (n, d = 0) => (n == null ? "n/a" : n.toFixed(d) + "%");

  /* Provenance mark: filled = measured from Qloo, half = modeled by xC, hollow = assumed. */
  function prov(p) {
    const t = { measured: "Measured from Qloo", modeled: "Modeled by xC from measured inputs", assumed: "Assumption, stated and adjustable" }[p] || p;
    const body = p === "measured" ? `<circle cx="6" cy="6" r="4.5" fill="${C.ink}"/>`
      : p === "modeled" ? `<circle cx="6" cy="6" r="4.5" fill="none" stroke="${C.ink}" stroke-width="1.4"/><path d="M6 1.5a4.5 4.5 0 0 0 0 9z" fill="${C.ink}"/>`
      : `<circle cx="6" cy="6" r="4.5" fill="none" stroke="${C.ink}" stroke-width="1.4"/>`;
    return `<svg class="prov" width="12" height="12" viewBox="0 0 12 12" role="img" aria-label="${esc(t)}"><title>${esc(t)}</title>${body}</svg>`;
  }

  /* Histogram of IP value at risk. dist = {lo,hi,counts,mean,p5,p95}; live=true while running. */
  function histogram(d, o = {}) {
    const W = 760, H = o.h || 210, L = 8, R = 8, T = 18, B = 34;
    const n = d.counts.length, bw = (W - L - R) / n, max = Math.max(1, ...d.counts);
    const x = (v) => L + ((v - d.lo) / (d.hi - d.lo)) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Distribution of IP value at risk across simulation runs">`;
    if (d.p5 != null && d.p95 != null) s += `<rect x="${x(d.p5)}" y="${T - 8}" width="${Math.max(2, x(d.p95) - x(d.p5))}" height="${H - T - B + 8}" fill="${C.a}" opacity=".07" rx="6"/>`;
    d.counts.forEach((c, i) => {
      const h = (c / max) * (H - T - B), mid = d.lo + ((i + 0.5) / n) * (d.hi - d.lo);
      const tail = d.p95 != null && mid > d.p95;
      s += `<rect x="${L + i * bw + 1.5}" y="${H - B - h}" width="${bw - 3}" height="${Math.max(0, h)}" rx="3" fill="${tail ? C.risk : C.a}" opacity="${tail ? 0.85 : 0.9}"/>`;
    });
    s += `<line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="${C.rule}"/>`;
    const step = (d.hi - d.lo) / 4;
    for (let i = 0; i <= 4; i++) { const v = d.lo + i * step; s += `<text x="${x(v)}" y="${H - 12}" font-size="12" fill="${C.ink3}" text-anchor="${i === 0 ? "start" : i === 4 ? "end" : "middle"}">${v.toFixed(0)}%</text>`; }
    if (d.mean != null) s += `<line x1="${x(d.mean)}" x2="${x(d.mean)}" y1="${T - 6}" y2="${H - B}" stroke="${C.ink}" stroke-width="1.5" stroke-dasharray="3 3"/><text x="${Math.min(W - 70, x(d.mean) + 6)}" y="${T}" font-size="12.5" fill="${C.ink}" font-weight="600">mean ${d.mean.toFixed(1)}%</text>`;
    return s + `</svg>`;
  }

  /* Low / base / high range. The scale is zoomed to the range so the three marks never collide. */
  function rangeBar(lo, base, hi) {
    if (lo == null || base == null || hi == null) return `<p class="working">The dollar range could not be computed from the data returned.</p>`;
    const W = 760, H = 92, pad = 70, span = Math.max(hi - lo, hi * 0.04), min = lo - span * 1.1, max = hi + span * 0.9, x = (v) => pad + ((v - min) / (max - min)) * (W - 2 * pad);
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Expansion range from ${usd(lo)} to ${usd(hi)}, base ${usd(base)}">
      <rect x="${pad}" y="42" width="${W - 2 * pad}" height="10" rx="5" fill="${C.soft}"/>
      <rect x="${x(lo)}" y="42" width="${x(hi) - x(lo)}" height="10" rx="5" fill="${C.a}" opacity=".28"/>
      <rect x="${x(lo)}" y="42" width="${x(base) - x(lo)}" height="10" rx="5" fill="${C.a}"/>
      <circle cx="${x(base)}" cy="47" r="10" fill="#fff" stroke="${C.a}" stroke-width="3"/>
      <text x="${x(base)}" y="24" font-size="16" fill="${C.ink}" font-weight="600" text-anchor="middle">base ${usd(base)}</text>
      <line x1="${x(lo)}" x2="${x(lo)}" y1="40" y2="60" stroke="${C.ink3}"/><line x1="${x(hi)}" x2="${x(hi)}" y1="40" y2="60" stroke="${C.ink3}"/>
      <text x="${x(lo)}" y="80" font-size="13" fill="${C.ink2}" text-anchor="middle">low ${usd(lo)}</text>
      <text x="${x(hi)}" y="80" font-size="13" fill="${C.ink2}" text-anchor="middle">high ${usd(hi)}</text></svg>`;
  }

  /* Sensitivity bars around the base case. */
  const SENS = { penetration_rate: "How many customers convert", annual_spend_per_customer_usd: "Spend per customer", regional_populations: "Size of each market", regional_affinity: "Strength of regional fit", ip_loss: "Value lost to fan rebellion" };
  function tornado(sens, base) {
    if (!sens || !sens.length || base == null) return "";
    const rows = sens.map((r) => ({ k: r.assumption_key, lo: Math.min(r.low_usd, r.high_usd), hi: Math.max(r.low_usd, r.high_usd) })).sort((p, q) => (q.hi - q.lo) - (p.hi - p.lo));
    const W = 760, rh = 34, H = rows.length * rh + 28, L = 230, R = 70;
    const min = Math.min(...rows.map((r) => r.lo)), max = Math.max(...rows.map((r) => r.hi));
    const x = (v) => L + ((v - min) / (max - min || 1)) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="How the base case moves when each assumption changes">`;
    rows.forEach((r, i) => {
      const y = 12 + i * rh;
      s += `<text x="0" y="${y + 14}" font-size="13" fill="${C.ink2}">${esc(SENS[r.k] || r.k)}</text>`;
      s += `<rect x="${x(r.lo)}" y="${y + 2}" width="${Math.max(3, x(r.hi) - x(r.lo))}" height="16" rx="8" fill="${C.a}" opacity=".85"/>`;
      s += `<text x="${x(r.lo) - 6}" y="${y + 15}" font-size="12" fill="${C.ink3}" text-anchor="end">${usd(r.lo)}</text><text x="${x(r.hi) + 6}" y="${y + 15}" font-size="12" fill="${C.ink3}">${usd(r.hi)}</text>`;
    });
    s += `<line x1="${x(base)}" x2="${x(base)}" y1="2" y2="${H - 14}" stroke="${C.ink}" stroke-dasharray="3 3"/><text x="${x(base)}" y="${H - 1}" font-size="12" fill="${C.ink}" text-anchor="middle">base ${usd(base)}</text></svg>`;
    return s;
  }

  /* Age indices for the two audiences. Signed: positive = over-indexes against the baseline. */
  const AGE = { "24_and_younger": "24 and under", "25_to_29": "25 to 29", "30_to_34": "30 to 34", "35_to_44": "35 to 44", "45_to_54": "45 to 54", "55_and_older": "55 and over" };
  function ages(da, db, nameA, nameB) {
    const A = (da && da.age) || [], B = (db && db.age) || [];
    if (!A.length && !B.length) return `<p class="working">Audience age data was not returned for this pair.</p>`;
    const keys = (A.length ? A : B).map((r) => r.bucket);
    const val = (arr, k) => { const r = (arr || []).find((x) => x.bucket === k); return r ? r.share * 100 : null; };
    const W = 440, rh = 38, H = keys.length * rh + 30, mid = 230, sc = 3.2;
    let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Audience age: over- and under-indexing for each brand">`;
    keys.forEach((k, i) => {
      const y = 6 + i * rh;
      s += `<text x="0" y="${y + 20}" font-size="12.5" fill="${C.ink2}">${AGE[k] || k}</text>`;
      [[val(A, k), C.a, 4], [val(B, k), C.b, 19]].forEach(([v, col, dy]) => {
        if (v == null) return;
        const w = Math.abs(v) * sc;
        s += `<rect x="${v >= 0 ? mid : mid - w}" y="${y + dy - 2}" width="${Math.max(1.5, w)}" height="11" rx="5.5" fill="${col}" opacity="${v >= 0 ? 0.95 : 0.4}"/>`;
      });
    });
    s += `<line x1="${mid}" x2="${mid}" y1="0" y2="${H - 26}" stroke="${C.ink3}" stroke-width="1"/>`;
    s += `<text x="${mid - 8}" y="${H - 6}" font-size="12" fill="${C.ink3}" text-anchor="end">fewer than average</text><text x="${mid + 8}" y="${H - 6}" font-size="12" fill="${C.ink3}">more than average</text></svg>`;
    return s;
  }

  /* Proportional tag bar: only A, shared, only B. */
  function tagBar(c) {
    const t = (c.a_only || 0) + (c.shared || 0) + (c.b_only || 0) || 1;
    const seg = (v, col) => `<i style="flex:${Math.max(v, t * 0.015)};background:${col}"></i>`;
    return `<div style="display:flex;height:14px;border-radius:14px;overflow:hidden;gap:3px">${seg(c.a_only, C.a)}${seg(c.shared, C.both)}${seg(c.b_only, C.b)}</div>
      <div style="display:flex;justify-content:space-between;font-size:13px;color:${C.ink2};margin-top:8px"><span>${c.a_only} only one brand</span><span>${c.shared} shared</span><span>${c.b_only} only the other</span></div>`;
  }

  /* Heat panel. Cells carry hot values for A and B (0..1 inside the area). Light adds up: white = both brands hot. */
  function drawHeat(canvas, heat) {
    const cells = (heat && heat.cells) || [];
    const dpr = Math.min(2, window.devicePixelRatio || 1), cw = canvas.clientWidth || 360, ch = canvas.clientHeight || 270;
    canvas.width = cw * dpr; canvas.height = ch * dpr;
    const g = canvas.getContext("2d");
    g.scale(dpr, dpr);
    g.fillStyle = "#12162b"; g.fillRect(0, 0, cw, ch);
    g.strokeStyle = "#ffffff10"; g.lineWidth = 1;
    for (let i = 1; i < 8; i++) { g.beginPath(); g.moveTo((cw / 8) * i, 0); g.lineTo((cw / 8) * i, ch); g.stroke(); g.beginPath(); g.moveTo(0, (ch / 6) * i); g.lineTo(cw, (ch / 6) * i); g.stroke(); }
    if (!cells.length) { g.fillStyle = "#7f87ad"; g.font = "13px sans-serif"; g.fillText("No heatmap cells returned", 18, ch / 2); return; }
    const la = cells.map((c) => c.lat), lo = cells.map((c) => c.lon);
    const minLa = Math.min(...la), maxLa = Math.max(...la), minLo = Math.min(...lo), maxLo = Math.max(...lo);
    const px = (c) => 24 + ((c.lon - minLo) / (maxLo - minLo || 1)) * (cw - 48);
    const py = (c) => ch - 24 - ((c.lat - minLa) / (maxLa - minLa || 1)) * (ch - 48);
    g.globalCompositeOperation = "lighter";
    const blob = (c, v, rgb) => {
      if (v < 0.12) return;
      const r = 9 + v * 8, gr = g.createRadialGradient(px(c), py(c), 0, px(c), py(c), r);
      gr.addColorStop(0, `rgba(${rgb},${0.09 * v})`); gr.addColorStop(1, `rgba(${rgb},0)`);
      g.fillStyle = gr; g.beginPath(); g.arc(px(c), py(c), r, 0, 6.2832); g.fill();
    };
    cells.forEach((c) => { blob(c, c.a, "70,100,255"); blob(c, c.b, "255,170,50"); });
    g.globalCompositeOperation = "source-over";
  }

  w.XCharts = { esc, num, usd, pct, prov, histogram, rangeBar, tornado, ages, tagBar, drawHeat, C };
})(window);
