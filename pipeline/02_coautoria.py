"""02 · Publicaciones y aristas de coautoría (con años).

Salida: data/processed/pubs.json, coautoria.json, productividad.json; añade una sección al reporte de calidad.
"""
import json
import re
from collections import defaultdict
from itertools import combinations

import numpy as np
import pandas as pd

from config import (ANIO_REF, EXCLUIR_HIPERAUTORIA, PROCESSED, RAW_DETALLE, UMBRAL_HIPERAUTORIA,
                    read_json, write_json)

personas = read_json(PROCESSED / "personas.json")
id_de = {p["nombre"]: p["id"] for p in personas}
dep_de = {p["id"]: p["departamento"] for p in personas}

puente = pd.read_csv(RAW_DETALLE / "publicacion_investigador.csv", dtype=str, keep_default_na=False)
det = pd.read_csv(RAW_DETALLE / "publicaciones_detalle.csv", dtype=str, keep_default_na=False)
det_json = json.loads((RAW_DETALLE / "publicaciones_detalle.json").read_text(encoding="utf-8"))
assert [r["url"] for r in det_json] == det.url.tolist()

# --- Cruce persona <-> publicación por nombre exacto del perfil ---
puente["id"] = puente.investigador.map(id_de)
sin_cruce = puente[puente.id.isna()]
print(f"02 · filas persona–publicación: {len(puente)} | cruzan: {puente.id.notna().sum()} | sin cruce: {len(sin_cruce)}")

# --- Publicaciones únicas ---
det = det.drop_duplicates("url").reset_index(drop=True)


def anio(r):
    if re.fullmatch(r"(19|20)\d{2}", r.anio.strip()):
        return int(r.anio)
    m = re.search(r"(19|20)\d{2}", r.Estado)
    return int(m.group(0)) if m else None


det["year"] = det.apply(anio, axis=1)

# Nº de autores. El portal oculta parte de las listas largas: el texto termina en
# "Mostrar N otrosMostrar menos" y los N ocultos quedan pegados al último visible sin coma,
# así que se cuenta: nombres separados por coma (o '&') + 1 si hay ocultos.
ocultos = det.autores.str.extract(r"Mostrar (\d+) otros")[0].notna()
lista = det.autores.str.replace(r"Mostrar \d+ otrosMostrar menos$", "", regex=True)
det["n_autores"] = lista.map(lambda s: len([t for t in re.split(r",\s*|\s+&\s+", s) if t.strip()])) + ocultos
# Firma colectiva: ningún investigador UTEC aparece por nombre (solo "LHCb Collaboration", etc.)
det["firma_colectiva"] = [len(r["autores_utec"]) == 0 for r in det_json]
det["hyper"] = det.firma_colectiva | (det.n_autores > UMBRAL_HIPERAUTORIA)
# Para el peso fraccional, una firma colectiva usa la mediana de las hiperautorías con lista conocida
n_med_hyper = int(det.loc[det.hyper & ~det.firma_colectiva, "n_autores"].median())
det["n_eff"] = np.where(det.firma_colectiva, n_med_hyper, det.n_autores).astype(int)

ids_pub = puente.dropna(subset=["id"]).groupby("url").id.apply(lambda s: sorted(set(s)))
det["ids"] = det.url.map(ids_pub)
assert det.ids.notna().all()

# --- Aristas ---
E = defaultdict(lambda: {"w": 0, "w_all": 0, "w_hyper": 0, "w_frac": 0.0, "w_by_year": defaultdict(int),
                         "w_sin_anio": 0, "pubs": []})
for r in det.itertuples():
    if len(r.ids) < 2:
        continue
    for a, b in combinations(r.ids, 2):
        e = E[(a, b)]
        e["w_all"] += 1
        e["w_hyper"] += int(r.hyper)
        if r.hyper and EXCLUIR_HIPERAUTORIA:
            continue
        e["w"] += 1
        e["w_frac"] += 1 / max(r.n_eff - 1, 1)
        if r.year is None or pd.isna(r.year):
            e["w_sin_anio"] += 1
        else:
            e["w_by_year"][int(r.year)] += 1
        e["pubs"].append({"titulo": r.titulo, "url": r.url, "anio": None if pd.isna(r.year) else int(r.year),
                          "hyper": bool(r.hyper)})

