---
title: UtecVis T5
emoji: ⭐
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# UtecVis · T5 (tema → equipo)

API de la tarea T5 de [UtecVis](https://andrea-coa.github.io/utecviz/): dado un tema, devuelve los docentes de
UTEC cuya producción más se le parece, con sus facetas (habilidades del catálogo).

- `GET /api/tema?q=visualization of brain signals`: el resultado.
- `GET /`: estado del modelo (`listo` cuando terminó de cargar, 1–2 minutos después de despertar).

Modelo: `intfloat/multilingual-e5-base`. Código y método: repositorio `utecviz` (`tema.py`).
