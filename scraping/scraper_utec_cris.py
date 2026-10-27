#!/usr/bin/env python3
"""
Scraper de perfiles y publicaciones del portal CRIS de UTEC (https://cris.utec.edu.pe).

Reproduce los mismos datos que se extrajeron en la sesión original:

  Perfiles  ->  perfiles.csv, publicaciones.csv, huella_digital.csv,
                datos_completos.json, fotos/
  Detalle   ->  publicaciones_detalle.csv, publicacion_investigador.csv,
                publicaciones_detalle.json

Uso:
    pip install requests beautifulsoup4 playwright
    playwright install chromium                  # solo si no tienes Google Chrome instalado
    python scraper_utec_cris.py --limit 3        # prueba rápida con 3 personas
    python scraper_utec_cris.py                  # todo (perfiles + fotos + detalle)
    python scraper_utec_cris.py --sin-detalle    # solo perfiles

Notas:
  * El portal está detrás de Cloudflare y responde 403 a clientes HTTP como `requests`.
    Por eso, por defecto el script abre un navegador real (Playwright) y descarga cada página
    desde ahí. Si aparece una verificación de Cloudflare, resuélvela en la ventana.
  * robots.txt del portal pide Crawl-Delay: 5. Por defecto se respeta (1 página cada 5 s);
    la corrida completa (~3.400 descargas) tarda unas 4–5 horas. Con --sin-detalle
    (solo perfiles y fotos) son unos 30 minutos. Puedes bajar --delay bajo tu criterio.
  * Los CSV salen en UTF-8 con BOM (se abren bien en Excel). Las celdas se recortan a
    32.000 caracteres (límite de Excel); los JSON guardan el texto completo.
"""
import argparse
import base64
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, unquote, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://cris.utec.edu.pe"
LISTADO = BASE + "/es/persons/?page={}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
}
MAX_CELDA = 32000
_local = threading.local()
ARGS = None
NAV = None  # navegador Playwright (modo por defecto)


class Navegador:
    """Abre un navegador real (Playwright) y pide cada página con fetch() desde dentro del sitio.

    El portal está detrás de Cloudflare, que rechaza (403) a clientes que no son navegadores,
    como `requests`. Con un navegador real las peticiones se comportan igual que al navegar
    a mano. Si aparece una verificación de Cloudflare, resuélvela tú en la ventana.
    """

    def __init__(self, headless=False):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        try:
            self.browser = self.pw.chromium.launch(channel="chrome", headless=headless)
        except Exception:  # noqa: BLE001  (Chrome no instalado -> Chromium de Playwright)
            self.browser = self.pw.chromium.launch(headless=headless)
        self.page = self.browser.new_page(locale="es-PE")
        self.page.goto(BASE + "/es/persons/", wait_until="domcontentloaded", timeout=120000)
        log("  Esperando a que cargue el portal (si aparece una verificación, resuélvela en la ventana)…")
        self.page.wait_for_selector(".result-container", timeout=300000)

    def get(self, url, binario=False):
        js = """async ([u, bin]) => {
            const r = await fetch(u, {credentials: 'include'});
            if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + u);
            if (!bin) return await r.text();
            const b = new Uint8Array(await r.arrayBuffer());
            let s = ''; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
            return btoa(s);
        }"""
        for intento in range(4):
            try:
                res = self.page.evaluate(js, [url, binario])
                return base64.b64decode(res) if binario else res
            except Exception as e:  # noqa: BLE001
                if intento == 3:
                    raise
                log(f"  reintento {intento + 1} ({e})")
                time.sleep(5 * (intento + 1))

    def cerrar(self):
        self.browser.close()
        self.pw.stop()


