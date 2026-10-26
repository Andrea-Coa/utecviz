/* UtecVis · main.js
   Orquestación: carga de datos, estado centralizado y controles. Cada control modifica `state`
   y llama a render(); los cálculos pesados ya vienen hechos del pipeline. */
(async function () {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const fmtInt = (v) => v.toLocaleString("es-ES");
  const DATA = UV.base + "data/";
  const [nodes, edges, sim, metrics, zones, resumen] = await Promise.all(
    ["nodes.json", "edges.json", "similarity.json", "metrics_by_year.json", "departamentos.json", "resumen.json"]
      .map((f) => fetch(DATA + f, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(f); return r.json(); })));

  const YEARS = Object.keys(metrics).map(Number).sort((a, b) => a - b);
  const Y_MAX = YEARS[YEARS.length - 1];

  // ---------- estado centralizado ----------
  const state = {
    year: Y_MAX, group: "dept", rings: true, potential: false, threshold: 0.50, crossOnly: true,
    selected: null, hiddenZones: new Set(), rankMode: "w", potRank: "sim",
    tema: null,   // T5: {q, cargando} | {q, error} | {q, candidatos} (respuesta de /api/tema)
  };

  // ---------- contexto compartido con network.js y panel.js ----------
  function corto(nombre) {
    const t = nombre.split(" ");
    if (t.length <= 2) return nombre;
    if (t.length === 3) return /\.$|vich$/.test(t[1]) ? `${t[0]} ${t[2]}` : `${t[0]} ${t[1]}`;
    const ap = ["Del", "De", "La"].includes(t[t.length - 2]) ? t[t.length - 3] : t[t.length - 2];
    return `${t[0]} ${ap}`;
  }
  nodes.forEach((n) => { n.corto = corto(n.nombre); n.m = metrics[Y_MAX].nodes[n.id]; });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const zoneIndex = new Map(zones.map((z, i) => [z.zona, i]));
  const zoneOf = new Map(nodes.map((n) => [n.departamento, n.zona === "Dirección, facultades y centros" ? n.departamento : n.zona]));
  edges.forEach((e) => { e.key = e.source + "|" + e.target; });
  sim.forEach((p) => {
    p.key = p.source + "~" + p.target; p.score = p.score_combinado;
    p.cross = byId.get(p.source).departamento !== byId.get(p.target).departamento;
  });

  const ctx = {
    state, nodes, byId, zones, zoneIndex, zoneOf, sim, metrics,
    WMAX: d3.max(Object.values(metrics[Y_MAX].nodes), (m) => m.wdeg) || 1,
    WEDGEMAX: d3.max(edges, (e) => e.w) || 1,
    active: [], pairs: [], hover: null,
  };

  function wHasta(e, Y) {
    let w = 0;
    for (const [y, n] of Object.entries(e.w_by_year)) if (+y <= Y) w += n;
    return w + (Y >= Y_MAX ? e.w_sin_anio : 0);
  }
  function setYearData(Y) {
    ctx.year = Y;
    const M = metrics[Y];
    nodes.forEach((n) => { n.m = M.nodes[n.id]; });
    ctx.active = edges.filter((e) => e.first_year <= Y).map((e) => ({ ...e, w: wHasta(e, Y) })).filter((e) => e.w > 0);
    ctx.glob = M.global;
    ctx.comms = M.communities;
    ctx.bcMax = d3.max(nodes, (n) => n.m.bc) || 0;
    ctx.topB = nodes.filter((n) => n.m.bc > 0).sort((a, b) => b.m.bc - a.m.bc).slice(0, 5).map((n) => n.id);
    computePairs();
    computeTema();
  }
  // T5: candidatos del tema (lista única, ordenada por cercanía al tema completo) + qué los une en la red del año
  // (coautorías directas o caminos cortos con puentes). Con 2 o más facetas, cada faceta tiene su estrella y se
  // une a quienes llevan su etiqueta; con una o ninguna, una sola estrella.
  function computeTema() {
    const t = state.tema;
    if (!t || !t.candidatos) { ctx.tema = null; return; }
    const cand = t.candidatos.map((c) => ({ ...c, n: byId.get(c.id) }));
    const facetas = (t.facetas || []).length >= 2
      ? t.facetas.map((nombre, i) => ({ i, nombre, exp: cand.filter((c) => c.facetas.some((f) => f.nombre === nombre)) }))
        .filter((f) => f.exp.length) : [];
    const C = new Set(cand.map((c) => c.id));
    const adj = new Map(nodes.map((n) => [n.id, []]));
    ctx.active.forEach((e) => { adj.get(e.source).push([e.target, e.key]); adj.get(e.target).push([e.source, e.key]); });
    const camino = (a, b) => {   // BFS de a hasta b, como máximo 4 saltos; devuelve [nodos, aristas] o null
      const prev = new Map([[a, null]]);
      let frente = [a];
      for (let d = 0; d < 4 && frente.length; d++) {
        const sig = [];
        for (const u of frente) for (const [v, k] of adj.get(u)) if (!prev.has(v)) { prev.set(v, [u, k]); sig.push(v); }
        if (prev.has(b)) break;
        frente = sig;
      }
      if (!prev.has(b)) return null;
      const ns = [], ks = [];
      for (let v = b; prev.get(v); v = prev.get(v)[0]) { ks.push(prev.get(v)[1]); ns.push(prev.get(v)[0]); }
      return [ns.filter((x) => x !== a), ks];
    };
    const ids = [...C], puentes = new Set(), edgeKeys = new Set(), conectados = new Set(), dist = new Map();
    let directas = 0;
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const r = camino(ids[i], ids[j]);
      if (!r) continue;
      conectados.add(ids[i]); conectados.add(ids[j]);
      dist.set(ids[i] + "|" + ids[j], r[1].length); dist.set(ids[j] + "|" + ids[i], r[1].length);
      r[1].forEach((k) => edgeKeys.add(k));
      if (!r[0].length) directas++;
      r[0].forEach((x) => { if (!C.has(x)) puentes.add(x); });
    }
    // entre cada par de facetas: ¿comparten experto, hay coautoría directa, un camino más largo o nada?
    const enlaces = [];
    for (let i = 0; i < facetas.length; i++) for (let j = i + 1; j < facetas.length; j++) {
      let d = Infinity;
      for (const a of facetas[i].exp) for (const b of facetas[j].exp) d = Math.min(d, a.id === b.id ? 0 : dist.get(a.id + "|" + b.id) ?? Infinity);
      enlaces.push({ a: facetas[i].nombre, b: facetas[j].nombre, d });
    }

    // geometría para network.js: estrellas (centro + una por faceta) y líneas estrella → docente / estrella
    const centro = { key: "tema", kind: "tema", label: t.q, members: cand };
    const stars = [centro], lines = [];
    facetas.forEach((f) => {
      const s = { key: "f" + f.i, kind: "faceta", label: f.nombre, members: f.exp };
      stars.push(s);
      lines.push({ key: "hub|" + f.i, from: centro, toStar: s });
      f.exp.forEach((c) => lines.push({ key: f.i + "|" + c.id, from: s, c, faceta: f.nombre }));
    });
    // quien no lleva etiqueta de ninguna faceta (o si no hay facetas) se une a la estrella del tema
    cand.filter((c) => !facetas.some((f) => f.exp.includes(c))).forEach((c) => lines.push({ key: "c|" + c.id, from: centro, c }));
    ctx.tema = {
      q: t.q, C, puentes, edgeKeys, directas, cand, facetas, enlaces, stars, lines,
      multi: facetas.length ? cand.filter((c) => c.facetas.length > 1).map((c) => c.id) : [],
      aislados: ids.filter((x) => !conectados.has(x)),
    };
  }
  function computePairs() {
    const Y = ctx.year, t = state.threshold;
    const key = state.potRank === "score" ? "score" : "sim";
    ctx.pairs = sim.filter((p) => p.sim >= t && !(p.coautores && p.first_year <= Y) && (!state.crossOnly || p.cross))
      .sort((a, b) => b[key] - a[key]);
    const mx = d3.max(ctx.pairs, (p) => p.sim) || t + 0.01;
    ctx.potScale = d3.scaleLinear().domain([t, Math.max(mx, t + 0.01)]).range([0.45, 1]).clamp(true);
  }

  setYearData(Y_MAX);
  const handlers = {
    select(id, center) {
      state.selected = id;
      render(0);
      if (id && center) net.centerOn(id);
    },
    rank(m) { state.rankMode = m; renderPanel(); },
    potRank(m) { state.potRank = m; computePairs(); render(0); },
    hoverPair(a, b) { if (a) net.highlightPair(a, b); else net.applyStyles(false); },
    clearTema() { setTema(null); render(0); },
  };
  const net = UV.createNetwork(ctx, handlers);

  // ---------- render ----------
  function renderPanel() { UV.renderPanel(ctx, handlers); }
  function render(reheat) {
    net.render(reheat);
    renderPanel();
    renderLegend();
    if (!$("#tablaWrap").hidden) renderTable();
  }

  let legendOpen = window.innerWidth > 860;
  function renderLegend() {
    const lg = $("#legend");
    lg.innerHTML = `<button type="button" class="lg-title" id="lgToggle" aria-expanded="${legendOpen}">${legendOpen ? "▾" : "▸"} Departamento · clic para ocultar</button>`
      + (!legendOpen ? "" : zones.map((z) =>
      `<button type="button" data-zona="${z.zona}" aria-pressed="${!state.hiddenZones.has(z.zona)}">
        <span class="dot" style="background:var(--c${z.color})"></span>${z.zona} <span class="hint" style="margin:0">(${z.n})</span></button>`).join(""));
    $("#lgToggle").addEventListener("click", () => { legendOpen = !legendOpen; renderLegend(); });
    lg.querySelectorAll("button[data-zona]").forEach((b) => b.addEventListener("click", () => {
      const z = b.dataset.zona;
      state.hiddenZones.has(z) ? state.hiddenZones.delete(z) : state.hiddenZones.add(z);
      computePairs(); render(0);
    }));
  }

  function renderTable() {
    const rows = [...nodes].sort((a, b) => b.m.wdeg - a.m.wdeg || b.m.bc - a.m.bc || a.nombre.localeCompare(b.nombre));
    $("#tablaWrap").innerHTML = `<table class="datos"><caption>Métricas de red en ${ctx.year} (${nodes.length} docentes; ordenado por grado ponderado)</caption>
      <thead><tr><th>#</th><th>Docente</th><th>Departamento</th><th class="r">Grado ponderado</th><th class="r">Coautores UTEC</th>
      <th class="r">De otros dptos.</th><th class="r">Betweenness</th><th>Comunidad</th><th class="r">Publicaciones</th><th class="r">Índice h</th></tr></thead>
      <tbody>${rows.map((n, i) => `<tr><td class="r">${i + 1}</td><td>${n.nombre}</td><td>${n.departamento}</td><td class="r">${n.m.wdeg}</td>
        <td class="r">${n.m.degree}</td><td class="r">${n.m.cross_degree}</td><td class="r">${UV.dec(n.m.bc * 100, 1)} %</td>
        <td>${n.m.comm >= 0 ? "C" + n.m.comm : "—"}</td><td class="r">${n.pubs_total}</td><td class="r">${n.indice_h ?? "—"}</td></tr>`).join("")}</tbody></table>`;
  }

  // ---------- controles ----------
  const yr = $("#yearRange"), yrOut = $("#yearOut"), mark = $("#yearMark");
  yr.min = YEARS[0]; yr.max = Y_MAX; yr.value = Y_MAX;
  function setYear(Y) {
    state.year = Y; yr.value = Y; yrOut.textContent = Y; mark.textContent = Y; yr.setAttribute("aria-valuetext", Y);
    setYearData(Y);
    render(0.35);
  }
  yr.addEventListener("input", () => { stop(); setYear(+yr.value); });

  let timer = null;
  const play = $("#playBtn");
  function stop() { if (timer) { clearInterval(timer); timer = null; } play.textContent = "▶ Animar"; play.setAttribute("aria-pressed", "false"); }
  function start() {
    let Y = state.year >= Y_MAX ? YEARS[0] : state.year;
    play.textContent = "❚❚ Pausa"; play.setAttribute("aria-pressed", "true");
    setYear(Y);
    timer = setInterval(() => { Y += 1; if (Y > Y_MAX) { stop(); return; } setYear(Y); }, 900);
  }
  play.addEventListener("click", () => (timer ? stop() : start()));

  document.querySelectorAll("[data-group]").forEach((b) => b.addEventListener("click", () => setGroup(b.dataset.group)));
  function setGroup(g) {
    state.group = g;
    document.querySelectorAll("[data-group]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.group === g));
    render(0.6);
  }
  const ringBtn = $("#ringBtn"), potBtn = $("#potBtn");
  function setRings(v) { state.rings = v; ringBtn.setAttribute("aria-pressed", v); }
  function setPotential(v) {
    state.potential = v; potBtn.setAttribute("aria-pressed", v); $("#potCtl").hidden = !v;
    if (v) { state.selected = null; setTema(null); }
  }
  ringBtn.addEventListener("click", () => { setRings(!state.rings); render(0); });
  potBtn.addEventListener("click", () => { setPotential(!state.potential); render(0); });

  // T5: tema → equipo. El tema se convierte en vector en el servidor (tema.py); aquí solo se dibuja.
  const temaInput = $("#temaInput");
  let temaPeticion = 0;
  function setTema(t) {
    state.tema = t; computeTema();
    if (!t) { temaPeticion++; temaInput.value = ""; }
  }
  async function buscarTema(q, intento = 0) {
    q = q.trim(); if (!q) return;
    const id = ++temaPeticion;
    stop(); setPotential(false); state.selected = null;
    setTema({ q, cargando: true }); render(0);
    let r;
    try {
      const resp = await fetch("api/tema?q=" + encodeURIComponent(q));
      r = await resp.json();
    } catch (e) { r = { error: "No se pudo contactar al servidor." }; }
    if (id !== temaPeticion) return;   // llegó otra búsqueda mientras tanto
    if (r.candidatos) { setTema(r); net.resetZoom(); render(0); return; }
    if (r.cargando && intento < 60) { setTimeout(() => { if (id === temaPeticion) buscarTema(q, intento + 1); }, 3000); return; }
    setTema({ q, error: r.error || "El modelo no está disponible." }); render(0);
  }
  $("#temaForm").addEventListener("submit", (ev) => { ev.preventDefault(); buscarTema(temaInput.value); });
  const thr = $("#thrRange");
  thr.value = state.threshold; $("#thrOut").textContent = UV.dec(state.threshold);
  thr.addEventListener("input", () => { state.threshold = +thr.value; $("#thrOut").textContent = UV.dec((+thr.value)); computePairs(); render(0); });
  $("#crossOnly").addEventListener("change", (ev) => { state.crossOnly = ev.target.checked; computePairs(); render(0); });

  // buscador con autocompletado (datalist nativo)
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  $("#names").innerHTML = [...nodes].sort((a, b) => a.nombre.localeCompare(b.nombre)).map((n) => `<option value="${n.nombre}">`).join("");
  const search = $("#search");
  function buscar() {
    const q = norm(search.value); if (!q) return;
    const n = nodes.find((x) => norm(x.nombre) === q) || nodes.find((x) => norm(x.nombre).includes(q));
    if (n) { state.hiddenZones.delete(n.zona); handlers.select(n.id, true); }
  }
  search.addEventListener("change", buscar);
  search.addEventListener("keydown", (ev) => { if (ev.key === "Enter") buscar(); });

  // tabla
  const tableBtn = $("#tableBtn");
  tableBtn.addEventListener("click", () => {
    const w = $("#tablaWrap"), open = w.hidden;
    w.hidden = !open; tableBtn.setAttribute("aria-expanded", open);
    tableBtn.textContent = open ? "▤ Ocultar tabla" : "▤ Ver datos como tabla";
    if (open) renderTable();
  });

  // tema claro / oscuro
  $("#themeBtn").addEventListener("click", () => {
    const actual = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const nuevo = actual === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nuevo;
    try { localStorage.setItem("utecvis-tema", nuevo); } catch (e) { /* almacenamiento no disponible */ }
    render(0);
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => render(0));

  // tarjetas de preguntas: configuran la vista
  document.querySelectorAll("[data-task]").forEach((c) => c.addEventListener("click", () => {
    const t = c.dataset.task;
    if (t === "t5") {
      setRings(true); setGroupSilently("dept");
      document.getElementById("red").scrollIntoView({ behavior: "smooth", block: "start" });
      if (!temaInput.value.trim()) temaInput.value = "visualization of brain signals";
      buscarTema(temaInput.value);
      temaInput.focus({ preventScroll: true });
      return;
    }
    stop(); state.selected = null; state.hiddenZones.clear(); setTema(null);
    if (state.year !== Y_MAX) { state.year = Y_MAX; yr.value = Y_MAX; yrOut.textContent = Y_MAX; mark.textContent = Y_MAX; setYearData(Y_MAX); }
    if (t === "t1") { setPotential(false); setRings(false); state.rankMode = "w"; setGroupSilently("dept"); }
    if (t === "t2") { setPotential(false); setRings(true); state.rankMode = "b"; setGroupSilently("dept"); }
    if (t === "t3") { setPotential(false); setRings(true); setGroupSilently("comm"); }
    if (t === "t4") { setPotential(true); state.crossOnly = true; $("#crossOnly").checked = true; computePairs(); setGroupSilently("dept"); }
    document.getElementById("red").scrollIntoView({ behavior: "smooth", block: "start" });
    net.resetZoom();
    render(0.6);
  }));
  function setGroupSilently(g) {
    state.group = g;
    document.querySelectorAll("[data-group]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.group === g));
  }

  let rz = null;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => net.resize(), 150); });
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (state.selected) handlers.select(null);
    else if (state.tema) handlers.clearTema();
  });

  // ---------- textos de la página a partir de los datos ----------
  $("#st-docentes").textContent = fmtInt(resumen.n_docentes);
  $("#st-pubs").textContent = fmtInt(resumen.n_publicaciones);
  $("#st-cross").textContent = Math.round(resumen.pct_cross * 100) + " %";
  $("#st-comm").textContent = resumen.n_comunidades;
  $("#findings").innerHTML = resumen.hallazgos.map((h) => `<li><b>${h.titulo}.</b> ${h.texto}</li>`).join("");

  render(0);
})().catch((err) => {
  console.error(err);
  const s = document.getElementById("side");
  if (s) s.innerHTML = `<p class="hint">No se pudieron cargar los datos (${err.message}). Ejecuta el pipeline y abre la app con <code>flask run</code>.</p>`;
});
