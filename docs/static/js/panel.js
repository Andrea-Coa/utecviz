/* UtecVis · panel.js
   Panel lateral que se adapta al estado: ficha del docente, pares potenciales, comunidades,
   ranking del año y "Cómo leer la red". */
(function () {
  "use strict";

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v, d = 1) => (v === 0 ? "0 %" : v < 0.001 ? "< 0,1 %" : (v * 100).toFixed(d).replace(".", ",") + " %");
  const dot = (n) => `<span class="dot" style="background:var(--c${n.color})"></span>`;

  // Evidencia de un par potencial: conceptos en común y las dos publicaciones más cercanas (ver 03_embeddings.py).
  const corta = (t, k = 95) => (t.length > k ? t.slice(0, k - 1).trimEnd() + "…" : t);
  UV.comunHtml = (p) => (p.comun && p.comun.length ? `En común: <b>${p.comun.map(esc).join(" · ")}</b>` : "");
  UV.pubsHtml = (p, a, b, links) => {
    if (!p.pubs_cercanas) return "";
    const li = (x, n) => `<li><span class="k">${esc(n.corto)}${x.y ? " · " + x.y : ""}:</span> ${links
      ? `<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t)}</a>` : `<i>${esc(corta(x.t))}</i>`}</li>`;
    return `<ul class="pubpar">${li(p.pubs_cercanas[0], a)}${li(p.pubs_cercanas[1], b)}</ul>`;
  };

  function box(title, body, extra = "") {
    return `<section class="pbox"><h3>${title}${extra}</h3><div class="pb">${body}</div></section>`;
  }

  // ---------- 1. Ficha ----------
  function ficha(ctx) {
    const n = ctx.byId.get(ctx.state.selected), m = n.m, Y = ctx.year;
    const av = n.foto
      ? `<img class="avatar" src="${UV.base + n.foto + ctx.fotoExt}" alt="" style="border-color:var(--c${n.color})">`
      : `<div class="avatar" style="background:var(--c${n.color});border-color:var(--c${n.color})">${esc(n.iniciales)}</div>`;
    const temas = n.temas_top.length ? `<div class="chips">${n.temas_top.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>`
      : `<p class="hint">Sin temas declarados.</p>`;

    const co = ctx.active.filter((e) => e.source === n.id || e.target === n.id)
      .map((e) => ({ o: ctx.byId.get(e.source === n.id ? e.target : e.source), e }))
      .sort((a, b) => b.e.w - a.e.w || a.o.nombre.localeCompare(b.o.nombre));
    const coHtml = co.length ? `<ul class="coauthors">${co.map(({ o, e }) => {
      const pubs = e.pubs.filter((p) => p.anio == null || p.anio <= Y);
      return `<li><details><summary><span class="dot" style="background:var(--c${o.color})"></span>
        <span class="${e.cross ? "xd" : ""}">${esc(o.nombre)}</span><span class="n">${e.w} pub.</span></summary>
        <ol>${pubs.map((p) => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.titulo)}</a> (${p.anio ?? "s/f"})</li>`).join("")}</ol>
        ${e.w > pubs.length ? `<p class="hint">… y ${e.w - pubs.length} más.</p>` : ""}
        <button class="linkbtn" type="button" data-sel="${esc(o.id)}">Ver ficha de ${esc(o.corto)}</button></details></li>`;
    }).join("")}</ul>` : `<p class="hint">Sin coautores UTEC hasta ${Y}.</p>`;

    const hyper = n.hiperautoria_con.map((h) => `${h.n} con ${esc(ctx.byId.get(h.id).nombre)}`);
    const hyperHtml = hyper.length ? `<p class="hint">Además comparte publicaciones de hiperautoría (más de 50 autores) que no cuentan como arista: ${hyper.join("; ")}.</p>` : "";

    const sug = ctx.sim.filter((p) => (p.source === n.id || p.target === n.id) && !(p.coautores && p.first_year <= Y))
      .sort((a, b) => b.sim - a.sim).slice(0, 3)
      .map((p) => ({ o: ctx.byId.get(p.source === n.id ? p.target : p.source), p }));
    const sugHtml = !n.tiene_vector ? `<p class="hint">Sin publicaciones ni perfil para comparar.</p>`
      : `<ul class="coauthors">${sug.map(({ o, p }) => {
          const [pa, pb] = p.source === n.id ? [n, o] : [o, n], ev = UV.comunHtml(p), pubsEv = UV.pubsHtml(p, pa, pb, true);
          return `<li><button class="linkbtn" type="button" data-sel="${esc(o.id)}" style="display:flex;gap:6px;align-items:center;width:100%;text-decoration:none;color:var(--ink)">
          <span class="dot" style="background:var(--c${o.color})"></span><span class="${o.departamento !== n.departamento ? "xd" : ""}">${esc(o.nombre)}</span>
          <span class="n">sim. ${UV.dec(p.sim)}</span></button>
          ${ev || pubsEv ? `<details class="porque"><summary>¿Por qué?</summary>${ev ? `<p class="hint">${ev}</p>` : ""}${pubsEv ? `<p class="hint">Sus publicaciones más cercanas:</p>${pubsEv}` : ""}</details>` : ""}</li>`;
        }).join("")}</ul>`;

    const links = [["ORCID", n.orcid], ["Google Scholar", n.scholar], ["Scopus", n.scopus], ["Perfil CRIS", n.url_perfil]]
      .filter((l) => l[1]).map(([t, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${t} ↗</a>`).join("");

    const body = `<div class="ficha-hd">${av}<div><b>${esc(n.nombre)}</b><br>
        <span class="hint">${esc(n.departamento)}<br>${esc(n.grado_academico)}${n.renacyt ? " · RENACYT " + esc(n.renacyt) : ""}</span></div></div>
      <div class="kv">
        <div><b>${m.wdeg}</b><span>grado ponderado (pub. compartidas)</span></div>
        <div><b>${pct(m.bc)}</b><span>qué tan puente es (betweenness)</span></div>
        <div><b>${m.comm >= 0 ? "C" + m.comm : "—"}</b><span>comunidad</span></div>
        <div><b>${m.degree}</b><span>coautores UTEC</span></div>
        <div><b>${m.cross_degree}</b><span>de otros departamentos</span></div>
        <div><b>${n.indice_h ?? "—"}</b><span>índice h (Scopus)</span></div>
      </div>
      <p class="hint">${n.pubs_total} publicaciones en el portal${n.primer_anio ? ", desde " + n.primer_anio : ""}${ctx.topB.includes(n.id) ? " · <b>top 5 puente en " + Y + "</b>" : ""}.</p>
      <h4>Temas principales</h4>${temas}
      <h4>Coautores UTEC hasta ${Y}</h4>${coHtml}${co.length ? '<p class="hint">↔ = de otro departamento. Clic en un nombre para ver los títulos.</p>' : ""}${hyperHtml}
      <h4>Más similares sin coautoría</h4>${sugHtml}
      <div class="links">${links}</div>`;
    return box("Ficha del docente", body, `<button class="mini-btn" type="button" data-close>Cerrar ✕</button>`);
  }

  // ---------- 2. Pares potenciales ----------
  function pares(ctx) {
    const st = ctx.state, P = ctx.pairs;
    const lis = P.slice(0, 10).map((p, i) => {
      const a = ctx.byId.get(p.source), b = ctx.byId.get(p.target), v = st.potRank === "score" ? p.score : p.sim;
      return `<li tabindex="0" data-pair="${esc(p.source)}|${esc(p.target)}"><span class="n">${i + 1}</span>
        <span>${dot(a)} ${esc(a.corto)} <span class="hint">(${esc(a.zona)})</span><br>${dot(b)} ${esc(b.corto)} <span class="hint">(${esc(b.zona)})</span>
          ${p.comun && p.comun.length ? `<br><span class="hint">${UV.comunHtml(p)}</span>` : ""}</span>
        <span class="n">${UV.dec(v)}</span></li>`;
    }).join("");
    const body = `<p class="hint">${P.length} pares superan el umbral de ${UV.dec(st.threshold)}${st.crossOnly ? " entre departamentos distintos" : ""} y aún no han publicado juntos (hasta ${ctx.year}).</p>
      <div class="selrow"><label for="potRank">Ordenar por</label>
        <select id="potRank"><option value="sim"${st.potRank === "sim" ? " selected" : ""}>similitud temática</option>
        <option value="score"${st.potRank === "score" ? " selected" : ""}>puntaje combinado (0,7·sim + 0,3·Adamic-Adar)</option></select></div>
      ${lis ? `<ol class="rank pairs">${lis}</ol>` : `<p class="hint">Ningún par supera el umbral. Bájalo con el control de la barra.</p>`}
      <p class="hint">Pasa el ratón por un par para verlo en la red y sus publicaciones más cercanas; clic para abrir su ficha. «En común» = conceptos compartidos de la huella digital (Elsevier).</p>`;
    return box("Colaboraciones potenciales", body);
  }

  // ---------- 2b. Tema → equipo (T5) ----------
  function equipo(ctx) {
    const t = ctx.state.tema, tm = ctx.tema;
    const quitar = `<button class="mini-btn" type="button" data-cleartema>Quitar ✕</button>`;
    if (t.cargando) return box("Equipo para un tema", `<p class="hint">Buscando docentes cercanos a «${esc(t.q)}»… La primera búsqueda puede tardar mientras se carga el modelo.</p>`, quitar);
    if (t.error) return box("Equipo para un tema", /^https?:/.test(UV.api || "")
      ? `<p class="hint">El servidor de búsqueda no respondió y «${esc(t.q)}» no está entre los temas precalculados. Prueba con una habilidad de la lista (o una frase que la mencione), o vuelve a intentar en un minuto: el servidor puede estar despertando.</p>`
      : `<p class="hint">No se pudo buscar el tema: ${esc(t.error)}.<br>
      Instala las dependencias con <code>pip install -r requirements.txt</code> y reinicia <code>flask run</code>.</p>`, quitar);
    const nombres = (ids) => ids.map((i) => esc(ctx.byId.get(i).corto)).join(", ");
    const lista = (cs) => `<ul class="coauthors tema-cand">${cs.map((c) => `<li>
        <button class="linkbtn" type="button" data-sel="${esc(c.id)}" style="display:flex;gap:6px;align-items:center;width:100%;text-decoration:none;color:var(--ink)">
          ${dot(c.n)}<span>${esc(c.n.nombre)}<br><span class="hint">${esc(c.n.departamento)}</span></span><span class="n">${Math.round(c.rel * 100)} %</span></button>
        ${tm.facetas.length && c.facetas.length ? `<div class="chips tema-chips">${c.facetas.map((f) => `<span class="chip" title="${f.pubs
          ? f.pubs + (f.pubs > 1 ? " títulos la mencionan" : " título la menciona") : "destaca en esta habilidad"}">★ ${esc(f.nombre)}${f.pubs ? ` · ${f.pubs}` : ""}</span>`).join("")}</div>` : ""}
        ${c.pubs.length ? `<details><summary>Publicaciones más cercanas</summary><ul class="pubpar">${c.pubs.map((p) =>
          `<li><a href="${esc(p.u)}" target="_blank" rel="noopener">${esc(p.t)}</a>${p.y ? " (" + p.y + ")" : ""}</li>`).join("")}</ul></details>`
          : `<p class="hint" style="margin-left:16px">Sin publicaciones: coincide por su perfil.</p>`}</li>`).join("")}</ul>`;
    const equipo = [...tm.C].map((i) => ctx.byId.get(i));
    const deps = new Set(equipo.map((n) => n.departamento)).size;
    const red = [
      tm.directas ? `<b>${tm.directas}</b> ${tm.directas === 1 ? "par ya publicó junto" : "pares ya publicaron juntos"}` : "ninguno ha publicado con otro del equipo",
      tm.puentes.size ? `podrían presentarlos: <b>${nombres([...tm.puentes])}</b> (camino corto en la red)` : "",
      tm.aislados.length ? `sin camino corto hasta otro del equipo: ${nombres(tm.aislados)}` : "",
    ].filter(Boolean).join("; ");
    const aviso = t.aprox ? `<p class="hint aviso">Resultado <b>aproximado</b>, precalculado para «${esc(t.aprox)}». ${t.esperando
      ? "El servidor de búsqueda está despertando; se reemplaza solo cuando responda."
      : "El servidor de búsqueda no respondió: la búsqueda exacta está en la versión local."}</p>` : "";
    const nota = `<p class="hint">% = relativo al más cercano. Puntaje: sus 3 publicaciones más parecidas, pesando más la mejor (0,6 / 0,3 / 0,1; 75 %) y su perfil (25 %), con el modelo de embeddings de T4. Mejor en inglés: el 97 % de las publicaciones lo está.</p>`;
    if (!tm.facetas.length) {
      const body = `${aviso}<p class="tema-sum"><b>${tm.cand.length}</b> docentes de <b>${deps}</b> departamento${deps > 1 ? "s" : ""} con producción cercana a «${esc(tm.q)}». En ${ctx.year}: ${red}.</p>
        ${lista(tm.cand)}${nota}`;
      return box("Equipo para un tema", body, quitar);
    }
    const enlace = (e) => e.d === 0 ? "comparten un experto" : e.d === 1 ? "ya hay coautoría directa"
      : e.d < Infinity ? `se conectan a ${e.d} saltos en la red` : "<b>sin camino corto en la red</b> (hay que crear la colaboración)";
    const cobertura = [
      ...tm.enlaces.map((e) => `${esc(e.a)} ↔ ${esc(e.b)}: ${enlace(e)}`),
      tm.multi.length ? `cubre${tm.multi.length > 1 ? "n" : ""} más de una faceta: <b>${nombres(tm.multi)}</b>` : "nadie cubre más de una faceta",
    ];
    const body = `${aviso}<p class="tema-sum">«${esc(tm.q)}» combina <b>${tm.facetas.length} facetas</b>: ${tm.facetas.map((f) => `★ ${esc(f.nombre)}`).join(" · ")}.
        <b>${tm.C.size}</b> docentes de <b>${deps}</b> departamento${deps > 1 ? "s" : ""}.</p>
      <ul class="cobertura">${cobertura.map((x) => `<li>${x}</li>`).join("")}</ul>
      <p class="hint">En ${ctx.year}: ${red}.</p>
      ${lista(tm.cand)}
      <p class="hint">Orden = cercanía al tema completo. ★ = faceta en la que destaca: muy fuerte en esa habilidad, o fuerte y con títulos que la mencionan (el número). Facetas = habilidades del catálogo (26) que aparecen en el tema o en sus partes («with», «for», «con», «para»…).</p>${nota}`;
    return box("Equipo para un tema", body, quitar);
  }

  // ---------- 3. Comunidades ----------
  function comunidades(ctx) {
    const g = ctx.glob;
    const short = (d) => (ctx.zoneOf.get(d) || d);
    const rows = ctx.comms.map((c) => {
      const comp = Object.entries(c.composicion).map(([d, k]) => {
        const z = ctx.zones.find((x) => x.unidades.includes(d));
        return `<span class="dep"><span class="dot" style="background:var(--c${z ? z.color : 0})"></span><span>${esc(short(d))}&nbsp;${k}</span></span>`;
      }).join("");
      return `<tr><td><b>C${c.id}</b></td><td class="num">${c.size}</td><td>${comp}</td><td class="num">${Math.round(c.pureza * 100)} %</td></tr>`;
    }).join("");
    const f = (v) => (v == null ? "—" : UV.dec(v));
    const body = `<div class="scores">
        <div><div class="score">${f(g.NMI)}</div><div class="hint">NMI comunidad ↔ dpto.<br>(0 = nada, 1 = idénticos)</div></div>
        <div><div class="score">${f(g.Q)}</div><div class="hint">Modularidad Q<br>(&gt; 0,3 = grupos claros)</div></div>
        <div><div class="score">${f(g.ARI)}</div><div class="hint">ARI</div></div></div>
      ${rows ? `<table class="mini"><thead><tr><th></th><th>n</th><th>Departamentos</th><th>Pureza</th></tr></thead><tbody>${rows}</tbody></table>`
        : `<p class="hint">Aún no hay comunidades de 3 o más personas en ${ctx.year}.</p>`}
      <p class="hint">Pureza = % del departamento dominante. Solo ${g.n_en_comunidad} de ${ctx.nodes.length} docentes pertenecen a una comunidad; el resto aparece en el anillo exterior, junto a su departamento.</p>`;
    return box(`¿Comunidades = departamentos? · ${ctx.year}`, body);
  }

  // ---------- 4. Ranking ----------
  function ranking(ctx) {
    const st = ctx.state, b = st.rankMode === "b";
    const val = (n) => (b ? n.m.bc : n.m.wdeg);
    const items = ctx.nodes.filter((n) => val(n) > 0)
      .sort((x, y) => val(y) - val(x) || y.m.degree - x.m.degree || x.nombre.localeCompare(y.nombre)).slice(0, 8);
    const mx = d3.max(items, val) || 1;
    const lis = items.map((n, i) => `<li tabindex="0" data-id="${esc(n.id)}" class="${st.selected === n.id ? "sel" : ""}">
        <span class="n">${i + 1}</span>${dot(n)}<span>${esc(n.nombre)}<div class="bar"><i style="width:${(val(n) / mx) * 100}%"></i></div></span>
        <span class="n">${b ? pct(val(n)) : val(n)}</span></li>`).join("");
    const g = ctx.glob;
    const seg = `<span class="seg" role="group" aria-label="Tipo de ranking">
      <button type="button" data-rank="w" aria-pressed="${!b}">Prolíficos</button><button type="button" data-rank="b" aria-pressed="${b}">Puentes</button></span>`;
    const body = `${seg}<p class="hint">${b ? "Betweenness: % de caminos más cortos que pasan por la persona." : "Publicaciones compartidas con otros docentes UTEC (grado ponderado)."}</p>
      ${lis ? `<ol class="rank">${lis}</ol>` : `<p class="hint">Aún no hay coautorías internas en ${ctx.year}.</p>`}
      <p class="hint">${g.n_aristas} pares de coautores; ${Math.round(g.pct_cross * 100)} % cruzan departamentos. ${g.n_conectados} de ${ctx.nodes.length} docentes tienen algún coautor UTEC.</p>`;
    return box(`Ranking ${ctx.year}`, body);
  }

  // ---------- 5. Cómo leer la red (va en la leyenda, dentro de la red; ver main.js renderLegend) ----------
  UV.leerHtml = function (ctx) {
    const st = ctx.state, sw = (inner) => `<svg width="34" height="18" viewBox="0 0 38 20" aria-hidden="true">${inner}</svg>`;
    const ink = css("--edge-cross"), lig = css("--edge-in"), ring = css("--ring"), pot = css("--potential"), c1 = css("--c1"), tema = css("--tema");
    let h = `<div class="enc">
      ${sw(`<circle cx="9" cy="10" r="4.5" fill="${c1}"/><circle cx="26" cy="10" r="8.5" fill="${c1}"/>`)}<span><b>Tamaño</b> = publicaciones compartidas en UTEC</span>
      ${sw(`<circle cx="19" cy="10" r="7.5" fill="none" stroke="${c1}" stroke-width="3"/>`)}<span><b>Borde</b> = departamento (abajo)</span>`;
    if (st.rings) h += `${sw(`<circle cx="19" cy="10" r="5.5" fill="${c1}"/><circle cx="19" cy="10" r="9" fill="none" stroke="${ring}" stroke-width="2.5"/>`)}<span><b>Anillo oscuro</b> = puente (betweenness)</span>`;
    h += `${sw(`<line x1="2" y1="10" x2="36" y2="10" stroke="${ink}" stroke-width="2.5"/>`)}<span><b>Línea oscura</b> = coautoría entre departamentos</span>
      ${sw(`<line x1="2" y1="10" x2="36" y2="10" stroke="${lig}" stroke-width="2.5"/>`)}<span><b>Línea clara</b> = mismo departamento</span>`;
    if (st.potential) h += `${sw(`<line x1="2" y1="10" x2="36" y2="10" stroke="${pot}" stroke-width="2.4" stroke-dasharray="6 4"/>`)}<span><b>Punteada roja</b> = colaboración potencial</span>`;
    if (ctx.tema) h += `${sw(`<line x1="10" y1="10" x2="36" y2="10" stroke="${tema}" stroke-width="3.5" stroke-linecap="round" stroke-dasharray="1 5"/><path transform="translate(8,10)" d="${d3.symbol(d3.symbolStar, 110)()}" fill="${tema}"/>`)}<span><b>Estrella</b> = tema${ctx.tema.facetas.length ? " y sus facetas" : ""}; puntos más gruesos = más cercano</span>`;
    h += `</div>`;
    return h;
  };

  UV.renderPanel = function (ctx, on) {
    const st = ctx.state;
    let h = "";
    if (st.tema) h += equipo(ctx);
    if (st.selected) h += ficha(ctx);
    if (st.potential) h += pares(ctx);
    if (st.group === "comm") h += comunidades(ctx);
    h += ranking(ctx);
    const side = document.getElementById("side");
    const scroll = side.scrollTop;
    side.innerHTML = h;
    side.scrollTop = st.selected === ctx._lastSel ? scroll : 0;
    ctx._lastSel = st.selected;

    const act = (el, fn) => { el.addEventListener("click", fn); el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); fn(); } }); };
    side.querySelectorAll("li[data-id]").forEach((li) => act(li, () => on.select(li.dataset.id, true)));
    side.querySelectorAll("[data-sel]").forEach((b) => b.addEventListener("click", () => on.select(b.dataset.sel, true)));
    side.querySelectorAll("[data-rank]").forEach((b) => b.addEventListener("click", () => on.rank(b.dataset.rank)));
    side.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => on.select(null)));
    side.querySelectorAll("[data-cleartema]").forEach((b) => b.addEventListener("click", () => on.clearTema()));
    const pr = side.querySelector("#potRank");
    if (pr) pr.addEventListener("change", () => on.potRank(pr.value));
    side.querySelectorAll("li[data-pair]").forEach((li) => {
      const [a, b] = li.dataset.pair.split("|");
      li.addEventListener("mouseenter", () => on.hoverPair(a, b));
      li.addEventListener("focus", () => on.hoverPair(a, b));
      li.addEventListener("mouseleave", () => on.hoverPair(null));
      li.addEventListener("blur", () => on.hoverPair(null));
      act(li, () => on.select(a, true));
    });
  };
})();
