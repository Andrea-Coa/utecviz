"""UtecVis · T5: dado un tema escrito por el usuario, ¿qué docentes podrían formar el equipo?

El tema se convierte en vector con el mismo modelo del pipeline (intfloat/multilingual-e5-base, prefijo
"query: ") y se compara con los embeddings ya calculados de cada publicación y de cada perfil
(data/processed/emb_pubs.npy, emb_perfiles.npy). Es lo único que la app calcula en vivo.

Puntaje de una persona = 0,75 · media ponderada (0,6 / 0,3 / 0,1) de sus 3 publicaciones más cercanas al tema
                       + 0,25 · similitud con su perfil (mismos pesos que el vector de persona de 03).
Sin publicaciones, el primer término es la mediana de las demás personas.
Candidatos: los que superan en 1,5 desviaciones a la media de las 104 personas (mínimo 3, máximo 8).
Además, el tema se descompone en facetas (habilidades del catálogo): se suman los expertos de cada faceta a la
lista, para que un tema compuesto («visualization of brain signals») traiga a los de cada parte, y cada persona
lleva la etiqueta de las facetas en que destaca.

Requiere sentence-transformers y torch. Si no están instalados, la app sigue funcionando y T5 avisa.
El modelo (~1 GB) se descarga de Hugging Face la primera vez y se carga en segundo plano al iniciar.
"""
import json
import re
import threading
from pathlib import Path

PROC = Path(__file__).resolve().parent / "data" / "processed"
MODELO = "intfloat/multilingual-e5-base"
PESO_PUBS, PESO_PERFIL = 0.75, 0.25
# las 3 publicaciones más cercanas pesan 0,6 / 0,3 / 0,1: una publicación muy precisa (un paper de EEG) cuenta
# más que varias medianamente parecidas; con el promedio plano, quien tiene un solo paper del tema se diluía
PESOS_TOP = (0.6, 0.3, 0.1)
Z_MIN, N_MIN, N_MAX = 1.5, 3, 8