# --------------------------------------------------------------------------- utilidades
def sesion():
    """Una sesión HTTP por hilo, con reintentos."""
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        r = Retry(total=5, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
        s.mount("https://", HTTPAdapter(max_retries=r))
        _local.s = s
    return s


def get(url, binario=False):
    if ARGS and ARGS.delay:
        time.sleep(ARGS.delay)
    if NAV is not None:
        return NAV.get(url, binario)
    r = sesion().get(url, timeout=60)
    r.raise_for_status()
    return r.content if binario else r.text


def sopa(url):
    soup = BeautifulSoup(get(url), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return soup


def T(el):
    """Texto de un elemento con espacios colapsados (equivale a textContent + trim)."""
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text()).strip()


def absoluta(href):
    return urljoin(BASE, href) if href else ""


def href(el):
    return el.get("href", "") if el is not None else ""


def unir(v):
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)
    return v or ""


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def en_paralelo(func, items, workers, etiqueta):
    resultados, errores = [None] * len(items), []
    if workers <= 1:  # secuencial en el hilo principal (obligatorio con Playwright)
        for k, it in enumerate(items, 1):
            try:
                resultados[k - 1] = func(it)
            except Exception as e:  # noqa: BLE001
                errores.append(f"{it}: {e}")
            if k % 10 == 0 or k == len(items):
                log(f"  {etiqueta}: {k}/{len(items)}")
        for e in errores:
            log("  ERROR " + e)
        return resultados, errores
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(func, it): i for i, it in enumerate(items)}
        for k, f in enumerate(as_completed(futs), 1):
            i = futs[f]
            try:
                resultados[i] = f.result()
            except Exception as e:  # noqa: BLE001
                errores.append(f"{items[i]}: {e}")
            if k % 25 == 0 or k == len(items):
                log(f"  {etiqueta}: {k}/{len(items)}")
    for e in errores:
        log("  ERROR " + e)
    return resultados, errores


# --------------------------------------------------------------------------- listado
def listar_personas():
    urls = []
    for p in range(20):
        s = sopa(LISTADO.format(p))
        antes = len(urls)
        for a in s.select(".result-container h3.title a"):
            u = absoluta(a.get("href"))
            if u not in urls:
                urls.append(u)
        if len(urls) == antes:
            break
    return urls


# --------------------------------------------------------------------------- perfil
def parse_perfil(url):
    base = url.rstrip("/")
    d = sopa(url)
    r = {"url": url, "slug": base.split("/")[-1]}
    w = d.select_one(".person-vcard-wrapper") or d

    r["nombre"] = T(w.select_one("h1"))
    org = w.select_one(".rendering_personorganisationlistrendererportal")
    r["cargos"] = [T(li) for li in org.select("li")] if org else []
    if not r["cargos"] and T(org):
        r["cargos"] = [T(org)]

    em = w.select_one("a.email")
    r["email"] = ""
    if em is not None and em.get("data-md5"):
        try:
            r["email"] = base64.b64decode(em["data-md5"]).decode("utf-8").replace("mailto:", "")
        except Exception:  # noqa: BLE001
            pass

    r["orcid"] = href(w.select_one('a[href*="orcid.org"]'))
    r["direccion"] = T(w.select_one(".rendering_personorganisationcontactrendererportal .address, .address"))
    r["telefono"] = T(w.select_one(".phone"))
    r["google_scholar"] = href(w.select_one('.google a, a.google, a[href*="scholar.google"]'))
    r["linkedin"] = href(w.select_one('.linkedin a, a.linkedin, a[href*="linkedin.com/in"]'))
    r["scopus"] = href(w.select_one('a.scopus-link, .scopus-link a, a[href*="scopus.com/authid"]'))
    r["otros_links"] = [h for h in (href(a) for a in w.select(".social-media-list a"))
                        if h and not re.search(r"scholar|linkedin", h)]

    im = w.select_one("img.image") or w.select_one("img")
    r["foto"] = absoluta(im.get("src")) if im is not None else ""

    txt = w.get_text(" ")
    c = re.search(r"(\d[\d.,]*)\s*Citas", txt)
    h = re.search(r"(\d+)\s*Índice h", txt)
    r["citas"] = c.group(1) if c else ""
    r["indice_h"] = h.group(1) if h else ""

    # Secciones de "Perfil personal" (Perfil profesional, Educación, Temas, Renacyt, ...)
    r["perfil"] = {}
    for sh in d.select("h3.subheader"):
        k = T(sh)
        caja = sh.parent
        if re.search(r"Educación|Formación", k, re.I):
            r["perfil"][k] = [T(e) for e in caja.select(".rendering_personeducation")]
        else:
            caja = BeautifulSoup(str(caja), "html.parser")
            h3 = caja.find("h3")
            if h3:
                h3.decompose()
            kws = [t for t in (T(li) for li in caja.select("li")) if t]
            r["perfil"][k] = kws if kws else T(caja)

    # Huella digital completa
    r["huella_digital"] = []
    try:
        f = sopa(base + "/fingerprints/")
        for ol in f.select("ol.concept_listing"):
            area = re.sub(r".*por", "", ol.get("aria-label", "")).strip()
            for b in ol.select("button"):
                r["huella_digital"].append({"concepto": T(b.select_one(".concept")), "area": area,
                                            "peso": T(b.select_one(".value"))})
    except Exception as e:  # noqa: BLE001
        log(f"  huella {url}: {e}")

    # Lista de publicaciones (todas las páginas)
    r["publicaciones"] = []
    for p in range(40):
        q = sopa(f"{base}/publications/?page={p}")
        items = q.select(".result-container .rendering_researchoutput_portal-short")
        if not items:
            break
        for it in items:
            a = it.select_one("h3.title a, .title a")
            r["publicaciones"].append({
                "titulo": T(it.select_one(".title")),
                "url": absoluta(href(a)),
                "autores": "; ".join(T(x) for x in it.select("a.link.person")),
                "anio": T(it.select_one(".date")),
                "tipo": T(it.select_one(".type_classification")) or T(it.select_one(".type")),
                "referencia": re.sub(r"Producción científica:.*", "", T(it)).strip(),
            })
        if len(items) < 50:
            break
    return r


