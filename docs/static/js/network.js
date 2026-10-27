/* UtecVis · network.js
   Render D3 de la única red y su layout de fuerzas. Los botones nunca cambian el grafo:
   solo cambian posiciones (con la simulación) u opacidades y capas superpuestas. */
(function () {
  "use strict";

  UV.dec = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d).replace(".", ","));
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const R_MIN = 8, R_MAX = 30;          // radio del nodo (px): escala sqrt con dominio fijo al máximo de 2026
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
    const gPot = root.append("g");
    const gTema = root.append("g");
    const gNode = root.append("g");
    const gLbl = root.append("g");
    const gStar = root.append("g");      // estrellas de T5 encima de todo, para que ninguna foto las tape

    let W = 800, H = 600;
    // dominio fijo al máximo de 2026; el rango solo depende del tamaño del lienzo (no de los botones)
    const rScale = d3.scaleSqrt().domain([0, ctx.WMAX]).range([R_MIN, R_MAX]);
    const hScale = rScale.copy().domain([0, ctx.HMAX]);   // «Tamaño: Calidad»: índice h (sin dato = mínimo)
    const radius = (n) => (ctx.state.size === "h" ? hScale(n.indice_h || 0) : rScale(n.m.wdeg));
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
      if (ctx.state.group === "comm") return n.m.comm >= 0 ? 0.2 : 0.08;
      if (!n.m.degree) return 0.2;
      // quien colabora fuera de su departamento queda "suelto" y sus coautores lo llevan entre zonas
      return 0.26 * (1 - 0.85 * n.m.cross_frac);
    }

    // ---------- simulación ----------
    const sim = d3.forceSimulation(ctx.nodes)
      .force("charge", d3.forceManyBody().strength(-60).distanceMax(180))
      .force("collide", d3.forceCollide((n) => radius(n) + 3).iterations(2))
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
      sim.force("charge").strength(isHier() ? 0 : -60);
      sim.force("link", d3.forceLink(links).id((d) => d.id).distance(55).strength((l) => {
        if (isHier()) return 0;
        const a = byId.get(l.source.id || l.source), b = byId.get(l.target.id || l.target);
        if (ctx.state.group === "comm") return a.m.comm >= 0 && a.m.comm === b.m.comm ? 0.35 : 0.01;
        return a.departamento === b.departamento ? 0.35 : 0.07;
      }));
      sim.force("x", d3.forceX((n) => anchor(n)[0]).strength(anchorStrength));
      sim.force("y", d3.forceY((n) => anchor(n)[1]).strength(anchorStrength));
      sim.force("collide").radius((n) => (isHier() ? 0 : radius(n) + 3));
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

    function edgeOpacity(e, sel, hov) {
      if (!visible(e.source) || !visible(e.target)) return 0.04;
      const touches = (id) => e.source === id || e.target === id;
      if (ctx.state.potential) return sel && touches(sel) ? 0.35 : 0.07;
      if (sel) return touches(sel) ? 0.95 : 0.05;
      if (hov) return touches(hov) ? 0.95 : 0.08;
      if (ctx.tema) return ctx.tema.edgeKeys.has(e.key) ? 1 : 0.05;
      return e.cross ? 0.75 : 0.9;
    }
    const enEquipo = (id) => ctx.tema && (ctx.tema.C.has(id) || ctx.tema.puentes.has(id));
    function nodeOpacity(n, sel, nb, hov, hovNb) {
      if (!visible(n.id)) return 0.08;
      if (sel) return nb.has(n.id) ? 1 : 0.15;
      if (hov) return hovNb.has(n.id) ? 1 : 0.35;
      if (ctx.tema) return enEquipo(n.id) ? 1 : 0.13;
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
      const ink = css("--edge-cross"), light = css("--edge-in"), ringC = css("--ring"), pot = css("--potential");
      const wmax = ctx.WEDGEMAX;

      // coautorías: data join con clave estable
      const co = gCo.selectAll("path:not(.exiting)").data(ctx.active, (e) => e.key);
      co.exit().classed("exiting", true).interrupt().transition("salida").duration(300).attr("stroke-opacity", 0).remove();
      co.enter().append("path").attr("fill", "none").attr("stroke-linecap", "round").attr("stroke-opacity", 0)
        .merge(co)
        .attr("stroke", (e) => (e.cross ? ink : light))
        .attr("stroke-width", (e) => 1 + 4 * Math.sqrt(e.w / wmax));

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
        .on("mouseenter", (ev, d) => { ctx.hover = d.id; showTip(ev, nodeTip(d)); applyStyles(false); })
        .on("mousemove", moveTip)
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
      if (st.rings && !st.potential) lab = ctx.topB.slice();
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
        st.forEach((s) => { s.x = Math.max(80, Math.min(W - 80, s.x)); s.y = Math.max(44, Math.min(H - 12, s.y)); });
      }
      gTema.selectAll("line").each(function (l) {
        const b = l.c ? l.c.n : l.toStar;
        this.setAttribute("x1", l.from.x); this.setAttribute("y1", l.from.y); this.setAttribute("x2", b.x); this.setAttribute("y2", b.y);
      });
      gStar.selectAll("g.star").attr("transform", (s) => `translate(${s.x},${s.y})`);
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
    function ticked() {
      const byId = ctx.byId;
      gCo.selectAll("path").attr("d", (e) => edgePath(byId.get(e.source), byId.get(e.target)));
      gPot.selectAll("path").attr("d", (p) => edgePath(byId.get(p.source), byId.get(p.target)));
      if (ctx.tema) placeStars(ctx.tema);
      gNode.selectAll("g.node").attr("transform", (n) => `translate(${n.x},${n.y})`);
      gLbl.selectAll("text").attr("x", (n) => n.x + radius(n) + 7).attr("y", (n) => n.y + 4);
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
      const k = Math.max(1.4, d3.zoomTransform(svg.node()).k);
      svg.transition().duration(650).call(zoom.transform, d3.zoomIdentity.translate(W / 2 - k * n.x, H / 2 - k * n.y).scale(k));
    }
    function resetZoom() { svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity); }
    function highlightPair(a, b) {
      gPot.selectAll("path").interrupt().attr("stroke-opacity", (p) => (p.source === a && p.target === b ? 1 : 0.05));
      gNode.selectAll("g.node").interrupt().style("opacity", (n) => (n.id === a || n.id === b ? 1 : 0.18));
      gCo.selectAll("path:not(.exiting)").interrupt().attr("stroke-opacity", 0.04);
    }
    function highlightNode(id) { ctx.hover = id; applyStyles(false); }
    function resize() { size(); render(0.3); }

    warmStart();
    return { render, applyStyles, centerOn, resetZoom, highlightPair, highlightNode, resize, sim };
  };
})();
