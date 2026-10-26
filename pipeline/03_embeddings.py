"""03 · Embeddings por persona, matriz de similitud, puntaje combinado y validación temporal de T4.

Salida: data/processed/emb_pubs.npy (+ emb_pubs_urls.json), emb_perfiles.npy, vectores.npy,
        similitud.json, validacion_t4.json
"""
import hashlib
import json
from itertools import combinations

import networkx as nx
import numpy as np
import pandas as pd

from config import (ANIO_REF, MODELO_EMB, PESO_PERFIL, PESO_PUBS, PROCESSED, RAW_DETALLE, SEED,
                    SIM_MIN_EXPORT, TAU_RECENCIA, TOP_VECINOS, read_json, write_json)

personas = read_json(PROCESSED / "personas.json")
pubs = read_json(PROCESSED / "pubs.json")
coaut = read_json(PROCESSED / "coautoria.json")
ids = [p["id"] for p in personas]
idx = {i: k for k, i in enumerate(ids)}
N = len(ids)

det = pd.read_csv(RAW_DETALLE / "publicaciones_detalle.csv", dtype=str, keep_default_na=False).set_index("url")

_modelo = None


def modelo():
    global _modelo
    if _modelo is None:
        from sentence_transformers import SentenceTransformer
        _modelo = SentenceTransformer(MODELO_EMB, device="cpu")
        _modelo.max_seq_length = 512
    return _modelo


def embed(textos):
    return modelo().encode(["passage: " + t for t in textos], batch_size=16, normalize_embeddings=True,
                           show_progress_bar=True, convert_to_numpy=True).astype(np.float32)


def cache(nombre, claves, textos):
    """Embeddings cacheados por clave: solo se calculan los que faltan."""
    f_emb, f_key = PROCESSED / f"{nombre}.npy", PROCESSED / f"{nombre}_claves.json"
    viejo = {}
    if f_emb.exists() and f_key.exists():
        E0 = np.load(f_emb)
        viejo = {k: E0[i] for i, k in enumerate(json.loads(f_key.read_text(encoding="utf-8")))}
    faltan = [i for i, k in enumerate(claves) if k not in viejo]
    if faltan:
        print(f"     calculando {len(faltan)} embeddings de {nombre} con {MODELO_EMB}…")
        nuevos = embed([textos[i] for i in faltan])
        for j, i in enumerate(faltan):
            viejo[claves[i]] = nuevos[j]
    E = np.stack([viejo[k] for k in claves])
    np.save(f_emb, E)
    f_key.write_text(json.dumps(claves, ensure_ascii=False), encoding="utf-8")
    return E


# --- 1. Embedding de cada publicación: título + resumen ---
urls = [p["url"] for p in pubs]
txt_pub = [(det.at[u, "titulo"] + ". " + det.at[u, "resumen"]).strip(". ") for u in urls]
E_pub = cache("emb_pubs", urls, txt_pub)

# --- 3. Embedding del perfil: perfil profesional + temas de interés + conceptos de la huella ---
txt_perf, tiene_perf = [], []
for p in personas:
    partes = [p["perfil_profesional"], "; ".join(p["temas_interes"]), "; ".join(p["conceptos_huella"][:25])]
    t = ". ".join(x for x in partes if x)
    txt_perf.append(t or "-")
    tiene_perf.append(bool(t))
E_perf = cache("emb_perfiles", [p["id"] + "|" + hashlib.md5(t.encode("utf-8")).hexdigest()[:10] for p, t in zip(personas, txt_perf)], txt_perf)


# --- 2 y 4. Vector de la persona ---
def peso_pub(p):
    """Recencia exp(-(2026-año)/8) × atenuación de equipos grandes (peso 1 hasta 10 autores, luego 10/n)."""
    rec = np.exp(-(ANIO_REF - (p["year"] or ANIO_REF)) / TAU_RECENCIA)
    return rec * min(1.0, 10 / p["n_eff"])


def vectores(hasta=None):
    """Vectores L2 por persona usando solo publicaciones con año <= `hasta` (None = todas)."""
    acc = np.zeros((N, E_pub.shape[1]), np.float32)
    wsum = np.zeros(N)
    for k, p in enumerate(pubs):
        if hasta is not None and (p["year"] is None or p["year"] > hasta):
            continue
        w = peso_pub(p)
        for i in p["ids"]:
            acc[idx[i]] += w * E_pub[k]
            wsum[idx[i]] += w
    V = np.full((N, E_pub.shape[1]), np.nan, np.float32)
    for j in range(N):
        tiene_pubs = wsum[j] > 0
        if tiene_pubs:
            vp = acc[j] / np.linalg.norm(acc[j])
            v = PESO_PUBS * vp + PESO_PERFIL * E_perf[j] if tiene_perf[j] else vp
        elif tiene_perf[j]:
            v = E_perf[j]
        else:
            continue
        V[j] = v / np.linalg.norm(v)
    return V


def similitud(V):
    """Coseno tras centrar los vectores (restar la media). Los modelos e5 producen cosenos comprimidos
    (casi todo entre 0,7 y 0,9); centrar devuelve un rango interpretable sin alterar el orden de vecinos
    de forma relevante."""
    ok = ~np.isnan(V).any(axis=1)
    C = V.copy()
    C[ok] -= C[ok].mean(axis=0)
    C[ok] /= np.linalg.norm(C[ok], axis=1, keepdims=True)
    S = np.full((N, N), np.nan)
    S[np.ix_(ok, ok)] = C[ok] @ C[ok].T
    return S, ok