# Facetas: un tema compuesto se descompone en habilidades del catálogo y se buscan expertos en cada una.
# El catálogo se revisó a mano contra los datos: cada habilidad devuelve expertos reconocibles, salvo
# «Grafos y redes» (casi nadie publica sobre eso en el portal).
HABILIDADES = {
    "Visualización de datos": "data visualization, visual analytics and interactive visual exploration of data",
    "Machine learning": "machine learning models for classification and prediction",
    "Deep learning": "deep learning with convolutional and recurrent neural networks",
    "Grafos y redes": "graph-based methods, network analysis and graph neural networks",
    "Procesamiento de lenguaje": "natural language processing and text mining",
    "Visión por computadora": "computer vision and image processing",
    "Señales biomédicas": "biomedical signal processing such as EEG and EMG",
    "Estadística": "statistical modeling, regression and hypothesis testing",
    "Series de tiempo": "time series analysis and forecasting",
    "Optimización": "mathematical optimization and operations research",
    "Elementos finitos": "finite element modeling and simulation of structures",
    "Mecánica de fluidos (CFD)": "computational fluid dynamics simulation",
    "Ensayos de materiales": "mechanical testing and characterization of materials",
    "Robótica y control": "robotics, control systems and actuators",
    "Sistemas embebidos e IoT": "embedded systems, sensors and internet of things",
    "Teledetección y SIG": "remote sensing, satellite imagery and geographic information systems",
    "Hidrología": "hydrology, rivers and water resources",
    "Clima": "climate change and climate modeling",
    "Bioinformática": "bioinformatics, genomics and molecular biology",
    "Química y procesos": "chemical synthesis and chemical process engineering",
    "Energía": "energy systems, renewable energy and power",
    "Ingeniería estructural": "structural engineering, concrete and seismic behavior",
    "Biomecánica": "biomechanics of human movement",
    "Investigación social": "surveys, interviews and qualitative social research",
    "Economía": "economics and econometrics",
    "Educación en ingeniería": "engineering education and student learning",
}
# Evidencia textual por habilidad, en el TÍTULO. Una etiqueta de faceta exige z ≥ 2 en la habilidad, o z ≥ 1,5 y
# al menos un título que mencione estos términos: el embedding sola no separa, p. ej., series de tiempo
# multivariadas (sin EEG) de señales biomédicas. Se usa el título y no el resumen porque en los resúmenes los
# términos aparecen de pasada («…to visualize the data…» en un sistema de control).
TERMINOS = {
    "Visualización de datos": r"visuali[sz]|visual analytic|dashboard",
    "Machine learning": r"machine learning|random forest|support vector|xgboost|gradient boosting|classifier",
    "Deep learning": r"deep learning|neural network|convolutional|\bcnn|lstm|transformer",
    "Grafos y redes": r"\bgraph|network analysis|complex network",
    "Procesamiento de lenguaje": r"natural language|text mining|\bnlp\b|language model|sentiment",
    "Visión por computadora": r"computer vision|image processing|image segmentation|object detection|\bimages?\b",
    "Señales biomédicas": r"\beeg\b|electroencephalog|\bemg\b|electromyog|\becg\b|electrocardiog|biosignal|biomedical signal|brain.computer|myoelectric",
    "Estadística": r"statistic|regression|hypothesis",
    "Series de tiempo": r"time.series|forecast",
    "Optimización": r"optimi[sz]|operations research|linear programming|heuristic",
    "Elementos finitos": r"finite.element|\bfem\b",
    "Mecánica de fluidos (CFD)": r"computational fluid|\bcfd\b|fluid dynamic|turbulen",
    "Ensayos de materiales": r"mechanical propert|tensile|compressive strength|characteri[sz]",
    "Robótica y control": r"robot|control system|actuator|controller",
    "Sistemas embebidos e IoT": r"embedded|\biot\b|internet of things|sensor|microcontroller|fpga",
    "Teledetección y SIG": r"remote sensing|satellite|\bgis\b|landsat|sentinel",
    "Hidrología": r"hydrolog|\brivers?\b|basin|streamflow|watershed|water resource|precipitation",
    "Clima": r"climat|global warming|el ni[ñn]o|\benso\b",
    "Bioinformática": r"genom|bioinformatic|sequenc|\bgenes?\b|protein|molecular",
    "Química y procesos": r"synthes|chemical|cataly|adsorption|reactor",
    "Energía": r"energy|solar|photovoltaic|wind power|power system|batter|hydropower",
    "Ingeniería estructural": r"structural|concrete|seismic|\bbeams?\b|masonry|earthquake",
    "Biomecánica": r"biomechanic|\bgait\b|musculoskeletal|kinematic|\bjoints?\b",
    "Investigación social": r"survey|interview|qualitative|perception|participatory",
    "Economía": r"econom|market|poverty",
    "Educación en ingeniería": r"education|student|curricul|teaching",
}
CONECTORES = r"\b(?:with|using|for|and|in|on|through|via|con|para|usando|mediante|y|en|sobre)\b|[,;:/+]"
Z_FACETA = 2.0       # una habilidad es faceta si destaca 2 desviaciones entre las 26 frente al tema o a un trozo
Z_TROZO = 2.8        # un trozo solo aporta facetas si alguna habilidad domina claramente (si no, es ambiguo)
MAX_FACETAS = 4
Z_EXPERTO = 2.0      # experto en una faceta: 2 desviaciones sobre los 104 (mínimo 2, máximo 3 por faceta)
Z_ETIQUETA = 1.5     # etiqueta de faceta en la lista: z ≥ 2, o z ≥ 1,5 con un título que la mencione (TERMINOS)

_lock = threading.Lock()
_st = {"modelo": None, "datos": None, "error": None, "cargando": False}


