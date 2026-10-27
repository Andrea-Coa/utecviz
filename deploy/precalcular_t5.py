"""Respaldo de T5 sin servidor: precalcula resultados para usarlos en GitHub Pages cuando el Space no responde.

Genera static/data/tema_precalc.json con:
  - las 26 habilidades del catálogo, solas;
  - las 325 combinaciones de 2 habilidades (temas compuestos);
  - temas de ejemplo (EJEMPLOS), con la búsqueda exacta de texto libre;
  - por habilidad, una expresión regular (términos en inglés de tema.TERMINOS + alias en español) para que la
    página detecte las habilidades de un texto libre y muestre la combinación más parecida.
Las publicaciones se guardan una sola vez (tabla `pubs`) y los candidatos las referencian por índice.

Uso (desde la raíz, con el modelo instalado):  python deploy/precalcular_t5.py
"""
import json
import sys
import time
import unicodedata
from itertools import combinations
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import tema  # noqa: E402

SALIDA = RAIZ / "static" / "data" / "tema_precalc.json"

EJEMPLOS = [
    "visualization of brain signals", "EEG signal classification",
    "climate change impacts on hydropower energy", "monitoreo de calidad del agua en ríos amazónicos con sensores IoT",
    "predicting concrete strength with machine learning and finite element models",
    "materiales compuestos con fibras naturales", "deep learning for medical images",
    "rehabilitation robots and exoskeletons", "natural language processing in Spanish",
    "renewable energy and solar power", "seismic behavior of masonry buildings", "remote sensing of glaciers",
    "genomics of Amazonian biodiversity", "engineering education and student learning", "air pollution in Lima",
    "water treatment and wastewater", "computational fluid dynamics of rivers", "process mining with machine learning",
    "visual analytics for student dropout", "biomechanics of human gait", "optimization of logistics and supply chain",
    "economic impact of mining", "bioplastics from agricultural waste", "sign language recognition with sensor gloves",
]

# alias en español (texto en minúsculas y sin tildes) que se suman a tema.TERMINOS para detectar habilidades
ALIAS_ES = {
    "Visualización de datos": r"visualiz|analitica visual",
    "Machine learning": r"aprendizaje automatico|clasificacion|prediccion",
    "Deep learning": r"aprendizaje profundo|redes? neuronal",
    "Grafos y redes": r"grafo|redes complejas",
    "Procesamiento de lenguaje": r"lenguaje natural|mineria de texto",
    "Visión por computadora": r"vision por computadora|vision artificial|imagen",
    "Señales biomédicas": r"senal|cerebr|electroencefal|electromiograf",
    "Estadística": r"estadistic|regresion",
    "Series de tiempo": r"series? de tiempo|serie temporal|pronostic",
    "Optimización": r"optimiz|investigacion operativa|logistic|cadena de suministro",
    "Elementos finitos": r"elementos? finitos?",
    "Mecánica de fluidos (CFD)": r"fluido|dinamica de fluidos",
    "Ensayos de materiales": r"materiales|ensayo|resistencia|fibra",
    "Robótica y control": r"robot|actuador|exoesquelet|control automatico",
    "Sistemas embebidos e IoT": r"sensor|embebid|internet de las cosas|monitoreo",
    "Teledetección y SIG": r"satelit|teledeteccion|percepcion remota|glaciar",
    "Hidrología": r"hidrolog|\brios?\b|cuenca|caudal|lluvia|\bagua\b",
    "Clima": r"clim|calentamiento global",
    "Bioinformática": r"genom|bioinformat|proteina|molecular|biodiversidad",
    "Química y procesos": r"quimic|sintesis|catalis|bioplastic|aguas residuales",
    "Energía": r"energi|fotovolt|eolic|hidroelectric|bateria",
    "Ingeniería estructural": r"estructur|concreto|hormigon|sismic|albanileria|edificio",
    "Biomecánica": r"biomecan|marcha humana|articulac|movimiento humano",
    "Investigación social": r"encuesta|entrevista|cualitativ|percepcion social",
    "Economía": r"econom|mercado|pobreza|mineria",
    "Educación en ingeniería": r"educacion|estudiant|ensenanza|deserci",
}


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()


def main():
    tema.iniciar()
    while not tema.estado()["listo"]:
        if tema.estado().get("error"):
            sys.exit("No se pudo cargar el modelo: " + tema.estado()["error"])
        time.sleep(1)
    H = list(tema.HABILIDADES)
    pubs, pos = [], {}

    def compacto(r):
        """Reemplaza cada publicación por su índice en la tabla compartida `pubs`."""
        for c in r["candidatos"]:
            idx = []
            for p in c["pubs"]:
                if p["u"] not in pos:
                    pos[p["u"]] = len(pubs)
                    pubs.append(p)
                idx.append(pos[p["u"]])
            c["pubs"] = idx
            for k in ("score", "z"):
                c.pop(k, None)
        return r

    res, ejemplos = {}, {}
    for h in range(len(H)):
        res[H[h]] = compacto(tema.buscar_habilidades([h]))
    for a, b in combinations(range(len(H)), 2):
        res[H[a] + " + " + H[b]] = compacto(tema.buscar_habilidades([a, b]))
    for q in EJEMPLOS:
        res["ej:" + q] = compacto(tema.buscar(q))
        ejemplos[sin_tildes(q)] = "ej:" + q
    salida = {
        "habilidades": [{"nombre": h, "re": tema.TERMINOS[h] + "|" + ALIAS_ES[h]} for h in H],
        "ejemplos": ejemplos, "pubs": pubs, "res": res,
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{SALIDA.relative_to(RAIZ)}: {len(res)} resultados ({len(H)} habilidades, {len(H) * (len(H) - 1) // 2} pares, "
          f"{len(EJEMPLOS)} ejemplos), {len(pubs)} publicaciones, {SALIDA.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