def grafo(hasta):
    G = nx.Graph()
    G.add_nodes_from(ids)
    for e in coaut:
        w = sum(n for y, n in e["w_by_year"].items() if int(y) <= hasta) + (e["w_sin_anio"] if hasta >= ANIO_REF else 0)
        if w > 0:
            G.add_edge(e["source"], e["target"], w=w)
    return G


def adamic_adar(G):
    aa = np.zeros((N, N))
    pares = [(a, b) for a, b in combinations(ids, 2)]
    for a, b, v in nx.adamic_adar_index(G, pares):
        aa[idx[a], idx[b]] = aa[idx[b], idx[a]] = v
    return aa / aa.max() if aa.max() > 0 else aa


V = vectores()
S, ok = similitud(V)
G26 = grafo(ANIO_REF)
AA = adamic_adar(G26)
SCORE = 0.7 * S + 0.3 * AA
np.save(PROCESSED / "vectores.npy", V)

first = {}
for e in coaut:
    first[(e["source"], e["target"])] = first[(e["target"], e["source"])] = e["first_year"]

# Pares exportados: sim >= umbral, más los top-10 vecinos de cada persona (para la ficha)
sel = set()
for a, b in combinations(range(N), 2):
    if ok[a] and ok[b] and S[a, b] >= SIM_MIN_EXPORT:
        sel.add((a, b))
for a in range(N):
    if not ok[a]:
        continue
    orden = [b for b in np.argsort(-np.nan_to_num(S[a], nan=-9)) if b != a and ok[b]][:TOP_VECINOS]
    sel |= {tuple(sorted((a, b))) for b in orden}
pares = []
for a, b in sorted(sel):
    ia, ib = ids[a], ids[b]
    pares.append({"source": ia, "target": ib, "sim": round(float(S[a, b]), 4),
                  "score_combinado": round(float(SCORE[a, b]), 4), "adamic_adar": round(float(AA[a, b]), 4),
                  "coautores": (ia, ib) in first, "first_year": first.get((ia, ib))})
write_json(pares, PROCESSED / "similitud.json")

tri = S[np.triu_indices(N, 1)]
tri = tri[~np.isnan(tri)]
print(f"03 · personas con vector: {ok.sum()}/{N} | sim: p50={np.median(tri):.2f} p90={np.quantile(tri, .9):.2f} "
      f"p99={np.quantile(tri, .99):.2f} max={tri.max():.2f} | pares exportados: {len(pares)} "
      f"(≥{SIM_MIN_EXPORT}: {(tri >= SIM_MIN_EXPORT).sum()}; ≥0.70: {(tri >= 0.7).sum()})")
sin_vector = [ids[j] for j in range(N) if not ok[j]]
if sin_vector:
    print("     sin vector (no participan en T4):", sin_vector)

# --- Validación temporal: sugerencias con datos hasta 2022, ¿publicaron juntos en 2023–2026? ---
CORTE = 2022
V22 = vectores(hasta=CORTE)
S22, ok22 = similitud(V22)
G22 = grafo(CORTE)
AA22 = adamic_adar(G22)
dep = {p["id"]: p["departamento"] for p in personas}
nuevos = {tuple(sorted((idx[e["source"]], idx[e["target"]]))) for e in coaut
          if not G22.has_edge(e["source"], e["target"])
          and sum(n for y, n in e["w_by_year"].items() if CORTE < int(y) <= ANIO_REF) > 0}
cand = [(a, b) for a, b in combinations(range(N), 2)
        if ok22[a] and ok22[b] and not G22.has_edge(ids[a], ids[b])]
res = {"corte": CORTE, "ventana": f"{CORTE + 1}-{ANIO_REF}", "candidatos": len(cand),
       "positivos": sum(p in nuevos for p in cand), "resultados": []}
rng = np.random.default_rng(SEED)
for nombre, M in [("similitud", S22), ("puntaje_combinado", 0.7 * S22 + 0.3 * AA22)]:
    for solo_cross in (False, True):
        c = [p for p in cand if not solo_cross or dep[ids[p[0]]] != dep[ids[p[1]]]]
        pos = np.array([p in nuevos for p in c])
        orden = np.argsort(-np.array([M[a, b] for a, b in c]))
        fila = {"ranking": nombre, "solo_entre_departamentos": solo_cross, "candidatos": len(c),
                "positivos": int(pos.sum()), "base_aleatoria": round(float(pos.mean()), 4)}
        for K in (10, 20, 50, 100):
            fila[f"precision@{K}"] = round(float(pos[orden[:K]].mean()), 3)
            fila[f"aciertos@{K}"] = int(pos[orden[:K]].sum())
        # AUC: probabilidad de que un positivo puntúe más que un negativo
        sc = np.array([M[a, b] for a, b in c])
        if 0 < pos.sum() < len(pos):
            r = pd.Series(sc).rank().values
            fila["auc"] = round(float((r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())), 3)
        res["resultados"].append(fila)
res["pares_nuevos"] = [[ids[a], ids[b]] for a, b in sorted(nuevos)]
write_json(res, PROCESSED / "validacion_t4.json", indent=1)
print(f"     validación T4: {res['positivos']} pares nuevos en {res['ventana']} entre {res['candidatos']} candidatos")
for f in res["resultados"]:
    print("      ", {k: v for k, v in f.items() if k.startswith(("ranking", "solo", "base", "precision@10", "precision@50", "aciertos@50", "auc"))})
