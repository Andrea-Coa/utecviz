"""01 · Personas: identificador, departamento, grado académico, métricas bibliométricas y temas.

Salida: data/processed/personas.json y la primera parte de data/processed/reporte_calidad.md
"""
import re
from urllib.parse import unquote

import pandas as pd

from config import MANUAL, PROCESSED, RAW_PERFILES, norm, split_pipe, write_json

perf = pd.read_csv(RAW_PERFILES / "perfiles.csv", dtype=str, keep_default_na=False)
huella = pd.read_csv(RAW_PERFILES / "huella_digital.csv", dtype=str, keep_default_na=False)
reporte = ["# Reporte de calidad de datos", ""]

# --- Identificador: slug del perfil, decodificado ---
perf["id"] = perf.url_perfil.map(lambda u: unquote(u.rstrip("/").split("/")[-1]))
assert perf.id.is_unique and perf.nombre.is_unique


# --- Departamento ---
def limpia_unidad(u):
    return re.sub(r"\s+", " ", u).strip()


def unidades(cargos, prefijo):
    """Unidades del tipo `prefijo` (p. ej. 'Departamento de …') mencionadas en los cargos."""
    out = []
    for c in split_pipe(cargos):
        m = re.search(rf"(?:^|, )({prefijo}\b.*)$", c)
        if m:
            out.append(limpia_unidad(m.group(1)))
    return out


def departamento(cargos):
    deps = [d.replace("Departamento de ", "", 1) for d in unidades(cargos, "Departamento de")]
    if deps:
        return deps[0], deps, "Departamento"
    for tipo in ("Facultad", "Escuela", "Centro", "Instituto"):
        u = unidades(cargos, tipo)
        if u:
            return u[0], [], tipo
    return "Sin departamento", [], None


perf[["departamento", "departamentos", "tipo_unidad"]] = perf.cargos.apply(lambda c: pd.Series(departamento(c)))

# Normalización: misma clave sin tildes/mayúsculas/espacios → una sola forma (la más frecuente)
clave = perf.departamento.map(norm)
canon = perf.groupby(clave).departamento.agg(lambda s: s.mode().iloc[0])
perf["departamento"] = clave.map(canon)
perf["departamentos"] = perf.departamentos.map(lambda ds: [canon.get(norm(d), d) for d in ds])

# Correcciones manuales (data/manual/departamentos_override.csv: id,departamento,motivo)
ovr_path = MANUAL / "departamentos_override.csv"
if not ovr_path.exists():
    ovr_path.write_text("id,departamento,motivo\n", encoding="utf-8")
ovr = pd.read_csv(ovr_path, dtype=str).dropna(subset=["id", "departamento"])
for _, r in ovr.iterrows():
    perf.loc[perf.id == r.id, ["departamento", "tipo_unidad"]] = [r.departamento, "Manual"]

reporte += ["## Departamentos", "",
            f"- Unidades distintas tras normalizar: **{perf.departamento.nunique()}**",
            f"- Correcciones manuales aplicadas: {len(ovr)}", "",
            "Personas sin `Departamento de …` en sus cargos (se usó Facultad / Escuela / Centro / Instituto, "
            "o quedan como *Sin departamento*). Para corregir, añadir filas a `data/manual/departamentos_override.csv`:", "",
            "| id | asignado | tipo | cargos |", "|---|---|---|---|"]
for _, r in perf[perf.tipo_unidad.ne("Departamento")].iterrows():
    tipo = r.tipo_unidad if isinstance(r.tipo_unidad, str) else "—"
    reporte.append(f"| {r.id} | {r.departamento} | {tipo} | {r.cargos.replace('|', '·')} |")
reporte += ["", "| unidad | personas |", "|---|---|"]
reporte += [f"| {d} | {n} |" for d, n in perf.departamento.value_counts().items()]
reporte.append("")

# --- Grado académico máximo (se ignoran grados en curso, con fecha de fin '…') ---
ORDEN = ["Doctorado", "Maestría", "Título profesional / Licenciatura", "Bachiller", "Desconocido"]


