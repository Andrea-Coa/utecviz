/* UtecVis · network.js
   Render D3 de la única red y su layout de fuerzas. Los botones nunca cambian el grafo:
   solo cambian posiciones (con la simulación) u opacidades y capas superpuestas. */
(function () {
  "use strict";

  UV.dec = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d).replace(".", ","));
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const R_MIN = 8, R_MAX = 30;          // radio del nodo (px): escala sqrt con dominio fijo al máximo de 2026
  const GAP = 7, CHARGE = -85;          // separación mínima entre fotos (px) y repulsión: red más holgada
  const LEGEND_H = 0;                   // la leyenda flota a la izquierda; se reserva margen en el layout

  UV.createNetwork = function (ctx, on) {
    const svg = d3.select("#svg");
    const chartEl = document.getElementById("chart");
    const tip = document.getElementById("tip");
    const defs = svg.append("defs");
    const bg = svg.append("rect").attr("class", "bg").attr("fill", "transparent");
    const root = svg.append("g");
    const gGuide = root.append("g").attr("class", "guides");   // vista jerárquica: anillos y arcos de departamento
    const gHull = root.append("g").attr("class", "hulls");
    const gZone = root.append("g");
    const gCo = root.append("g");
    const gCoHit = root.append("g");   // franjas invisibles sobre las coautorías: hover y clic
    const gPot = root.append("g");
    const gTema = root.append("g");
    const gNode = root.append("g");
    const gLbl = root.append("g");
    const gStar = root.append("g");      // estrellas de T5 encima de todo, para que ninguna foto las tape

    let W = 800, H = 600;
    // dominio fijo al máximo de 2026; el rango solo depende del tamaño del lienzo (no de los botones)
    const rScale = d3.scaleSqrt().domain([0, ctx.WMAX]).range([R_MIN, R_MAX]);
    const hScale = rScale.copy().domain([0, ctx.HMAX]);   // «Tamaño: Calidad»: índice h (sin dato = mínimo)
    // T5: cercanía al tema (rel). Lineal desde 0,3 (los candidatos van de ~35 % a 100 %; con √ desde 0 casi no se
    // distinguían) y hasta 1,3 × el radio máximo, para que el más cercano resalte. Fuera del equipo = mínimo.
    const temaScale = d3.scaleLinear().domain([0.3, 1]).clamp(true);
    const radius = (n) => (ctx.tema ? (ctx.tema.rel.has(n.id) ? temaScale(ctx.tema.rel.get(n.id)) : rScale.range()[0])
      : ctx.state.size === "h" ? hScale(n.indice_h || 0) : rScale(n.m.wdeg));
    const colorOf = (n) => css("--c" + n.color);
    const zoneIdx = (z) => ctx.zoneIndex.get(z);

    // ---------- fotos como <pattern> ----------
    const ext = (() => {
      try { return document.createElement("canvas").toDataURL("image/webp").startsWith("data:image/webp") ? ".webp" : ".jpg"; }
      catch (e) { return ".jpg"; }
    })();
    ctx.fotoExt = ext;
    // un único recorte circular (en unidades del objeto) para todas las fotos
    defs.append("clipPath").attr("id", "clipCirc").attr("clipPathUnits", "objectBoundingBox")
      .append("circle").attr("cx", 0.5).attr("cy", 0.5).attr("r", 0.5);

    // ---------- zoom y pan ----------
    const zoom = d3.zoom().scaleExtent([0.35, 5]).on("zoom", (ev) => root.attr("transform", ev.transform));
    svg.call(zoom).on("dblclick.zoom", null);
    svg.on("click", (ev) => {
      if (ev.target === svg.node() || ev.target === bg.node()) on.select(null);
    });

    // ---------- anclas ----------
    function size() {
      const r = chartEl.getBoundingClientRect();
      W = Math.max(320, r.width); H = Math.max(320, r.height);
      bg.attr("width", W).attr("height", H);
      const k = Math.max(0.55, Math.min(1, Math.min(W, H) / 680));
      rScale.range([R_MIN * Math.max(k, 0.75), R_MAX * k]);
      hScale.range(rScale.range());
      temaScale.range([rScale.range()[0], rScale.range()[1] * 1.3]);
    }
    // en pantallas anchas la leyenda ocupa una franja a la izquierda: el layout se centra en el resto
    const legendW = () => (W > 900 ? Math.min(300, W * 0.26) : 0);
    const cx = () => legendW() + (W - legendW()) / 2;
    const cy = () => (H - LEGEND_H) / 2;
    function zoneAnchor(z, k = 1) {
      const i = zoneIdx(z), nZ = ctx.zones.length;
      const a = (i / nZ) * 2 * Math.PI - Math.PI / 2;
      return [cx() + Math.cos(a) * (W - legendW()) * 0.35 * k, cy() + Math.sin(a) * (H - LEGEND_H) * 0.36 * k, a];
    }
    function commAnchor(c) {
      const ids = ctx.comms.map((d) => d.id), i = ids.indexOf(c), nC = Math.max(1, ids.length);
      const a = (i / nC) * 2 * Math.PI - Math.PI / 2, rr = Math.min(W - legendW(), H) * (nC > 1 ? 0.24 : 0);
      return [cx() + Math.cos(a) * rr, cy() + Math.sin(a) * rr];
    }
    // ---------- vista jerárquica (radial): UTEC → departamento (zona) → persona ----------
    // Cada zona ocupa un sector del círculo, en el mismo orden que en la vista por departamento. Dentro del
    // sector, quien tiene coautores UTEC en el año va en el anillo interior (ordenado por comunidad y grado
    // ponderado) y quien no, en el exterior. Las aristas se agrupan pasando por el centro de su departamento
    // (hierarchical edge bundling, Holten 2006): las coautorías entre departamentos forman haces por el centro.
    let hier = null;
    const isHier = () => ctx.state.group === "hier";
    function computeHier() {
      const CX = cx(), CY = cy();
      const sinCo = ctx.nodes.filter((n) => !n.m.degree), conCo = ctx.nodes.filter((n) => n.m.degree);
      const rOut = d3.max(sinCo, radius) || R_MIN, rIn = d3.max(conCo, radius) || R_MIN;
      // margen para las etiquetas de departamento: ~110 px a los lados (texto horizontal), ~44 arriba y abajo
      const Rout = Math.max(120, Math.min((W - legendW()) / 2 - rOut - 110, H / 2 - rOut - 44));
      const Rin = Math.max(70, Rout - rOut - rIn - 10);
      const ancho = (ms, R) => d3.sum(ms, (n) => (2 * radius(n) + 3) / R);
      const porZona = ctx.zones.map((z) => {
        const ms = ctx.nodes.filter((n) => n.zona === z.zona);
        const inner = ms.filter((n) => n.m.degree).sort((a, b) => (a.m.comm < 0) - (b.m.comm < 0)
          || a.m.comm - b.m.comm || b.m.wdeg - a.m.wdeg || a.nombre.localeCompare(b.nombre));
        const outer = ms.filter((n) => !n.m.degree).sort((a, b) => b.pubs_total - a.pubs_total || a.nombre.localeCompare(b.nombre));
        return { z, inner, outer, need: Math.max(ancho(inner, Rin), ancho(outer, Rout)) };
      });
      const gap = 0.05, libre = 2 * Math.PI - gap * porZona.length, total = d3.sum(porZona, (d) => d.need);
      const pos = new Map(), hub = new Map(), sectores = [];
      let a = -Math.PI / 2 - (porZona[0].need * libre / total) / 2;   // el primer departamento queda arriba
      const colocar = (ms, R, mid, A) => {   // centra los nodos en el sector; si no caben, los comprime
        const wt = ancho(ms, R), f = Math.min(1, A / (wt || 1));
        let acc = mid - (wt * f) / 2;
        ms.forEach((n) => {
          const w = ((2 * radius(n) + 3) / R) * f;
          pos.set(n.id, [CX + Math.cos(acc + w / 2) * R, CY + Math.sin(acc + w / 2) * R]);
          acc += w;
        });
      };
      porZona.forEach((d) => {
        const A = (d.need * libre) / total, mid = a + A / 2;
        colocar(d.inner, Rin, mid, A);
        colocar(d.outer, Rout, mid, A);
        hub.set(d.z.zona, [CX + Math.cos(mid) * Rin * 0.45, CY + Math.sin(mid) * Rin * 0.45]);
        sectores.push({ zona: d.z.zona, color: d.z.color, a0: a, a1: a + A, mid });
        a += A + gap;
      });
      return { pos, hub, sectores, Rin, Rout, rOut, CX, CY };
    }
    function anchor(n) {
      if (ctx.state.group === "comm") return n.m.comm >= 0 ? commAnchor(n.m.comm) : zoneAnchor(n.zona, 1.1);
      if (isHier() && hier) return hier.pos.get(n.id);
      return zoneAnchor(n.zona);
    }
    function anchorStrength(n) {
      if (isHier()) return 0.3;
      if (ctx.state.group === "comm") return n.m.comm >= 0 ? 0.16 : 0.07;
      if (!n.m.degree) return 0.16;
      // quien colabora fuera de su departamento queda "suelto" y sus coautores lo llevan entre zonas
      return 0.2 * (1 - 0.85 * n.m.cross_frac);
    }

    // ---------- simulación ----------
    const sim = d3.forceSimulation(ctx.nodes)
      .force("charge", d3.forceManyBody().strength(CHARGE).distanceMax(200))
      .force("collide", d3.forceCollide((n) => radius(n) + GAP).iterations(4))
      .force("bounds", () => {   // mantiene los nodos dentro del lienzo
        for (const n of ctx.nodes) {
          const r = radius(n) + 4;
          n.x = Math.max(r, Math.min(W - r, n.x)); n.y = Math.max(r, Math.min(H - r, n.y));
        }
      })
      .alphaDecay(0.03)
      .stop()
      .on("tick", ticked);
    let links = [];

    function setForces() {
      hier = isHier() ? computeHier() : null;
      links = ctx.active.map((e) => ({ source: e.source, target: e.target, cross: e.cross, key: e.key }));
      const byId = ctx.byId;
      // en la vista jerárquica las posiciones son fijas: sin repulsión, enlaces ni colisión
      sim.force("charge").strength(isHier() ? 0 : CHARGE);
      sim.force("link", d3.forceLink(links).id((d) => d.id).distance(55).strength((l) => {
        if (isHier()) return 0;
        const a = byId.get(l.source.id || l.source), b = byId.get(l.target.id || l.target);
        if (ctx.state.group === "comm") return a.m.comm >= 0 && a.m.comm === b.m.comm ? 0.35 : 0.01;
        return a.departamento === b.departamento ? 0.35 : 0.07;
      }));
      sim.force("x", d3.forceX((n) => anchor(n)[0]).strength(anchorStrength));
      sim.force("y", d3.forceY((n) => anchor(n)[1]).strength(anchorStrength));
      // jerárquica: posiciones fijas, sin colisión, salvo los candidatos de T5, que crecen y pueden encimarse
      // con sus vecinos de anillo si el sector va comprimido
      sim.force("collide").radius((n) => (!isHier() ? radius(n) + GAP : ctx.tema && ctx.tema.rel.has(n.id) ? radius(n) + 2 : 0));
    }

    function warmStart() {
      size();
      // posiciones iniciales deterministas (espiral alrededor del ancla): layout reproducible entre recargas
      const porZona = d3.group(ctx.nodes, (n) => n.zona);
      porZona.forEach((ms, z) => {
        const [ax, ay] = zoneAnchor(z);
        ms.forEach((n, k) => {
          const a = k * 2.399963, rr = 9 * Math.sqrt(k + 1);
          n.x = ax + Math.cos(a) * rr; n.y = ay + Math.sin(a) * rr;
        });
      });
      setForces();
      sim.alpha(1);
      for (let i = 0; i < 300; i++) sim.tick();
      sim.alpha(0);
    }

    // ---------- estilos dependientes del estado ----------
    function neighborhood() {
      const s = ctx.state.selected, nb = new Set();
      if (!s) return nb;
      nb.add(s);
      ctx.active.forEach((e) => { if (e.source === s) nb.add(e.target); if (e.target === s) nb.add(e.source); });
      if (ctx.state.potential) ctx.pairs.forEach((p) => { if (p.source === s) nb.add(p.target); if (p.target === s) nb.add(p.source); });
      return nb;
    }
    const visible = (id) => !ctx.state.hiddenZones.has(ctx.byId.get(id).zona);
    // Vista "Puentes": los 5 puentes del año y sus coautores directos se ven al 100 %; el resto queda atenuado,
    // para que se lea entre quiénes está cada puente.
    const modoPuentes = () => ctx.state.rings && !ctx.state.potential && !ctx.tema;
    function vecindadPuentes() {
      const b = new Set(ctx.topB), v = new Set(ctx.topB);
      ctx.active.forEach((e) => { if (b.has(e.source)) v.add(e.target); if (b.has(e.target)) v.add(e.source); });
      return { b, v };
    }

    function edgeOpacity(e, sel, hov) {
      if (!visible(e.source) || !visible(e.target)) return 0.04;
      const touches = (id) => e.source === id || e.target === id;
      if (ctx.state.potential) return sel && touches(sel) ? 0.35 : 0.07;
      if (sel) return touches(sel) ? 0.95 : 0.05;
      if (hov) return touches(hov) ? 0.95 : 0.08;
      if (ctx.tema) return ctx.tema.edgeKeys.has(e.key) ? 1 : 0.05;
      if (modoPuentes()) { const { b } = vecindadPuentes(); return b.has(e.source) || b.has(e.target) ? 1 : 0.1; }
      return e.cross ? 0.75 : 0.9;
    }
    const enEquipo = (id) => ctx.tema && (ctx.tema.C.has(id) || ctx.tema.puentes.has(id));
    function nodeOpacity(n, sel, nb, hov, hovNb) {
      if (!visible(n.id)) return 0.08;
      if (sel) return nb.has(n.id) ? 1 : 0.15;
      if (hov) return hovNb.has(n.id) ? 1 : 0.35;
      if (ctx.tema) return enEquipo(n.id) ? 1 : 0.13;
      if (modoPuentes()) return vecindadPuentes().v.has(n.id) ? 1 : 0.22;
      return 1;
    }
    function potOpacity(p, sel) {
      if (!visible(p.source) || !visible(p.target)) return 0.03;
      if (sel) return p.source === sel || p.target === sel ? 1 : 0.06;
      return ctx.potScale(p.sim);
    }

    function applyStyles(animate) {
      const sel = ctx.state.selected, hov = ctx.hover, nb = neighborhood();
      const hovNb = new Set();
      if (hov) { hovNb.add(hov); ctx.active.forEach((e) => { if (e.source === hov) hovNb.add(e.target); if (e.target === hov) hovNb.add(e.source); }); }
      const t = (s) => (animate ? s.transition().duration(350) : s.interrupt());
      t(gCo.selectAll("path:not(.exiting)")).attr("stroke-opacity", (e) => edgeOpacity(e, sel, hov));
      t(gPot.selectAll("path")).attr("stroke-opacity", (p) => potOpacity(p, sel));
      t(gTema.selectAll("line")).attr("stroke-opacity", (l) => (!l.c ? 0.45 : sel ? (l.c.id === sel ? 0.9 : 0.12) : 0.35 + 0.6 * l.c.rel));
      t(gNode.selectAll("g.node")).style("opacity", (n) => nodeOpacity(n, sel, nb, hov, hovNb));
    }

    // ---------- render completo ----------
    function render(reheat) {
      const st = ctx.state, sel = st.selected;
      const ink = css("--edge-cross"), ringC = css("--ring"), pot = css("--potential");
      const wmax = ctx.WEDGEMAX;

      // coautorías: data join con clave estable
      const co = gCo.selectAll("path:not(.exiting)").data(ctx.active, (e) => e.key);
      co.exit().classed("exiting", true).interrupt().transition("salida").duration(300).attr("stroke-opacity", 0).remove();
      co.enter().append("path").attr("fill", "none").attr("stroke-linecap", "round").attr("stroke-opacity", 0)
        .merge(co)
        // entre departamentos: tinta oscura; dentro de un departamento: el color de ese departamento
        .attr("stroke", (e) => (e.cross ? ink : colorOf(ctx.byId.get(e.source))))
        .attr("stroke-width", (e) => 1 + 4 * Math.sqrt(e.w / wmax));
      // coautorías: tooltip con las publicaciones en conjunto; clic → todas, con enlaces, en el panel
      const hit = gCoHit.selectAll("path").data(ctx.active, (e) => e.key);
      hit.exit().remove();
      hit.enter().append("path").attr("fill", "none").attr("stroke", "transparent").attr("stroke-width", 10).style("cursor", "pointer")
        .on("mouseenter", (ev, e) => showTip(ev, edgeTip(e)))
        .on("mousemove", moveTip).on("mouseleave", hideTip)
        .on("click", (ev, e) => { ev.stopPropagation(); hideTip(); on.edge(e.key); });

      // colaboraciones potenciales (solo con el botón activo)
      const pt = gPot.selectAll("path").data(st.potential ? ctx.pairs : [], (p) => p.key);
      pt.exit().remove();
      pt.enter().append("path").attr("fill", "none").attr("stroke-dasharray", "6 4").attr("stroke-linecap", "round").attr("stroke-opacity", 0)
        .on("mouseenter", (ev, p) => showTip(ev, potTip(p)))
        .on("mousemove", moveTip).on("mouseleave", hideTip)
        .on("click", (ev, p) => { ev.stopPropagation(); on.select(p.source); })
        .merge(pt)
        .attr("stroke", pot).attr("stroke-width", (p) => (p.cross ? 2.6 : 1.5));

      // T5: estrella del tema y, si el tema tiene varias facetas, una estrella con etiqueta por faceta en el
      // centro de sus expertos (sin color: el color ya es el departamento). Líneas de puntos estrella → docente.
      const tm = ctx.tema;
      const tl = gTema.selectAll("line").data(tm ? tm.lines : [], (l) => l.key);
      tl.exit().remove();
      tl.enter().append("line").attr("stroke-linecap", "round").attr("stroke-opacity", 0)
        .on("mouseenter", (ev, l) => { if (l.c) showTip(ev, temaTip(l)); })
        .on("mousemove", moveTip).on("mouseleave", hideTip)
        .on("click", (ev, l) => { ev.stopPropagation(); if (l.c) on.select(l.c.id); })
        .merge(tl)
        .attr("stroke", css("--tema"))
        .attr("stroke-dasharray", (l) => (l.c ? "1 5" : "6 5"))
        .attr("stroke-width", (l) => (l.c ? 2 + 3 * l.c.rel : 1.5));
      const ts = gStar.selectAll("g.star").data(tm ? tm.stars : [], (s) => s.key);
      ts.exit().remove();
      const tse = ts.enter().append("g").attr("class", "star")
        .on("mouseenter", (ev, s) => showTip(ev, starTip(s)))
        .on("mousemove", moveTip).on("mouseleave", hideTip);
      tse.append("path");
      tse.append("text").attr("class", "lbl star-lbl").attr("text-anchor", "middle");
      const tsa = tse.merge(ts);
      tsa.select("path").attr("d", (s) => d3.symbol(d3.symbolStar, s.kind === "tema" ? 560 : 260)())
        .attr("fill", css("--tema")).attr("stroke", css("--canvas")).attr("stroke-width", 2);
      tsa.select("text").attr("y", (s) => (s.kind === "tema" ? -20 : -14))
        .classed("faceta-lbl", (s) => s.kind === "faceta")
        .text((s) => (s.label.length > 34 ? s.label.slice(0, 33) + "…" : s.label));

      // nodos (se crean una sola vez; luego solo cambian atributos)
      const nd = gNode.selectAll("g.node").data(ctx.nodes, (n) => n.id);
      const ne = nd.enter().append("g").attr("class", "node")
        .call(d3.drag()
          .on("start", (ev, d) => { if (!ev.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
          .on("end", (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }))
        .on("mouseenter", (ev, d) => { ctx.hover = d.id; tip.innerHTML = nodeTip(d); tip.style.opacity = 1; tipJuntoA(d, this_(ev)); applyStyles(false); })
        .on("mouseleave", () => { ctx.hover = null; hideTip(); applyStyles(false); })
        .on("click", (ev, d) => { ev.stopPropagation(); on.select(ctx.state.selected === d.id ? null : d.id); });
      ne.append("circle").attr("class", "ring").attr("fill", "none");
      ne.append("circle").attr("class", "selring").attr("fill", "none");
      ne.append("circle").attr("class", "body");
      ne.filter((n) => n.foto).append("image").attr("class", "foto").attr("clip-path", "url(#clipCirc)")
        .attr("href", (n) => UV.base + n.foto + ext).attr("preserveAspectRatio", "xMidYMid slice");
      ne.append("circle").attr("class", "border").attr("fill", "none");
      ne.append("text").attr("class", "ini");
      const all = nd.merge(ne);
      // T5: el más cercano al tema se dibuja encima (ninguna foto tapa al top 1); sin tema, el orden original
      const orden = new Map(ctx.nodes.map((n, i) => [n.id, i]));
      all.sort((a, b) => (tm ? (tm.rel.get(a.id) ?? -1) - (tm.rel.get(b.id) ?? -1) : 0) || orden.get(a.id) - orden.get(b.id));

      const bcMax = ctx.bcMax, thr = 0.12 * bcMax;
      const ringW = d3.scaleLinear().domain([thr, Math.max(bcMax, thr + 1e-9)]).range([1.5, 6]).clamp(true);
      const rw = (n) => (st.rings && bcMax > 0 && n.m.bc >= thr ? ringW(n.m.bc) : 0);
      all.select("circle.body").transition().duration(450)
        .attr("r", radius).attr("fill", colorOf).attr("stroke", "none");
      all.select("image.foto").transition().duration(450)
        .attr("x", (n) => -radius(n)).attr("y", (n) => -radius(n))
        .attr("width", (n) => 2 * radius(n)).attr("height", (n) => 2 * radius(n));
      all.select("circle.border").transition().duration(450)
        .attr("r", radius).attr("stroke", colorOf).attr("stroke-width", 3);
      all.select("text.ini").text((n) => (n.foto ? "" : n.iniciales))
        .attr("fill", (n) => (n.color === 0 ? css("--ink") : "#fff"))
        .style("font-size", (n) => Math.max(7, radius(n) * 0.75) + "px");
      all.select("circle.ring").transition().duration(450)
        .attr("r", (n) => radius(n) + 1.5 + 2 + rw(n) / 2).attr("stroke", ringC).attr("stroke-width", rw);
      all.select("circle.selring")
        .attr("r", (n) => radius(n) + 1.5 + 2 + rw(n) + 3).attr("stroke", ringC)
        .attr("stroke-width", (n) => (n.id === sel ? 1.5 : 0)).attr("stroke-dasharray", "3 2");

      // etiquetas de texto: top 5 puentes, top 3 pares potenciales, selección y su vecindario
      let lab = [];
      // con Puentes activo no se ponen nombres: se leen al pasar el mouse
      if (st.potential) lab = [...new Set(ctx.pairs.slice(0, 3).flatMap((p) => [p.source, p.target]))];
      if (tm) lab = [...tm.C, ...tm.puentes];
      if (sel) { const nb = [...neighborhood()].filter((i) => i !== sel); lab = [sel, ...nb].slice(0, 12); }
      lab = lab.filter(visible).map((i) => ctx.byId.get(i));
      const lb = gLbl.selectAll("text").data(lab, (n) => n.id);
      lb.exit().remove();
      lb.enter().append("text").attr("class", "lbl").merge(lb).text((n) => n.corto);

      // etiquetas de zona (modo departamento)
      if (isHier()) hier = computeHier();   // posiciones del año y tamaño actuales, para etiquetas y guías
      const zl = gZone.selectAll("text").data(st.group !== "comm" ? ctx.zones : [], (z) => z.zona);
      zl.exit().transition().duration(250).style("opacity", 0).remove();
      zl.enter().append("text").attr("class", "zonelbl").style("opacity", 0).merge(zl)
        .each(function (z) {
          const [x, y, a] = zoneLabelPos(z.zona), c = Math.cos(a);
          const lines = partir(z.zona), t = d3.select(this);
          // jerárquica: el texto crece hacia afuera del círculo (las de arriba, hacia arriba); elipse: hacia adentro
          const h = isHier(), arriba = h && Math.sin(a) < -0.3 ? 12 * (lines.length - 1) : 0;
          const X = Math.min(W - 6, Math.max(6, x)), Y = Math.min(H - 8 - 12 * (lines.length - 1), Math.max(14, y - arriba));
          const fuera = c > 0.35 ? "start" : c < -0.35 ? "end" : "middle", dentro = c > 0.35 ? "end" : c < -0.35 ? "start" : "middle";
          t.attr("x", X).attr("y", Y).style("text-anchor", h ? fuera : dentro);
          t.selectAll("tspan").data(lines).join("tspan").attr("x", X).attr("dy", (d, i) => (i ? "1.15em" : 0)).text((d) => d);
        })
        .transition().duration(400).style("opacity", (z) => (st.hiddenZones.has(z.zona) ? 0.25 : 1));

      // comunidades (modo comunidad): manchas suaves + etiqueta C1, C2…
      const groups = st.group === "comm" ? d3.groups(ctx.nodes.filter((n) => n.m.comm >= 0), (n) => n.m.comm) : [];
      const hu = gHull.selectAll("g.hull").data(groups, (d) => d[0]);
      hu.exit().remove();
      const he = hu.enter().append("g").attr("class", "hull");
      he.append("path");
      he.append("text").attr("class", "commlbl");

      // vista jerárquica: anillos guía y un arco de color por departamento
      const hg = isHier() && hier ? hier : null;
      const anillos = gGuide.selectAll("circle").data(hg ? [hg.Rin, hg.Rout] : []);
      anillos.exit().remove();
      anillos.enter().append("circle").attr("class", "guide-ring").merge(anillos)
        .attr("cx", (r) => (hg ? hg.CX : 0)).attr("cy", (r) => (hg ? hg.CY : 0)).attr("r", (r) => r);
      const arco = d3.arc();
      const arcos = gGuide.selectAll("path.guide-arc").data(hg ? hg.sectores : [], (d) => d.zona);
      arcos.exit().remove();
      arcos.enter().append("path").attr("class", "guide-arc").style("opacity", 0).merge(arcos)
        .attr("transform", hg ? `translate(${hg.CX},${hg.CY})` : null)
        .attr("d", (d) => arco({ innerRadius: hg.Rout + hg.rOut + 6, outerRadius: hg.Rout + hg.rOut + 10,
          startAngle: d.a0 + Math.PI / 2, endAngle: d.a1 + Math.PI / 2 }))
        .attr("fill", (d) => css("--c" + d.color))
        .transition().duration(400).style("opacity", (d) => (st.hiddenZones.has(d.zona) ? 0.2 : 0.9));

      applyStyles(true);
      if (reheat) { setForces(); sim.alpha(reheat).restart(); } else ticked();
    }

    function partir(t) {   // nombres largos en dos líneas, cortando en el espacio más cercano al centro
      if (t.length <= 14) return [t];
      const sp = [...t].map((ch, i) => (ch === " " ? i : -1)).filter((i) => i > 0);
      if (!sp.length) return [t];
      const k = sp.reduce((b, i) => (Math.abs(i - t.length / 2) < Math.abs(b - t.length / 2) ? i : b));
      return [t.slice(0, k), t.slice(k + 1)];
    }
    // estrellas de T5: cada faceta junto a sus expertos (centro de gravedad ponderado por cercanía), empujada
    // hacia afuera del lienzo, donde hay espacio para su etiqueta; se separan si quedan encimadas (comparten
    // expertos). La del tema va entre las facetas, desplazada hacia el centro del lienzo.
    function placeStars(tm) {
      const centroide = (ms) => {
        const w = (c) => 0.2 + c.rel, sw = d3.sum(ms, w);
        return [d3.sum(ms, (c) => w(c) * c.n.x) / sw, d3.sum(ms, (c) => w(c) * c.n.y) / sw];
      };
      const desde = (x, y, d) => {   // desplaza (x, y) d px en la dirección que se aleja del centro del lienzo
        const dx = x - cx(), dy = y - cy(), r = Math.hypot(dx, dy) || 1;
        return [x + (dx / r) * d, y + (dy / r) * d];
      };
      const fs = tm.stars.filter((s) => s.kind === "faceta"), centro = tm.stars[0];
      fs.forEach((s) => { [s.x, s.y] = desde(...centroide(s.members), 60); });
      if (fs.length) [centro.x, centro.y] = desde(d3.mean(fs, (s) => s.x), d3.mean(fs, (s) => s.y), -110);
      else [centro.x, centro.y] = centroide(centro.members);
      // relajación: las estrellas se separan entre sí (sus etiquetas no se enciman), ninguna queda sobre una
      // foto y todas quedan dentro del lienzo; las tres reglas a la vez, para que una no deshaga a la otra
      const st = tm.stars;
      const cands = ctx.nodes.filter((n) => tm.rel.has(n.id));
      gStar.selectAll("g.star").each(function (s) {
        const t = this.querySelector("text");
        s.w = (t && t.getComputedTextLength()) || s.label.length * 7;
      });
      for (let it = 0; it < 80; it++) {
        for (let i = 0; i < st.length; i++) for (let j = i + 1; j < st.length; j++) {
          const a = st[i], b = st[j], dx = b.x - a.x || 1, dy = b.y - a.y, d = Math.hypot(dx, dy);
          const min = a.kind === "tema" || b.kind === "tema" ? 90 : 130;
          if (d < min) { const k = (min - d) / (2 * d); a.x -= dx * k; a.y -= dy * k; b.x += dx * k; b.y += dy * k; }
        }
        for (const s of st) for (const n of ctx.nodes) {
          const dx = s.x - n.x || 0.5, dy = s.y - n.y, d = Math.hypot(dx, dy), min = radius(n) + 22;
          if (d < min) { s.x += (dx / d) * (min - d); s.y += (dy / d) * (min - d); }
        }
        // caja de la etiqueta (texto centrado sobre la estrella): se aleja de las fotos de los candidatos
        for (const s of st) for (const n of cands) {
          const b = starBox(s), px = Math.max(b[0], Math.min(b[2], n.x)), py = Math.max(b[1], Math.min(b[3], n.y));
          let dx = px - n.x, dy = py - n.y, d = Math.hypot(dx, dy);
          const min = radius(n) + 3;
          if (d >= min) continue;
          if (d < 1e-6) { dx = (b[0] + b[2]) / 2 - n.x || 0.5; dy = (b[1] + b[3]) / 2 - n.y; d = Math.hypot(dx, dy); }
          s.x += (dx / d) * (min - d) * 0.5; s.y += (dy / d) * (min - d) * 0.5;
        }
        st.forEach((s) => { s.x = Math.max(80, Math.min(W - 80, s.x)); s.y = Math.max(44, Math.min(H - 12, s.y)); });
      }
      gTema.selectAll("line").each(function (l) {
        const b = l.c ? l.c.n : l.toStar;
        this.setAttribute("x1", l.from.x); this.setAttribute("y1", l.from.y); this.setAttribute("x2", b.x); this.setAttribute("y2", b.y);
      });
      gStar.selectAll("g.star").attr("transform", (s) => `translate(${s.x},${s.y})`);
    }
    // caja [x0, y0, x1, y1] de la etiqueta de una estrella (ver el atributo y del texto en render)
    function starBox(s) {
      const y = s.y + (s.kind === "tema" ? -20 : -14), w = s.w || s.label.length * 7;
      return [s.x - w / 2 - 3, y - 12, s.x + w / 2 + 3, y + 4];
    }
    const blob = d3.line().curve(d3.curveCatmullRomClosed.alpha(0.6));
    // aristas: rectas; en la vista jerárquica, curvas que pasan por el centro de cada departamento y, si son
    // entre departamentos, por el centro del círculo (la raíz de la jerarquía)
    const bundle = d3.line().curve(d3.curveBundle.beta(0.85));
    function edgePath(a, b) {
      if (!isHier() || !hier) return `M${a.x},${a.y}L${b.x},${b.y}`;
      const ha = hier.hub.get(a.zona), hb = hier.hub.get(b.zona);
      return bundle(a.zona === b.zona ? [[a.x, a.y], ha, [b.x, b.y]]
        : [[a.x, a.y], ha, [hier.CX, hier.CY], hb, [b.x, b.y]]);
    }
    // etiqueta de zona: alrededor de la elipse (vista por departamento) o fuera del círculo (jerárquica)
    function zoneLabelPos(z) {
      if (!isHier() || !hier) return zoneAnchor(z, 1.3);
      const s = hier.sectores.find((d) => d.zona === z), R = hier.Rout + hier.rOut + 20;
      return [hier.CX + Math.cos(s.mid) * R, hier.CY + Math.sin(s.mid) * R, s.mid];
    }
    // Etiquetas sin encimarse: cada nombre prueba posiciones alrededor de su nodo (derecha, izquierda, arriba,
    // abajo, diagonales y luego más lejos) y se queda con la que no choca con otros nombres ni con los nodos visibles.
    // Primero se ubica la persona seleccionada y luego los nodos más grandes.
    const anchoLbl = new Map();
    function placeLabels() {
      const sel = gLbl.selectAll("text");
      if (sel.empty()) return;
      const items = [];
      sel.each(function (n) {
        const k = n.id + "|" + this.textContent;
        if (!anchoLbl.has(k)) anchoLbl.set(k, this.getComputedTextLength() || this.textContent.length * 7);
        items.push({ el: this, n, w: anchoLbl.get(k) });
      });
      const conNombre = new Set(items.map((it) => it.n.id));
      const nodos = ctx.nodes.filter((n) => conNombre.has(n.id)).map((n) => ({ x: n.x, y: n.y, r: radius(n) + 3 }));
      items.sort((a, b) => (b.n.id === ctx.state.selected) - (a.n.id === ctx.state.selected) || radius(b.n) - radius(a.n));
      const puestos = [], LH = 12;
      // obstáculos fijos, que pesan más que otro nombre: estrellas de T5 (símbolo y etiqueta) y nombres de departamento
      const fijos = [];
      if (ctx.tema) gStar.selectAll("g.star").each((s) => {
        if (s.x == null) return;
        fijos.push(starBox(s), [s.x - 14, s.y - 14, s.x + 14, s.y + 14]);
      });
      gZone.selectAll("text").each(function () {
        try { const b = this.getBBox(); if (b.width) fijos.push([b.x, b.y, b.x + b.width, b.y + b.height]); } catch (e) { /* sin layout */ }
      });
      const choca = (b1, b2) => Math.max(0, Math.min(b1[2], b2[2]) - Math.max(b1[0], b2[0])) * Math.max(0, Math.min(b1[3], b2[3]) - Math.max(b1[1], b2[1]));
      const tapaNodo = (bx) => nodos.reduce((s, c) => {
        const dx = Math.max(bx[0] - c.x, 0, c.x - bx[2]), dy = Math.max(bx[1] - c.y, 0, c.y - bx[3]);
        return s + (dx * dx + dy * dy < c.r * c.r ? 1 : 0);
      }, 0);
      for (const it of items) {
        const { n, w } = it, r = radius(n);
        let best = null, bestS = Infinity, i = 0;
        for (const extra of [0, 10, 22]) {
          const g = r + 6 + extra, d = (r + 4 + extra) * 0.72;
          const cands = [
            [n.x + g, n.y + 4, "start"], [n.x - g, n.y + 4, "end"],
            [n.x, n.y - g + 2, "middle"], [n.x, n.y + g + 9, "middle"],
            [n.x + d, n.y - d, "start"], [n.x + d, n.y + d + 9, "start"],
            [n.x - d, n.y - d, "end"], [n.x - d, n.y + d + 9, "end"],
          ];
          for (const [x, y, an] of cands) {
            const x0 = an === "start" ? x : an === "end" ? x - w : x - w / 2;
            const bx = [x0 - 2, y - LH + 2, x0 + w + 2, y + 3];
            let sc = i++ * 0.5;
            for (const q of puestos) sc += choca(bx, q) * 4;
            for (const q of fijos) sc += choca(bx, q) * 20;
            sc += tapaNodo(bx) * 60;
            if (bx[0] < 0 || bx[2] > W || bx[1] < 0 || bx[3] > H) sc += 500;
            if (sc < bestS) { bestS = sc; best = { x, y, an, bx }; }
          }
          if (bestS < 20) break;   // ya hay un lugar libre cerca: no alejar el nombre
        }
        puestos.push(best.bx);
        d3.select(it.el).attr("x", best.x).attr("y", best.y).attr("text-anchor", best.an);
      }
    }

    function ticked() {
      const byId = ctx.byId;
      gCo.selectAll("path").attr("d", (e) => edgePath(byId.get(e.source), byId.get(e.target)));
      gCoHit.selectAll("path").attr("d", (e) => edgePath(byId.get(e.source), byId.get(e.target)));
      gPot.selectAll("path").attr("d", (p) => edgePath(byId.get(p.source), byId.get(p.target)));
      if (ctx.tema) placeStars(ctx.tema);
      gNode.selectAll("g.node").attr("transform", (n) => `translate(${n.x},${n.y})`);
      placeLabels();
      gHull.selectAll("g.hull").each(function ([c, ms]) {
        const pts = [];
        ms.forEach((n) => { const r = radius(n) + 12; for (let k = 0; k < 10; k++) { const a = k / 10 * 2 * Math.PI; pts.push([n.x + Math.cos(a) * r, n.y + Math.sin(a) * r]); } });
        const h = d3.polygonHull(pts);
        const g = d3.select(this);
        g.select("path").attr("d", h ? blob(h) : null);
        g.select("text").attr("x", d3.mean(ms, (n) => n.x)).attr("y", d3.min(pts, (p) => p[1]) - 6).text("C" + c);
      });
    }

    // ---------- tooltip ----------
    function showTip(ev, html) { tip.innerHTML = html; tip.style.opacity = 1; moveTip(ev); }
    function moveTip(ev) {
      const r = chartEl.getBoundingClientRect();
      let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
      const tw = tip.offsetWidth || 260, th = tip.offsetHeight || 150;
      if (x + tw > r.width - 4) x = ev.clientX - r.left - tw - 14;
      if (y + th > r.height - 4) y = ev.clientY - r.top - th - 14;
      tip.style.left = Math.max(4, x) + "px"; tip.style.top = Math.max(4, y) + "px";
    }
    function hideTip() { tip.style.opacity = 0; }
    const this_ = (ev) => ev.currentTarget;
    // Tooltip de un docente: se prueba alrededor del nodo y se elige el lugar que tapa menos sus coautorías
    // (puntos muestreados sobre sus líneas y los nodos de sus coautores). Queda fijo mientras el mouse esté encima.
    function tipJuntoA(d, el) {
      const r = chartEl.getBoundingClientRect(), b = el.getBoundingClientRect();
      const cx = b.left + b.width / 2 - r.left, cy = b.top + b.height / 2 - r.top, rad = b.width / 2;
      const tw = tip.offsetWidth || 260, th = tip.offsetHeight || 150;
      const pts = [];
      gCo.selectAll("path:not(.exiting)").filter((e) => e.source === d.id || e.target === d.id).each(function () {
        const L = this.getTotalLength(), M = this.getScreenCTM();
        for (let i = 0; i <= 40; i++) {
          const q = this.getPointAtLength((L * i) / 40);
          pts.push([M.a * q.x + M.c * q.y + M.e - r.left, M.b * q.x + M.d * q.y + M.f - r.top]);
        }
      });
      gNode.selectAll("g.node").filter((n) => n.id !== d.id && ctx.active.some((e) =>
        (e.source === d.id && e.target === n.id) || (e.target === d.id && e.source === n.id))).each(function () {
        const q = this.getBoundingClientRect();
        for (const fx of [0, 0.5, 1]) for (const fy of [0, 0.5, 1]) pts.push([q.left + q.width * fx - r.left, q.top + q.height * fy - r.top]);
      });
      const g = rad + 10, cands = [];
      // a la derecha, izquierda, abajo, arriba y diagonales; también un poco más lejos
      for (const k of [1, 2.2]) {
        const o = g * k;
        cands.push([cx + o, cy - th / 2], [cx - o - tw, cy - th / 2], [cx - tw / 2, cy + o], [cx - tw / 2, cy - o - th],
          [cx + o * 0.7, cy + o * 0.7], [cx - o * 0.7 - tw, cy + o * 0.7], [cx + o * 0.7, cy - o * 0.7 - th], [cx - o * 0.7 - tw, cy - o * 0.7 - th]);
      }
      let best = null, bestS = Infinity;
      cands.forEach(([x, y], i) => {
        const fuera = Math.max(0, 4 - x) + Math.max(0, x + tw - r.width + 4) + Math.max(0, 4 - y) + Math.max(0, y + th - r.height + 4);
        let tapa = 0;
        for (const [px, py] of pts) if (px > x - 6 && px < x + tw + 6 && py > y - 6 && py < y + th + 6) tapa++;
        const s = tapa * 10 + fuera * 5 + i * 0.5;   // a igualdad, el orden de preferencia (cerca y a la derecha)
        if (s < bestS) { bestS = s; best = [x, y]; }
      });
      tip.style.left = Math.min(Math.max(4, best[0]), r.width - tw - 4) + "px";
      tip.style.top = Math.min(Math.max(4, best[1]), r.height - th - 4) + "px";
    }
    const fmtBC = (v) => (v === 0 ? "0 %" : v < 0.001 ? "< 0,1 %" : (v * 100).toFixed(1).replace(".", ",") + " %");
    function nodeTip(n) {
      const m = n.m, top = ctx.topB.includes(n.id);
      return `<div class="tip-hd">${n.nombre}</div><div class="tip-bd">
        <span class="k">${n.departamento}</span><br>
        Publicaciones compartidas UTEC (grado pond.): <b>${m.wdeg}</b><br>
        Coautores UTEC: <b>${m.degree}</b> · ${m.cross_degree} de otros dptos.<br>
        Qué tan puente es (betweenness): <b>${fmtBC(m.bc)}</b>${top ? '<span class="tag">TOP 5 PUENTE</span>' : ""}<br>
        Comunidad: <b>${m.comm >= 0 ? "C" + m.comm : "—"}</b> · índice h: <b>${n.indice_h ?? "—"}</b></div>`;
    }
    function edgeTip(e) {
      const a = ctx.byId.get(e.source), b = ctx.byId.get(e.target), ps = UV.pubsEnConjunto(e, ctx.year);
      return `<div class="tip-hd">${esc(a.corto)} ↔ ${esc(b.corto)}</div><div class="tip-bd">
        <b>${ps.length}</b> ${ps.length === 1 ? "publicación" : "publicaciones"} en conjunto hasta ${ctx.year}
        <ul class="pubpar">${ps.slice(0, 5).map((p) => `<li><i>${esc(p.titulo)}</i> (${p.anio ?? "s/f"})</li>`).join("")}</ul>
        <span class="k">${ps.length > 5 ? `y ${ps.length - 5} más · ` : ""}clic: ver con enlaces</span></div>`;
    }
    function potTip(p) {
      const a = ctx.byId.get(p.source), b = ctx.byId.get(p.target);
      return `<div class="tip-hd">Colaboración potencial</div><div class="tip-bd">
        <b>${a.nombre}</b> <span class="k">(${a.zona})</span><br>↔ <b>${b.nombre}</b> <span class="k">(${b.zona})</span><br>
        Similitud temática: <b>${UV.dec(p.sim)}</b> · puntaje combinado: <b>${UV.dec(p.score)}</b><br>
        ${p.cross ? "Entre departamentos" : "Mismo departamento"} · aún sin coautorías
        ${UV.comunHtml(p) ? `<br>${UV.comunHtml(p)}` : ""}
        ${p.pubs_cercanas ? `<br><span class="k">Publicaciones más cercanas:</span>${UV.pubsHtml(p, a, b, false)}` : ""}</div>`;
    }

    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    function starTip(s) {
      const tm = ctx.tema;
      if (s.kind === "faceta") return `<div class="tip-hd">Faceta: ${esc(s.label)}</div><div class="tip-bd">
        Destacan: ${s.members.map((c) => `<b>${esc(c.n.corto)}</b>`).join(", ")}</div>`;
      return `<div class="tip-hd">Tema</div><div class="tip-bd"><b>${esc(tm.q)}</b><br>
        ${tm.facetas.length ? `${tm.facetas.length} facetas: ${tm.facetas.map((f) => esc(f.nombre)).join(" · ")}<br>` : ""}
        ${tm.C.size} docentes · ${tm.directas} pares ya publicaron juntos</div>`;
    }
    function temaTip(l) {
      const c = l.c, p = c.pubs[0];
      return `<div class="tip-hd">${esc(c.n.nombre)}</div><div class="tip-bd">
        <span class="k">${esc(c.n.departamento)}</span><br>
        Cercanía al tema: <b>${Math.round(c.rel * 100)} %</b> del máximo<br>
        ${c.facetas && c.facetas.length && ctx.tema.facetas.length ? `Destaca en: <b>${c.facetas.map((f) => esc(f.nombre)).join(" · ")}</b><br>` : ""}
        ${p ? `<span class="k">Publicación más cercana${p.y ? " (" + p.y + ")" : ""}:</span> <i>${esc(p.t.length > 110 ? p.t.slice(0, 109) + "…" : p.t)}</i>`
          : '<span class="k">Sin publicaciones: coincide por su perfil.</span>'}</div>`;
    }

    // ---------- API ----------
    function centerOn(id) {
      const n = ctx.byId.get(id); if (!n) return;
      // zoom según el tamaño del nodo: que su foto se vea de ~36 px de radio (los chicos se acercan más), sin
      // acercar tanto que se pierda su vecindario; si ya había más zoom, se mantiene
      const k = Math.max(d3.zoomTransform(svg.node()).k, Math.min(3, Math.max(1.6, 30 / radius(n))));
      // centrado en el área libre (a la derecha de la leyenda en pantallas anchas)
      svg.transition().duration(650).call(zoom.transform, d3.zoomIdentity.translate(cx() - k * n.x, cy() - k * n.y).scale(k));
    }
    function resetZoom() { svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity); }
    function highlightPair(a, b) {
      gPot.selectAll("path").interrupt().attr("stroke-opacity", (p) => (p.source === a && p.target === b ? 1 : 0.05));
      gNode.selectAll("g.node").interrupt().style("opacity", (n) => (n.id === a || n.id === b ? 1 : 0.18));
      gCo.selectAll("path:not(.exiting)").interrupt().attr("stroke-opacity", 0.04);
    }
    function highlightNode(id) { ctx.hover = id; applyStyles(false); }
    function resize() { size(); render(0.3); }

    // ---------- descargar imagen: la vista actual (zoom y filtros incluidos) como PNG ----------
    // La hoja de estilos y los archivos de fotos no viajan dentro de una imagen SVG: se copian los estilos
    // calculados en línea y las fotos como data URI antes de pasarla a un canvas.
    const ESTILOS = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray", "stroke-linecap",
      "stroke-linejoin", "opacity", "font-family", "font-size", "font-weight", "letter-spacing", "text-anchor",
      "dominant-baseline", "paint-order", "visibility", "display"];
    const dataURL = (blob) => new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(blob); });
    async function toCanvas(k = 2) {
      const src = svg.node(), clone = src.cloneNode(true), orig = src.querySelectorAll("*"), copia = clone.querySelectorAll("*");
      orig.forEach((el, i) => { const cs = getComputedStyle(el); copia[i].setAttribute("style", ESTILOS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";")); });
      clone.querySelectorAll("title, desc").forEach((el) => el.remove());
      await Promise.all([...clone.querySelectorAll("image")].map(async (im) => {
        const href = im.getAttribute("href");
        if (!href || href.startsWith("data:")) return;
        try { im.setAttribute("href", await dataURL(await (await fetch(href)).blob())); } catch (e) { im.remove(); }
      }));
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.setAttribute("width", W); clone.setAttribute("height", H);
      const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
      const img = new Image();
      await new Promise((ok, ko) => { img.onload = ok; img.onerror = ko; img.src = url; });
      const cv = document.createElement("canvas");
      cv.width = W * k; cv.height = H * k;
      const g = cv.getContext("2d");
      g.fillStyle = css("--canvas"); g.fillRect(0, 0, cv.width, cv.height);
      g.drawImage(img, 0, 0, cv.width, cv.height);
      URL.revokeObjectURL(url);
      return cv;
    }

    warmStart();
    return { render, applyStyles, centerOn, resetZoom, highlightPair, highlightNode, resize, toCanvas, sim };
  };
})();
