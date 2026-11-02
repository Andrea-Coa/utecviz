"""05 · Exportación para la app: JSON/CSV finales, miniaturas de fotos y resumen con hallazgos.

Salida: static/data/{nodes,edges,similarity,metrics_by_year,departamentos,resumen}.json,
        static/data/{nodes,edges}.csv, entrega/{nodes,edges}.csv, static/img/fotos/{id}.webp|.jpg
"""
import hashlib
import shutil
from collections import Counter

import pandas as pd
from PIL import Image

from config import (ANIO_REF, ENTREGA, EXCLUIR_HIPERAUTORIA, MODELO_EMB, PROCESSED, RAW_PERFILES, STATIC_DATA,
                    STATIC_FOTOS, read_json, write_json)

personas = read_json(PROCESSED / "personas.json")
prod = read_json(PROCESSED / "productividad.json")
coaut = read_json(PROCESSED / "coautoria.json")
sim = read_json(PROCESSED / "similitud.json")
met = read_json(PROCESSED / "metricas_por_anio.json")
val = read_json(PROCESSED / "validacion_t4.json")
pubs = read_json(PROCESSED / "pubs.json")
import numpy as np  # noqa: E402

V = np.load(PROCESSED / "vectores.npy")
by_id = {p["id"]: p for p in personas}

# --- Zonas (anclas del layout) y grupos de color ---
# Cada unidad con >= 2 personas tiene su zona; las unidades de una sola persona (facultades, un centro)
# y quienes no tienen unidad comparten la zona "Dirección, facultades y centros".
CORTO = {
    "Ciencia de Computación y de Datos": "Computación y Datos",
    "Bioingeniería e Ingeniería Química": "Bioingeniería e Ing. Química",
    "Ciencias": "Ciencias",
    "Ingeniería Electrónica y Mecatrónica": "Electrónica y Mecatrónica",
    "Ingeniería Civil y Ambiental": "Civil y Ambiental",
    "Ingeniería Mecánica y de la Energía": "Mecánica y Energía",
    "Humanidades, Artes y Ciencias Sociales": "Humanidades, Artes y CC. SS.",
    "Ingeniería Industrial y Gestión de la Ingeniería": "Industrial y Gestión",
    "Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI": "Amazonía (ASRI)",
    "Sistemas y Seguridad de la Información": "Sistemas y Seguridad",
    "Negocios Digitales": "Negocios Digitales",
    "Física": "Física",
}
ZONA_OTRAS = "Dirección, facultades y centros"
n_unidad = Counter(p["departamento"] for p in personas)
for p in personas:
    d = p["departamento"]
    p["zona"] = CORTO.get(d, d) if n_unidad[d] >= 2 and d != "Sin departamento" else ZONA_OTRAS

# Color: 7 tonos de la paleta (el rojo queda reservado para las colaboraciones potenciales).
# Se asignan, en orden fijo, a las 7 zonas con más personas con publicaciones; el resto es "Otros" (gris).
con_pubs = Counter(p["zona"] for p in personas if p["id"] in prod)
total = Counter(p["zona"] for p in personas)
orden_zonas = sorted(total, key=lambda z: (-con_pubs[z], -total[z], z))
coloreadas = [z for z in orden_zonas if z != ZONA_OTRAS][:7]
deps = []
for z in orden_zonas:
    deps.append({"zona": z, "color": coloreadas.index(z) + 1 if z in coloreadas else 0,
                 "n": total[z], "n_con_pubs": con_pubs[z],
                 "unidades": sorted({p["departamento"] for p in personas if p["zona"] == z})})
color_de = {d["zona"]: d["color"] for d in deps}

# --- Fotos: miniatura cuadrada 96×96 recortada al centro, WebP + JPEG; placeholder -> sin foto ---
md5 = {p["id"]: hashlib.md5((RAW_PERFILES / p["archivo_foto"]).read_bytes()).hexdigest() for p in personas}
repetidas = {h for h, n in Counter(md5.values()).items() if n > 1}
for f in STATIC_FOTOS.glob("*"):
    f.unlink()