def descargar_foto(r, carpeta):
    r["archivo_foto"] = ""
    if not r.get("foto"):
        return
    ext = os.path.splitext(urlsplit(r["foto"]).path)[1] or ".jpg"
    nombre = f"fotos/{unquote(r['slug'])}{ext}"
    try:
        data = get(r["foto"], binario=True)
        with open(os.path.join(carpeta, nombre), "wb") as fh:
            fh.write(data)
        r["archivo_foto"] = nombre
    except Exception as e:  # noqa: BLE001
        log(f"  foto {r['slug']}: {e}")


# --------------------------------------------------------------------------- detalle de publicación
def parse_publicacion(url):
    d = sopa(url)
    r = {"url": url}
    r["titulo"] = T(d.select_one("h1"))
    r["subtitulo"] = T(d.select_one("h1 + .subtitle, .subtitle"))
    r["tipo"] = T(d.select_one(".type_classification")) or T(d.select_one(".type"))
    r["tipo_familia"] = T(d.select_one(".type_family"))
    r["tipo_padre"] = T(d.select_one(".type_classification_parent"))
    r["revision"] = T(d.select_one(".type_classification_parent ~ .type_classification ~ *"))

    pers = d.select_one(".persons, p.relations.persons")
    r["autores"] = T(pers)
    r["autores_utec"] = [f"{T(a)} <{absoluta(href(a)).split('?')[0]}>"
                         for a in (pers.select("a.link.person") if pers else [])]
    r["organizaciones"] = [T(a) for a in d.select("p.relations.organisations a, .organisations a")]

    r["resumen"] = ""
    for h2 in d.select("h2"):
        if "Resumen" in T(h2):
            tb = h2.parent.select_one(".textblock")
            r["resumen"] = T(tb) if tb else re.sub(r"^Resumen\s*", "", T(h2.parent))
            break

    r["propiedades"] = {}
    for tr in d.select("table.properties tr"):
        k = T(tr.select_one("th"))
        if k:
            r["propiedades"][k] = T(tr.select_one("td"))

    r["doi"] = r["propiedades"].get("DOI") or href(d.select_one('a[href*="doi.org"]'))
    r["scopus"] = href(d.select_one('a[href*="scopus.com/pages/publications"], '
                                    'a[href*="scopus.com/record"], a[href*="scopus.com/inward"]')).split("?")[0]
    enl = []
    for a in d.select('.links a, .rendering_researchoutput_documentrelatedlinksportal a, a.link[href^="http"]'):
        h = href(a)
        if h and not re.search(r"scopus\.com/?$|linkedin|twitter|facebook|cris\.utec", h) and h not in enl:
            enl.append(h)
    r["enlaces"] = enl
    r["archivos"] = [absoluta(href(a)).split("?")[0] for a in d.select('a[href*="/files/"]')]

    r["huella"] = []
    for b in d.select(".concept-badge-large-container button, .concept-badge-small-container button"):
        th = T(b.select_one(".thesauri"))
        r["huella"].append(T(b.select_one(".concept")) + (f" [{th}]" if th else "") + " " + T(b.select_one(".value")))

    r["citar_apa"] = T(d.select_one("#cite-apa"))
    r["citar_bibtex"] = T(d.select_one("#cite-BIBTEX"))
    r["citar_ris"] = T(d.select_one("#cite-RIS"))
    return r


