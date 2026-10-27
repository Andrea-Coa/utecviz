"""Arma en dist/space/ la carpeta lista para subir al Space de Hugging Face (T5 en línea).

Copia el servidor (deploy/space/), tema.py y los datos que T5 necesita (data/processed/). Nada de esto es secreto:
son los mismos archivos del repositorio.

Uso:  python deploy/preparar_space.py
"""
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DEST = RAIZ / "dist" / "space"
DATOS = ["personas.json", "pubs.json", "emb_pubs.npy", "emb_pubs_claves.json", "emb_perfiles.npy", "emb_perfiles_claves.json"]

if DEST.exists():
    shutil.rmtree(DEST)
shutil.copytree(RAIZ / "deploy" / "space", DEST)
shutil.copy2(RAIZ / "tema.py", DEST / "tema.py")
(DEST / "data" / "processed").mkdir(parents=True)
for f in DATOS:
    shutil.copy2(RAIZ / "data" / "processed" / f, DEST / "data" / "processed" / f)
total = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
print(f"{DEST.relative_to(RAIZ)}: {sum(1 for p in DEST.rglob('*') if p.is_file())} archivos, {total / 1e6:.1f} MB")
for p in sorted(DEST.rglob("*")):
    if p.is_file():
        print("  ", p.relative_to(DEST))
