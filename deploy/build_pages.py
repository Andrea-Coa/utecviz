"""Genera docs/: la versión estática de la página para GitHub Pages.

GitHub Pages solo sirve archivos, así que la plantilla de Flask se convierte en un index.html con rutas relativas
(funciona en https://<usuario>.github.io/utecviz/) y se copia static/. T5 consulta la API del Space de Hugging
Face (--api); si no responde, usa static/data/tema_precalc.json (generarlo antes con deploy/precalcular_t5.py).

Uso:  python deploy/build_pages.py --api https://<usuario>-<space>.hf.space/api/tema
"""
import argparse
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import tema  # noqa: E402  (solo se usa el catálogo; el modelo no se carga)

DOCS = RAIZ / "docs"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", required=True, help="URL de /api/tema en el Space, p. ej. https://usuario-utecviz-t5.hf.space/api/tema")
    args = ap.parse_args()
    if not (RAIZ / "static" / "data" / "tema_precalc.json").exists():
        sys.exit("Falta static/data/tema_precalc.json: corre antes  python deploy/precalcular_t5.py")

    def url_for(_endpoint, filename=""):
        return "static/" + filename

    def asset(filename):   # mismo versionado que app.py (?v=fecha de modificación) para no mezclar cachés
        return f"static/{filename}?v={int((RAIZ / 'static' / filename).stat().st_mtime)}"

    env = Environment(loader=FileSystemLoader(RAIZ / "templates"), autoescape=True)
    html = env.get_template("index.html").render(url_for=url_for, asset=asset, api_url=args.api,
                                                 habilidades=list(tema.HABILIDADES))
    if DOCS.exists():
        shutil.rmtree(DOCS)
    shutil.copytree(RAIZ / "static", DOCS / "static")
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")   # que Pages sirva los archivos tal cual
    total = sum(p.stat().st_size for p in DOCS.rglob("*") if p.is_file())
    print(f"docs/: index.html + static/ ({total / 1e6:.1f} MB) · T5 → {args.api}")


if __name__ == "__main__":
    main()