# --------------------------------------------------------------------------- exportación
def escribir_csv(ruta, filas, columnas):
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(columnas)
        for f in filas:
            fila = []
            for c in columnas:
                v = "" if f.get(c) is None else str(f.get(c))
                if len(v) > MAX_CELDA:
                    v = v[:MAX_CELDA] + "…"
                fila.append(v)
            w.writerow(fila)


def exportar_perfiles(D, out):
    prof = []
    for r in D:
        p = r.get("perfil", {})
        temas = [p.get(k) for k in ("Temas de Interés de Investigación", "Intereses de la investigación", "Palabras clave")]
        prof.append({
            "nombre": r["nombre"], "cargos": unir(r["cargos"]), "email": r["email"], "orcid": r["orcid"],
            "telefono": r["telefono"], "direccion": r["direccion"], "google_scholar": r["google_scholar"],
            "linkedin": r["linkedin"], "scopus": r["scopus"], "otros_links": unir(r["otros_links"]),
            "citas": r["citas"], "indice_h": r["indice_h"],
            "perfil_profesional": unir(p.get("Perfil profesional")), "educacion": unir(p.get("Educación")),
            "temas_interes": " | ".join(unir(t) for t in temas if t),
            "calificacion_renacyt": unir(p.get("Calificación Renacyt")),
            "posiciones_externas": unir(p.get("Posiciones externas")),
            "n_publicaciones": len(r["publicaciones"]),
            "huella_digital_top10": " | ".join(f"{h['concepto']} ({h['peso']})" for h in r["huella_digital"][:10]),
            "archivo_foto": r.get("archivo_foto", ""), "foto_url": r["foto"], "url_perfil": r["url"],
        })
    escribir_csv(os.path.join(out, "perfiles.csv"), prof, list(prof[0].keys()))

    pubs = [{"investigador": r["nombre"], "email_investigador": r["email"], **p}
            for r in D for p in r["publicaciones"]]
    escribir_csv(os.path.join(out, "publicaciones.csv"), pubs,
                 ["investigador", "email_investigador", "titulo", "anio", "tipo", "autores", "referencia", "url"])

    hu = [{"investigador": r["nombre"], **h} for r in D for h in r["huella_digital"]]
    escribir_csv(os.path.join(out, "huella_digital.csv"), hu, ["investigador", "concepto", "area", "peso"])

    with open(os.path.join(out, "datos_completos.json"), "w", encoding="utf-8") as fh:
        json.dump(D, fh, ensure_ascii=False, indent=1)


PROPS = ["Publicación", "Título de la publicación alojada", "Subtítulo de la publicación alojada", "Editorial",
         "Editores", "Volumen", "N.º", "Número", "Número de artículo", "Páginas (desde-hasta)", "Páginas",
         "Número de páginas", "Edición", "ISSN (versión impresa)", "ISSN (versión digital)",
         "ISBN (versión impresa)", "ISBN (versión digital)", "Estado", "Idioma original",
         "Título traducido de la contribución", "Publicado de forma externa", "Evento", "Conferencia", "Nombre",
         "País/Territorio", "Ciudad", "Período"]


def anio_de(r):
    m = re.search(r"(19|20)\d\d", (r.get("propiedades") or {}).get("Estado", ""))
    return m.group(0) if m else ""


def limpiar_tipo(s):
    return re.sub(r"[›:]", "", (s or "").replace("Producción científica", "")).strip()


