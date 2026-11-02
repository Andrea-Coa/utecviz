"""UtecVis by Batimix: aplicación Flask.

Al iniciar, lee y VALIDA los datos que calculó el pipeline (static/data/*.json): ids de nodo únicos, cada arista
une dos nodos existentes, sin lazos ni aristas repetidas, y métricas para cada nodo en cada año. Si algo no cuadra,
la app no arranca y dice qué falta (mejor que una red rota en el navegador).

Rutas
  /                     la página (D3)
  /api/red              todo lo que la página necesita para dibujar la red, en una sola respuesta comprimida
  /api/nodes            nodos (docentes) con sus métricas del año ?year= (por defecto, el último)
  /api/edges            aristas (coautorías) vigentes en ?year=, con el peso acumulado hasta ese año
  /api/salud            estado: conteos de nodos y aristas, años disponibles y si el modelo de T5 está listo
  /api/tema?q=…         T5: el único cómputo por pedido (ver tema.py)

Las respuestas JSON, JS y CSS se comprimen con gzip (la carga inicial baja de ~0,7 MB a ~0,15 MB) y llevan ETag:
una recarga sin cambios responde 304 sin volver a enviar los datos.
Uso:  pip install -r requirements.txt && flask run
      UTECVIS_SIN_T5=1 flask run   → sin cargar el modelo de T5 (arranque inmediato; T5 usa el resultado precalculado)
"""
import gzip
import hashlib
import json
import os
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, url_for
from werkzeug.exceptions import HTTPException

import tema

app = Flask(__name__)
# Los estáticos (fotos, JS, CSS) se sirven con ETag y respuesta condicional (304); además se cachean una hora.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
DATA = Path(app.static_folder) / "data"
ARCHIVOS_RED = ["nodes", "edges", "similarity", "metrics_by_year", "departamentos", "resumen"]
COMPRIMIBLES = {"application/json", "text/javascript", "application/javascript", "text/css", "text/html", "image/svg+xml"}


class DatosInvalidos(RuntimeError):
    pass


def cargar_red():
    """Lee los JSON de la red y comprueba que nodos y aristas sean coherentes entre sí."""
    faltan = [f"{f}.json" for f in ARCHIVOS_RED if not (DATA / f"{f}.json").exists()]
    if faltan:
        raise DatosInvalidos(f"Faltan {', '.join(faltan)} en {DATA}. Corre ./run_pipeline.sh")
    red = {f: json.loads((DATA / f"{f}.json").read_text(encoding="utf-8")) for f in ARCHIVOS_RED}
    ids = [n["id"] for n in red["nodes"]]
    errores = []
    if len(ids) != len(set(ids)):
        errores.append("hay ids de nodo repetidos")
    validos, vistas = set(ids), set()
    for e in red["edges"]:
        a, b = e["source"], e["target"]
        if a not in validos or b not in validos:
            errores.append(f"la arista {a} – {b} apunta a un nodo inexistente")
        if a == b:
            errores.append(f"la arista {a} – {b} es un lazo")
        par = frozenset((a, b))
        if par in vistas:
            errores.append(f"la arista {a} – {b} está repetida")
        vistas.add(par)
    for y, m in red["metrics_by_year"].items():
        sin = validos - set(m["nodes"])
        if sin:
            errores.append(f"{y}: faltan métricas de {len(sin)} nodos")
    for p in red["similarity"]:
        if p["source"] not in validos or p["target"] not in validos:
            errores.append(f"el par potencial {p['source']} – {p['target']} apunta a un nodo inexistente")
    if errores:
        raise DatosInvalidos("Datos inconsistentes: " + "; ".join(errores[:10]))
    return red


RED = cargar_red()
ANIOS = sorted(map(int, RED["metrics_by_year"]))


def _cuerpo(obj):
    """JSON compacto + su ETag (los datos no cambian mientras corre la app: se serializan una sola vez)."""
    datos = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return datos, hashlib.sha1(datos).hexdigest()[:16]


