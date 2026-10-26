"""Rutas y parámetros compartidos por los scripts del pipeline."""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Datos crudos (tal como se extrajeron del scraping de cris.utec.edu.pe)
RAW_PERFILES = ROOT / "utec_perfiles"
RAW_DETALLE = RAW_PERFILES / "utec_publicaciones_detalle"

MANUAL = ROOT / "data" / "manual"
PROCESSED = ROOT / "data" / "processed"
STATIC_DATA = ROOT / "static" / "data"
STATIC_FOTOS = ROOT / "static" / "img" / "fotos"
ENTREGA = ROOT / "entrega"
for _d in (MANUAL, PROCESSED, STATIC_DATA, STATIC_FOTOS, ENTREGA):
    _d.mkdir(parents=True, exist_ok=True)

# --- Parámetros ---
ANIO_REF = 2026                 # año de la extracción (oct-2026)
ANIOS = list(range(2012, ANIO_REF + 1))   # rango de la animación
UMBRAL_HIPERAUTORIA = 50        # > 50 autores = hiperautoría
# Si es True, las publicaciones con hiperautoría no suman al peso `w` de las aristas
# (su conteo se conserva aparte en `w_hyper`). Ver README, sección "Hiperautoría".
EXCLUIR_HIPERAUTORIA = True

MODELO_EMB = "intfloat/multilingual-e5-base"   # requiere el prefijo "passage: "
TAU_RECENCIA = 8                # peso de una publicación = exp(-(2026 - año) / 8)
PESO_PUBS, PESO_PERFIL = 0.75, 0.25
SIM_MIN_EXPORT = 0.40           # se exportan los pares con similitud >= este valor
TOP_VECINOS = 10
SEED = 42


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def norm(s):
    return re.sub(r"\s+", " ", strip_accents(s)).lower().strip()


def split_pipe(s):
    if s is None or (isinstance(s, float) and s != s):
        return []
    return [t.strip() for t in str(s).split(" | ") if t.strip()]


def write_json(obj, path, **kw):
    path = Path(path)
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False, **kw)
    path.write_text(txt, encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