foto = {}
for p in personas:
    if md5[p["id"]] in repetidas:
        foto[p["id"]] = None
        continue
    im = Image.open(RAW_PERFILES / p["archivo_foto"]).convert("RGB")
    w, h = im.size
    s = min(w, h)
    top = max(0, int((h - s) * 0.25))   # retratos: el rostro está en el tercio superior
    im = im.crop(((w - s) // 2, top, (w - s) // 2 + s, top + s)).resize((96, 96), Image.LANCZOS)
    im.save(STATIC_FOTOS / f"{p['id']}.webp", "WEBP", quality=82, method=6)
    im.save(STATIC_FOTOS / f"{p['id']}.jpg", "JPEG", quality=82, optimize=True)
    foto[p["id"]] = f"img/fotos/{p['id']}"

# --- Coautorías con hiperautoría que no generan arista (para la ficha) ---
hyper_pares = Counter()
for pb in pubs:
    if pb["hyper"] and len(pb["ids"]) > 1:
        for i in pb["ids"]:
            for j in pb["ids"]:
                if i != j:
                    hyper_pares[(i, j)] += 1

# --- nodes ---
nodes = []
for k, p in enumerate(personas):
    pr = prod.get(p["id"], {})
    temas = p["temas_interes"][:6] or p["conceptos_huella"][:6]
    nodes.append({
        "id": p["id"], "nombre": p["nombre"], "iniciales": p["iniciales"],
        "departamento": p["departamento"], "departamentos": p["departamentos"], "zona": p["zona"],
        "color": color_de[p["zona"]], "grado_academico": p["grado_academico"],
        "citas": p["citas"], "indice_h": p["indice_h"], "renacyt": p["renacyt"],
        "orcid": p["orcid"], "scholar": p["scholar"], "scopus": p["scopus"], "url_perfil": p["url_perfil"],
        "foto": foto[p["id"]], "temas_top": temas, "conceptos_top": p["conceptos_huella"][:8],
        "pubs_total": pr.get("pubs_total", 0), "pubs_hyper": pr.get("pubs_hyper", 0),
        "pubs_por_anio_activo": pr.get("pubs_por_anio_activo"), "pubs_fraccional": pr.get("pubs_fraccional", 0),
        "primer_anio": pr.get("primer_anio"), "tiene_vector": bool(~np.isnan(V[k]).any()),
        "hiperautoria_con": [{"id": j, "n": n} for (i, j), n in sorted(hyper_pares.items(), key=lambda x: -x[1])
                             if i == p["id"] and not any({e["source"], e["target"]} == {i, j} for e in coaut)],
    })

edges = [{"source": e["source"], "target": e["target"], "w": e["w"], "w_frac": e["w_frac"],
          "w_hyper": e["w_hyper"], "first_year": e["first_year"], "w_by_year": e["w_by_year"],
          "w_sin_anio": e["w_sin_anio"], "cross": e["cross"], "n_pubs": e["n_pubs"],
          "pubs": [{"titulo": x["titulo"], "url": x["url"], "anio": x["anio"]} for x in e["pubs"][:5]]}
         for e in coaut]

metrics = met
write_json(nodes, STATIC_DATA / "nodes.json")
write_json(edges, STATIC_DATA / "edges.json")
write_json(sim, STATIC_DATA / "similarity.json")
write_json(metrics, STATIC_DATA / "metrics_by_year.json")
write_json(deps, STATIC_DATA / "departamentos.json")

# Publicaciones de cada persona para la ficha (se carga al primer clic): [título, slug, año, hiperautoría],
# de la más reciente a la más antigua. El slug es la URL sin el prefijo común del portal.
PREFIJO_PUB = "https://cris.utec.edu.pe/es/publications/"
pubs_de = {p["id"]: [] for p in personas}
for pb in sorted(pubs, key=lambda x: (-(x["year"] or 0), x["titulo"])):
    slug = pb["url"][len(PREFIJO_PUB):] if pb["url"].startswith(PREFIJO_PUB) else pb["url"]
    for i in pb["ids"]:
        pubs_de[i].append([pb["titulo"], slug, pb["year"], int(pb["hyper"])])
assert sum(map(len, pubs_de.values())) == sum(len(pb["ids"]) for pb in pubs)
write_json({"prefijo": PREFIJO_PUB, "pubs": pubs_de}, STATIC_DATA / "publicaciones.json")

# CSV planos para la entrega
m26 = metrics[str(ANIO_REF)]["nodes"]
ncsv = pd.DataFrame([{**{k: v for k, v in n.items() if k not in ("departamentos", "temas_top", "conceptos_top",
                                                                    "hiperautoria_con")},
                      "departamentos": " | ".join(n["departamentos"]), "temas_top": " | ".join(n["temas_top"]),
                      **{f"{k}_2026": v for k, v in m26[n["id"]].items()}} for n in nodes])
ecsv = pd.DataFrame([{**{k: v for k, v in e.items() if k not in ("w_by_year", "pubs")},
                      "w_by_year": ";".join(f"{y}:{c}" for y, c in e["w_by_year"].items()),
                      "pubs_urls": " | ".join(x["url"] for x in e["pubs"])} for e in edges])
for d in (STATIC_DATA, ENTREGA):
    ncsv.to_csv(d / "nodes.csv", index=False, encoding="utf-8")
    ecsv.to_csv(d / "edges.csv", index=False, encoding="utf-8")
shutil.copy(PROCESSED / "reporte_calidad.md", ENTREGA / "reporte_calidad.md")

# --- Resumen y hallazgos (redactados a partir de los datos) ---
nombre = {n["id"]: n["nombre"] for n in nodes}
zona = {n["id"]: n["zona"] for n in nodes}
g26 = metrics[str(ANIO_REF)]["global"]
top_w = sorted(m26.items(), key=lambda kv: (-kv[1]["wdeg"], -kv[1]["degree"]))[:5]
top_b = sorted(m26.items(), key=lambda kv: -kv[1]["bc"])[:5]
pot = sorted([s for s in sim if not s["coautores"] and zona[s["source"]] != zona[s["target"]]
              and by_id[s["source"]]["departamento"] != by_id[s["target"]]["departamento"]],
             key=lambda s: -s["sim"])
comms = metrics[str(ANIO_REF)]["communities"]
mezcla = min(comms, key=lambda c: c["pureza"]) if comms else None
anio_1 = next((int(y) for y in sorted(metrics) if metrics[y]["global"]["n_aristas"] > 0), None)
v_sim = next(r for r in val["resultados"] if r["ranking"] == "similitud" and not r["solo_entre_departamentos"])
v_cross = next(r for r in val["resultados"] if r["ranking"] == "similitud" and r["solo_entre_departamentos"])
aislados = sum(1 for v in m26.values() if v["degree"] == 0)

# --- Colaboradores y puentes: más allá del ranking ---
# El betweenness normalizado sobre 104 personas (69 aisladas) da valores muy chicos (≤ 2,3 %) y no dice QUÉ se pierde
# sin la persona. Se complementa con un análisis de corte en la red de ANIO_REF: si la persona no estuviera,
# ¿su grupo se parte? (punto de articulación), ¿cuántos colegas quedan fuera del trozo mayor? y ¿qué pares de
# departamentos pierden su única conexión? (el mismo cálculo hace main.js para cada año). Si la persona es la única
# de su unidad (p. ej. un centro de una sola persona), los pares con esa unidad no cuentan: se perderían por definición.
import networkx as nx  # noqa: E402

dep_de = {n["id"]: n["departamento"] for n in nodes}
G26 = nx.Graph()
G26.add_nodes_from(dep_de)
G26.add_edges_from((e["source"], e["target"], {"w": e["w"]}) for e in edges if e["first_year"] <= ANIO_REF)


def pares_dep(H):
    """Pares de departamentos con al menos un camino entre alguna de sus personas."""
    s = set()
    for c in nx.connected_components(H):
        ds = sorted({dep_de[i] for i in c})
        s |= {(a, b) for k, a in enumerate(ds) for b in ds[k + 1:]}
    return s


pares_base = pares_dep(G26)
corte = {}
for v in G26:
    if G26.degree(v) == 0:
        continue
    comp = nx.node_connected_component(G26, v) - {v}
    trozos = sorted((len(c) for c in nx.connected_components(G26.subgraph(comp))), reverse=True)
    H = G26.copy()
    H.remove_node(v)
    corte[v] = {"comp": len(comp) + 1, "trozos": trozos, "fuera": len(comp) - trozos[0],
                # si la persona es la única de su unidad, sus pares se perderían por definición: no cuentan
                "pares": sorted(x for x in pares_base - pares_dep(H) if n_unidad[dep_de[v]] > 1 or dep_de[v] not in x),
                "deps": sorted({dep_de[j] for j in G26[v]} - {dep_de[v]})}
articulacion = [v for v in corte if len(corte[v]["trozos"]) > 1]
comp_mayor = max(nx.connected_components(G26), key=len)
peso_total = sum(d["w"] for *_, d in G26.edges(data=True))
peso_top4 = sum(d["w"] for a, b, d in G26.edges(data=True) if a in {i for i, _ in top_w[:4]} or b in {i for i, _ in top_w[:4]})
rank_b = {i: k + 1 for k, (i, _) in enumerate(sorted(m26.items(), key=lambda kv: -kv[1]["bc"]))}
p1 = top_b[0][0]
# el de mayor betweenness casi sin coautores de otros departamentos, y el conector más amplio sin betweenness alto
broker = next((i for i, _ in top_b[1:5] if m26[i]["cross_degree"] <= m26[i]["degree"] / 3), None)
conector = max((i for i in corte if i not in {x for x, _ in top_b[:3]}),
               key=lambda i: (len(corte[i]["deps"]), m26[i]["cross_degree"], m26[i]["wdeg"]))
# quien sostiene más pares de departamentos fuera del componente principal
repite = max((i for i, _ in top_w[:4]), key=lambda i: m26[i]["wdeg"] / m26[i]["degree"])
fuera_cp = max((i for i in corte if i not in comp_mayor), key=lambda i: (len(corte[i]["pares"]), m26[i]["degree"]), default=None)


def dec(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def lista(xs):
    return ", ".join(xs[:-1]) + " y " + xs[-1] if len(xs) > 1 else xs[0]


hallazgos = [
    {"titulo": "La colaboración interna es escasa",
     "texto": f"Solo {g26['n_conectados']} de los {len(nodes)} docentes comparten al menos una publicación con otro "
              f"docente UTEC del portal; hay {g26['n_aristas']} pares de coautores y {aislados} personas aisladas. "
              f"La primera coautoría entre docentes del portal es de {anio_1}."},
    {"titulo": "Quiénes colaboran más",
     "texto": "; ".join(f"[[{i}]] {v['wdeg']} con {v['degree']} colegas"
                        + (f", {v['cross_degree']} de otro departamento" if v["cross_degree"] else ", todos de su departamento")
                        for i, v in top_w[:4])
              + f" (publicaciones compartidas · coautores UTEC). Estas 4 personas participan en {round(peso_top4 / peso_total * 100)} % "
              f"del peso de la coautoría interna ({peso_total} publicaciones compartidas, contadas por par). Hay dos perfiles: quien repite con pocos colegas "
              f"([[{repite}]], {dec(m26[repite]['wdeg'] / m26[repite]['degree'], 1)} publicaciones por coautor) y quien "
              f"abre colaboraciones con muchos ([[{max((i for i, _ in top_w[:4]), key=lambda i: m26[i]['degree'])}]])."},
    {"titulo": "El puente principal",
     "texto": f"[[{p1}]] ({dep_de[p1]}) tiene el mayor betweenness ({dec(top_b[0][1]['bc'] * 100, 1)} %) y "
              + (f"sus {m26[p1]['degree']} coautores son" if m26[p1]['cross_degree'] == m26[p1]['degree']
                 else f"{m26[p1]['cross_degree']} de sus {m26[p1]['degree']} coautores son") + " de otros departamentos "
              f"({lista(corte[p1]['deps'])}). Si no estuviera, el grupo principal de {corte[p1]['comp']} personas se "
              f"partiría en {len(corte[p1]['trozos'])} (el mayor de {corte[p1]['trozos'][0]}) y "
              f"{len(corte[p1]['pares'])} pares de departamentos perderían su única conexión. "
              f"La red es frágil: {len(articulacion)} de los {g26['n_conectados']} docentes conectados son puntos de corte."},
    {"titulo": "Betweenness alto no es lo mismo que puente entre departamentos",
     "texto": (f"[[{broker}]] es el n.º {rank_b[broker]} en betweenness, pero solo {m26[broker]['cross_degree']} de "
               f"sus {m26[broker]['degree']} coautores es de otro departamento: su intermediación viene de estar en una cadena "
               f"(sin esta persona, {corte[broker]['fuera']} colegas quedan separados del resto), no de reunir departamentos. "
               if broker else "")
              + f"Al revés, [[{conector}]] colabora con {len(corte[conector]['deps'])} departamentos distintos al suyo, "
              f"pero es el n.º {rank_b[conector]} en betweenness: sus colegas también se conectan entre sí y, sin esta persona, "
              f"{corte[conector]['fuera']} colega{'s' if corte[conector]['fuera'] != 1 else ''} quedaría{'n' if corte[conector]['fuera'] != 1 else ''} "
              f"fuera y " + (f"{len(corte[conector]['pares'])} pares de departamentos perderían su conexión."
                             if corte[conector]["pares"] else "ningún par de departamentos perdería su conexión.")
              + (f" Y [[{fuera_cp}]] tiene betweenness casi nulo (su grupo es de {corte[fuera_cp]['comp']} personas), pero "
                 f"sin esa persona {len(corte[fuera_cp]['pares'])} pares de departamentos quedarían desconectados. Por eso el "
                 f"panel muestra, junto al betweenness, qué se rompe sin cada persona." if fuera_cp and corte[fuera_cp]["pares"] else "")},
    {"titulo": "La mitad de la colaboración cruza departamentos",
     "texto": f"{round(g26['pct_cross'] * 100)} % de los pares de coautores son de departamentos distintos, pero se apoyan "
              f"en pocas personas: el grupo principal ({len(comp_mayor)} docentes de "
              f"{len({dep_de[i] for i in comp_mayor})} unidades) se sostiene por {sum(1 for v in articulacion if v in comp_mayor)} "
              f"puntos de corte."},
    {"titulo": "Las comunidades no calcan los departamentos",
     "texto": f"Louvain encuentra {g26['n_comm']} comunidades de 3 o más personas (modularidad Q = {dec(g26['Q'])}). "
              f"Su parecido con los departamentos es parcial (NMI = {dec(g26['NMI'])})"
              + (f"; la más mezclada, C{mezcla['id']}, reúne {mezcla['size']} personas de "
                 f"{len(mezcla['composicion'])} unidades distintas." if mezcla else ".")},
    {"titulo": "La colaboración potencial más fuerte",
     "texto": (f"{nombre[pot[0]['source']]} ({zona[pot[0]['source']]}) y {nombre[pot[0]['target']]} "
               f"({zona[pot[0]['target']]}) no han publicado juntos, pero su producción es la más parecida entre "
               f"departamentos distintos (similitud {dec(pot[0]['sim'])}).") if pot else ""},
]
resumen = {
    "fecha_datos": "octubre de 2026", "anio_ref": ANIO_REF, "modelo_embeddings": MODELO_EMB,
    "excluir_hiperautoria": EXCLUIR_HIPERAUTORIA,
    "n_docentes": len(nodes), "n_publicaciones": len(pubs), "n_pubs_hyper": sum(p["hyper"] for p in pubs),
    "n_relaciones": sum(len(p["ids"]) for p in pubs), "n_aristas": g26["n_aristas"],
    "pct_cross": g26["pct_cross"], "n_comunidades": g26["n_comm"], "Q": g26["Q"], "NMI": g26["NMI"],
    "ARI": g26["ARI"], "n_conectados": g26["n_conectados"], "n_sin_vector": sum(not n["tiene_vector"] for n in nodes),
    "n_con_foto": sum(1 for n in nodes if n["foto"]),
    "n_sin_pubs": sum(1 for n in nodes if n["pubs_total"] == 0),
    "validacion": {"corte": val["corte"], "ventana": val["ventana"], "positivos": v_sim["positivos"],
                   "candidatos": v_sim["candidatos"], "p10": v_sim["precision@10"], "aciertos10": v_sim["aciertos@10"],
                   "p50": v_sim["precision@50"], "aciertos50": v_sim["aciertos@50"],
                   "base": v_sim["base_aleatoria"], "auc": v_sim.get("auc"),
                   "positivos_cross": v_cross["positivos"], "auc_cross": v_cross.get("auc")},
    "hallazgos": [h for h in hallazgos if h["texto"]],
}
write_json(resumen, STATIC_DATA / "resumen.json", indent=1)
print(f"05 · nodes={len(nodes)} edges={len(edges)} pares_sim={len(sim)} fotos={resumen['n_con_foto']} "
      f"(placeholder: {len(nodes) - resumen['n_con_foto']})")
print("     zonas/colores:", [(d["zona"], d["color"], d["n"]) for d in deps])
for h in resumen["hallazgos"]:
    print("     -", h["titulo"], "→", h["texto"])
