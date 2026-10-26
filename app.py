"""UtecVis by Batimix: aplicación Flask.

Sirve la página y los archivos ya calculados por el pipeline (static/data/*.json). El único cómputo
por request es T5 (/api/tema): convertir en vector el tema que escribe el usuario (ver tema.py).
Uso:  pip install -r requirements.txt && flask run
"""
import os

from flask import Flask, jsonify, render_template, request, url_for

import tema

app = Flask(__name__)
# Los estáticos (JSON, fotos, JS, CSS) se sirven con ETag y respuesta condicional (304) por defecto;
# además se permite cachearlos una hora en el navegador.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
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
    return render_template("index.html", habilidades=list(tema.HABILIDADES))


@app.route("/api/tema")
def api_tema():
    q = request.args.get("q", "").strip()[:300]
    if not q:
        return jsonify(tema.estado())
    res = tema.buscar(q)
    if res is None:
        return jsonify(tema.estado()), 503
    return jsonify(res)


@app.after_request
def cabeceras(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


if __name__ == "__main__":
    app.run(debug=False)