def _cargar_datos():
    import numpy as np
    leer = lambda f: json.loads((PROC / f).read_text(encoding="utf-8"))
    personas, pubs = leer("personas.json"), leer("pubs.json")
    E_pub = np.load(PROC / "emb_pubs.npy")
    pos = {u: k for k, u in enumerate(leer("emb_pubs_claves.json"))}
    E_pub = E_pub[[pos[p["url"]] for p in pubs]]
    E_perf = np.load(PROC / "emb_perfiles.npy")
    perf = {c.split("|")[0]: k for k, c in enumerate(leer("emb_perfiles_claves.json"))}
    ids = [p["id"] for p in personas]
    # publicaciones de cada persona; las de hiperautoría solo si no tiene otras
    propias = {i: [] for i in ids}
    hyper = {i: [] for i in ids}
    for k, p in enumerate(pubs):
        for i in p["ids"]:
            (hyper if p["hyper"] else propias)[i].append(k)
    de = {i: propias[i] or hyper[i] for i in ids}
    tiene_perfil = {p["id"]: bool(p["perfil_profesional"] or p["temas_interes"] or p["conceptos_huella"]) for p in personas}
    # por habilidad, cuántas publicaciones de cada persona la mencionan en el título
    evidencia = []
    for patron in TERMINOS.values():
        rx = re.compile(patron)
        menciona = [bool(rx.search(p["titulo"].lower())) for p in pubs]
        evidencia.append([sum(menciona[k] for k in de[i]) for i in ids])
    return {"ids": ids, "pubs": pubs, "E_pub": E_pub, "E_perf": E_perf[[perf[i] for i in ids]],
            "de": de, "tiene_perfil": tiene_perfil, "evidencia": evidencia}


def _cargar():
    try:
        datos = _cargar_datos()
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(MODELO, device="cpu")
        m.max_seq_length = 512
        datos["A"] = m.encode(["query: " + t for t in HABILIDADES.values()], normalize_embeddings=True)
        datos["habilidad"] = [_puntaje(datos, a) for a in datos["A"]]   # expertos por habilidad, precalculados
        with _lock:
            _st.update(modelo=m, datos=datos)
    except Exception as e:  # dependencias o modelo no disponibles: T5 queda desactivada
        with _lock:
            _st["error"] = f"{type(e).__name__}: {e}"
    finally:
        with _lock:
            _st["cargando"] = False


def iniciar():
    """Carga el modelo en segundo plano para que la primera búsqueda no espere."""
    with _lock:
        if _st["modelo"] or _st["cargando"] or _st["error"]:
            return
        _st["cargando"] = True
    threading.Thread(target=_cargar, daemon=True).start()


def estado():
    with _lock:
        if _st["modelo"]:
            return {"listo": True}
        return {"listo": False, "cargando": _st["cargando"], "error": _st["error"]}


def _puntaje(d, v):
    """Puntaje de cada persona frente a un vector de consulta, y sus publicaciones más cercanas."""
    import numpy as np
    s_pub = d["E_pub"] @ v
    s_perf = d["E_perf"] @ v
    sps, top = [], []
    for i in d["ids"]:
        orden = sorted(d["de"][i], key=lambda k: -s_pub[k])[:len(PESOS_TOP)]
        w = PESOS_TOP[:len(orden)]
        sps.append(float(np.dot(s_pub[orden], w) / sum(w)) if orden else None)
        top.append(orden)
    # quien no tiene publicaciones recibe la mediana del grupo en ese componente: solo su perfil lo distingue,
    # y un perfil en español no le gana por idioma a quien publica sobre el tema (el corpus es 97 % inglés)
    sp_med = float(np.median([x for x in sps if x is not None]))
    score = []
    for j, i in enumerate(d["ids"]):
        sp = sps[j]
        if sp is None:
            sc = PESO_PUBS * sp_med + PESO_PERFIL * float(s_perf[j])
        elif d["tiene_perfil"][i]:
            sc = PESO_PUBS * sp + PESO_PERFIL * float(s_perf[j])
        else:
            sc = sp
        score.append(sc)
    return np.array(score), top


def _seleccion(d, score, top, z_min, n_min, n_max):
    import numpy as np
    z = (score - score.mean()) / (score.std() or 1)
    orden = np.argsort(-score)
    sel = [j for j in orden[:n_max] if z[j] >= z_min]
    if len(sel) < n_min:
        sel = list(orden[:n_min])
    med, mx = float(np.median(score)), float(score.max())
    return [{
        "id": d["ids"][j], "score": round(float(score[j]), 4), "z": round(float(z[j]), 2),
        "rel": round((float(score[j]) - med) / ((mx - med) or 1), 3),
        "pubs": [{"t": d["pubs"][k]["titulo"], "u": d["pubs"][k]["url"], "y": d["pubs"][k]["year"]} for k in top[j]],
    } for j in sel]


