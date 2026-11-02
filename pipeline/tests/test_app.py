"""La app Flask: arranca, carga nodos y aristas coherentes y responde sin errores (sin cargar el modelo de T5)."""
import gzip
import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
os.environ["UTECVIS_SIN_T5"] = "1"


@pytest.fixture(scope="module")
def cliente():
    import app
    return app.app.test_client()


def test_pagina(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'datos: "api/red"' in html and "d3.v7" in html


def test_red_completa_y_coherente(cliente):
    d = cliente.get("/api/red").get_json()
    ids = {n["id"] for n in d["nodes"]}
    assert len(ids) == len(d["nodes"]) == d["resumen"]["n_docentes"]
    assert len(d["edges"]) == d["resumen"]["n_aristas"]
    assert all(e["source"] in ids and e["target"] in ids for e in d["edges"])
    assert set(d) == {"nodes", "edges", "similarity", "metrics_by_year", "departamentos", "resumen"}


def test_red_comprimida_y_304(cliente):
    r = cliente.get("/api/red", headers={"Accept-Encoding": "gzip"})
    assert r.headers["Content-Encoding"] == "gzip"
    assert json.loads(gzip.decompress(r.data))["nodes"]
    r2 = cliente.get("/api/red", headers={"Accept-Encoding": "gzip", "If-None-Match": r.headers["ETag"]})
    assert r2.status_code == 304


def test_aristas_por_anio(cliente):
    todas = cliente.get("/api/edges").get_json()["edges"]
    d = cliente.get("/api/edges?year=2018").get_json()
    assert 0 < len(d["edges"]) < len(todas)
    assert all(e["first_year"] <= 2018 and e["w"] > 0 for e in d["edges"])


def test_nodos_con_metricas_y_error_json(cliente):
    d = cliente.get("/api/nodes?year=2026").get_json()
    assert all("metricas" in n for n in d["nodes"])
    r = cliente.get("/api/nodes?year=1990")
    assert r.status_code == 400 and "error" in r.get_json()
    assert cliente.get("/api/salud").get_json()["ok"]
