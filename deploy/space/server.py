"""UtecVis · API de T5 para Hugging Face Spaces.

Solo expone /api/tema (mismo contrato que app.py) para la página publicada en GitHub Pages. No hay llaves ni
secretos: corre nuestro propio código con el modelo descargado en la imagen. Protecciones contra abuso:
  - CORS solo para los orígenes de ALLOWED_ORIGINS (la página de github.io y pruebas locales);
  - límite de pedidos por IP (LIMITE por VENTANA segundos);
  - largo máximo del tema (300 caracteres, como en app.py).
"""
import os
import threading
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request

import tema

ORIGENES = {o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "https://andrea-coa.github.io,http://127.0.0.1:8000,http://localhost:8000").split(",") if o.strip()}
LIMITE, VENTANA = 30, 60

app = Flask(__name__)
tema.iniciar()
_pedidos, _lk = defaultdict(deque), threading.Lock()


def permitido(ip):
    ahora = time.time()
    with _lk:
        h = _pedidos[ip]
        while h and ahora - h[0] > VENTANA:
            h.popleft()
        if len(h) >= LIMITE:
            return False
        h.append(ahora)
        return True


@app.after_request
def cors(resp):
    origen = request.headers.get("Origin")
    if origen in ORIGENES:
        resp.headers["Access-Control-Allow-Origin"] = origen
        resp.headers["Vary"] = "Origin"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


@app.get("/")
def inicio():
    return jsonify({"servicio": "UtecVis · T5 (tema → equipo)", **tema.estado()})


@app.get("/api/tema")
def api_tema():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if not permitido(ip):
        return jsonify({"error": "Demasiadas búsquedas seguidas; espera un minuto."}), 429
    q = request.args.get("q", "").strip()[:300]
    if not q:
        return jsonify(tema.estado())
    res = tema.buscar(q)
    if res is None:
        return jsonify(tema.estado()), 503
    return jsonify(res)
