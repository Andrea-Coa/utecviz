#!/usr/bin/env bash
# Ejecuta el pipeline offline completo (01 → 05) y el test de métricas.
# Uso:  ./run_pipeline.sh        (usa .venv si existe; si no, el python del PATH)
set -euo pipefail
cd "$(dirname "$0")"
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python
else PY=python; fi
export PYTHONIOENCODING=utf-8
for s in 01_limpieza 02_coautoria 03_embeddings 04_metricas 05_exportar; do
  echo "== $s"
  "$PY" "pipeline/$s.py"
done
echo "== tests"
"$PY" -m pytest pipeline/tests -q