def _zs(s):
    return (s - s.mean()) / (s.std() or 1)


def facetas(d, m, q):
    """Habilidades del catálogo que componen el tema: las que destacan frente a la frase completa y frente a
    cada trozo separado por conectores («with», «for», «con», «para»…), para que una parte no se diluya
    en el promedio de una frase larga. Devuelve índices de HABILIDADES, del más al menos marcado."""
    import numpy as np
    nombres = [h.lower() for h in HABILIDADES]
    if q.strip().lower() in nombres:          # elegida del catálogo
        return [nombres.index(q.strip().lower())]
    trozos = [t.strip() for t in re.split(CONECTORES, q, flags=re.I) if t and len(t.strip()) > 2]
    textos = [q] + (trozos if len(trozos) > 1 else [])
    V = m.encode(["query: " + t for t in textos], normalize_embeddings=True)
    mejor = {}
    for k, v in enumerate(V):
        z = _zs(d["A"] @ v)
        if k > 0 and z.max() < Z_TROZO:      # trozo ambiguo («fibras naturales»): no aporta facetas
            continue
        for h in np.where(z >= Z_FACETA)[0]:
            mejor[int(h)] = max(mejor.get(int(h), 0), float(z[h]))
    return sorted(mejor, key=lambda h: -mejor[h])[:MAX_FACETAS]


def _resultado(d, q, v, hs):
    """Lista única ordenada por cercanía al vector del tema `v` (candidatos del tema + los 2–3 expertos de cada
    faceta `hs`), y en cada persona, las facetas en las que destaca (z ≥ Z_EXPERTO, o z ≥ Z_ETIQUETA con evidencia)."""
    import numpy as np
    score, top = _puntaje(d, v)
    zh = {h: _zs(d["habilidad"][h][0]) for h in hs}
    sel = {c["id"] for c in _seleccion(d, score, top, Z_MIN, N_MIN, N_MAX)}
    for h in hs:
        sel |= {c["id"] for c in _seleccion(d, *d["habilidad"][h], Z_EXPERTO, 2, 3)}
    idx = [d["ids"].index(i) for i in sel]
    cand = {c["id"]: c for c in _seleccion(d, score, top, -np.inf, len(d["ids"]), len(d["ids"]))}
    lista = []
    for j in sorted(idx, key=lambda j: -score[j]):
        c = cand[d["ids"][j]]
        ev = {h: d["evidencia"][h][j] for h in hs}
        c["facetas"] = [{"nombre": list(HABILIDADES)[h], "pubs": ev[h]} for h in hs
                        if zh[h][j] >= Z_EXPERTO or (zh[h][j] >= Z_ETIQUETA and ev[h] > 0)]
        lista.append(c)
    return {"q": q, "candidatos": lista, "facetas": [list(HABILIDADES)[h] for h in hs]}


def buscar(q):
    with _lock:
        m, d = _st["modelo"], _st["datos"]
    if m is None:
        return None
    hs = facetas(d, m, q)
    nombres = [h.lower() for h in HABILIDADES]
    if q.strip().lower() in nombres:        # habilidad del catálogo: se busca por su descripción, no por el nombre corto
        v = d["A"][nombres.index(q.strip().lower())]
    else:
        v = m.encode(["query: " + q], normalize_embeddings=True)[0]
    return _resultado(d, q, v, hs)


def buscar_habilidades(hs):
    """Tema formado por habilidades del catálogo (índices): vector = promedio normalizado de sus descripciones y
    facetas = esas habilidades. Lo usa deploy/precalcular_t5.py para el respaldo sin servidor."""
    import numpy as np
    with _lock:
        d = _st["datos"]
    if d is None:
        return None
    v = d["A"][list(hs)].sum(axis=0)
    v = v / np.linalg.norm(v)
    return _resultado(d, " + ".join(list(HABILIDADES)[h] for h in hs), v, list(hs) if len(hs) > 1 else [])