RED_JSON = _cuerpo({f: RED[f] for f in ARCHIVOS_RED})


def responder_json(cuerpo):
    datos, etag = cuerpo
    resp = app.response_class(datos, mimetype="application/json")
    resp.set_etag(etag)
    resp.headers["Cache-Control"] = "no-cache"   # se revalida con el ETag: 304 si no cambió
    return resp.make_conditional(request)


def anio_pedido():
    y = request.args.get("year", type=int, default=ANIOS[-1])
    if y not in ANIOS:
        abort(400, description=f"year debe estar entre {ANIOS[0]} y {ANIOS[-1]}")
    return y


if os.environ.get("UTECVIS_SIN_T5") != "1":
    tema.iniciar()


@app.context_processor
def asset_version():
    """asset('js/main.js') → /static/js/main.js?v=<mtime>: tras editar un archivo, el navegador no mezcla
    la versión nueva con otras viejas guardadas en su caché."""
    def asset(filename):
        v = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        return url_for("static", filename=filename, v=v)
    return {"asset": asset}


@app.route("/")
def index():
    return render_template("index.html", habilidades=list(tema.HABILIDADES), api_url="api/tema", datos_url="api/red")


@app.route("/api/red")
def api_red():
    return responder_json(RED_JSON)


@app.route("/api/nodes")
def api_nodes():
    y = anio_pedido()
    m = RED["metrics_by_year"][str(y)]["nodes"]
    return jsonify({"year": y, "nodes": [{**n, "metricas": m[n["id"]]} for n in RED["nodes"]]})


@app.route("/api/edges")
def api_edges():
    """Aristas vigentes en el año: primera coautoría hasta ese año y peso = publicaciones compartidas hasta él
    (el mismo cálculo que main.js hace en el navegador para la animación)."""
    y = anio_pedido()
    out = []
    for e in RED["edges"]:
        if e["first_year"] > y:
            continue
        w = sum(c for a, c in e["w_by_year"].items() if int(a) <= y) + (e["w_sin_anio"] if y >= ANIOS[-1] else 0)
        if w > 0:
            out.append({**e, "w": w})
    return jsonify({"year": y, "edges": out})


@app.route("/api/salud")
def api_salud():
    return jsonify({"ok": True, "nodos": len(RED["nodes"]), "aristas": len(RED["edges"]),
                    "anios": [ANIOS[0], ANIOS[-1]], "t5": tema.estado()})


@app.route("/api/tema")
def api_tema():
    q = request.args.get("q", "").strip()[:300]
    if not q:
        return jsonify(tema.estado())
    res = tema.buscar(q)
    if res is None:
        return jsonify(tema.estado()), 503
    return jsonify(res)


@app.errorhandler(HTTPException)
def error_http(e):
    """En /api/* los errores también son JSON (el front puede mostrarlos); en el resto, la página de error normal."""
    if request.path.startswith("/api/"):
        return jsonify({"error": e.description, "status": e.code}), e.code
    return e


@app.after_request
def cabeceras(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return comprimir(resp)


def comprimir(resp):
    """gzip para texto (JSON, JS, CSS, HTML) si el navegador lo acepta: los datos de la red pesan ~5 veces menos."""
    if (resp.status_code != 200 or resp.mimetype not in COMPRIMIBLES or "Content-Encoding" in resp.headers
            or "gzip" not in request.headers.get("Accept-Encoding", "").lower()):
        return resp
    resp.direct_passthrough = False          # los archivos de static/ llegan como flujo: se leen para comprimirlos
    datos = resp.get_data()
    if len(datos) < 1024:
        return resp
    resp.set_data(gzip.compress(datos, compresslevel=6))
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Vary"] = "Accept-Encoding"
    etag, _ = resp.get_etag()
    if etag:
        resp.set_etag(etag, weak=True)        # el cuerpo comprimido ya no es byte a byte el original
    return resp


if __name__ == "__main__":
    app.run(debug=False)
