"""UtecVis by Batimix: aplicación Flask.

Solo sirve la página y los archivos ya calculados por el pipeline (static/data/*.json); no hay cómputo
por request. Uso:  pip install -r requirements.txt && flask run
"""
from flask import Flask, render_template

app = Flask(__name__)
# Los estáticos (JSON, fotos, JS, CSS) se sirven con ETag y respuesta condicional (304) por defecto;
# además se permite cachearlos una hora en el navegador.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600


@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def cabeceras(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


if __name__ == "__main__":
    app.run(debug=False)
