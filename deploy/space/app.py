"""UtecVis · API de T5 para un Space de Hugging Face (SDK Gradio, hardware gratis ZeroGPU; el modelo corre en CPU).

Una app de Gradio es un servidor FastAPI: aquí se le agrega la ruta /api/tema (mismo contrato que app.py) para la
página publicada en GitHub Pages, y Gradio queda como pantalla de prueba en "/". No hay llaves ni secretos: corre
nuestro propio código; el modelo se descarga de Hugging Face al arrancar. Protecciones contra abuso:
  - CORS solo para los orígenes de ALLOWED_ORIGINS (la página de github.io y pruebas locales);
  - límite de pedidos por IP (LIMITE por VENTANA segundos);
  - largo máximo del tema (300 caracteres, como en app.py).
"""
try:  # ZeroGPU exige `spaces` importado antes que torch y al menos una función @spaces.GPU
    import spaces
except ImportError:
    spaces = None

import os
import threading
import time
from collections import defaultdict, deque

import gradio as gr
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

import tema

ORIGENES = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "https://andrea-coa.github.io,http://127.0.0.1:8000,http://localhost:8000").split(",") if o.strip()]
LIMITE, VENTANA = 30, 60

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


def responder(request, cuerpo, status=200):
    """JSON con CORS solo para ORIGENES (un GET sin cabeceras propias no necesita preflight)."""
    r = JSONResponse(cuerpo, status_code=status)
    origen = request.headers.get("origin", "")
    if origen in ORIGENES:
        r.headers["Access-Control-Allow-Origin"] = origen
        r.headers["Vary"] = "Origin"
    return r


def api_tema(request: Request, q: str = ""):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()
    if not permitido(ip):
        return responder(request, {"error": "Demasiadas búsquedas seguidas; espera un minuto."}, 429)
    q = q.strip()[:300]
    if not q:
        return responder(request, tema.estado())
    res = tema.buscar(q)
    if res is None:
        return responder(request, tema.estado(), 503)
    return responder(request, res)


if spaces:
    @spaces.GPU
    def _gpu():
        """No se usa: el modelo corre en CPU, pero ZeroGPU no arranca sin al menos una función @spaces.GPU."""


def probar(q):
    """Pantalla de prueba: nombres y facetas de los candidatos."""
    res = tema.buscar(q.strip()[:300]) if q.strip() else None
    if res is None:
        return "El modelo se está cargando (1–2 minutos después de despertar). Intenta de nuevo." if q.strip() else ""
    filas = [f"{c['id']}  ·  {round(c['rel'] * 100)} %  ·  " + ", ".join(f["nombre"] for f in c["facetas"]) for c in res["candidatos"]]
    return f"Facetas: {', '.join(res['facetas']) or '—'}\n\n" + "\n".join(filas)


demo = gr.Interface(fn=probar, inputs=gr.Textbox(label="Tema", placeholder="visualization of brain signals"),
                    outputs=gr.Textbox(label="Equipo sugerido", lines=12), title="UtecVis · T5 (tema → equipo)",
                    description="API para https://andrea-coa.github.io/utecviz/ · ruta /api/tema?q=…",
                    flagging_mode="never")

if __name__ == "__main__":
    # ZeroGPU espera demo.launch(); la ruta va en el constructor del servidor para que quede antes que las de Gradio.
    # Sin SSR: con SSR (activo por defecto en Spaces) un servidor Node atiende las rutas y /api/tema no llega aquí.
    demo.launch(ssr_mode=False, app_kwargs={"routes": [APIRoute("/api/tema", api_tema, methods=["GET"])]})