def grado(item):
    t = norm(item)
    if re.search(r"doctor|ph\.?\s?d|dphil", t): return "Doctorado"
    if re.search(r"master|maestr|magister|m\.?sc\b", t): return "Maestría"
    if re.search(r"titulo|licenciad|ingenier|abogad|arquitect|economista", t): return "Título profesional / Licenciatura"
    if "bachiller" in t: return "Bachiller"
    return "Desconocido"


def grado_max(educacion):
    gs = [grado(i) for i in split_pipe(educacion) if "→ …" not in i]
    return min(gs, key=ORDEN.index) if gs else "Desconocido"


perf["grado_academico"] = perf.educacion.map(grado_max)


# --- Numéricos: texto con posible '.' de miles; vacío -> null (no 0) ---
def entero(s):
    s = str(s).strip()
    if not s:
        return None
    s = re.sub(r"\.0+$", "", s)          # '15.0' (export de pandas) -> '15'
    return int(re.sub(r"[.,\s]", "", s))


perf["citas_n"] = perf.citas.map(entero)
perf["indice_h_n"] = perf.indice_h.map(entero)

# --- RENACYT: dos nomenclaturas -> un nivel (0 = Distinguido, 1..7 = Nivel I..VII) ---
ROMANO = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}
ETQ = {0: "Distinguido", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII"}


def renacyt(s):
    if not s.strip():
        return None
    t = norm(s)
    if "distinguido" in t:
        return ETQ[0]
    n = ROMANO[re.search(r"\b([iv]+)$", t).group(1)]
    return ETQ[n + 4 if "rostworowski" in t else n]


perf["renacyt"] = perf.calificacion_renacyt.map(renacyt)

# --- Temas: temas de interés + conceptos de la huella (por peso) ---
huella["peso"] = huella.peso.str.rstrip("%").astype(float) / 100
conceptos = (huella.sort_values("peso", ascending=False).drop_duplicates(["investigador", "concepto"])
             .groupby("investigador").concepto.apply(list))
perf["temas_interes_l"] = perf.temas_interes.map(split_pipe)
perf["conceptos_huella"] = perf.nombre.map(conceptos).map(lambda x: x if isinstance(x, list) else [])


def iniciales(nombre):
    t = [w for w in nombre.replace("-", " ").split() if w[0].isupper()]
    return (t[0][0] + (t[-2][0] if len(t) >= 3 else t[-1][0] if len(t) == 2 else "")).upper()


def link(s):
    return s.strip() or None


def int_o_null(x):
    return None if pd.isna(x) else int(x)


personas = [{
    "id": r.id, "nombre": r.nombre, "iniciales": iniciales(r.nombre),
    "departamento": r.departamento, "departamentos": r.departamentos or [r.departamento],
    "tipo_unidad": r.tipo_unidad if isinstance(r.tipo_unidad, str) else None,
    "grado_academico": r.grado_academico,
    "citas": int_o_null(r.citas_n), "indice_h": int_o_null(r.indice_h_n), "renacyt": r.renacyt if isinstance(r.renacyt, str) else None,
    "orcid": link(r.orcid), "scholar": link(r.google_scholar), "scopus": link(r.scopus),
    "url_perfil": r.url_perfil, "archivo_foto": r.archivo_foto,
    "temas_interes": r.temas_interes_l, "conceptos_huella": r.conceptos_huella,
    "perfil_profesional": r.perfil_profesional.strip(),
} for r in perf.itertuples()]

write_json(personas, PROCESSED / "personas.json", indent=1)
(PROCESSED / "reporte_calidad.md").write_text("\n".join(reporte), encoding="utf-8")
print(f"01 · {len(personas)} personas | {perf.departamento.nunique()} unidades | "
      f"sin departamento: {(perf.departamento == 'Sin departamento').sum()}")
print(perf.departamento.value_counts().to_string())
print(perf.grado_academico.value_counts().to_string())
