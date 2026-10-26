"""04 · Métricas de red por año (grafo acumulado), comunidades estables entre años, NMI/ARI y pureza.

Salida: data/processed/metricas_por_anio.json
"""
from collections import Counter

import networkx as nx
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from config import ANIO_REF, ANIOS, PROCESSED, SEED, read_json, write_json

personas = read_json(PROCESSED / "personas.json")
coaut = read_json(PROCESSED / "coautoria.json")
ids = [p["id"] for p in personas]
dep = {p["id"]: p["departamento"] for p in personas}
MIN_COMUNIDAD = 3


def grafo(Y):
    """Coautorías con first_year <= Y; peso = publicaciones compartidas hasta Y (las sin año cuentan en 2026)."""
    G = nx.Graph()
    G.add_nodes_from(ids)
    for e in coaut:
        w = sum(n for y, n in e["w_by_year"].items() if int(y) <= Y) + (e["w_sin_anio"] if Y >= ANIO_REF else 0)
        if w > 0:
            G.add_edge(e["source"], e["target"], w=w, dist=1 / w)
    return G


def louvain(G):
    if G.number_of_edges() == 0:
        return [{n} for n in G]
    return nx.community.louvain_communities(G, weight="w", seed=SEED)


grafos = {Y: grafo(Y) for Y in ANIOS}
particiones = {Y: louvain(grafos[Y]) for Y in ANIOS}

# --- Etiquetas estables: C1, C2… por tamaño en 2026; hacia atrás, cada año se empareja con el
#     siguiente por máxima similitud de Jaccard (emparejamiento voraz 1 a 1) ---
etiquetas = {}   # Y -> list[(label, set)]
grandes = sorted([c for c in particiones[ANIO_REF] if len(c) >= MIN_COMUNIDAD], key=lambda c: (-len(c), min(c)))
etiquetas[ANIO_REF] = [(k + 1, c) for k, c in enumerate(grandes)]
siguiente = len(grandes) + 1
for Y in reversed(ANIOS[:-1]):
    actuales = [c for c in particiones[Y] if len(c) >= MIN_COMUNIDAD]
    ref = etiquetas[Y + 1]
    cand = sorted(((len(a & b) / len(a | b), i, lab) for i, a in enumerate(actuales) for lab, b in ref if a & b),
                  reverse=True)
    asignado, usadas = {}, set()
    for j, i, lab in cand:
        if i not in asignado and lab not in usadas:
            asignado[i] = lab
            usadas.add(lab)
    for i in range(len(actuales)):
        if i not in asignado:
            asignado[i] = siguiente
            siguiente += 1
    etiquetas[Y] = [(asignado[i], c) for i, c in enumerate(actuales)]

salida = {}
for Y in ANIOS:
    G = grafos[Y]
    part = {n: k for k, c in enumerate(sorted(particiones[Y], key=lambda c: min(c))) for n in c}  # partición completa
    comm = {n: -1 for n in ids}
    for lab, c in etiquetas[Y]:
        for n in c:
            comm[n] = lab
    bc = nx.betweenness_centrality(G, normalized=True)
    bc_w = nx.betweenness_centrality(G, normalized=True, weight="dist")
    nodos = {}
    for n in ids:
        wdeg = G.degree(n, weight="w")
        cross_w = sum(d["w"] for _, m, d in G.edges(n, data=True) if dep[m] != dep[n])
        nodos[n] = {"degree": G.degree(n), "wdeg": wdeg, "bc": round(bc[n], 6), "bc_w": round(bc_w[n], 6),
                    "cross_frac": round(cross_w / wdeg, 4) if wdeg else 0,
                    "cross_degree": sum(dep[m] != dep[n] for m in G.neighbors(n)), "comm": comm[n],
                    "part": part[n]}
    con = [n for n in ids if comm[n] >= 0]
    m = G.number_of_edges()
    glob = {"Q": round(nx.community.modularity(G, particiones[Y], weight="w"), 4) if m else 0.0,
            "NMI": round(normalized_mutual_info_score([dep[n] for n in con], [comm[n] for n in con]), 4) if con else None,
            "ARI": round(adjusted_rand_score([dep[n] for n in con], [comm[n] for n in con]), 4) if con else None,
            "pct_cross": round(sum(dep[a] != dep[b] for a, b in G.edges()) / m, 4) if m else 0.0,
            "n_comm": len(etiquetas[Y]), "n_aristas": m,
            "n_conectados": sum(1 for n in ids if G.degree(n) > 0),
            "n_en_comunidad": len(con)}
    comunidades = []
    for lab, c in sorted(etiquetas[Y]):
        cnt = Counter(dep[n] for n in c)
        d0, k0 = cnt.most_common(1)[0]
        comunidades.append({"id": lab, "size": len(c), "pureza": round(k0 / len(c), 3), "dominante": d0,
                            "composicion": dict(cnt.most_common())})
    salida[str(Y)] = {"nodes": nodos, "global": glob, "communities": comunidades}

write_json(salida, PROCESSED / "metricas_por_anio.json")
g = salida[str(ANIO_REF)]["global"]
print(f"04 · {ANIO_REF}: aristas={g['n_aristas']} conectados={g['n_conectados']} comunidades={g['n_comm']} "
      f"Q={g['Q']} NMI={g['NMI']} ARI={g['ARI']} %cross={g['pct_cross']}")
for c in salida[str(ANIO_REF)]["communities"]:
    print(f"     C{c['id']}: {c['size']} · pureza {c['pureza']:.0%} · {c['composicion']}")
print("     comunidades por año:", {Y: salida[str(Y)]["global"]["n_comm"] for Y in ANIOS})
print("     etiquetas usadas:", sorted({lab for Y in ANIOS for lab, _ in etiquetas[Y]}))
