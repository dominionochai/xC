/* xC dashboard. One renderer fed by one event stream: live (SSE from the backend) or a recorded run (synthetic, labelled). */
(function () {
  const X = window.XCharts, esc = X.esc, num = X.num, usd = X.usd;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const API = "/api/xc";
  const PHASES = ["NORMALIZATION", "GRAPH_QUERYING", "BRIDGE_DISCOVERY", "ADVERSARIAL_AUDIT", "SYNTHESIS"];
  const PHASE_NAME = { NORMALIZATION: "Match the brands", GRAPH_QUERYING: "Read the taste graph", BRIDGE_DISCOVERY: "Find a bridge", ADVERSARIAL_AUDIT: "Simulate the backlash", SYNTHESIS: "Price the deal" };
  const VERDICT = { proceed: ["Proceed", "good"], proceed_with_remediation: ["Proceed with remediation", "warn"], high_risk: ["High risk", "risk"], insufficient_data: ["Insufficient data", ""] };
  const params = new URLSearchParams(location.search);
  const S = { mode: "recorded", speed: params.get("instant") === "1" ? 0 : 3, token: 0, running: false, presets: [], report: null, metrics: {}, t0: null, phase: null, sims: null, qs: {} };
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ---------------- boot ---------------- */
  async function boot() {
    bindUI();
    $$("#speed button").forEach((b) => b.classList.toggle("on", Number(b.dataset.speed) === S.speed));
    renderStatus();
    renderLanding();
    try { S.presets = (await (await fetch("data/presets.json")).json()).presets; } catch (e) { S.presets = []; }
    renderPresets();
    S.mode = (await detectLive()) ? "live" : "recorded";
    renderStatus();
    const pid = params.get("preset");
    if (pid && S.presets.find((p) => p.id === pid)) { runPreset(pid); }
    else if (params.get("tour") !== "0" && !store.get("xc_tour_1")) { setTimeout(() => startTour(1), 700); }
  }
  async function detectLive() {
    if (params.get("mode") === "recorded") return false;
    try {
      const c = new AbortController(); const t = setTimeout(() => c.abort(), 2500);
      const r = await fetch(API + "/health", { signal: c.signal }); clearTimeout(t);
      if (!r.ok) return false;
      const j = await r.json(); return j && j.status === "ok" && j.mode === "live";
    } catch (e) { return false; }
  }

  /* ---------------- chrome ---------------- */
  function renderStatus() {
    const live = S.mode === "live";
    $("#status").innerHTML = `<span class="pill"><span class="dot ${live ? "live" : "rec"}"></span>${live ? "Live from Qloo" : "Recorded runs"}</span><button class="help" id="helpBtn" type="button">Take the tour</button>`;
    $("#helpBtn").onclick = () => startTour(S.report ? 2 : 1);
    const b = $("#banner");
    if (live) { b.hidden = true; }
    else { b.hidden = false; b.innerHTML = "Showing recorded runs of the three case studies. The numbers are <b>synthetic</b> and are not Qloo output. Connect the backend for live audits on any two brands."; }
  }
  function renderPresets() {
    $("#presets").innerHTML = `<span class="presets-label">Case studies</span>` + S.presets.map((p) => `<button class="preset" type="button" data-id="${esc(p.id)}">${esc(p.label.replace(" x ", " × "))}</button>`).join("");
    $$("#presets .preset").forEach((b) => (b.onclick = () => runPreset(b.dataset.id)));
  }
  function markPreset(id) { $$("#presets .preset").forEach((b) => b.classList.toggle("on", b.dataset.id === id)); }
  function bindUI() {
    $("#ask").addEventListener("submit", (e) => { e.preventDefault(); runFree($("#brandA").value.trim(), $("#brandB").value.trim()); });
    $$("#speed button").forEach((b) => (b.onclick = () => { S.speed = Number(b.dataset.speed); $$("#speed button").forEach((x) => x.classList.toggle("on", x === b)); }));
    $("#pickerCancel").onclick = () => ($("#picker").hidden = true);
    window.addEventListener("resize", () => $$("canvas[data-heat]").forEach(drawOne));
  }

  /* ---------------- landing ---------------- */
  function renderLanding() {
    $("#log").innerHTML = `<div class="idle"><strong>Waiting for two brands.</strong><br>Every request xC sends to Qloo, every simulation step and every evidence record will appear here as it happens.</div>`;
    $("#phasebar").innerHTML = PHASES.map(() => "<i></i>").join("");
    $("#card").innerHTML = `<div class="wrap land"><p class="kicker">Cultural due diligence for brand deals</p>
      <h1>What Tony Bloom did to football, xC does to M&amp;A.</h1>
      <p class="lead">Give xC any two brands. It reads Qloo's taste graph, simulates how the fans will react, finds a bridge when the fit is weak, and puts a dollar figure on the deal.</p>
      <div class="cases" id="cases"></div>
      <p class="try">Or type any two brands in the bar above and press <b>Run audit</b>.</p></div>`;
    const fill = () => { if (!$("#cases")) return; $("#cases").innerHTML = S.presets.map((p) => `<button class="case" type="button" data-id="${esc(p.id)}"><span class="t">${esc(p.label.replace(" x ", " × "))}</span><span class="go2">Run this audit</span><span class="d">${esc(p.description)}</span></button>`).join(""); $$("#cases .case").forEach((b) => (b.onclick = () => runPreset(b.dataset.id))); };
    fill(); const iv = setInterval(() => { if (S.presets.length) { fill(); clearInterval(iv); } }, 200); setTimeout(() => clearInterval(iv), 4000);
  }

  /* ---------------- run control ---------------- */
  function busy(on) { S.running = on; $("#go").disabled = on; $("#go").textContent = on ? "Running…" : "Run audit"; }
  function norm(s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function runPreset(id) {
    const p = S.presets.find((x) => x.id === id); if (!p) return;
    $("#brandA").value = p.acquirer_brand; $("#brandB").value = p.target_brand; markPreset(id);
    if (S.mode === "live") return runLive(p.acquirer_brand, p.target_brand, id);
    return runRecorded(id);
  }
  function runFree(a, b) {
    if (!a || !b) return;
    const hit = S.presets.find((p) => { const x = norm(a), y = norm(b), pa = norm(p.acquirer_brand), pb = norm(p.target_brand); return (x.includes(pa) || pa.includes(x)) && (y.includes(pb) || pb.includes(y)); });
    if (S.mode === "live") { markPreset(hit ? hit.id : null); return runLive(a, b, hit ? hit.id : null); }
    if (hit) return runPreset(hit.id);
    markPreset(null);
    $("#card").innerHTML = `<div class="wrap land"><p class="kicker">Live audits need the backend</p><h1 style="font-size:34px">Recorded runs only, for now.</h1><p class="lead">This page is showing recorded runs of the three case studies. Typing any other pair needs the live backend and a Qloo key. Run one of the case studies below.</p><div class="cases" id="cases"></div></div>`;
    $("#cases").innerHTML = S.presets.map((p) => `<button class="case" type="button" data-id="${esc(p.id)}"><span class="t">${esc(p.label.replace(" x ", " × "))}</span><span class="go2">Run this audit</span><span class="d">${esc(p.description)}</span></button>`).join("");
    $$("#cases .case").forEach((x) => (x.onclick = () => runPreset(x.dataset.id)));
  }

  function resetRun(a, b) {
    S.token++; S.report = null; S.metrics = {}; S.t0 = null; S.phase = null; S.sims = null; S.qs = {};
    $("#log").innerHTML = ""; $("#phasebar").innerHTML = PHASES.map(() => "<i></i>").join(""); $("#clock").textContent = "0.0s";
    $("#card").innerHTML = `<div class="wrap" id="live"><p class="kicker">Auditing</p><h2 class="hero-line">${esc(a)} × ${esc(b)}</h2>
      <div class="skel" style="width:80%"></div><div class="skel" style="width:62%"></div>
      <div class="facts" id="lfacts"></div>
      <div id="lsim" class="sec" hidden><h3>Simulating the fan reaction</h3><p class="find">Running thousands of scenarios. The histogram fills in as they finish.</p><div id="lhist"></div><div id="lcomms"></div></div></div>`;
    renderLiveFacts();
  }

  async function runRecorded(id) {
    const p = S.presets.find((x) => x.id === id); if (S.running) S.token++;
    resetRun(p.acquirer_brand, p.target_brand); busy(true); const my = S.token;
    try {
      const events = (await (await fetch(`data/events.${id}.json`)).json()).events;
      for (const e of events) {
        if (S.token !== my) return;
        if (S.speed > 0) await sleep(e.delay_ms / S.speed); else if (S.queue++ % 25 === 0) await sleep(0);
        await onEvent(e.event, my);
      }
    } catch (err) { logLine("err", "", "Could not play the recorded run: " + err.message); }
    if (S.token === my) busy(false);
  }
  S.queue = 0;

  /* ---------------- live path ---------------- */
  async function api(path, opt = {}) {
    const r = await fetch(API + path, { headers: { "Content-Type": "application/json", Accept: "application/json" }, ...opt });
    const body = await r.json().catch(() => null);
    if (!r.ok) { const d = body && body.detail; throw Object.assign(new Error(typeof d === "string" ? d : (d && d.message) || "Request failed (" + r.status + ")"), { status: r.status, detail: d }); }
    return body;
  }
  async function pickEntity(name) {
    const res = await api("/api/v1/resolve", { method: "POST", body: JSON.stringify({ query: name, types: ["urn:entity:brand"] }) });
    const c = res.candidates || [];
    if (!c.length) throw new Error(`No Qloo brand matched "${name}". Try the full brand name.`);
    if (norm(c[0].name) === norm(name) || c.length === 1 && norm(c[0].name).includes(norm(name))) return c[0];
    return new Promise((resolve, reject) => {
      $("#pickerSub").textContent = `Qloo returned several matches for "${name}". Pick the one you mean.`;
      $("#pickerList").innerHTML = c.slice(0, 6).map((x, i) => `<button class="cand" data-i="${i}"><b>${esc(x.name)}</b><span>${esc(x.subtitle || x.type || "")}</span></button>`).join("");
      $("#picker").hidden = false;
      $$("#pickerList .cand").forEach((b) => (b.onclick = () => { $("#picker").hidden = true; resolve(c[Number(b.dataset.i)]); }));
      $("#pickerCancel").onclick = () => { $("#picker").hidden = true; reject(new Error("Cancelled")); };
    });
  }
  async function runLive(a, b, presetId) {
    if (S.running) S.token++;
    resetRun(a, b); busy(true); const my = S.token;
    try {
      logLine("", "0.0s", "Matching brands against Qloo…");
      const [ea, eb] = presetId ? [null, null] : [await pickEntity(a), await pickEntity(b)];
      const body = { acquirer_brand: ea ? ea.name : a, target_brand: eb ? eb.name : b, preset_id: presetId || null };
      if (ea) body.source_entity_id = ea.entity_id; if (eb) body.comparison_entity_id = eb.entity_id;
      const rec = await api("/api/v1/reports", { method: "POST", body: JSON.stringify(body) });
      await streamLive(rec.id, my);
    } catch (err) {
      if (err.message !== "Cancelled") {
        const d = err.detail && typeof err.detail === "object" && !Array.isArray(err.detail) ? err.detail : null;
        const missing = d && (d.missing_configuration || []).concat(d.missing_inputs || []);
        logLine("err", "", err.message + (missing && missing.length ? " Missing: " + missing.join(", ") + "." : ""));
        $("#card").innerHTML = `<div class="wrap land"><p class="kicker">The audit stopped</p><h1 style="font-size:34px">${esc(err.status === 401 ? "The backend rejected the access token." : err.status === 429 ? "Qloo is rate limiting us." : err.status === 502 ? "Qloo did not respond." : "Something stopped the run.")}</h1><p class="lead">${esc(err.message)} ${err.status === 429 ? "Wait a minute and run it again." : "Check the stream on the left for the last step that completed."}</p></div>`;
      }
    }
    if (S.token === my) busy(false);
  }
  async function streamLive(id, my) {
    let last = 0, tries = 0;
    while (S.token === my) {
      try {
        const headers = { Accept: "text/event-stream" }; if (last) headers["Last-Event-ID"] = String(last);
        const r = await fetch(`${API}/api/v1/reports/${id}/generate/stream`, { method: "POST", headers });
        if (!r.ok) { const j = await r.json().catch(() => null); throw Object.assign(new Error((j && j.detail && (j.detail.message || j.detail)) || "Stream failed (" + r.status + ")"), { status: r.status, detail: j && j.detail }); }
        const reader = r.body.getReader(), dec = new TextDecoder(); let buf = "";
        for (;;) {
          const { value, done } = await reader.read(); if (done) break;
          buf += dec.decode(value, { stream: true });
          let i; while ((i = buf.indexOf("\n\n")) >= 0) {
            const block = buf.slice(0, i); buf = buf.slice(i + 2);
            const data = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
            if (!data) continue;
            const ev = JSON.parse(data); last = ev.seq || last;
            if (ev.type === "error" && ev.data && ev.data.code === "RUN_NOT_RESUMABLE") { const rec = await api(`/api/v1/reports/${id}`); if (rec.result) await onEvent({ type: "report.completed", seq: last + 1, ts: new Date().toISOString(), data: { result: rec.result } }, my); return; }
            await onEvent(ev, my); if (ev.type === "run.finished") return;
          }
        }
        return;
      } catch (err) {
        if (err.status) throw err;
        if (++tries > 5) { logLine("err", "", "The stream was lost."); const rec = await api(`/api/v1/reports/${id}`).catch(() => null); if (rec && rec.result) await onEvent({ type: "report.completed", seq: last + 1, ts: new Date().toISOString(), data: { result: rec.result } }, my); return; }
        await sleep(500 * 2 ** (tries - 1));
      }
    }
  }

  /* ---------------- event handling ---------------- */
  const tsec = (ev) => { const t = Date.parse(ev.ts); if (S.t0 == null) S.t0 = t; const s = Math.max(0, (t - S.t0) / 1000); return s; };
  const fmtT = (s) => s.toFixed(1) + "s";
  function logLine(cls, t, html) { const l = $("#log"); const d = document.createElement("div"); d.className = "ln " + cls; d.innerHTML = `<span class="t">${esc(t)}</span><span class="m">${html}</span>`; l.appendChild(d); l.scrollTop = l.scrollHeight; return d; }
  function setPhase(p, state) {
    const i = PHASES.indexOf(p); if (i < 0) return;
    const bars = $$("#phasebar i"); bars.forEach((b, k) => { if (k < i) { b.className = "done"; } });
    bars[i].className = state === "done" ? "done" : "run";
  }
  async function onEvent(ev, my) {
    if (S.token !== my) return;
    const s = tsec(ev), t = fmtT(s), d = ev.data || {}; $("#clock").textContent = t;
    switch (ev.type) {
      case "run.started": logLine("fin", t, `Run started. Seed ${d.seed}, ${d.simulation_runs.toLocaleString()} simulation runs.`); break;
      case "phase.started": { S.phase = ev.phase; setPhase(ev.phase, "run"); const n = PHASES.indexOf(ev.phase) + 1; const h = document.createElement("div"); h.className = "ph"; h.id = "ph-" + ev.phase; h.innerHTML = `<span>${n}. ${esc(PHASE_NAME[ev.phase] || d.title)}</span><small></small>`; $("#log").appendChild(h); $("#log").scrollTop = 1e9; break; }
      case "phase.completed": { setPhase(ev.phase, "done"); const h = $("#ph-" + ev.phase); if (h) $("small", h).textContent = (d.duration_ms / 1000).toFixed(1) + "s"; break; }
      case "agent.note": logLine("note", t, esc(d.text)); break;
      case "tool.call": { const q = Object.entries(d.params || {}).map(([k, v]) => `${esc(k)}=${esc(String(v).slice(0, 40))}`).join(" "); S.qs[d.call_id] = logLine("call", t, `GET ${esc(d.endpoint)} <span style="opacity:.7">${q}</span>`); break; }
      case "tool.result": logLine(d.suspect_empty ? "warn" : "ok", "", `${d.status} · ${(d.latency_ms / 1000).toFixed(1)}s · ${d.result_count == null ? "no count" : d.result_count + " results"}${d.cache_hit ? " · cached" : ""}${d.suspect_empty ? " · may be empty because a parameter was ignored" : ""}`); break;
      case "metric.updated": S.metrics[d.key] = d.metric; renderLiveFacts(); break;
      case "ledger.entry": logLine("led", t, `evidence <b>#${d.index}</b> ${esc((d.current_hash || "").slice(0, 10))}… ${esc(d.claim || "")}`); break;
      case "warning": logLine("warn", t, "Note: " + esc(d.message)); break;
      case "error": logLine("err", t, esc(d.message)); break;
      case "simulation.started": { $("#lsim").hidden = false; const sk = $$("#live .skel"); sk.forEach((k) => k.remove()); logLine("call", t, `Simulation started: ${d.runs.toLocaleString()} runs, ${d.communities} communities`); S.sims = logLine("", "", `<div class="sim"></div>`); S.sims.style.display = "block"; break; }
      case "simulation.progress": {
        const h = d.histogram, r = d.running; const dist = { lo: h.lo, hi: h.hi, counts: h.counts, mean: r.mean, p5: null, p95: null };
        if (S.sims) $(".sim", S.sims).innerHTML = X.histogram(dist, { h: 90 }).replace('width="100%"', 'width="100%" style="height:64px"') + `<div class="cap">${d.completed.toLocaleString()} / ${d.total.toLocaleString()} runs · mean ${r.mean == null ? "n/a" : r.mean.toFixed(1) + "%"}</div>`;
        const lh = $("#lhist"); if (lh) lh.innerHTML = X.histogram(dist);
        break;
      }
      case "simulation.community": { const lc = $("#lcomms"); if (lc) lc.insertAdjacentHTML("beforeend", communityRow(d.community)); logLine("ok", "", `${esc(d.community.label)} · rebellion ${(num(d.community.rebellion_probability) * 100).toFixed(0)}%`); break; }
      case "report.completed": {
        let res = d.result; if (res && res.$ref) res = await (await fetch("data/" + res.$ref)).json();
        S.report = res; renderReport(res); logLine("fin", t, "Report complete."); break;
      }
      case "run.finished": logLine("fin", t, `Run ${esc(d.status)}.`); break;
      default: logLine("led", t, "Unrecognised event: " + esc(ev.type));
    }
  }

  /* ---------------- live facts while running ---------------- */
  function renderLiveFacts() {
    const el = $("#lfacts"); if (!el) return; const m = S.metrics;
    const cell = (v, l) => `<div class="fact"><div class="v">${v}</div><div class="l">${l}</div></div>`;
    const f = num(m["fit.affinity"]), r = num(m["rebellion.index"]), i = num(m["rebellion.ip_value_at_risk_pct.mean"]), t = num(m["tam.expansion_usd.base"]);
    el.innerHTML = cell(f == null ? "…" : f.toFixed(0), "Fit, out of 100") + cell(r == null ? "…" : r.toFixed(0), "Rebellion risk, out of 100") + cell(i == null ? "…" : i.toFixed(1) + "%", "IP value at risk") + cell(t == null ? "…" : usd(t), "Yearly expansion, base case");
  }

  /* ---------------- the report ---------------- */
  function refsFor(r, re) { return r.evidence.filter((e) => re.test(e.claim) || re.test(e.reference)).map((e) => e.index); }
  function refsHtml(list) { return list.length ? `<div class="refs">Evidence ${list.map((i) => `<button class="ref" type="button" data-ev="${i}" aria-label="Open evidence record ${i}">${i}</button>`).join("")}</div>` : ""; }
  function communityRow(c) {
    const p = num(c.rebellion_probability), sh = num(c.core_audience_share);
    const ch = (c.channels || []).map((x) => `${esc(x.name)}`).join(", ");
    return `<div class="comm"><div class="n">${esc(c.label)}</div><div class="p">${p == null ? "n/a" : (p * 100).toFixed(0) + "%"}<small>likely to rebel</small></div>
      <div class="bar2"><i style="width:${Math.round((p || 0) * 100)}%"></i></div>
      <div class="where">${sh == null ? "" : (sh * 100).toFixed(0) + "% of the core audience. "}${ch ? `Most likely to organise on ${ch}.<span class="hyp">Channels are hypotheses, not verified.</span>` : ""}</div></div>`;
  }
  function heroSentence(r) {
    const base = num(r.tam.expansion_usd.base), A = esc(r.acquirer.name), B = esc(r.target.name), v = r.headline.verdict;
    if (base == null) return `The data is not enough to put a dollar figure on pairing ${A} with ${B}.`;
    const tail = { proceed: "The audiences already overlap, and the main risk is contained.", proceed_with_remediation: "That holds only if the fan communities below are brought along.", high_risk: "The fan reaction could erase most of that value.", insufficient_data: "Treat this as a rough guide." }[v] || "";
    return `Pairing ${A} with ${B} is worth an estimated <span class="fig">${usd(base)}</span> a year. ${tail}`;
  }
  function renderReport(r) {
    const [vl, vc] = VERDICT[r.headline.verdict] || ["Unknown", ""];
    const fit = num(r.fit.affinity), ov = r.fit.tag_overlap.value, pan = num(r.rebellion.index.score), sim = r.rebellion.simulation;
    const regs = r.locality.regions, rv = regs.map((x) => num(x.affinity)).filter((x) => x != null);
    const spread = rv.length > 1 ? Math.max(...rv) - Math.min(...rv) : null;
    const best = regs.slice().sort((a, b) => num(b.affinity) - num(a.affinity))[0], worst = regs.slice().sort((a, b) => num(a.affinity) - num(b.affinity))[0];
    const tc = r.fit.tag_counts || { a_only: 0, shared: 0, b_only: 0 };
    const t = r.tam, base = num(t.expansion_usd.base);
    const comms = r.rebellion.communities;
    const ipm = sim ? num(sim.ip_value_at_risk_pct.mean) : null;
    const conf = num(r.headline.confidence);
    const fx = (v, l, p) => `<div class="fact"><div class="v">${v}</div><div class="l">${X.prov(p)}${l}</div></div>`;
    let h = `<div class="wrap">
      <p class="kicker">${esc(r.acquirer.name)} × ${esc(r.target.name)}${r.mode === "fixture" ? " · recorded run, synthetic data" : ""}</p>
      <h2 class="hero-line">${heroSentence(r)}</h2>
      <div><span class="verdict ${vc}"><i></i>${vl}</span>${conf == null ? "" : `<span class="conf">${(conf * 100).toFixed(0)}% confident</span>`}</div>
      <div class="range">${X.rangeBar(num(t.expansion_usd.low), base, num(t.expansion_usd.high))}<div class="range-cap"><span>Yearly expansion of the combined audience, from the lowest to the highest fan-loss scenario.</span></div></div>
      <div class="facts">${fx(fit == null ? "n/a" : fit.toFixed(0), "Fit, out of 100", "measured")}${fx(pan == null ? "n/a" : pan.toFixed(0), "Rebellion risk, out of 100", "modeled")}${fx(ipm == null ? "n/a" : ipm.toFixed(1) + "%", "Core IP value at risk", "modeled")}${fx(spread == null ? "n/a" : spread.toFixed(0) + " pts", "Gap between best and worst market", "modeled")}</div>
      <div class="legend"><span>${X.prov("measured")}Measured from Qloo</span><span>${X.prov("modeled")}Modeled by xC</span><span>${X.prov("assumed")}Assumption you can change</span></div>`;

    /* fit */
    const demoA = r.fit.demographics.acquirer, demoB = r.fit.demographics.target;
    h += `<section class="sec" id="s-fit"><h3>${ov < 0.15 ? "The two brands share less than the score suggests" : ov < 0.3 ? "The two brands share some real ground" : "The two brands share a lot of ground"}</h3>
      <p class="find">Their audiences sit at <b>${fit == null ? "n/a" : fit.toFixed(0)} out of 100</b> on Qloo's taste affinity. They share <b>${tc.shared}</b> of ${tc.a_only + tc.shared + tc.b_only} cultural tags, which is ${ov < 0.15 ? "a narrow overlap" : ov < 0.3 ? "a moderate overlap" : "a wide overlap"}. What each brand owns alone is where the friction comes from.</p>
      ${X.tagBar(tc)}
      <div class="cols" style="margin-top:26px"><div><p class="sub">Shared ground</p><div class="chips">${r.fit.shared_signals.map((s) => `<span class="chip s">${esc(s.name)}</span>`).join("")}</div>
        <p class="sub">Only ${esc(r.acquirer.name)}</p><div class="chips">${r.fit.contrast_axes.filter((c) => c.side === "acquirer").map((c) => `<span class="chip a">${esc(c.name)}</span>`).join("")}</div>
        <p class="sub">Only ${esc(r.target.name)}</p><div class="chips">${r.fit.contrast_axes.filter((c) => c.side === "target").map((c) => `<span class="chip b">${esc(c.name)}</span>`).join("")}</div></div>
        <div><p class="sub" style="margin-top:0">Who the audiences are <span class="chip a" style="height:20px;margin-left:6px">${esc(r.acquirer.name)}</span> <span class="chip b" style="height:20px">${esc(r.target.name)}</span></p>${X.ages(demoA, demoB)}</div></div>
      ${refsHtml(refsFor(r, /Pairwise|share|resolved|Age and gender/))}</section>`;

    /* rebellion */
    h += `<section class="sec" id="s-reb"><h3>${comms.length ? "Fans are likely to push back, and we know where" : "No fan community stands out"}</h3>`;
    if (sim && sim.distribution) {
      const d = sim.distribution;
      h += `<p class="find">${comms.length} communities could rebel. <b>${esc(comms[0].label)}</b> is the most likely at <b>${(num(comms[0].rebellion_probability) * 100).toFixed(0)}%</b>. Across ${sim.runs.toLocaleString()} simulated runs the deal puts <b>${d.mean.toFixed(1)}%</b> of the core franchise's value at risk, and in nine runs out of ten the loss stays between <b>${d.p5.toFixed(1)}%</b> and <b>${d.p95.toFixed(1)}%</b>.</p>${X.histogram(d)}
        <p class="sub">The shaded band holds the middle 90% of runs. Red bars are the worst 5%.</p>`;
    } else { h += `<p class="find">The simulation did not run for this pair. ${esc((r.warnings.find((w) => w.section === "rebellion") || {}).message || "")}</p>`; }
    h += `<div style="margin-top:14px">${comms.map(communityRow).join("")}</div>
      <details class="how"><summary>How the risk is calculated</summary><p>Communities come from tags only one brand carries. For each of ${sim ? sim.runs.toLocaleString() : "thousands of"} runs, every community reacts at random around its own probability and influences the others. The Pandering index (${pan == null ? "n/a" : pan.toFixed(0)}) blends how much the pairing contradicts each brand's own audience, how far its marketing overclaims, and the gap between the audiences. Seed ${r.seed}: the same inputs always give the same result.</p></details>
      ${refsHtml(refsFor(r, /communities|simulation|IP value/))}</section>`;

    /* bridge */
    const br = r.bridge;
    h += `<section class="sec" id="s-bridge"><h3>${br.status === "found" ? "A three-step bridge closes most of the gap" : br.status === "not_needed" ? "No bridge needed" : "No bridge found"}</h3>`;
    if (br.status === "found") {
      const b0 = num(br.friction_before), b1 = num(br.friction_after), red = num(br.friction_reduction_pct);
      h += `<p class="find">Direct fit is weak, so xC searched the categories in between. Walking the audience through these three steps cuts friction from <b>${b0.toFixed(0)}</b> to <b>${b1.toFixed(0)}</b>, a <b>${red.toFixed(0)}%</b> reduction.</p>
        <div class="path">${br.steps.map((s) => `<div class="step"><div class="num">${s.number}</div><h4>${esc(s.to_category)}</h4><div class="ph2">${esc(s.phase)}</div><p>${esc(s.objective)}</p><div class="chips">${s.entities.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("")}</div><div class="lift">+${num(s.affinity_lift).toFixed(1)} affinity</div></div>`).join("")}</div>
        <div class="fric"><span>Friction now <b>${b0.toFixed(0)}</b></span><div class="tr"><i style="left:0;width:${b0}%;background:${X.C.risk};opacity:.25"></i><i style="left:0;width:${b1}%;background:${X.C.both}"></i></div><span>With the bridge <b>${b1.toFixed(0)}</b></span></div>`;
    } else if (br.status === "not_needed") {
      h += `<div class="nob">Direct fit is strong. The two audiences can meet without any help.</div>`;
    } else { h += `<p class="find">xC searched within its limits and found no path that lowers friction. See the notes in the evidence list.</p>`; }
    h += refsHtml(refsFor(r, /bridge|Middleman/i)) + `</section>`;

    /* locality */
    h += `<section class="sec" id="s-loc"><h3>${best && worst && best !== worst ? `${esc(best.label.split(",")[0])} welcomes it, ${esc(worst.label.split(",")[0])} is the hard market` : "Regional fit"}</h3>
      <p class="find">${best && worst ? `The audiences overlap most in <b>${esc(best.label)}</b> (${num(best.affinity).toFixed(0)}) and least in <b>${esc(worst.label)}</b> (${num(worst.affinity).toFixed(0)}), a gap of <b>${spread.toFixed(0)} points</b>. Bright ground is where both brands are hot at once.` : ""}</p>
      <div class="heats">${regs.map((g, i) => { const dl = num(g.delta_vs_global); return `<div class="heat"><canvas data-heat="${i}" aria-label="Heatmap for ${esc(g.label)}"></canvas><div class="cap"><div><div class="nm">${esc(g.label)}</div><div class="dl ${dl >= 0 ? "up" : "dn"}">${dl == null ? "" : (dl >= 0 ? "+" : "") + dl.toFixed(0) + " vs average"}</div></div><div class="sc">${num(g.affinity).toFixed(0)}</div></div></div>`; }).join("")}</div>
      <div class="hlegend"><span><i class="sw" style="background:#4664ff"></i>${esc(r.acquirer.name)} is hot</span><span><i class="sw" style="background:#ffaa32"></i>${esc(r.target.name)} is hot</span><span><i class="sw" style="background:#fff;border:1px solid #ccc"></i>Both are hot</span></div>
      <details class="how"><summary>How regional fit is measured</summary><p>Qloo scales each map inside its own area, so raw values cannot be compared between cities. xC compares how much the two brands' hottest cells overlap inside each area. ${esc((r.locality.caveats || []).join(" "))}</p></details>
      ${refsHtml(refsFor(r, /Heatmaps|overlap/))}</section>`;

    /* money */
    h += `<section class="sec" id="s-tam"><h3>The dollars and what they depend on</h3>
      <p class="find">Base expansion is <b>${usd(base)}</b> a year, against a current baseline of <b>${usd(num(t.baseline_usd))}</b>. The range reflects how much IP value the fan reaction could take. Every input below is stated and can be changed.</p>
      ${X.tornado(t.sensitivity, base)}
      <p class="sub">Assumptions</p><table class="assump"><tbody>${t.assumptions.map((a) => `<tr><td>${X.prov(a.provenance)}${esc(a.label)}</td><td>${esc(typeof a.value === "number" ? (a.unit === "fraction" ? (a.value * 100).toFixed(1) + "%" : a.unit === "usd" ? "$" + a.value : a.value) : a.value)}</td></tr>`).join("")}</tbody></table>
      ${refsHtml(refsFor(r, /expansion|assumed/))}</section>`;

    /* evidence + memo */
    h += `<section class="sec" id="s-ev"><h3>Every claim has a receipt</h3>
      <p class="find">Each step writes a record to a hash-chained ledger, so no number can be changed after the fact without breaking the chain.</p>
      <div class="verify">${r.evidence_verification.valid ? "✓ Chain verified" : "✕ Chain broken"} · ${r.evidence_verification.records_checked} records</div>
      <table class="ledger"><thead><tr><th></th><th>Source</th><th>What was established</th><th>Hash</th></tr></thead><tbody>${r.evidence.map((e) => `<tr id="ev-${e.index}"><td class="i">${e.index}</td><td>${esc(e.source)}</td><td>${esc(e.claim)}</td><td class="h">${esc(e.current_hash.slice(0, 10))}…</td></tr>`).join("")}</tbody></table>
      ${r.analyst_review ? `<p class="sub">Analyst review</p><div class="find" style="margin:0">${r.analyst_review.findings.map(esc).join(" ")}</div>` : ""}
      <div class="dl-row" id="dlrow"></div></section></div>`;
    $("#card").innerHTML = h; $("#card").scrollTop = 0; $("#card").parentElement.scrollTop = 0;
    wireReport(r);
    if (S.mode !== "live" || true) requestAnimationFrame(() => $$("canvas[data-heat]").forEach(drawOne));
    if (!store.get("xc_tour_2") && params.get("tour") !== "0" && !params.get("instant")) setTimeout(() => startTour(2), 600);
  }
  function drawOne(cv) { const r = S.report; if (!r) return; X.drawHeat(cv, r.locality.regions[Number(cv.dataset.heat)].heat); }
  function wireReport(r) {
    $$(".ref").forEach((b) => (b.onclick = () => { const row = $("#ev-" + b.dataset.ev); if (!row) return; row.scrollIntoView({ behavior: "smooth", block: "center" }); row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }));
    const row = $("#dlrow"), fixture = r.mode === "fixture";
    if (fixture) { row.innerHTML = `<button class="btn" id="mdBtn" type="button">Download memo (Markdown)</button><button class="btn ghost" id="prBtn" type="button">Save as PDF</button>`; $("#mdBtn").onclick = () => download(`xc-memo-${r.run_id}.md`, memo(r)); $("#prBtn").onclick = () => window.print(); }
    else { row.innerHTML = `<a class="btn" href="${API}${r.memo.pdf_path}">Download memo (PDF)</a><a class="btn ghost" href="${API}${r.memo.markdown_path}">Download Markdown</a>`; }
  }
  function download(name, text) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" })); a.download = name; document.body.appendChild(a); a.click(); a.remove(); }
  function memo(r) {
    const m = (x, u) => (x == null ? "n/a" : u === "usd" ? usd(x) : x.toFixed(1)), t = r.tam, L = [];
    L.push(`# ${r.acquirer.name} × ${r.target.name}: cultural due diligence`, "", r.mode === "fixture" ? "> SYNTHETIC RECORDED RUN. The numbers below are not Qloo output." : "", "", `**Verdict:** ${(VERDICT[r.headline.verdict] || [""])[0]}  `, `**Confidence:** ${num(r.headline.confidence) == null ? "n/a" : (num(r.headline.confidence) * 100).toFixed(0) + "%"}`, "", r.headline.summary, "",
      "## Dollars", "", `| Case | Yearly expansion |`, `| --- | --- |`, `| Low | ${usd(num(t.expansion_usd.low))} |`, `| Base | ${usd(num(t.expansion_usd.base))} |`, `| High | ${usd(num(t.expansion_usd.high))} |`, "",
      "## Fit", "", `Affinity ${m(num(r.fit.affinity))} out of 100 (measured). Tag overlap ${(r.fit.tag_overlap.value * 100).toFixed(0)}%.`, "",
      "## Fan rebellion", "", `Pandering index ${m(num(r.rebellion.index.score))}.`, "", ...r.rebellion.communities.map((c) => `- ${c.label}: ${(num(c.rebellion_probability) * 100).toFixed(0)}% likely to rebel`), "",
      "## Bridge", "", r.bridge.status === "found" ? r.bridge.steps.map((s) => `${s.number}. ${s.phase}: ${s.to_category}. ${s.objective}`).join("\n") : r.bridge.status === "not_needed" ? "No bridge needed." : "No bridge found.", "",
      "## Regional fit", "", `| Region | Overlap | vs average |`, `| --- | --- | --- |`, ...r.locality.regions.map((g) => `| ${g.label} | ${m(num(g.affinity))} | ${m(num(g.delta_vs_global))} |`), "",
      "## Assumptions", "", ...t.assumptions.map((a) => `- ${a.label}: ${a.value} (${a.provenance})`), "", "## Evidence", "", `| # | Source | Claim | Hash |`, `| --- | --- | --- | --- |`, ...r.evidence.map((e) => `| ${e.index} | ${e.source} | ${e.claim} | ${e.current_hash.slice(0, 10)} |`), "");
    return L.join("\n");
  }

  /* ---------------- guided tour ---------------- */
  const TOURS = {
    1: [
      ["#presets", "Start with a case study", "Three real-world deals are built in. Pick one and xC runs a full audit on it.", "bottom"],
      ["#ask", "Or type any two brands", "Enter two brands, media assets or acquisition targets. This is the live test.", "bottom"],
      ["#go", "Run the audit", "xC reads Qloo's taste data, simulates how fans will react, and prices the deal. It takes under a minute.", "bottom"],
      ["#speed", "Choose the pace", "Real time shows each step as it happens. Instant jumps straight to the finished result.", "left"],
      [".stream", "Watch the work", "Every request to Qloo, every simulation step and every evidence record appears here as it happens.", "right"],
      ["#cardpane", "Read the answer", "The verdict, the dollar figure, the risks and the bridge land here, in plain language.", "left"],
    ],
    2: [
      [".hero-line", "The answer comes first", "This sentence is the deal in one line: what it is worth and what it depends on.", "bottom"],
      [".legend", "How sure are we?", "A filled dot is measured from Qloo. A half dot is modeled by xC. A hollow dot is an assumption you can change.", "bottom"],
      [".refs", "Every claim has a receipt", "Click a numbered chip to jump to the evidence record behind that section.", "top"],
      ["#dlrow", "Take it with you", "Download the investment memo to share with your team.", "top"],
    ],
  };
  function startTour(n) {
    endTour(); const steps = TOURS[n].filter((s) => $(s[0])); if (!steps.length) return; let i = 0;
    const hole = document.createElement("div"); hole.className = "tour-hole"; const shade = document.createElement("div"); shade.className = "tour-shade"; const pop = document.createElement("div"); pop.className = "tour-pop"; pop.setAttribute("role", "dialog");
    document.body.append(shade, hole, pop); S.tour = { hole, shade, pop, n };
    const place = () => {
      const [sel, title, body, side] = steps[i], el = $(sel); el.scrollIntoView({ block: "nearest", behavior: "auto" });
      const r = el.getBoundingClientRect(), pad = 8;
      Object.assign(hole.style, { left: r.left - pad + "px", top: r.top - pad + "px", width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px" });
      pop.innerHTML = `<h4>${esc(title)}</h4><p>${esc(body)}</p><div class="tour-foot"><div class="tour-dots">${steps.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</div><button class="tour-skip" type="button">Skip</button>${i ? `<button class="tour-btn back" type="button">Back</button>` : ""}<button class="tour-btn" type="button">${i === steps.length - 1 ? "Done" : "Next"}</button></div>`;
      const pw = pop.offsetWidth, ph = pop.offsetHeight, vw = innerWidth, vh = innerHeight; let x, y;
      if (side === "bottom") { x = r.left; y = r.bottom + 18; } else if (side === "top") { x = r.left; y = r.top - ph - 18; } else if (side === "left") { x = r.left - pw - 18; y = r.top + 12; } else { x = r.right + 18; y = r.top + 12; }
      if (x + pw > vw - 16 || x < 16) { x = Math.min(Math.max(16, x), vw - pw - 16); } if (y + ph > vh - 16) y = Math.max(16, r.top - ph - 18); if (y < 16) y = Math.min(vh - ph - 16, r.bottom + 18);
      if (side === "left" || side === "right") { const overlaps = x < r.right && x + pw > r.left; if (overlaps) { x = Math.min(vw - pw - 16, Math.max(16, vw - pw - 40)); y = Math.min(vh - ph - 16, r.top + 40); } }
      pop.style.left = x + "px"; pop.style.top = y + "px";
      $(".tour-skip", pop).onclick = () => finish(); $(".tour-btn:not(.back)", pop).onclick = () => (i === steps.length - 1 ? finish() : (i++, place())); const bk = $(".tour-btn.back", pop); if (bk) bk.onclick = () => (i--, place());
    };
    const finish = () => { store.set("xc_tour_" + n, "1"); endTour(); };
    shade.onclick = finish; place();
    S.tour.key = (e) => { if (e.key === "Escape") finish(); if (e.key === "ArrowRight") $(".tour-btn:not(.back)", pop).click(); if (e.key === "ArrowLeft") { const b = $(".tour-btn.back", pop); if (b) b.click(); } };
    document.addEventListener("keydown", S.tour.key); S.tour.resize = () => place(); addEventListener("resize", S.tour.resize);
  }
  function endTour() { const t = S.tour; if (!t) return; t.hole.remove(); t.shade.remove(); t.pop.remove(); document.removeEventListener("keydown", t.key); removeEventListener("resize", t.resize); S.tour = null; }

  window.__xc = S;
  boot();
})();
