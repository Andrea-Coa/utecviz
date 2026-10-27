---
title: UtecVis T5
emoji: ⭐
colorFrom: red
colorTo: gray
sdk: gradio
sdk_version: 5.49.1
python_version: "3.10"
app_file: app.py
pinned: false
---

# UtecVis · T5 (tema → equipo)

API de la tarea T5 de [UtecVis](https://andrea-coa.github.io/utecviz/): dado un tema, devuelve los docentes de
UTEC cuya producción más se le parece, con sus facetas (habilidades del catálogo).

- `GET /api/tema?q=visualization of brain signals`: resultado en JSON (lo usa la página).
- `GET /api/tema`: estado del modelo (`listo` cuando terminó de cargar, 1–2 minutos después de despertar).
- `/`: pantalla de prueba.

Modelo: `intfloat/multilingual-e5-base`. Código y método: repositorio `utecviz` (`tema.py`).