coaut = []
solo_hyper = []
for (a, b), e in sorted(E.items()):
    if e["w"] == 0:
        solo_hyper.append((a, b, e["w_hyper"]))
        continue
    wby = {str(y): n for y, n in sorted(e["w_by_year"].items())}
    first = min(e["w_by_year"]) if e["w_by_year"] else ANIO_REF
    e["pubs"].sort(key=lambda p: -(p["anio"] or 0))
    coaut.append({"source": a, "target": b, "w": e["w"], "w_all": e["w_all"], "w_hyper": e["w_hyper"],
                  "w_frac": round(e["w_frac"], 4), "first_year": first, "w_by_year": wby,
                  "w_sin_anio": e["w_sin_anio"], "cross": dep_de[a] != dep_de[b], "n_pubs": e["w"],
                  "pubs": e["pubs"]})

# --- Productividad individual ---
fila = puente.dropna(subset=["id"]).merge(det[["url", "year", "n_eff", "hyper"]], on="url")
prod = {}
for pid, g in fila.groupby("id"):
    primer = int(g.year.min()) if g.year.notna().any() else None
    prod[pid] = {"pubs_total": int(len(g)), "pubs_hyper": int(g.hyper.sum()), "primer_anio": primer,
                 "ultimo_anio": int(g.year.max()) if primer else None,
                 "pubs_por_anio_activo": round(len(g) / (ANIO_REF - primer + 1), 2) if primer else None,
                 "pubs_fraccional": round(float((1 / g.n_eff).sum()), 3)}

pubs = [{"url": r.url, "titulo": r.titulo, "tipo": r.tipo, "year": None if pd.isna(r.year) else int(r.year),
         "n_autores": int(r.n_autores), "n_eff": int(r.n_eff), "firma_colectiva": bool(r.firma_colectiva),
         "hyper": bool(r.hyper), "ids": r.ids} for r in det.itertuples()]

write_json(pubs, PROCESSED / "pubs.json")
write_json(coaut, PROCESSED / "coautoria.json")
write_json(prod, PROCESSED / "productividad.json")

rep = (PROCESSED / "reporte_calidad.md").read_text(encoding="utf-8").split("\n## Publicaciones")[0]
rep += "\n".join([
    "", "## Publicaciones y coautoría", "",
    f"- Filas persona–publicación (`publicacion_investigador.csv`): {len(puente)}; cruzan por nombre exacto: "
    f"{puente.id.notna().sum()} ({puente.id.notna().mean():.1%}); sin cruce: {len(sin_cruce)}"
    + ("" if sin_cruce.empty else " → " + ", ".join(sorted(sin_cruce.investigador.unique()))),
    f"- Publicaciones únicas (por URL): {len(det)}; sin año: {det.year.isna().sum()}",
    f"- Hiperautoría (> {UMBRAL_HIPERAUTORIA} autores o firma colectiva): {det.hyper.sum()} "
    f"({det.firma_colectiva.sum()} con firma colectiva; para ellas n_eff = {n_med_hyper}, mediana de las hiperautorías con lista)",
    f"- Publicaciones con autores ocultos tras 'Mostrar N otros' (conteo corregido +1): {ocultos.sum()}",
    f"- `EXCLUIR_HIPERAUTORIA = {EXCLUIR_HIPERAUTORIA}`. Pares de coautores cuya única coautoría es hiperautoría "
    f"(no generan arista): {len(solo_hyper)}"
    + ("" if not solo_hyper else " → " + "; ".join(f"{a} – {b} ({n} pubs)" for a, b, n in solo_hyper)),
    f"- Aristas de coautoría: {len(coaut)} ({sum(e['cross'] for e in coaut)} entre departamentos)",
    f"- Personas con publicaciones: {len(prod)} de {len(personas)}", ""])
(PROCESSED / "reporte_calidad.md").write_text(rep, encoding="utf-8")

print(f"     publicaciones: {len(det)} | hiperautoría: {det.hyper.sum()} | aristas: {len(coaut)} "
      f"| solo-hiperautoría descartadas: {len(solo_hyper)}")
for a, b, n in solo_hyper:
    print("       ", a, "–", b, n)
w = sorted(coaut, key=lambda e: -e["w"])[:5]
print("     aristas más pesadas:", [(e["source"], e["target"], e["w"], e["w_hyper"]) for e in w])