def exportar_detalle(L, out):
    filas = []
    for r in L:
        p = r.get("propiedades") or {}
        o = {
            "titulo": r["titulo"], "subtitulo": r["subtitulo"], "tipo": r["tipo"],
            "categoria": limpiar_tipo(r["tipo_padre"]), "revision": limpiar_tipo(r["revision"]),
            "anio": anio_de(r), "investigadores_utec": " | ".join(r["investigadores_utec_perfil"]),
            "autores": r["autores"],
            "n_autores": len([x for x in re.split(r",| & ", r["autores"] or "") if x.strip()]),
            "organizaciones_utec": " | ".join(r["organizaciones"]), "resumen": r["resumen"],
        }
        for k in PROPS:
            o[k] = p.get(k, "")
        o["doi"] = r["doi"]
        o["scopus"] = r["scopus"]
        o["otros_enlaces"] = " | ".join(x for x in r["enlaces"] if x not in (r["doi"], r["scopus"]))
        o["huella"] = " | ".join(r["huella"])
        o["cita_apa"] = r.get("citar_apa", "")
        o["cita_bibtex"] = r["citar_bibtex"]
        o["url"] = r["url"]
        filas.append(o)
    escribir_csv(os.path.join(out, "publicaciones_detalle.csv"), filas, list(filas[0].keys()))

    rel = [{"investigador": n, "titulo": r["titulo"], "tipo": r["tipo"], "anio": anio_de(r),
            "doi": r["doi"], "url": r["url"]}
           for r in L for n in r["investigadores_utec_perfil"]]
    escribir_csv(os.path.join(out, "publicacion_investigador.csv"), rel,
                 ["investigador", "titulo", "tipo", "anio", "doi", "url"])

    with open(os.path.join(out, "publicaciones_detalle.json"), "w", encoding="utf-8") as fh:
        json.dump(L, fh, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- main
def main():
    global ARGS
    ap = argparse.ArgumentParser(description="Scraper del portal CRIS de UTEC")
    ap.add_argument("--out", default="datos_utec", help="carpeta de salida (default: datos_utec)")
    ap.add_argument("--modo", choices=["navegador", "requests"], default="navegador",
                    help="navegador = Playwright con navegador real (default; evita el 403 de Cloudflare); "
                         "requests = HTTP directo (más rápido, pero el portal suele bloquearlo)")
    ap.add_argument("--headless", action="store_true", help="navegador sin ventana (Cloudflare puede bloquearlo)")
    ap.add_argument("--workers", type=int, default=1, help="hilos en paralelo, solo modo requests (default: 1)")
    ap.add_argument("--delay", type=float, default=5.0,
                    help="pausa por página en segundos (default: 5, lo que pide robots.txt del portal)")
    ap.add_argument("--limit", type=int, default=0, help="procesar solo N personas (para probar)")
    ap.add_argument("--sin-fotos", action="store_true", help="no descargar fotos")
    ap.add_argument("--sin-detalle", action="store_true", help="no entrar al detalle de cada publicación")
    ARGS = ap.parse_args()

    global NAV
    out = ARGS.out
    os.makedirs(os.path.join(out, "fotos"), exist_ok=True)
    t0 = time.time()
    if ARGS.modo == "navegador":
        if ARGS.workers != 1:
            log("  Modo navegador: se usa 1 hilo (Playwright no admite varios hilos).")
        ARGS.workers = 1
        log("0/4 Abriendo el navegador…")
        NAV = Navegador(headless=ARGS.headless)
    try:
        correr(out, t0)
    finally:
        if NAV is not None:
            NAV.cerrar()


def correr(out, t0):

    log("1/4 Listando perfiles…")
    urls = listar_personas()
    if ARGS.limit:
        urls = urls[:ARGS.limit]
    log(f"  {len(urls)} perfiles")

    log("2/4 Extrayendo perfiles, huella digital y listas de publicaciones…")
    D, _ = en_paralelo(parse_perfil, urls, ARGS.workers, "perfiles")
    D = [d for d in D if d]

    if not ARGS.sin_fotos:
        log("3/4 Descargando fotos…")
        en_paralelo(lambda r: descargar_foto(r, out), D, ARGS.workers, "fotos")
    else:
        for r in D:
            r["archivo_foto"] = ""

    exportar_perfiles(D, out)
    log(f"  perfiles.csv, publicaciones.csv, huella_digital.csv y datos_completos.json listos en {out}/")

    if not ARGS.sin_detalle:
        log("4/4 Extrayendo el detalle de cada publicación…")
        por_url = {}
        for r in D:
            for p in r["publicaciones"]:
                if not p["url"]:
                    continue
                por_url.setdefault(p["url"], []).append(r["nombre"])
        lista = list(por_url)
        log(f"  {len(lista)} publicaciones únicas")
        L, _ = en_paralelo(parse_publicacion, lista, ARGS.workers, "publicaciones")
        L = [x for x in L if x]
        for x in L:
            x["investigadores_utec_perfil"] = por_url[x["url"]]
        if L:
            exportar_detalle(L, out)
            log("  publicaciones_detalle.csv, publicacion_investigador.csv y publicaciones_detalle.json listos")

    log(f"Terminado en {time.time() - t0:.0f} s. Resultados en: {os.path.abspath(out)}")


if __name__ == "__main__":
    main()