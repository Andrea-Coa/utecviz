"""Verificación de "Technical Accuracy": recalcula las métricas de 2026 con networkx a partir de los
archivos exportados (static/data) y las compara con metrics_by_year.json.

Uso:  python -m pytest pipeline/tests -q      (o simplemente: python pipeline/tests/test_metricas.py)
"""
import json
from pathlib import Path

import networkx as nx
import pytest

DATA = Path(__file__).resolve().parents[2] / "static" / "data"
ANIO = "2026"


def cargar(nombre):
    return json.loads((DATA / nombre).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def datos():
    nodes, edges, met = cargar("nodes.json"), cargar("edges.json"), cargar("metrics_by_year.json")
    G = nx.Graph()
    G.add_nodes_from(n["id"] for n in nodes)
    for e in edges:
        G.add_edge(e["source"], e["target"], w=e["w"])
    return nodes, edges, met[ANIO], G


def test_nodos_y_aristas_coherentes(datos):
    nodes, edges, m, G = datos
    ids = {n["id"] for n in nodes}
    assert len(nodes) == 104 and len(ids) == 104
    assert all(e["source"] in ids and e["target"] in ids for e in edges)
    assert set(m["nodes"]) == ids
    for e in edges:   # el peso total coincide con la suma por año (+ sin año)
        assert e["w"] == sum(e["w_by_year"].values()) + e["w_sin_anio"]
    assert m["global"]["n_aristas"] == G.number_of_edges()


def test_grado_y_grado_ponderado(datos):
    _, _, m, G = datos
    for n, v in m["nodes"].items():
        assert v["degree"] == G.degree(n), n
        assert v["wdeg"] == G.degree(n, weight="w"), n


def test_betweenness(datos):
    _, _, m, G = datos
    bc = nx.betweenness_centrality(G, normalized=True)
    for n, v in m["nodes"].items():
        assert v["bc"] == pytest.approx(bc[n], abs=1e-6), n


def test_modularidad_y_comunidades(datos):
    nodes, _, m, G = datos
    part = {}
    for n, v in m["nodes"].items():
        part.setdefault(v["part"], set()).add(n)
    assert m["global"]["Q"] == pytest.approx(nx.community.modularity(G, list(part.values()), weight="w"), abs=1e-4)
    # Louvain con la misma semilla reproduce la partición exportada
    recal = nx.community.louvain_communities(G, weight="w", seed=42)
    assert sorted(map(sorted, recal)) == sorted(map(sorted, part.values()))
    # las comunidades etiquetadas (>= 3 miembros) coinciden con la tabla de comunidades
    tam = {}
    for v in m["nodes"].values():
        if v["comm"] >= 0:
            tam[v["comm"]] = tam.get(v["comm"], 0) + 1
    assert tam == {c["id"]: c["size"] for c in m["communities"]}
    assert all(c["size"] >= 3 for c in m["communities"])


def test_cross(datos):
    nodes, edges, m, G = datos
    dep = {n["id"]: n["departamento"] for n in nodes}
    assert all(e["cross"] == (dep[e["source"]] != dep[e["target"]]) for e in edges)
    pct = sum(e["cross"] for e in edges) / len(edges)
    assert m["global"]["pct_cross"] == pytest.approx(pct, abs=1e-4)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
